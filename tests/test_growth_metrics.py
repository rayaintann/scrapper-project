"""Test untuk Growth %, Daily Growth, dan proyeksi 30 hari (`db.SQL_GROWTH_CTE`).

KENAPA TEST INI MENYENTUH DATABASE, TAPI TIDAK MENULIS APA PUN
==============================================================
Logikanya ADA DI SQL, bukan di Python. Menulis ulang rumusnya sebagai fungsi
Python supaya "bisa di-unit-test" akan menghasilkan dua definisi yang cepat
atau lambat berbeda -- persis kesalahan yang dihindari `db.py` dengan tidak
menyalin rumus `followers_growth` dari `sp_build_unified_profile`.

Jadi test ini menjalankan SQL YANG SAMA PERSIS dengan produksi, tetapi
`sumber`-nya diganti klausa VALUES. Tidak ada CREATE, INSERT, UPDATE, maupun
TEMP TABLE: hanya SELECT atas literal, di sesi read-only. Yang diuji adalah
SQL yang benar-benar dijalankan, dengan data yang sepenuhnya dikendalikan test.

Skenario yang ditutup: contoh wajib 100->125/25 hari, naik, turun, tetap,
previous = 0, current NULL, previous NULL, tanggal sama, dan multiple snapshot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402

AKUN_A = "11111111-1111-1111-1111-111111111111"
AKUN_B = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# Perkakas
# ---------------------------------------------------------------------------

def _sumber(baris: list[tuple]) -> str:
    """Klausa VALUES beralias `p`, menggantikan l1_silver.unified_profile.

    Tipe di-cast eksplisit di baris pertama supaya Postgres tidak menebak
    `unknown` -- tanpa itu `count(followers_count)` dan aritmetika tanggal
    gagal dengan pesan yang tidak ada hubungannya dengan bug yang dicari.
    """
    potongan = []
    for i, (sid, tanggal, followers, growth) in enumerate(baris):
        f = "NULL" if followers is None else str(followers)
        g = "NULL" if growth is None else str(growth)
        if i == 0:
            potongan.append(
                f"('{sid}'::uuid, DATE '{tanggal}', {f}::bigint, {g}::numeric)"
            )
        else:
            potongan.append(f"('{sid}', DATE '{tanggal}', {f}, {g})")
    return (
        "(VALUES " + ", ".join(potongan) + ") "
        "AS p(social_account_id, date, followers_count, followers_growth)"
    )


def hitung(conn, baris: list[tuple]) -> dict[str, dict]:
    """Jalankan CTE produksi atas `baris`; hasilnya dipetakan per akun."""
    sql = "WITH " + db._GROWTH_CTE_TEMPLATE.format(sumber=_sumber(baris)) + """
        SELECT g.social_account_id::text, g.previous_snapshot_date,
               g.current_snapshot_date, g.previous_followers, g.current_followers,
               g.days_between, g.growth_pct, g.daily_growth, g.projected_30d,
               g.projected_followers_30d
          FROM growth g
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        kolom = ("previous_snapshot_date", "current_snapshot_date",
                 "previous_followers", "current_followers", "days_between",
                 "growth_pct", "daily_growth", "projected_30d",
                 "projected_followers_30d")
        return {r[0]: dict(zip(kolom, r[1:])) for r in cur.fetchall()}


@pytest.fixture(scope="module")
def conn():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        from config import load_config
        cfg = load_config()
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"konfigurasi DB tidak tersedia: {exc}")
    try:
        cn = psycopg2.connect(connect_timeout=5, **cfg.postgres.as_connect_kwargs())
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    # READ-ONLY: kalau ada statement yang mencoba menulis, Postgres menolaknya
    # dan test gagal -- itu jaring pengaman, bukan sekadar niat baik.
    cn.set_session(readonly=True, autocommit=True)
    yield cn
    cn.close()


# ---------------------------------------------------------------------------
# 1. Contoh wajib dari requirement
# ---------------------------------------------------------------------------

def test_contoh_wajib_100_ke_125_dalam_25_hari(conn):
    """previous=100, current=125, 25 hari.

        Growth %                = 25
        daily_growth            = 1 follower/hari
        projected_30d           = 30     (SELISIH, bukan jumlah absolut)
        projected_followers_30d = 155    (125 + 30)

    Ini angka acuan yang disepakati. Kalau baris ini berubah, yang berubah
    adalah kesepakatannya, bukan sekadar test.

    CATATAN PERUBAHAN: versi sebelumnya menguji projected_30d == 130, yaitu
    previous + daily*30. Titik acuan proyeksi dipindahkan ke snapshot SEKARANG
    dan projected_30d diubah menjadi selisih; test ini mengikuti keputusan itu.
    """
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 100, None),
        (AKUN_A, "2026-01-26", 125, 25.0000),
    ])[AKUN_A]
    assert h["previous_followers"] == 100
    assert h["current_followers"] == 125
    assert h["days_between"] == 25
    assert float(h["growth_pct"]) == pytest.approx(25.0)
    assert float(h["daily_growth"]) == pytest.approx(1.0)
    assert int(h["projected_30d"]) == 30
    assert int(h["projected_followers_30d"]) == 155


def test_projected_30d_adalah_selisih_bukan_jumlah_absolut(conn):
    """Penjaga terhadap kesalahan yang paling mungkin: mengembalikan jumlah
    follower ke kolom yang sekarang berisi selisih."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 100, None),
        (AKUN_A, "2026-01-26", 125, 25.0000),
    ])[AKUN_A]
    assert int(h["projected_30d"]) != 130, "projected_30d kembali ke definisi lama"
    assert int(h["projected_30d"]) < int(h["current_followers"])


def test_proyeksi_tidak_menuntut_jarak_tepat_30_hari(conn):
    """Jarak snapshot NYATA yang dipakai, bukan asumsi 30 hari.

    Dua akun dengan laju harian sama tapi jarak snapshot berbeda harus
    menghasilkan proyeksi 30 hari yang SAMA -- itulah buktinya days_between
    dipakai sebagai penyebut, bukan angka tetap.
    """
    pendek = hitung(conn, [(AKUN_A, "2026-01-01", 100, None),
                           (AKUN_A, "2026-01-11", 110, 10.0)])[AKUN_A]
    panjang = hitung(conn, [(AKUN_B, "2026-01-01", 100, None),
                            (AKUN_B, "2026-03-02", 160, 60.0)])[AKUN_B]
    assert pendek["days_between"] == 10 and panjang["days_between"] == 60
    assert float(pendek["daily_growth"]) == float(panjang["daily_growth"]) == 1.0
    assert int(pendek["projected_30d"]) == int(panjang["projected_30d"]) == 30


# ---------------------------------------------------------------------------
# 2. Arah pergerakan: naik, turun, tetap
# ---------------------------------------------------------------------------

def test_naik(conn):
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 1000, None),
        (AKUN_A, "2026-01-11", 1200, 20.0),
    ])[AKUN_A]
    assert h["days_between"] == 10
    assert float(h["daily_growth"]) == pytest.approx(20.0)   # 200/10
    assert int(h["projected_30d"]) == 600                    # 20*30
    assert int(h["projected_followers_30d"]) == 1800         # 1200 + 600


def test_turun(conn):
    """Growth negatif harus lolos apa adanya, bukan dipotong ke nol."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 1000, None),
        (AKUN_A, "2026-01-11", 800, -20.0),
    ])[AKUN_A]
    assert float(h["daily_growth"]) == pytest.approx(-20.0)
    assert int(h["projected_30d"]) == -600                   # -20*30
    assert int(h["projected_followers_30d"]) == 200          # 800 - 600


def test_tetap(conn):
    """Tidak berubah -> daily 0 dan proyeksi = previous. NOL, bukan NULL:
    'tidak tumbuh' adalah jawaban, bukan ketiadaan jawaban."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 5000, None),
        (AKUN_A, "2026-01-11", 5000, 0.0),
    ])[AKUN_A]
    assert float(h["daily_growth"]) == 0.0
    assert int(h["projected_30d"]) == 0
    assert int(h["projected_followers_30d"]) == 5000


def test_proyeksi_boleh_negatif_tidak_dijepit_ke_nol(conn):
    """Penurunan tajam menghasilkan proyeksi negatif. Itu memang arti rumusnya;
    menjepitnya ke 0 akan menyembunyikan akun yang runtuh."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 100, None),
        (AKUN_A, "2026-01-11", 50, -50.0),
    ])[AKUN_A]
    assert float(h["daily_growth"]) == pytest.approx(-5.0)
    assert int(h["projected_30d"]) == -150                   # -5*30
    # Proyeksi follower boleh NEGATIF; menjepitnya ke 0 akan menyembunyikan
    # akun yang runtuh, dan 50 - 150 memang -100.
    assert int(h["projected_followers_30d"]) == -100


# ---------------------------------------------------------------------------
# 3. Kasus yang harus menghasilkan NULL, bukan angka karangan
# ---------------------------------------------------------------------------

def test_previous_nol_menghasilkan_null(conn):
    """Pembagian Growth % tidak terdefinisi; daily growth ikut ditolak supaya
    kedua angka bercerita tentang pasangan snapshot yang sama."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 0, None),
        (AKUN_A, "2026-01-11", 500, None),
    ])[AKUN_A]
    assert h["previous_followers"] == 0
    assert h["daily_growth"] is None
    assert h["projected_30d"] is None


def test_current_null_menghasilkan_null(conn):
    """Snapshot yang di-NULL-kan sanity guard 035 tidak boleh jadi pembilang."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 1000, None),
        (AKUN_A, "2026-01-11", None, None),
    ])[AKUN_A]
    assert h["current_followers"] is None
    assert h["daily_growth"] is None
    assert h["projected_30d"] is None


def test_previous_null_menghasilkan_null(conn):
    """Snapshot pertama tidak punya pembanding."""
    h = hitung(conn, [(AKUN_A, "2026-01-01", 1000, None)])[AKUN_A]
    assert h["previous_followers"] is None
    assert h["days_between"] is None
    assert h["daily_growth"] is None
    assert h["projected_30d"] is None


def test_tanggal_sama_menghasilkan_null(conn):
    """days_between = 0 berarti pembagian nol. Ditolak, bukan dibagi.

    `uq_unified_profile` sebenarnya melarang dua baris bertanggal sama untuk
    satu akun, tapi rumusnya tidak boleh bergantung pada constraint tabel lain
    untuk tidak meledak.
    """
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 1000, None),
        (AKUN_B, "2026-01-01", 1000, None),
    ])
    assert h[AKUN_A]["daily_growth"] is None
    assert h[AKUN_B]["daily_growth"] is None


def test_growth_pct_tidak_pernah_dihitung_ulang(conn):
    """`growth_pct` dibawa apa adanya dari L1, termasuk kalau nilainya
    'salah' menurut angka di baris itu. Kalau test ini gagal, berarti rumus
    L1 sudah tersalin ke jalur baca -- dua sumber kebenaran."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 100, None),
        (AKUN_A, "2026-01-11", 200, 12.3456),   # sengaja bukan 100.0
    ])[AKUN_A]
    assert float(h["growth_pct"]) == pytest.approx(12.3456)


# ---------------------------------------------------------------------------
# 4. Multiple snapshot & interaksi dengan sanity guard 035
# ---------------------------------------------------------------------------

def test_multiple_snapshot_memakai_pasangan_terbaru(conn):
    """Tiga snapshot -> yang dilaporkan adalah pasangan TERAKHIR, bukan yang
    pertama dan bukan rata-rata seluruh rentang."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 1000, None),
        (AKUN_A, "2026-01-11", 1200, 20.0),
        (AKUN_A, "2026-01-21", 1500, 25.0),
    ])[AKUN_A]
    assert h["previous_snapshot_date"].isoformat() == "2026-01-11"
    assert h["current_snapshot_date"].isoformat() == "2026-01-21"
    assert h["previous_followers"] == 1200
    assert h["current_followers"] == 1500
    assert float(h["daily_growth"]) == pytest.approx(30.0)   # 300/10
    assert int(h["projected_30d"]) == 900                    # 30*30
    assert int(h["projected_followers_30d"]) == 2400         # 1500 + 900


def test_snapshot_suspect_dilewati_bukan_memutus_rantai(conn):
    """Inti kompatibilitas dengan sanity guard 035.

    Baris tengah di-NULL-kan guard. Pembandingnya harus melompat ke snapshot
    VALID terakhir (1 Januari), dan days_between dihitung terhadap tanggal
    snapshot valid itu -- bukan terhadap baris NULL, dan bukan menyerah.
    """
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 1000, None),
        (AKUN_A, "2026-01-11", None, None),     # di-NULL-kan guard
        (AKUN_A, "2026-01-21", 1400, 40.0),
    ])[AKUN_A]
    assert h["previous_followers"] == 1000, "pembanding harus melompati baris suspect"
    assert h["previous_snapshot_date"].isoformat() == "2026-01-01"
    assert h["days_between"] == 20, "jarak dihitung ke snapshot VALID terakhir"
    assert float(h["daily_growth"]) == pytest.approx(20.0)   # 400/20
    assert int(h["projected_30d"]) == 600                    # 20*30
    assert int(h["projected_followers_30d"]) == 2000         # 1400 + 600


def test_dua_akun_tidak_saling_bocor(conn):
    """Window function harus dipartisi per akun; tanpa itu snapshot akun A
    jadi pembanding akun B."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", 100, None),
        (AKUN_B, "2026-01-05", 900000, None),
        (AKUN_A, "2026-01-11", 200, 100.0),
        (AKUN_B, "2026-01-15", 900100, 0.0111),
    ])
    assert h[AKUN_A]["previous_followers"] == 100
    assert h[AKUN_B]["previous_followers"] == 900000


def test_seluruh_snapshot_null_tetap_menghasilkan_baris_kosong(conn):
    """Akun yang kedua snapshotnya di-NULL-kan guard (kasus nyata: lydiaaas__,
    zeejkt48) tetap muncul, dengan seluruh angka NULL."""
    h = hitung(conn, [
        (AKUN_A, "2026-01-01", None, None),
        (AKUN_A, "2026-01-11", None, None),
    ])[AKUN_A]
    assert h["previous_followers"] is None
    assert h["current_followers"] is None
    assert h["daily_growth"] is None
    assert h["projected_30d"] is None


# ---------------------------------------------------------------------------
# 5. Konsistensi dengan data produksi
# ---------------------------------------------------------------------------

@pytest.mark.needs_db
def test_db_daily_growth_searah_dengan_selisih_follower(conn):
    """Tanda daily_growth harus sama dengan tanda (current - previous).

    Ini invarian yang EKSAK -- tidak melibatkan pembulatan -- jadi kegagalannya
    selalu berarti bug, bukan artefak. Kalau tandanya berlawanan, berarti
    `previous_followers` di jalur baca sudah tidak menunjuk snapshot yang sama
    dengan yang dipakai L1.
    """
    for g in db.fetch_growth_metrics(conn, hanya_terhitung=True, limit=10000):
        selisih = g.current_followers - g.previous_followers
        assert (selisih > 0) == (g.daily_growth > 0), g
        assert (selisih < 0) == (g.daily_growth < 0), g


@pytest.mark.needs_db
def test_db_growth_pct_searah_dengan_daily_growth_bila_tidak_membulat_nol(conn):
    """Perbandingan dengan `growth_pct` hanya sah kalau ia belum hilang ke nol.

    `l1_silver.followers_growth` dibulatkan 4 desimal. Pada akun besar, +1
    follower atas 2.249.679 menghasilkan 0,00004% yang membulat menjadi 0,0000
    sementara daily growth-nya 0,1/hari -- keduanya benar, dan menuntut
    tandanya sama akan menghukum pembulatan, bukan menangkap bug. Contoh nyata
    itulah yang membuat asserti versi pertama test ini gagal.
    """
    for g in db.fetch_growth_metrics(conn, hanya_terhitung=True, limit=10000):
        if g.growth_pct in (None, 0.0) or g.daily_growth == 0.0:
            continue
        assert (g.growth_pct > 0) == (g.daily_growth > 0), g


@pytest.mark.needs_db
def test_db_proyeksi_konsisten_dengan_daily_growth(conn):
    """projected_30d harus benar-benar previous + daily*30 pada data nyata."""
    for g in db.fetch_growth_metrics(conn, hanya_terhitung=True, limit=10000):
        harap = round(g.daily_growth * 30)
        assert abs(g.projected_30d - harap) <= 1, (
            f"{g.social_account_id}: proyeksi {g.projected_30d} != {harap}"
        )


@pytest.mark.needs_db
def test_db_days_between_selalu_positif(conn):
    """Kalau ada days_between <= 0 yang lolos, pembagian nol sedang menunggu."""
    for g in db.fetch_growth_metrics(conn, hanya_terhitung=True, limit=10000):
        assert g.days_between > 0
