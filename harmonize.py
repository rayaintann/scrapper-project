"""Bersihkan l0_raw.ig_profile_apify -> l0_harmonization.instagram_profile.

Langkah ini tidak memanggil Apify. Ia membaca baris mentah, membersihkan teks,
menautkan ke public.social_account lewat username, lalu menulis satu snapshot
per (social_account_id, date).

Contoh:
    python harmonize.py --dry-run              # lihat rencananya
    python harmonize.py --yes                  # proses semua baris raw
    python harmonize.py --scrape-run-id <uuid> --yes
"""

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone

import psycopg2.extras

from clean import clean_line, clean_text, clean_website
from config import Config, ConfigError, load_config
from db import connect

logger = logging.getLogger("harmonize")

SOURCE_TABLE = "l0_raw.ig_profile_apify"
TARGET_TABLE = "l0_harmonization.instagram_profile"
SOURCE_NAME = "apify"

# Kolom insight (reach, profile_views, dst) hanya tersedia lewat Instagram
# Business API. Actor Apify tidak mengembalikannya, jadi dibiarkan NULL dan
# has_insights ditandai false supaya konsumen data tahu bedanya.
HAS_INSIGHTS = False

SELECT_SQL = f"""
    SELECT r.id,
           COALESCE(r.social_account_id, s.id) AS account_id,
           r.username,
           r.name,
           r.biography,
           r.website,
           r.followers_count,
           r.follows_count,
           r.media_count,
           r.scraped_at
    FROM {SOURCE_TABLE} r
    LEFT JOIN (
        SELECT sa.id,
               ltrim(lower(btrim(split_part(sa.username, '?', 1))), '@') AS uname
        FROM public.social_account sa
        JOIN public.platforms p ON p.id = sa.platform_id
        WHERE p.key = 'instagram'
    ) s ON s.uname = r.username
    WHERE (%(run_id)s::uuid IS NULL OR r.scrape_run_id = %(run_id)s::uuid)
    ORDER BY r.scraped_at
"""

UPSERT_SQL = f"""
    INSERT INTO {TARGET_TABLE} (
        social_account_id, date, username, name, biography, website,
        followers_count, follows_count, media_count,
        has_insights, source, source_table, source_id, processed_at
    )
    VALUES %s
    ON CONFLICT (social_account_id, date) DO UPDATE SET
        username        = EXCLUDED.username,
        name            = EXCLUDED.name,
        biography       = EXCLUDED.biography,
        website         = EXCLUDED.website,
        followers_count = EXCLUDED.followers_count,
        follows_count   = EXCLUDED.follows_count,
        media_count     = EXCLUDED.media_count,
        has_insights    = EXCLUDED.has_insights,
        source          = EXCLUDED.source,
        source_table    = EXCLUDED.source_table,
        source_id       = EXCLUDED.source_id,
        processed_at    = EXCLUDED.processed_at
    RETURNING (xmax = 0) AS inserted
"""

TEMPLATE = (
    "(%s::uuid, %s::date, %s::varchar, %s::varchar, %s::text, %s::text,"
    " %s::bigint, %s::bigint, %s::integer,"
    " %s::boolean, %s::varchar, %s::varchar, %s::uuid, %s::timestamptz)"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--scrape-run-id",
        default=None,
        help="hanya proses satu run tertentu (default: semua baris raw)",
    )
    parser.add_argument("--dry-run", action="store_true", help="tampilkan rencana tanpa menulis")
    parser.add_argument("--yes", action="store_true", help="lewati konfirmasi")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def build_rows(raw_rows: list[tuple], processed_at: datetime) -> tuple[list[tuple], Counter]:
    """Bersihkan baris raw dan buang yang tidak bisa ditulis.

    Kalau satu akun punya beberapa snapshot di tanggal yang sama, yang paling
    baru menang — unique index (social_account_id, date) hanya menerima satu,
    dan duplikat dalam satu statement akan ditolak Postgres.
    """
    stats: Counter = Counter()
    by_key: dict[tuple[str, object], tuple] = {}

    for (
        source_id,
        account_id,
        username,
        name,
        biography,
        website,
        followers,
        follows,
        media,
        scraped_at,
    ) in raw_rows:
        if account_id is None:
            # Tanpa social_account, baris tidak punya kunci unik yang sah.
            stats["tanpa_social_account"] += 1
            continue

        snapshot_date = scraped_at.date() if scraped_at else processed_at.date()
        key = (str(account_id), snapshot_date)
        if key in by_key:
            stats["duplikat_akun_tanggal"] += 1

        cleaned_name = clean_line(name)
        cleaned_bio = clean_text(biography)
        cleaned_site = clean_website(website)

        # Bandingkan dengan `is not None`, bukan truthiness: '' adalah nilai yang
        # memang kita ubah jadi NULL dan harus ikut terhitung.
        for label, before, after in (
            ("name", name, cleaned_name),
            ("biography", biography, cleaned_bio),
            ("website", website, cleaned_site),
        ):
            if before is None:
                continue
            if after is None:
                stats[f"{label}_jadi_null"] += 1
            elif after != before:
                stats[f"{label}_dirapikan"] += 1

        by_key[key] = (
            str(account_id),
            snapshot_date,
            username,
            cleaned_name,
            cleaned_bio,
            cleaned_site,
            followers,
            follows,
            media,
            HAS_INSIGHTS,
            SOURCE_NAME,
            SOURCE_TABLE,
            str(source_id),
            processed_at,
        )

    return list(by_key.values()), stats


def run(args: argparse.Namespace, cfg: Config) -> int:
    processed_at = datetime.now(timezone.utc)

    with connect(cfg.postgres) as conn:
        with conn.cursor() as cur:
            cur.execute(SELECT_SQL, {"run_id": args.scrape_run_id})
            raw_rows = cur.fetchall()

        logger.info("Membaca %d baris dari %s", len(raw_rows), SOURCE_TABLE)
        if not raw_rows:
            print("Tidak ada baris raw yang cocok.")
            return 0

        rows, stats = build_rows(raw_rows, processed_at)

        w = 32
        print("\n=== Rencana harmonisasi ===")
        print(f"{'Sumber':<{w}}: {SOURCE_TABLE}")
        print(f"{'Tujuan':<{w}}: {TARGET_TABLE}")
        print(f"{'Baris raw dibaca':<{w}}: {len(raw_rows)}")
        print(f"{'Baris siap ditulis':<{w}}: {len(rows)}")
        for label, count in sorted(stats.items()):
            print(f"{'  ' + label:<{w}}: {count}")

        if args.dry_run:
            print("\n[dry-run] DB tidak diubah.")
            if rows:
                print("\nContoh hasil bersih:")
                for row in rows[:2]:
                    print(f"  username : {row[2]}")
                    print(f"  name     : {row[3]!r}")
                    print(f"  biography: {(row[4] or '')[:70]!r}")
                    print(f"  website  : {row[5]!r}")
                    print()
            return 0

        if not rows:
            print("\nTidak ada baris yang bisa ditulis.")
            return 0

        if not args.yes:
            if not sys.stdin.isatty():
                print("\nStdin bukan terminal; jalankan ulang dengan --yes.")
                return 1
            if input(f"\nTulis {len(rows)} baris ke {TARGET_TABLE}? [y/N] ").strip().lower() not in {"y", "yes"}:
                print("Dibatalkan.")
                return 1

        with conn.cursor() as cur:
            returned = psycopg2.extras.execute_values(
                cur, UPSERT_SQL, rows, template=TEMPLATE, page_size=200, fetch=True
            )
        conn.commit()

        inserted = sum(1 for r in returned if r[0])
        updated = len(returned) - inserted
        print(f"\n{TARGET_TABLE}: {inserted} baris baru, {updated} baris diperbarui.")
        return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    try:
        cfg = load_config()
    except ConfigError as exc:
        logger.error("%s", exc)
        return 1
    return run(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
