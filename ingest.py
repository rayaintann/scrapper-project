"""Masukkan hasil scrape yang sudah ada di output/*.jsonl ke kol_directory.

Dipakai kalau pipeline sudah jalan tapi dijalankan tanpa penulisan ke DB, atau
kalau mau memuat ulang file lama. Tidak memanggil Apify sama sekali, jadi tidak
ada biaya tambahan.

Contoh:
    # lihat apa yang akan diupdate, tanpa menyentuh DB
    python ingest.py output/instagram_profiles_20260814T081609Z.jsonl --dry-run

    # file terbaru di output/
    python ingest.py --latest

    # tulis ke DB
    python ingest.py --latest --yes
"""

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from config import Config, ConfigError, load_config
from db import connect, dedupe_rows, fetch_rows_by_usernames, update_profiles
from raw_store import RAW_TABLE, count_existing, insert_profiles
from transform import extract_username, is_error_item, to_db_update

logger = logging.getLogger("ingest")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="satu atau beberapa file .jsonl hasil pipeline",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="pakai file instagram_profiles_*.jsonl terbaru di folder output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="tampilkan ringkasan tanpa menulis ke DB",
    )
    parser.add_argument(
        "--write-raw",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=f"tulis payload mentah ke {RAW_TABLE} (default: aktif)",
    )
    parser.add_argument(
        "--update-directory",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="update public.kol_directory (default: aktif)",
    )
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help=f"ikut memasukkan item not_found/restricted ke {RAW_TABLE}",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="lewati konfirmasi sebelum menulis ke DB",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def load_items(paths: list[Path]) -> list[dict]:
    """Baca semua item dari file JSONL, item terakhir menang kalau duplikat."""
    items: list[dict] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"file tidak ditemukan: {path}")
        count = 0
        with path.open(encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                    count += 1
                except json.JSONDecodeError as exc:
                    logger.warning("%s baris %d dilewati: %s", path.name, line_no, exc)
        logger.info("%s: %d item", path.name, count)
    return items


def resolve_files(args: argparse.Namespace, cfg: Config) -> list[Path]:
    files = list(args.files)
    if args.latest:
        candidates = sorted(cfg.output_dir.glob("instagram_profiles_*.jsonl"))
        candidates = [p for p in candidates if p.stat().st_size > 0]
        if not candidates:
            raise FileNotFoundError(f"tidak ada file jsonl berisi data di {cfg.output_dir}")
        files.append(candidates[-1])
    return files


def scraped_at_from(paths: list[Path]) -> datetime:
    """Waktu scrape diambil dari stamp di nama file, bukan waktu ingest.

    Nama file berbentuk instagram_profiles_20260814T081609Z.jsonl. Kalau tidak
    terbaca, pakai waktu modifikasi file.
    """
    newest = max(paths, key=lambda p: p.stat().st_mtime)
    stamp = newest.stem.replace("instagram_profiles_", "")
    try:
        return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc)


def run(args: argparse.Namespace, cfg: Config) -> int:
    files = resolve_files(args, cfg)
    if not files:
        logger.error("Sebutkan file .jsonl, atau pakai --latest.")
        return 1

    items = load_items(files)
    if not items:
        logger.warning("Tidak ada item untuk diproses.")
        return 0

    # Item terakhir menang supaya file yang dimuat belakangan menimpa yang lama.
    items_by_username: dict[str, dict] = {}
    no_username = 0
    for item in items:
        key = extract_username(item)
        if key:
            items_by_username[key] = item
        else:
            no_username += 1

    logger.info("%d item -> %d username unik", len(items), len(items_by_username))
    if no_username:
        logger.warning("%d item dilewati karena username tidak terbaca", no_username)

    with connect(cfg.postgres) as conn:
        rows = fetch_rows_by_usernames(conn, list(items_by_username))
        grouped = dedupe_rows(rows)

        missing_in_db = sorted(set(items_by_username) - set(grouped))
        updates: list[dict] = []
        failure_reasons: Counter[str] = Counter()
        for key, directory_rows in grouped.items():
            item = items_by_username[key]
            for row in directory_rows:
                update = to_db_update(row.id, item)
                updates.append(update)
                if update["scrape_status"] != "success":
                    failure_reasons[str(item.get("error") or "tidak_diketahui")] += 1

        success = sum(1 for u in updates if u["scrape_status"] == "success")
        failed = len(updates) - success

        raw_candidates = sum(
            1 for item in items_by_username.values()
            if args.include_failed or not is_error_item(item)
        )
        scraped_at = scraped_at_from(files)

        w = 30
        print("\n=== Rencana ingest ===")
        print(f"{'File':<{w}}: {', '.join(p.name for p in files)}")
        print(f"{'Waktu scrape':<{w}}: {scraped_at.isoformat()}")
        print(f"{'Item dibaca':<{w}}: {len(items)}")
        print(f"{'Username unik':<{w}}: {len(items_by_username)}")
        already = (
            count_existing(conn, scraped_at, cfg.apify.actor_id) if args.write_raw else 0
        )
        if args.write_raw:
            print(f"{'-> ' + RAW_TABLE:<{w}}: {raw_candidates} baris baru (append)")
            if already:
                print(f"{'   PERINGATAN':<{w}}: {already} baris dari scrape yang sama "
                      "sudah ada; ingest ulang akan menggandakannya")
        if args.update_directory:
            print(f"{'-> public.kol_directory':<{w}}: {len(updates)} baris")
            print(f"{'     akan success':<{w}}: {success}")
            print(f"{'     akan failed':<{w}}: {failed}")
            for reason, count in failure_reasons.most_common():
                print(f"{'       ' + reason:<{w}}: {count}")
        if missing_in_db:
            print(f"{'Tidak ada di kol_directory':<{w}}: {len(missing_in_db)} "
                  f"(contoh: {', '.join(missing_in_db[:5])})")

        if args.dry_run:
            print("\n[dry-run] DB tidak diubah.")
            return 0
        if not args.write_raw and not updates:
            print("\nTidak ada yang bisa ditulis.")
            return 0

        if not args.yes:
            if not sys.stdin.isatty():
                print("\nStdin bukan terminal; jalankan ulang dengan --yes untuk menulis ke DB.")
                return 1
            if input("\nLanjut menulis ke DB? [y/N] ").strip().lower() not in {"y", "yes"}:
                print("Dibatalkan.")
                return 1

        print()
        if args.write_raw:
            stats = insert_profiles(
                conn,
                list(items_by_username.values()),
                source_actor=cfg.apify.actor_id,
                scraped_at=scraped_at,
                include_failed=args.include_failed,
            )
            print(f"{RAW_TABLE}: {stats.inserted} baris masuk "
                  f"(scrape_run_id={stats.scrape_run_id})")
            print(f"  terhubung ke social_account : {stats.linked}")
            print(f"  tanpa pasangan              : {stats.unlinked}")
            if stats.skipped_failed:
                print(f"  dilewati (error item)       : {stats.skipped_failed}")

        if args.update_directory and updates:
            affected = update_profiles(conn, updates)
            print(f"public.kol_directory: {affected} baris terupdate.")

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
