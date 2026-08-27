"""Jalankan satu file migrasi SQL terhadap database dari .env.

File migrasi mengatur transaksinya sendiri (BEGIN/COMMIT) dan berisi blok
verifikasi yang melempar exception kalau hasilnya tidak sesuai, sehingga
kegagalan otomatis membatalkan seluruh perubahan.

Contoh:
    python apply_migration.py migrations/001_fix_ig_profile_apify_fk.sql --dry-run
    python apply_migration.py migrations/001_fix_ig_profile_apify_fk.sql --yes
"""

import argparse
import logging
import sys
from pathlib import Path

import psycopg2

from config import ConfigError, load_config

logger = logging.getLogger("migration")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path, help="path ke file .sql")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="jalankan lalu ROLLBACK, untuk melihat hasil verifikasi tanpa mengubah apa pun",
    )
    parser.add_argument("--yes", action="store_true", help="lewati konfirmasi")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")
    args = parse_args(argv)

    if not args.file.exists():
        logger.error("File tidak ditemukan: %s", args.file)
        return 1
    sql = args.file.read_text(encoding="utf-8")

    try:
        cfg = load_config()
    except ConfigError as exc:
        logger.error("%s", exc)
        return 1

    print(f"File     : {args.file}")
    print(f"Database : {cfg.postgres.database} @ {cfg.postgres.host}:{cfg.postgres.port}")
    print(f"Mode     : {'DRY-RUN (akan di-rollback)' if args.dry_run else 'TERAPKAN'}")

    if not args.yes:
        if not sys.stdin.isatty():
            print("Stdin bukan terminal; jalankan ulang dengan --yes.")
            return 1
        if input("\nLanjutkan? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("Dibatalkan.")
            return 1

    if args.dry_run:
        # File mengatur transaksinya sendiri; menukar COMMIT dengan ROLLBACK
        # membuat seluruh isinya benar-benar dijalankan lalu dibatalkan.
        sql = sql.replace("COMMIT;", "ROLLBACK;")

    conn = psycopg2.connect(**cfg.postgres.as_connect_kwargs())
    # autocommit agar BEGIN/COMMIT di dalam file yang menentukan batas transaksi,
    # persis seperti dijalankan lewat psql.
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        for notice in conn.notices:
            print(notice.rstrip())
        print(
            "\n[dry-run] Semua perubahan dibatalkan."
            if args.dry_run
            else "\nMigrasi selesai dan sudah di-commit."
        )
        return 0
    except psycopg2.Error as exc:
        # Exception di dalam file membatalkan transaksinya sendiri; rollback ini
        # untuk berjaga kalau kegagalan terjadi sebelum BEGIN sempat berjalan.
        conn.rollback()
        for notice in conn.notices:
            print(notice.rstrip())
        logger.error("Migrasi GAGAL, semua perubahan dibatalkan: %s", exc)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
