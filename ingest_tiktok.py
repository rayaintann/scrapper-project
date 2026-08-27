"""Masukkan hasil scrape TikTok yang sudah ada di output/*.jsonl ke l0_raw.tt_profile_apify.

Pendamping ingest.py (yang khusus Instagram). Dipakai kalau pipeline sudah
membayar hasilnya ke Apify tapi penulisan ke DB gagal — misalnya koneksi
Postgres sudah mati saat batch terakhir selesai. Tidak memanggil Apify sama
sekali, jadi tidak ada biaya tambahan.

Parsing, cleaning, dan penautan social_account_id memakai modul yang sudah ada
(tiktok_transform + tt_raw_store), jadi hasilnya identik dengan yang seharusnya
ditulis tiktok_pipeline.py.

Tiga pengaman:

  - `scraped_at` diambil dari stamp nama file, bukan waktu ingest. Kombinasi
    (scraped_at, source_actor) dipakai untuk menolak file yang sudah pernah
    masuk, karena tabelnya append-only dan tidak punya unique constraint.
  - Satu transaksi untuk seluruh file: insert, pemeriksaan hasil, baru commit.
    Kalau ada satu saja yang meleset, semuanya di-rollback.
  - Hanya INSERT. Baris yang sudah ada tidak pernah di-UPDATE atau di-DELETE,
    dan jumlahnya ikut diperiksa sebelum commit.

Contoh:
    # lihat rencananya; insert dijalankan lalu di-rollback, DB tidak berubah
    python ingest_tiktok.py output/tiktok_profiles_20260814T155905Z.jsonl --dry-run

    # tulis beneran
    python ingest_tiktok.py output/tiktok_profiles_20260814T155905Z.jsonl --yes
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import Config, ConfigError, load_config
from db import connect
from ingest import load_items
from tiktok_transform import extract_username, to_raw_row
from tt_raw_store import RAW_TABLE, count_existing, insert_profiles

logger = logging.getLogger("ingest_tiktok")

PLATFORM_KEY = "tiktok"
FILE_PREFIX = "tiktok_profiles_"


class VerificationError(RuntimeError):
    """Hasil di dalam transaksi tidak sesuai harapan; transaksi dibatalkan."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="*", type=Path,
                        help="satu atau beberapa file tiktok_profiles_*.jsonl")
    parser.add_argument("--latest", action="store_true",
                        help=f"pakai file {FILE_PREFIX}*.jsonl terbaru yang berisi data")
    parser.add_argument("--dry-run", action="store_true",
                        help="jalankan insert lalu rollback; DB tidak berubah")
    parser.add_argument("--yes", action="store_true",
                        help="lewati konfirmasi sebelum commit")
    parser.add_argument("--allow-duplicate", action="store_true",
                        help="tetap lanjut walau scrape yang sama sudah ada di tabel "
                             "(bawaan: berhenti, supaya file tidak masuk dua kali)")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def resolve_files(args: argparse.Namespace, cfg: Config) -> list[Path]:
    files = list(args.files)
    if args.latest:
        candidates = sorted(p for p in cfg.output_dir.glob(f"{FILE_PREFIX}*.jsonl")
                            if p.stat().st_size > 0)
        if not candidates:
            raise FileNotFoundError(f"tidak ada file jsonl berisi data di {cfg.output_dir}")
        files.append(candidates[-1])
    return files


def scraped_at_from(paths: list[Path]) -> datetime:
    """Waktu scrape dari stamp nama file (tiktok_profiles_20260814T155905Z.jsonl).

    Sengaja bukan waktu ingest: nilai inilah yang membuat file yang sama bisa
    dikenali kalau seseorang menjalankan ingest dua kali.
    """
    newest = max(paths, key=lambda p: p.stat().st_mtime)
    stamp = newest.stem.replace(FILE_PREFIX, "")
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("Stamp '%s' tidak terbaca; pakai waktu modifikasi file.", stamp)
        return datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc)


def snapshot(conn) -> tuple[int, set[str]]:
    """Jumlah baris dan id yang sudah ada sebelum ingest, untuk dibandingkan nanti."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT id FROM {RAW_TABLE}")
        ids = {str(r[0]) for r in cur.fetchall()}
    return len(ids), ids


def verify_in_transaction(conn, scrape_run_id: str, expected: int,
                          before_ids: set[str]) -> dict:
    """Periksa hasil insert selagi transaksi masih terbuka.

    Setiap kegagalan di sini melempar VerificationError, dan pemanggil me-rollback
    seluruh transaksi — termasuk baris yang sudah sempat masuk.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT count(*), count(DISTINCT username),
                       count(social_account_id), count(*) FILTER (WHERE social_account_id IS NULL)
                FROM {RAW_TABLE} WHERE scrape_run_id = %s::uuid""",
            (scrape_run_id,),
        )
        masuk, unik, terisi, kosong = cur.fetchone()

        # FK sudah dijamin Postgres, tapi diperiksa lagi supaya kalau constraint-nya
        # pernah dilepas manual, ingest ini tidak diam-diam menanam id yatim.
        cur.execute(
            f"""SELECT count(*)
                FROM {RAW_TABLE} t
                LEFT JOIN public.social_account s ON s.id = t.social_account_id
                WHERE t.scrape_run_id = %s::uuid
                  AND t.social_account_id IS NOT NULL AND s.id IS NULL""",
            (scrape_run_id,),
        )
        yatim = cur.fetchone()[0]

        cur.execute(f"SELECT count(*) FROM {RAW_TABLE}")
        total = cur.fetchone()[0]

        cur.execute(
            f"SELECT count(*) FROM {RAW_TABLE} WHERE scrape_run_id <> %s::uuid "
            "OR scrape_run_id IS NULL",
            (scrape_run_id,),
        )
        baris_lama = cur.fetchone()[0]

        cur.execute(f"SELECT id FROM {RAW_TABLE} WHERE id = ANY(%s::uuid[])",
                    (sorted(before_ids),))
        lama_masih_ada = {str(r[0]) for r in cur.fetchall()}

    if masuk != expected:
        raise VerificationError(f"{masuk} baris masuk, seharusnya {expected}")
    if unik != masuk:
        raise VerificationError(f"{masuk} baris tapi hanya {unik} username unik (ada duplikat)")
    if yatim:
        raise VerificationError(f"{yatim} baris punya social_account_id tanpa pasangan")
    if baris_lama != len(before_ids):
        raise VerificationError(
            f"baris di luar run ini jadi {baris_lama}, sebelumnya {len(before_ids)}"
        )
    if lama_masih_ada != before_ids:
        hilang = len(before_ids - lama_masih_ada)
        raise VerificationError(f"{hilang} baris lama hilang dari tabel")

    return {
        "masuk": masuk, "unik": unik, "terisi": terisi, "kosong": kosong,
        "yatim": yatim, "total": total, "baris_lama": baris_lama,
    }


def run(args: argparse.Namespace, cfg: Config) -> int:
    files = resolve_files(args, cfg)
    if not files:
        logger.error("Sebutkan file .jsonl, atau pakai --latest.")
        return 1

    items = load_items(files)
    if not items:
        logger.warning("Tidak ada item untuk diproses.")
        return 0

    scraped_at = scraped_at_from(files)
    source_actor = cfg.tiktok.actor_id

    # Hitung dulu di luar DB: berapa yang layak, berapa yang akan dilewati.
    layak: dict[str, dict] = {}
    tanpa_username = 0
    tanpa_profil = 0
    for item in items:
        username = extract_username(item)
        if not username:
            tanpa_username += 1
            continue
        if username in layak:
            continue
        if to_raw_row(item) is None:
            tanpa_profil += 1
            continue
        layak[username] = item

    w = 32
    print("\n=== Rencana ingest TikTok ===")
    print(f"{'File':<{w}}: {', '.join(p.name for p in files)}")
    print(f"{'Actor (source_actor)':<{w}}: {source_actor}")
    print(f"{'Waktu scrape (scraped_at)':<{w}}: {scraped_at.isoformat()}")
    print(f"{'Item dibaca':<{w}}: {len(items)}")
    print(f"{'Akan masuk':<{w}}: {len(layak)} baris")
    print(f"{'Dilewati - tanpa data profil':<{w}}: {tanpa_profil}")
    print(f"{'Dilewati - username tak terbaca':<{w}}: {tanpa_username}")

    if not layak:
        print("\nTidak ada yang bisa ditulis.")
        return 0

    with connect(cfg.postgres) as conn:
        # Satu transaksi untuk semuanya; psycopg2 sudah non-autocommit.
        try:
            sebelum_total, sebelum_ids = snapshot(conn)
            sudah_ada = count_existing(conn, scraped_at, source_actor)
            print(f"{'Baris di tabel sebelum ingest':<{w}}: {sebelum_total}")

            if sudah_ada and not args.allow_duplicate:
                conn.rollback()
                print(f"\nBERHENTI: {sudah_ada} baris dengan scraped_at "
                      f"{scraped_at.isoformat()} dan actor {source_actor} sudah ada "
                      f"di {RAW_TABLE}.")
                print("File ini sepertinya sudah pernah di-ingest. Tidak ada yang ditulis.")
                print("Kalau memang mau menambahkannya lagi, pakai --allow-duplicate.")
                return 1
            if sudah_ada:
                print(f"{'PERINGATAN':<{w}}: {sudah_ada} baris dari scrape yang sama "
                      "sudah ada; akan digandakan (--allow-duplicate)")

            if not args.dry_run and not args.yes:
                if not sys.stdin.isatty():
                    conn.rollback()
                    print("\nStdin bukan terminal; jalankan ulang dengan --yes untuk menulis ke DB.")
                    return 1
                if input("\nLanjut menulis ke DB? [y/N] ").strip().lower() not in {"y", "yes"}:
                    conn.rollback()
                    print("Dibatalkan.")
                    return 1

            print()
            stats = insert_profiles(
                conn,
                list(layak.values()),
                source_actor=source_actor,
                scraped_at=scraped_at,
                commit=False,
            )
            hasil = verify_in_transaction(conn, stats.scrape_run_id, len(layak), sebelum_ids)

            if args.dry_run:
                conn.rollback()
                print("\n[dry-run] Semua pemeriksaan lolos, transaksi di-rollback. "
                      "DB tidak berubah.")
                print(f"  akan masuk        : {hasil['masuk']} baris "
                      f"({hasil['unik']} username unik)")
                print(f"  social_account_id : {hasil['terisi']} terisi, {hasil['kosong']} kosong")
                print(f"  total setelahnya  : {hasil['total']} baris")
                return 0

            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("Ingest dibatalkan, seluruh transaksi di-rollback: %s", exc)
            print(f"\nGAGAL: {exc}")
            print("Transaksi di-rollback; tidak ada satu baris pun yang masuk.")
            return 1

        # Verifikasi ulang dari koneksi yang sudah commit, supaya angkanya
        # benar-benar yang tersimpan, bukan yang masih di dalam transaksi.
        print("\n=== Verifikasi setelah commit ===")
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT count(*), count(DISTINCT username),
                           count(social_account_id),
                           count(*) FILTER (WHERE social_account_id IS NULL)
                    FROM {RAW_TABLE} WHERE scrape_run_id = %s::uuid""",
                (stats.scrape_run_id,),
            )
            masuk, unik, terisi, kosong = cur.fetchone()
            cur.execute(
                f"""SELECT count(*) FROM {RAW_TABLE} t
                    LEFT JOIN public.social_account s ON s.id = t.social_account_id
                    WHERE t.scrape_run_id = %s::uuid
                      AND t.social_account_id IS NOT NULL AND s.id IS NULL""",
                (stats.scrape_run_id,),
            )
            yatim = cur.fetchone()[0]
            cur.execute(f"SELECT count(*), count(DISTINCT username), count(DISTINCT scrape_run_id) "
                        f"FROM {RAW_TABLE}")
            total, total_unik, total_run = cur.fetchone()
            cur.execute(f"SELECT count(*) FROM {RAW_TABLE} WHERE id = ANY(%s::uuid[])",
                        (sorted(sebelum_ids),))
            lama = cur.fetchone()[0]

        print(f"{'scrape_run_id':<{w}}: {stats.scrape_run_id}")
        print(f"{'Baris masuk':<{w}}: {masuk}")
        print(f"{'Username unik di run ini':<{w}}: {unik}")
        print(f"{'social_account_id terisi':<{w}}: {terisi}")
        print(f"{'social_account_id kosong':<{w}}: {kosong}")
        print(f"{'FK yatim (harus 0)':<{w}}: {yatim}")
        print(f"{'Dilewati - tanpa data profil':<{w}}: {tanpa_profil + stats.skipped_failed}")
        print(f"{'Dilewati - username tak terbaca':<{w}}: {tanpa_username + stats.skipped_no_username}")
        print(f"{'Baris lama masih utuh':<{w}}: {lama} dari {sebelum_total}")
        print(f"{'TOTAL tabel sekarang':<{w}}: {total} baris | {total_unik} username unik "
              f"| {total_run} scrape_run_id")
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
    try:
        return run(args, cfg)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
