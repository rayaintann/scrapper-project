"""Cari KOL di direktori — CLI read-only untuk menguji db.search_kol_directory().

Read-only. Aman dijalankan kapan saja, termasuk saat pipeline sedang jalan:
tidak ada satu pun perintah tulis di sini.

    python search_kol.py beauty
    python search_kol.py beauty --category Beauty
    python search_kol.py --category Fitness --limit 20
    python search_kol.py sarah --limit 10 --offset 10

Discovery Category yang sah (public.kol_categories.taxonomy_key):
Lifestyle, Beauty, Fashion, Food, Fitness, Entertainment, Moms, Gen Z, Tech.
"""

import argparse
import logging
import sys

from config import ConfigError, load_config
from db import connect, search_kol_directory

DISCOVERY_CATEGORIES = (
    "Lifestyle", "Beauty", "Fashion", "Food", "Fitness",
    "Entertainment", "Moms", "Gen Z", "Tech",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "keyword",
        nargs="?",
        default=None,
        help="kata kunci; dicari di username, display name, dan bio. "
             "Kosongkan untuk menelusuri tanpa kata kunci.",
    )
    parser.add_argument(
        "--category",
        default=None,
        metavar="DISCOVERY_CATEGORY",
        help="saring per Discovery Category, mis. --category Beauty",
    )
    parser.add_argument("--limit", type=int, default=20, help="jumlah baris (maks 200, default 20)")
    parser.add_argument("--offset", type=int, default=0, help="lewati N baris pertama")
    return parser.parse_args(argv)


def _potong(teks: str | None, lebar: int) -> str:
    """Potong agar kolom tabel tidak melebar karena satu nilai panjang."""
    nilai = teks if teks else "-"
    return nilai if len(nilai) <= lebar else nilai[: lebar - 1] + "…"


def main(argv: list[str] | None = None) -> int:
    # Nama tampilan KOL banyak yang memuat emoji; tanpa ini konsol Windows
    # gagal mencetak dan seluruh perintah ikut gagal.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s | %(message)s")
    args = parse_args(argv)

    if args.category and args.category not in DISCOVERY_CATEGORIES:
        print(f"Discovery Category '{args.category}' tidak dikenal.")
        print("Pilih salah satu: " + ", ".join(DISCOVERY_CATEGORIES))
        return 1

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"Konfigurasi: {exc}")
        return 1

    with connect(cfg.postgres) as conn:
        # Sesi read-only: perintah tulis apa pun akan ditolak database.
        conn.set_session(readonly=True, autocommit=True)
        hasil = search_kol_directory(
            conn,
            q=args.keyword,
            taxonomy_key=args.category,
            limit=args.limit,
            offset=args.offset,
        )

    judul = f"keyword={args.keyword!r}" if args.keyword else "tanpa keyword"
    if args.category:
        judul += f" · category={args.category}"
    print(f"\n{len(hasil)} hasil — {judul}\n")

    if not hasil:
        print("Tidak ada KOL yang cocok.")
        return 0

    baris = "{:<24} {:<26} {:<10} {:>12}  {}"
    print(baris.format("USERNAME", "DISPLAY NAME", "PLATFORM", "FOLLOWERS", "DISCOVERY CATEGORY"))
    print("-" * 104)
    for r in hasil:
        print(
            baris.format(
                _potong(r.username, 24),
                _potong(r.display_name, 26),
                _potong(r.platform, 10),
                f"{r.followers_count:,}" if r.followers_count is not None else "-",
                _potong(r.discovery_category, 30),
            )
        )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
