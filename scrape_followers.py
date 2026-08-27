"""Entry point: scrape daftar follower untuk akun KOL, lalu tulis ke L0.

    python scrape_followers.py --limit 100 --tanggal-profil 2026-08-24

Berhenti di L0. Lanjutannya (Harmonization -> L1 -> Feature -> L2) dijalankan
lewat asset Dagster, mengikuti pola project ini: scraping ada di luar Dagster,
transformasi ada di dalam.

============================================================================
PEMILIHAN AKUN -- KENAPA DARI unified_profile, BUKAN DAFTAR HARDCODE
============================================================================

Target task ini adalah "23 akun yang sama seperti scrape profile sebelumnya".
Daftar itu sudah ada di database sebagai fakta: baris `l1_silver.unified_profile`
dengan `date = <tanggal-profil>`. Menyalinnya jadi konstanta di kode akan
membuat dua sumber kebenaran yang bisa berbeda diam-diam.

`--tanggal-profil` membuat pilihan itu eksplisit dan bisa diaudit, bukan
tersembunyi di dalam kode.

============================================================================
BIAYA
============================================================================

Dilaporkan dari `usageTotalUsd` tiap run Apify -- angka yang ditagihkan, bukan
hasil perkalian tarif x jumlah item. Kalau Apify belum menyelesaikan
perhitungan saat run baru saja selesai, nilainya bisa 0 atau None; itu ditandai
sebagai "belum tersedia", tidak diam-diam dianggap gratis.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

import psycopg2

from apify_followers import (
    DEFAULT_IG_FOLLOWERS_ACTOR,
    DEFAULT_TT_FOLLOWERS_ACTOR,
    LIMIT_MAX,
    scrape_instagram_followers,
    scrape_tiktok_followers,
)
from follower_raw_store import simpan

logger = logging.getLogger("scrape_followers")

SQL_AKUN = """
    SELECT p.social_account_id, pl.key AS platform, p.username
    FROM l1_silver.unified_profile p
    JOIN public.platforms pl ON pl.id = p.platform_id
    WHERE p.date = %s
      AND p.social_account_id IS NOT NULL
      AND p.username IS NOT NULL
    ORDER BY pl.key, p.username
"""


def _muat_env() -> None:
    """Muat .env sekali di awal.

    Dipanggil di `main()` SEBELUM token dibaca. Sebelumnya pemuatan menumpang
    di `_conn()`, sehingga pengecekan APIFY_API_TOKEN berjalan lebih dulu dan
    selalu gagal meski tokennya ada di .env.
    """
    from dotenv import load_dotenv

    load_dotenv()


def _conn():
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.environ["PG_DB"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        connect_timeout=15,
    )


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Scrape follower KOL ke l0_raw.")
    p.add_argument("--limit", type=int, default=100,
                   help=f"Maksimum follower per akun (1..{LIMIT_MAX}).")
    p.add_argument("--tanggal-profil", default="2026-08-24",
                   help="Tanggal snapshot unified_profile yang jadi daftar akun.")
    p.add_argument("--platform", choices=["instagram", "tiktok", "semua"],
                   default="semua")
    p.add_argument("--ig-actor", default=os.getenv("IG_FOLLOWERS_ACTOR_ID")
                   or DEFAULT_IG_FOLLOWERS_ACTOR)
    p.add_argument("--tt-actor", default=os.getenv("TT_FOLLOWERS_ACTOR_ID")
                   or DEFAULT_TT_FOLLOWERS_ACTOR)
    p.add_argument("--dry-run", action="store_true",
                   help="Tampilkan akun yang akan discrape lalu berhenti. Nol biaya.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _muat_env()

    token = os.getenv("APIFY_API_TOKEN")
    if not token and not args.dry_run:
        print("APIFY_API_TOKEN belum diset.", file=sys.stderr)
        return 2

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_AKUN, (args.tanggal_profil,))
            semua = cur.fetchall()
    finally:
        pass

    if not semua:
        print(f"Tidak ada akun di unified_profile tanggal {args.tanggal_profil}.")
        conn.close()
        return 1

    ig = [r for r in semua if r[1] == "instagram"]
    tt = [r for r in semua if r[1] == "tiktok"]
    if args.platform == "instagram":
        tt = []
    elif args.platform == "tiktok":
        ig = []

    print(f"Akun terpilih: {len(ig)} Instagram + {len(tt)} TikTok "
          f"= {len(ig) + len(tt)} (limit {args.limit}/akun, "
          f"maks {(len(ig) + len(tt)) * args.limit} follower)")

    if args.dry_run:
        for sid, plat, uname in ig + tt:
            print(f"  {plat:<10} {uname}")
        conn.close()
        return 0

    scrape_run_id = str(uuid.uuid4())
    scraped_at = datetime.now(timezone.utc)
    print(f"scrape_run_id = {scrape_run_id}")

    baris = []
    total_biaya = 0.0
    biaya_hilang = 0

    for daftar, fungsi, actor in (
        (ig, scrape_instagram_followers, args.ig_actor),
        (tt, scrape_tiktok_followers, args.tt_actor),
    ):
        if not daftar:
            continue
        peta = {u: (sid, plat) for sid, plat, u in daftar}
        hasil = fungsi(token, [u for _, _, u in daftar], limit=args.limit,
                       actor_id=actor)
        for h in hasil:
            sid, plat = peta[h.username]
            ditulis = dihapus = 0
            simpan_err = None
            if h.berhasil and h.items:
                try:
                    st = simpan(conn, plat, sid, h.username, h.items,
                                source_actor=actor, scraped_at=scraped_at,
                                scrape_run_id=scrape_run_id)
                    ditulis, dihapus = st.ditulis, st.dihapus
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    simpan_err = str(exc)
                    logger.error("Gagal menulis L0 untuk %s: %s", h.username, exc)
            if h.biaya_usd:
                total_biaya += h.biaya_usd
            elif h.berhasil:
                biaya_hilang += 1
            baris.append({
                "platform": plat, "akun": h.username,
                "diminta": args.limit, "diterima": h.jumlah, "ditulis": ditulis,
                "dihapus_lama": dihapus,
                "status": "OK" if (h.berhasil and not simpan_err) else "GAGAL",
                "error": h.error or simpan_err,
                "biaya": h.biaya_usd, "run_id": h.run_id,
            })

    conn.close()

    print("\n" + "=" * 78)
    print(f"{'platform':<10} {'akun':<20} {'minta':>6} {'dapat':>6} {'tulis':>6} "
          f"{'biaya$':>9}  status")
    print("=" * 78)
    for b in baris:
        biaya = f"{b['biaya']:.5f}" if b["biaya"] else "-"
        print(f"{b['platform']:<10} {b['akun']:<20} {b['diminta']:>6} "
              f"{b['diterima']:>6} {b['ditulis']:>6} {biaya:>9}  {b['status']}")
        if b["error"]:
            print(f"           -> {b['error'][:100]}")

    ok = [b for b in baris if b["status"] == "OK"]
    print("-" * 78)
    print(f"berhasil {len(ok)}/{len(baris)} akun | "
          f"follower diterima {sum(b['diterima'] for b in baris)} | "
          f"ditulis ke L0 {sum(b['ditulis'] for b in baris)} | "
          f"biaya ${total_biaya:.4f}"
          + (f" (+{biaya_hilang} run biayanya belum tersedia)" if biaya_hilang else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
