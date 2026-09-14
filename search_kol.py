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

import kol_attribute_taxonomy as kat
import what_matters_scoring as wm
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
    parser.add_argument(
        "--matters",
        default=None,
        metavar="CSV",
        help="What Matters Most: daftar kriteria dipisah koma, mis. "
             "--matters engagement,consistency. Hasil diranking berdasarkan "
             "rata-rata skor kriteria terpilih yang punya nilai. Kriteria "
             "yang sah: " + ", ".join(wm.URUTAN_KRITERIA),
    )
    parser.add_argument(
        "--style",
        default=None,
        metavar="CSV",
        help="saring per Style, dipisah koma. Nilainya attribute_key, mis. "
             "--style content_style.educational,visual_style.minimalist. "
             "Beberapa nilai berarti SALAH SATUNYA.",
    )
    parser.add_argument(
        "--personality",
        default=None,
        metavar="CSV",
        help="saring per Personality, mis. "
             "--personality creator_personality.relatable. Digabung dengan "
             "--style secara AND.",
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

    # Parser di modul-modulnya sengaja MENGABAIKAN kunci tak dikenal, supaya
    # UI yang lebih baru boleh mengirim nilai yang backend belum kenal. Di CLI
    # perilaku itu membingungkan -- salah ketik akan tampil sebagai "filter
    # tidak berpengaruh" tanpa penjelasan -- jadi di sini ditolak di depan.
    gaya = kat.parse_attribute_keys(args.style, kind=kat.STYLE)
    if args.style and not gaya:
        print(f"Style '{args.style}' tidak dikenal.")
        print("Contoh: " + ", ".join(
            r["attribute_key"] for r in kat.TAXONOMY
            if r["kind"] == kat.STYLE)[:300] + " ...")
        return 1

    kepribadian = kat.parse_attribute_keys(args.personality,
                                           kind=kat.PERSONALITY)
    if args.personality and not kepribadian:
        print(f"Personality '{args.personality}' tidak dikenal.")
        print("Pilih dari: " + ", ".join(
            r["attribute_key"] for r in kat.TAXONOMY
            if r["kind"] == kat.PERSONALITY))
        return 1

    dipilih = wm.parse_matters(args.matters)
    if args.matters and not dipilih:
        print(f"Kriteria What Matters '{args.matters}' tidak dikenal.")
        print("Pilih dari: " + ", ".join(wm.URUTAN_KRITERIA))
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
            matters=dipilih or None,
            style=gaya or None,
            personality=kepribadian or None,
        )

    judul = f"keyword={args.keyword!r}" if args.keyword else "tanpa keyword"
    if args.category:
        judul += f" · category={args.category}"
    if gaya:
        judul += f" · style={','.join(gaya)}"
    if kepribadian:
        judul += f" · personality={','.join(kepribadian)}"
    if dipilih:
        judul += f" · matters={','.join(dipilih)}"
    print(f"\n{len(hasil)} hasil — {judul}\n")

    if not hasil:
        print("Tidak ada KOL yang cocok.")
        return 0

    if dipilih:
        # SKOR dan KRIT selalu berdampingan: skor 100 dari satu kriteria tidak
        # sebanding dengan 100 dari lima, dan tanpa KRIT keduanya terlihat sama.
        baris = "{:<24} {:<22} {:<10} {:>12}  {:>7} {:>5}  {}"
        print(baris.format("USERNAME", "DISPLAY NAME", "PLATFORM", "FOLLOWERS",
                           "SKOR", "KRIT", "DISCOVERY CATEGORY"))
        print("-" * 116)
        for r in hasil:
            print(
                baris.format(
                    _potong(r.username, 24),
                    _potong(r.display_name, 22),
                    _potong(r.platform, 10),
                    f"{r.followers_count:,}" if r.followers_count is not None else "-",
                    f"{r.what_matters_score:.2f}"
                    if r.what_matters_score is not None else "-",
                    r.what_matters_contributing
                    if r.what_matters_contributing is not None else "-",
                    _potong(r.discovery_category, 26),
                )
            )
        tanpa_skor = sum(1 for r in hasil if r.what_matters_score is None)
        if tanpa_skor:
            print(f"\n{tanpa_skor} dari {len(hasil)} baris belum punya skor "
                  f"(kriteria terpilih belum terukur). Mereka di urutan bawah, "
                  f"bukan dianggap nol.")
    else:
        baris = "{:<24} {:<26} {:<10} {:>12}  {}"
        print(baris.format("USERNAME", "DISPLAY NAME", "PLATFORM", "FOLLOWERS",
                           "DISCOVERY CATEGORY"))
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
