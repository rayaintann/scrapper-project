"""Entry point: scrape daftar follower untuk akun KOL, lalu tulis ke L0.

    python scrape_followers.py --limit-akun 5 --limit 50 --dry-run
    python scrape_followers.py --limit-akun 5 --limit 50 --max-cost-usd 0.50

Berhenti di L0. Lanjutannya (Harmonization -> L1 -> Feature -> L2) dijalankan
lewat asset Dagster, mengikuti pola project ini: scraping ada di luar Dagster,
transformasi ada di dalam.

============================================================================
PEMILIHAN AKUN -- KENAPA DARI unified_profile, BUKAN DAFTAR HARDCODE
============================================================================

Daftar akun diambil dari database sebagai fakta -- baris
`l1_silver.unified_profile` -- bukan dari konstanta di kode, supaya tidak ada
dua sumber kebenaran yang bisa berbeda diam-diam.

DEFAULTNYA SNAPSHOT TERBARU, bukan satu tanggal tetap. `--tanggal-profil`
tetap ada untuk mengunci ke satu tanggal secara eksplisit, tapi ia bukan lagi
default: default berupa tanggal harfiah membuat prosedur ini tidak bisa
dijadwalkan (lihat komentar di atas `SQL_AKUN_TERBARU`).

CAKUPAN dikendalikan `--limit-akun` (jumlah AKUN) dan `--limit` (follower PER
AKUN). Keduanya berbeda dan keduanya perlu: yang pertama menentukan berapa
banyak akun yang ditagih, yang kedua berapa dalam tiap akun digali.

BIAYA dijaga `--max-cost-usd` / `SCRAPE_MAX_COST_FOLLOWERS_USD`. Estimasi
dihitung SEBELUM panggilan Apify pertama, dan run ditolak (exit 3) kalau
melewati plafon.

CONCURRENCY dijaga `run_lock.RunLock`: dua eksekusi bersamaan tidak mungkin,
yang kedua keluar dengan `EXIT_TERKUNCI` (75) dan mencatat alasannya.

LOG per akun masuk `public.scheduler_logs` (`job_name='followers_scrape'`),
tabel yang sama dengan post_pipeline dan scheduler_engine.

EXIT CODE
    0  semua akun berhasil
    1  tidak ada akun yang berhasil / tidak ada kandidat
    2  APIFY_API_TOKEN kosong
    3  estimasi biaya melewati plafon -- tidak ada panggilan Apify
    4  sebagian akun berhasil, sebagian gagal
    75 dilewati karena prosedur yang sama sedang berjalan

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
from pathlib import Path

import psycopg2

from config import (
    PRICE_PER_FOLLOWER_USD,
    ConfigError,
    default_max_cost_usd,
    load_config,
)
from run_lock import EXIT_TERKUNCI, jalankan_terkunci
from scrape_log import AccountOutcome, ScrapeLogger
from post_errors import ACTOR_ERROR, SUCCESS
from apify_followers import (
    DEFAULT_IG_FOLLOWERS_ACTOR,
    DEFAULT_TT_FOLLOWERS_ACTOR,
    LIMIT_MAX,
    scrape_instagram_followers,
    scrape_tiktok_followers,
)
from follower_raw_store import simpan

logger = logging.getLogger("scrape_followers")

# ---------------------------------------------------------------------------
# PEMILIHAN AKUN
# ---------------------------------------------------------------------------
# Dua mode, dan defaultnya sengaja yang pertama:
#
#   tanpa --tanggal-profil : SNAPSHOT TERBARU tiap akun (DISTINCT ON).
#   dengan --tanggal-profil: hanya baris dengan `date` persis itu.
#
# Sebelumnya default-nya adalah tanggal harfiah "2026-08-24" yang tertulis di
# kode. Untuk sekali jalan manual itu tidak apa-apa; untuk Scheduled Task itu
# cacat: tiap eksekusi akan selamanya menargetkan hari yang sama, dan begitu
# snapshot bertambah, daftar akunnya membeku di masa lalu -- atau kosong sama
# sekali dan prosedurnya keluar dengan kode 1 tanpa ada yang salah.
#
# `DISTINCT ON` memakai tie-break eksplisit (`updated_at`, lalu `id`) supaya
# dua baris bertanggal sama tidak membuat hasilnya bergantung pada urutan
# fisik baris -- pola yang sama dipakai gold_profile.py butir 1.
SQL_AKUN_TERBARU = """
    SELECT DISTINCT ON (p.social_account_id)
           p.social_account_id, pl.key AS platform, p.username, p.date
    FROM l1_silver.unified_profile p
    JOIN public.platforms pl ON pl.id = p.platform_id
    WHERE p.social_account_id IS NOT NULL
      AND p.username IS NOT NULL
      AND btrim(p.username) <> ''
    ORDER BY p.social_account_id, p.date DESC,
             p.updated_at DESC NULLS LAST, p.id DESC
"""

SQL_AKUN_TANGGAL = """
    SELECT p.social_account_id, pl.key AS platform, p.username, p.date
    FROM l1_silver.unified_profile p
    JOIN public.platforms pl ON pl.id = p.platform_id
    WHERE p.date = %s
      AND p.social_account_id IS NOT NULL
      AND p.username IS NOT NULL
      AND btrim(p.username) <> ''
"""

# Kapan follower akun ini terakhir diambil. Dipakai urutan `stale`, dan hanya
# itu; tidak pernah dipakai untuk menyaring, supaya akun yang belum pernah
# di-scrape (NULL) tetap ikut dan justru didahulukan.
SQL_TERAKHIR_DISCRAPE = """
    SELECT social_account_id, max(scraped_at) AS terakhir
      FROM l0_raw.ig_followers_apify GROUP BY 1
    UNION ALL
    SELECT social_account_id, max(scraped_at)
      FROM l0_raw.tt_followers_apify GROUP BY 1
"""

#: Urutan kandidat. Nama `stale` sengaja sama dengan `db.ORDER_CLAUSES` supaya
#: operator tidak perlu mengingat dua kosakata untuk gagasan yang sama.
URUTAN = ("stale", "username", "random")

#: Plafon biaya kalau environment kosong. Sengaja seukuran UJI, bukan produksi:
#: budget produksi belum diputuskan bisnis, dan default yang besar akan
#: mengubah "lupa menyetel" menjadi tagihan. ~$1 = sekitar 750 follower.
_FALLBACK_MAX_COST = 1.00

#: Nama kunci prosedur. Satu kunci untuk seluruh scrape follower: kedua
#: platform memakai tabel sumber dan kuota Apify yang sama.
NAMA_KUNCI = "scrape_followers"

JOB_NAME = "followers_scrape"
CATEGORY = "followers"


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
                   help=f"Maksimum follower PER AKUN (1..{LIMIT_MAX}).")
    p.add_argument("--limit-akun", type=int, default=None, metavar="N",
                   help="Maksimum JUMLAH AKUN yang diproses. Berbeda dari "
                        "--limit, yang membatasi follower per akun. Tanpa ini "
                        "seluruh akun yang cocok ikut diproses.")
    p.add_argument("--order", choices=URUTAN, default="stale",
                   help="Urutan kandidat. 'stale' = follower paling lama tidak "
                        "diambil lebih dulu (yang belum pernah, paling depan).")
    p.add_argument("--tanggal-profil", default=None, metavar="YYYY-MM-DD",
                   help="Pakai snapshot unified_profile pada tanggal PERSIS ini. "
                        "Default: snapshot TERBARU tiap akun.")
    p.add_argument("--platform", choices=["instagram", "tiktok", "semua"],
                   default="semua")
    p.add_argument("--usernames", nargs="+", metavar="USERNAME", default=None,
                   help="Batasi ke username tertentu, mengabaikan --limit-akun.")
    p.add_argument("--usernames-file", type=Path, default=None, metavar="FILE",
                   help="Sama seperti --usernames, satu username per baris.")
    p.add_argument("--ig-actor", default=os.getenv("IG_FOLLOWERS_ACTOR_ID")
                   or DEFAULT_IG_FOLLOWERS_ACTOR)
    p.add_argument("--tt-actor", default=os.getenv("TT_FOLLOWERS_ACTOR_ID")
                   or DEFAULT_TT_FOLLOWERS_ACTOR)
    p.add_argument("--max-cost-usd", type=float, default=None, metavar="USD",
                   help="Plafon biaya untuk eksekusi ini. Default dari "
                        "SCRAPE_MAX_COST_FOLLOWERS_USD, atau "
                        f"${_FALLBACK_MAX_COST:.2f} kalau environment kosong.")
    p.add_argument("--no-log", action="store_true",
                   help="Jangan menulis ke public.scheduler_logs.")
    p.add_argument("--dry-run", action="store_true",
                   help="Tampilkan akun & estimasi biaya lalu berhenti. Nol biaya.")
    return p.parse_args(argv)


def _baca_usernames(args) -> set[str] | None:
    """Gabungan --usernames dan --usernames-file, atau None kalau tidak dipakai."""
    daftar: list[str] = list(args.usernames or [])
    if args.usernames_file:
        daftar += [b.strip() for b in
                   args.usernames_file.read_text(encoding="utf-8").splitlines()
                   if b.strip() and not b.lstrip().startswith("#")]
    return {u.lstrip("@").lower() for u in daftar} or None


#: Akun milik KOL serving, lewat jembatan resmi kol_social_account (bukan username).
SQL_AKUN_AKTIF = """
    SELECT ksa.social_account_id
      FROM public.kol_social_account ksa
      JOIN public.kol_directory kd ON kd.id = ksa.kol_id
     WHERE kd.directory_status = 'active'
"""


def pilih_akun(conn, args) -> list[tuple]:
    """Kandidat akun, sudah difilter platform/username dan dipotong --limit-akun.

    Dipisah dari `main()` supaya bisa diuji tanpa menyentuh Apify sama sekali.
    Tanpa --usernames hanya akun milik KOL `directory_status='active'` yang
    dipilih; daftar eksplisit boleh menyebut KOL inactive.
    """
    pilihan = _baca_usernames(args)
    with conn.cursor() as cur:
        if args.tanggal_profil:
            cur.execute(SQL_AKUN_TANGGAL, (args.tanggal_profil,))
        else:
            cur.execute(SQL_AKUN_TERBARU)
        semua = [(str(r[0]), r[1], r[2]) for r in cur.fetchall()]
        if pilihan is None:
            cur.execute(SQL_AKUN_AKTIF)
            aktif = {str(r[0]) for r in cur.fetchall()}
            semua = [r for r in semua if r[0] in aktif]

        # Urutan `stale` butuh kapan follower tiap akun terakhir diambil.
        terakhir: dict[str, object] = {}
        if args.order == "stale":
            cur.execute(SQL_TERAKHIR_DISCRAPE)
            for sid, ts in cur.fetchall():
                if sid is None:
                    continue
                sid = str(sid)
                if ts is not None and (sid not in terakhir or ts > terakhir[sid]):
                    terakhir[sid] = ts

    if args.platform != "semua":
        semua = [r for r in semua if r[1] == args.platform]

    if pilihan is not None:
        semua = [r for r in semua if (r[2] or "").lower() in pilihan]

    if args.order == "stale":
        # Akun yang BELUM PERNAH diambil followernya didahulukan (kunci 0),
        # lalu sisanya dari yang paling lama. Platform+username jadi tie-break
        # supaya urutannya deterministik antar-run.
        _awal = datetime.min.replace(tzinfo=timezone.utc)
        semua.sort(key=lambda r: (
            1 if r[0] in terakhir else 0,
            terakhir.get(r[0]) or _awal,
            r[1], r[2] or "",
        ))
    elif args.order == "random":
        import random as _random
        _random.shuffle(semua)
    else:
        semua.sort(key=lambda r: (r[1], r[2] or ""))

    # --usernames adalah pilihan eksplisit; memotongnya lagi akan diam-diam
    # membuang akun yang memang diminta namanya.
    if args.limit_akun is not None and pilihan is None:
        semua = semua[: max(0, args.limit_akun)]
    return semua


def _jalankan(args) -> int:
    """Isi sebenarnya `main()`, dijalankan di bawah kunci prosedur."""
    token = os.getenv("APIFY_API_TOKEN")
    if not token and not args.dry_run:
        print("APIFY_API_TOKEN belum diset.", file=sys.stderr)
        return 2

    conn = _conn()
    try:
        semua = pilih_akun(conn, args)
    except Exception:
        conn.close()
        raise

    sumber = (f"snapshot tanggal {args.tanggal_profil}" if args.tanggal_profil
              else "snapshot terbaru tiap akun")
    if not semua:
        print(f"Tidak ada akun yang cocok ({sumber}, platform={args.platform}).")
        conn.close()
        return 1

    ig = [r for r in semua if r[1] == "instagram"]
    tt = [r for r in semua if r[1] == "tiktok"]

    # ---------------------------------------------------------------------
    # COST GUARD -- sebelum satu pun panggilan Apify.
    # ---------------------------------------------------------------------
    # Estimasi konservatif: SETIAP akun dianggap mengembalikan --limit follower
    # penuh. Kenyataannya banyak akun mengembalikan lebih sedikit, jadi biaya
    # nyata cenderung di bawah angka ini -- dan itu arah salah yang benar untuk
    # sebuah plafon.
    n_akun = len(ig) + len(tt)
    maks_follower = n_akun * args.limit
    estimasi = maks_follower * PRICE_PER_FOLLOWER_USD
    plafon = (args.max_cost_usd if args.max_cost_usd is not None
              else default_max_cost_usd("SCRAPE_MAX_COST_FOLLOWERS_USD",
                                        _FALLBACK_MAX_COST))

    print(f"Sumber akun  : {sumber}")
    print(f"Urutan       : {args.order}")
    print(f"Akun terpilih: {len(ig)} Instagram + {len(tt)} TikTok = {n_akun}")
    print(f"Estimasi     : maks {maks_follower} follower "
          f"x ${PRICE_PER_FOLLOWER_USD} = ${estimasi:.4f}")
    print(f"Plafon       : ${plafon:.2f}")

    if estimasi > plafon:
        print(
            f"\nDIHENTIKAN: estimasi ${estimasi:.4f} melewati plafon "
            f"${plafon:.2f}.\n"
            f"Kecilkan cakupannya (--limit-akun / --limit), atau naikkan plafon "
            f"lewat --max-cost-usd atau SCRAPE_MAX_COST_FOLLOWERS_USD.\n"
            f"Tidak ada satu pun panggilan Apify yang dilakukan.",
            file=sys.stderr,
        )
        conn.close()
        return 3

    if args.dry_run:
        for sid, plat, uname in ig + tt:
            print(f"  {plat:<10} {uname}")
        print("\n[dry-run] Tidak ada panggilan Apify dan tidak ada tulisan ke L0.")
        conn.close()
        return 0

    scrape_run_id = str(uuid.uuid4())
    scraped_at = datetime.now(timezone.utc)
    print(f"scrape_run_id = {scrape_run_id}")

    baris = []
    total_biaya = 0.0
    biaya_hilang = 0

    # `public.scheduler_logs` -- tabel log yang SAMA dengan post_pipeline dan
    # scheduler_engine, dibedakan lewat job_name/category. Tidak ada mekanisme
    # logging baru. Logger memakai koneksi & autocommit sendiri, jadi kegagalan
    # ingest tidak ikut menghapus jejaknya (lihat docstring scrape_log.py).
    slog = None
    if not args.no_log:
        try:
            slog = ScrapeLogger(load_config().postgres, run_id=scrape_run_id,
                                job_name=JOB_NAME, category=CATEGORY)
        except ConfigError as exc:
            logger.warning("Logging dimatikan, konfigurasi DB tidak lengkap: %s", exc)

    try:
        for daftar, fungsi, actor in (
            (ig, scrape_instagram_followers, args.ig_actor),
            (tt, scrape_tiktok_followers, args.tt_actor),
        ):
            if not daftar:
                continue
            peta = {u: (sid, plat) for sid, plat, u in daftar}
            mulai_batch = datetime.now(timezone.utc)
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
                sukses = bool(h.berhasil and not simpan_err)
                baris.append({
                    "platform": plat, "akun": h.username,
                    "diminta": args.limit, "diterima": h.jumlah, "ditulis": ditulis,
                    "dihapus_lama": dihapus,
                    "status": "OK" if sukses else "GAGAL",
                    "error": h.error or simpan_err,
                    "biaya": h.biaya_usd, "run_id": h.run_id,
                })
                if slog is not None:
                    # Satu baris per akun. `records` = baris L0 yang benar-benar
                    # masuk, bukan jumlah item yang dikembalikan actor -- yang
                    # kedua bisa besar sementara penulisannya gagal.
                    slog.log_account(AccountOutcome(
                        username=h.username,
                        platform=plat,
                        # Kode dari kosakata post_errors, bukan string baru:
                        # `scheduler_logs.status` dibaca konsumen lain yang
                        # sudah mengenal kosakata itu.
                        status=SUCCESS if sukses else ACTOR_ERROR,
                        records=ditulis,
                        message=(h.error or simpan_err),
                        started_at=mulai_batch,
                        finished_at=datetime.now(timezone.utc),
                    ))
    finally:
        if slog is not None:
            slog.close()

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
    # Sebagian akun gagal TIDAK dianggap sukses penuh: exit 4 membedakannya
    # dari "semua gagal" (1) dan dari "semua berhasil" (0), supaya riwayat
    # Scheduled Task bisa dibaca tanpa membuka log.
    if not ok:
        return 1
    return 0 if len(ok) == len(baris) else 4


def main(argv=None) -> int:
    """Titik masuk: muat env, ambil kunci prosedur, lalu jalankan.

    Kunci dipasang DI SINI dan bukan di dalam `_jalankan()` supaya seluruh
    eksekusi -- termasuk pemilihan akun dan estimasi biaya -- berada di
    dalamnya. Dua Scheduled Task yang tumpang tindih tidak boleh sampai
    sama-sama memanggil Apify.
    """
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _muat_env()
    # dry-run tidak memanggil Apify dan tidak menulis apa pun, jadi tidak perlu
    # antre di belakang run yang sedang berjalan.
    if args.dry_run:
        return _jalankan(args)
    return jalankan_terkunci(NAMA_KUNCI, _jalankan, args)


if __name__ == "__main__":
    raise SystemExit(main())
