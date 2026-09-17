"""Test ambang kerja: Growth Classification, Gender Reliability, Post Frequency
Reliability, dan Monitoring Priority.

DUA HAL YANG DIUJI, DAN YANG KEDUA LEBIH PENTING
================================================
1. Tiap label benar pada nilai batasnya.
2. Versi PYTHON dan versi SQL memberi jawaban yang SAMA.

Butir 2 yang menjaga janji "ambang cuma di satu tempat". `metrics_thresholds.py`
menurunkan keduanya dari konstanta yang sama, tapi turunan bisa saja diedit
sebelah -- misalnya seseorang mengubah `>` jadi `>=` hanya di SQL. Test paritas
di bawah menjalankan KEDUANYA atas nilai yang identik dan membandingkan
hasilnya, jadi pergeseran seperti itu gagal di sini, bukan di produksi.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import metrics_thresholds as mt  # noqa: E402


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
    cn.set_session(readonly=True, autocommit=True)
    yield cn
    cn.close()


def _sql_satu(conn, ekspresi: str, **nilai) -> str | None:
    """Jalankan satu ekspresi CASE atas nilai literal."""
    kolom = ", ".join(
        f"{'NULL' if v is None else v}::numeric AS {k}" for k, v in nilai.items())
    with conn.cursor() as cur:
        cur.execute(f"SELECT {ekspresi} FROM (SELECT {kolom}) t")
        return cur.fetchone()[0]


# ===========================================================================
# 1. GROWTH CLASSIFICATION
# ===========================================================================

@pytest.mark.parametrize("growth, harapan", [
    (30.0, mt.GROWTH_HIGH),        # contoh requirement: 100 -> 130 = 30%
    (10.01, mt.GROWTH_HIGH),
    (10.0, mt.GROWTH_HIGH),        # batas: 10 tepat MASUK High (>= 10)
    (9.99, mt.GROWTH_MEDIUM),
    (7.5, mt.GROWTH_MEDIUM),
    (5.0, mt.GROWTH_MEDIUM),       # batas bawah Medium
    (4.99, mt.GROWTH_LOW),
    (0.0, mt.GROWTH_LOW),          # tidak tumbuh tetap Low, BUKAN Negative
    (-0.01, mt.GROWTH_NEGATIVE),
    (-25.0, mt.GROWTH_NEGATIVE),
    (None, None),
])
def test_growth_class(growth, harapan):
    assert mt.klasifikasi_growth(growth) == harapan


def test_growth_class_contoh_requirement_30_persen():
    """previous=100, current=130 -> Growth 30% -> High Growth."""
    growth = (130 - 100) / 100 * 100
    assert growth == 30.0
    assert mt.klasifikasi_growth(growth) == mt.GROWTH_HIGH


def test_growth_null_bukan_negative():
    """Akun tanpa dua snapshot belum punya pertumbuhan -- bukan pertumbuhan
    buruk. Melabelinya Negative mengubah ketiadaan data jadi tuduhan."""
    assert mt.klasifikasi_growth(None) is None


# ===========================================================================
# 2. GENDER RELIABILITY
# ===========================================================================

@pytest.mark.parametrize("known, harapan", [
    (100.0, mt.TINGKAT_HIGH),
    (70.0, mt.TINGKAT_HIGH),       # batas bawah High
    (69.99, mt.TINGKAT_MEDIUM),
    (40.0, mt.TINGKAT_MEDIUM),     # batas bawah Medium
    (39.99, mt.TINGKAT_LOW),
    (0.0, mt.TINGKAT_LOW),
    (None, None),
])
def test_gender_reliability(known, harapan):
    assert mt.klasifikasi_gender(known) == harapan


# ===========================================================================
# 3. POST FREQUENCY RELIABILITY
# ===========================================================================

@pytest.mark.parametrize("hari, post, harapan", [
    (30, 10, mt.TINGKAT_HIGH),     # batas High tepat
    (365, 200, mt.TINGKAT_HIGH),
    (29, 10, mt.TINGKAT_MEDIUM),   # hari kurang satu -> turun ke Medium
    (30, 9, mt.TINGKAT_MEDIUM),    # post kurang satu -> turun ke Medium
    (14, 5, mt.TINGKAT_MEDIUM),    # batas Medium tepat
    (13, 5, mt.TINGKAT_LOW),
    (14, 4, mt.TINGKAT_LOW),
    (2, 10, mt.TINGKAT_LOW),       # 10 post dalam 2 hari: kasus nyata
    (0, 1, mt.TINGKAT_LOW),
    (100, 0, None),                # tidak ada post valid -> belum bisa dinilai
    (None, None, None),
    (30, None, None),
])
def test_post_frequency_reliability(hari, post, harapan):
    assert mt.klasifikasi_post_frequency(hari, post) == harapan


def test_reliability_butuh_dua_syarat_bersamaan():
    """Rentang panjang saja tidak cukup, dan banyak post saja tidak cukup."""
    assert mt.klasifikasi_post_frequency(365, 3) == mt.TINGKAT_LOW
    assert mt.klasifikasi_post_frequency(3, 365) == mt.TINGKAT_LOW


def test_reliability_tanpa_post_null_bukan_low():
    """`Low` berarti "datanya ada tapi tipis". Tanpa post sama sekali,
    jawabannya "belum bisa dinilai"."""
    assert mt.klasifikasi_post_frequency(90, 0) is None


# ===========================================================================
# 4. MONITORING PRIORITY
# ===========================================================================

@pytest.mark.parametrize("er, harapan", [
    (12.0, mt.TINGKAT_HIGH),
    (5.0, mt.TINGKAT_HIGH),        # batas: ER 5% = High
    (4.99, mt.TINGKAT_MEDIUM),
    (2.0, mt.TINGKAT_MEDIUM),      # batas: ER 2% = Medium
    (1.99, mt.TINGKAT_LOW),
    (0.0, mt.TINGKAT_LOW),
    (None, None),
])
def test_monitoring_priority(er, harapan):
    assert mt.klasifikasi_monitoring(er) == harapan


def test_monitoring_null_bukan_low():
    """Diminta eksplisit di requirement: NULL tidak boleh jatuh ke Low."""
    assert mt.klasifikasi_monitoring(None) is None
    assert mt.klasifikasi_monitoring(0.0) == mt.TINGKAT_LOW


# ===========================================================================
# 5. PARITAS SQL <-> PYTHON
# ===========================================================================

@pytest.mark.needs_db
@pytest.mark.parametrize("growth", [30.0, 10.01, 10.0, 5.0, 4.99, 0.0, -0.01, -25.0, None])
def test_paritas_growth_class(conn, growth):
    assert _sql_satu(conn, mt.sql_growth_class("t.g"), g=growth) == \
           mt.klasifikasi_growth(growth)


@pytest.mark.needs_db
@pytest.mark.parametrize("known", [100.0, 70.0, 69.99, 40.0, 39.99, 0.0, None])
def test_paritas_gender_reliability(conn, known):
    assert _sql_satu(conn, mt.sql_gender_reliability("t.k"), k=known) == \
           mt.klasifikasi_gender(known)


@pytest.mark.needs_db
@pytest.mark.parametrize("hari, post", [
    (30, 10), (29, 10), (30, 9), (14, 5), (13, 5), (2, 10), (100, 0),
    (None, 5), (30, None), (None, None),
])
def test_paritas_post_frequency_reliability(conn, hari, post):
    assert _sql_satu(conn, mt.sql_post_frequency_reliability("t.h", "t.p"),
                     h=hari, p=post) == mt.klasifikasi_post_frequency(hari, post)


@pytest.mark.needs_db
@pytest.mark.parametrize("er", [12.0, 5.0, 4.99, 2.0, 1.99, 0.0, None])
def test_paritas_monitoring_priority(conn, er):
    assert _sql_satu(conn, mt.sql_monitoring_priority("t.e"), e=er) == \
           mt.klasifikasi_monitoring(er)


# ===========================================================================
# 6. AMBANG BENAR-BENAR TERPUSAT
# ===========================================================================

def test_ambang_tidak_ditulis_ulang_di_luar_modul():
    """Penjaga terhadap ambang yang menyebar.

    Yang dicari BUKAN angkanya (5, 10, 30, 70 muncul di mana-mana untuk hal
    lain), melainkan NAMA LABEL-nya di luar modul ambang. Kalau 'High Growth'
    muncul sebagai literal di gold_profile.py atau db.py, berarti seseorang
    menulis CASE-nya sendiri alih-alih memanggil generator.

    Baris KOMENTAR dilewati. Komentar yang menjelaskan "NULL bukan 'Negative
    Growth'" justru harus menyebut labelnya, dan melarang itu akan menghukum
    dokumentasi -- pengecualian yang sama sudah dipakai
    `test_tanggal_profil_tidak_lagi_hardcode`.
    """
    label = ("High Growth", "Medium Growth", "Low Growth", "Negative Growth")
    periksa = [ROOT / "db.py",
               ROOT / "orchestration/kol_orchestration/assets/gold_profile.py",
               ROOT / "orchestration/kol_orchestration/assets/feature_engagement.py"]
    for berkas in periksa:
        for baris in berkas.read_text(encoding="utf-8").splitlines():
            bersih = baris.strip()
            if bersih.startswith("#") or bersih.startswith("--"):
                continue
            for l in label:
                assert f"'{l}'" not in bersih and f'"{l}"' not in bersih, \
                    f"{berkas.name} menulis literal label {l!r}: {bersih}"


def test_ringkasan_ambang_mencerminkan_konstanta():
    """Metadata asset menerbitkan ambang yang dipakai; ia harus ikut berubah
    saat konstantanya berubah, bukan jadi teks basi."""
    assert str(mt.GROWTH_HIGH_MIN) in mt.RINGKASAN_AMBANG["growth_class"]
    assert str(mt.GENDER_HIGH_MIN) in mt.RINGKASAN_AMBANG["gender_reliability"]
    assert str(mt.FREQ_HIGH_HARI) in mt.RINGKASAN_AMBANG["post_frequency_reliability"]
    assert str(mt.PRIORITY_HIGH_MIN) in mt.RINGKASAN_AMBANG["monitoring_priority"]


# ===========================================================================
# 7. DATA NYATA
# ===========================================================================

@pytest.mark.needs_db
def test_db_label_konsisten_dengan_angkanya(conn):
    """Tiap label di kartu L2 harus cocok dengan fungsi Python atas kolom
    yang jadi dasarnya. Kalau tidak, gold_profile.py dan modul ambang sudah
    bercerita berbeda."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT followers_growth, growth_class,
                   gender_known_pct, gender_reliability,
                   observation_days, post_frequency_count, post_frequency_reliability,
                   monitoring_er_pct, monitoring_priority
              FROM l2_gold.kol_profile_card""")
        for (g, gc, gk, gr, hari, post, fr, er, mp) in cur.fetchall():
            assert gc == mt.klasifikasi_growth(float(g) if g is not None else None)
            assert gr == mt.klasifikasi_gender(float(gk) if gk is not None else None)
            assert fr == mt.klasifikasi_post_frequency(hari, post)
            assert mp == mt.klasifikasi_monitoring(float(er) if er is not None else None)


@pytest.mark.needs_db
def test_db_monitoring_null_tidak_pernah_jadi_low(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card
             WHERE monitoring_er_pct IS NULL AND monitoring_priority IS NOT NULL""")
        assert cur.fetchone()[0] == 0


@pytest.mark.needs_db
def test_db_post_frequency_daily_kali_30_sama_dengan_monthly(conn):
    """Dua satuan dari satu angka; kalau berbeda, salah satunya dihitung
    dari sampel yang lain."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card
             WHERE post_frequency_daily IS NOT NULL
               AND abs(post_frequency_daily * 30 - post_frequency_monthly) > 0.01""")
        assert cur.fetchone()[0] == 0

# ===========================================================================
# BATAS FINAL YANG SUDAH DISETUJUI
# ===========================================================================
# Tiga blok di bawah menguji angka yang sudah disepakati, bukan angka kerja.
# Kalau salah satu berubah, yang berubah adalah kesepakatannya.

@pytest.mark.parametrize("skor, harapan", [
    (49.0, mt.TINGKAT_LOW),      # tepat di bawah batas Medium
    (49.99, mt.TINGKAT_LOW),
    (50.0, mt.TINGKAT_MEDIUM),   # batas Medium tepat
    (74.99, mt.TINGKAT_MEDIUM),  # tepat di bawah batas High
    (75.0, mt.TINGKAT_HIGH),     # batas High tepat
    (100.0, mt.TINGKAT_HIGH),
    (0.0, mt.TINGKAT_LOW),
    (None, None),
])
def test_batas_final_audience_quality(skor, harapan):
    assert mt.klasifikasi_audience_quality(skor) == harapan


@pytest.mark.parametrize("er, harapan", [
    (1.99, mt.TINGKAT_LOW),      # tepat di bawah batas Medium
    (2.0, mt.TINGKAT_MEDIUM),    # batas Medium tepat
    (4.99, mt.TINGKAT_MEDIUM),   # tepat di bawah batas High
    (5.0, mt.TINGKAT_HIGH),      # batas High tepat
    (223.41, mt.TINGKAT_HIGH),   # nilai tertinggi yang benar-benar ada di data
    (0.0, mt.TINGKAT_LOW),
    (None, None),
])
def test_batas_final_monitoring_priority(er, harapan):
    assert mt.klasifikasi_monitoring(er) == harapan


@pytest.mark.parametrize("sd, n, harapan", [
    (1.0, 3, mt.STABIL_HIGH),      # batas High tepat
    (1.0001, 3, mt.STABIL_MEDIUM), # tepat di atasnya
    (3.0, 3, mt.STABIL_MEDIUM),    # batas Medium tepat
    (3.0001, 3, mt.STABIL_LOW),    # tepat di atasnya
    (0.0, 3, mt.STABIL_HIGH),      # ER benar-benar rata
    (0.0, 2, None),                # periode 2 -> NULL, bukan High
    (0.5, 2, None),
    (0.5, 3, mt.STABIL_HIGH),      # periode 3 -> baru boleh dinilai
    (None, 3, None),
])
def test_batas_final_performance_stability(sd, n, harapan):
    assert mt.klasifikasi_stability(sd, n) == harapan


@pytest.mark.needs_db
def test_stability_contoh_validasi_stabil(conn):
    """ER 4, 5, 3, 4, 4 persen -> sekitar 0,71 pp -> High.

    Dihitung dengan `stddev_samp` yang SAMA dengan produksi, atas nilai yang
    sudah dalam poin persen.
    """
    with conn.cursor() as cur:
        cur.execute("""SELECT round(stddev_samp(v)::numeric, 4)
                         FROM (VALUES (4.0),(5.0),(3.0),(4.0),(4.0)) t(v)""")
        sd = float(cur.fetchone()[0])
    assert sd == pytest.approx(0.71, abs=0.01)
    assert mt.klasifikasi_stability(sd, 5) == mt.STABIL_HIGH


@pytest.mark.needs_db
def test_stability_contoh_validasi_volatil(conn):
    """ER 1, 8, 2, 10, 1 persen -> volatil -> Low.

    ANGKA YANG DIPAKAI 4,2778 pp, BUKAN 3,91 pp.
    Contoh validasi menyebut "sekitar 3,91", tetapi rata-rata deret ini 4,4
    dan jumlah kuadrat simpangannya 73,2, sehingga:

        stddev_samp (n-1 = 4) = sqrt(73,2 / 4) = 4,2778   <- yang dipakai
        stddev_pop  (n   = 5) = sqrt(73,2 / 5) = 3,8262

    3,91 tidak sama dengan keduanya. Yang menentukan pilihan fungsinya adalah
    contoh PERTAMA: 4, 5, 3, 4, 4 menghasilkan 0,7071 dengan `stddev_samp` dan
    0,6325 dengan `stddev_pop`, dan angka acuan "sekitar 0,71" cocok persis
    dengan yang pertama. Jadi `stddev_samp` yang benar.

    Klasifikasinya tetap Low pada angka mana pun di antara ketiganya -- semua
    di atas 3 pp -- jadi maksud contoh validasinya tetap terpenuhi.
    """
    with conn.cursor() as cur:
        cur.execute("""SELECT round(stddev_samp(v)::numeric, 4)
                         FROM (VALUES (1.0),(8.0),(2.0),(10.0),(1.0)) t(v)""")
        sd = float(cur.fetchone()[0])
    assert sd == pytest.approx(4.2778, abs=0.001)
    assert mt.klasifikasi_stability(sd, 5) == mt.STABIL_LOW
    # Berlaku juga untuk angka yang disebut contoh dan untuk stddev populasi.
    assert mt.klasifikasi_stability(3.91, 5) == mt.STABIL_LOW
    assert mt.klasifikasi_stability(3.8262, 5) == mt.STABIL_LOW


def test_stability_er_rendah_tidak_berarti_tidak_stabil():
    """Diminta eksplisit: Stability mengukur naik-turunnya ER, bukan tingginya.

    ER 0,1% yang rata sempurna adalah High Stability; ER 20% yang berayun
    adalah Low. Membalik keduanya berarti metrik ini mengukur hal lain.
    """
    assert mt.klasifikasi_stability(0.02, 5) == mt.STABIL_HIGH
    assert mt.klasifikasi_stability(9.0, 5) == mt.STABIL_LOW


@pytest.mark.needs_db
def test_db_monitoring_er_berasal_dari_kol_directory(conn):
    """Sumber Monitoring Priority adalah ER ROSTER, bukan ER feature.

    Regresi untuk perpindahan sumber di migration 041: kalau seseorang
    mengembalikannya ke `feature.*_engagement_analysis`, angka di kartu akan
    berhenti cocok dengan `kol_directory` dan test ini gagal.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card c
            JOIN public.kol_social_account ksa
              ON ksa.social_account_id = c.social_account_id
            JOIN public.kol_directory kd ON kd.id = ksa.kol_id
             WHERE c.monitoring_er_pct IS DISTINCT FROM kd.engagement_rate""")
        assert cur.fetchone()[0] == 0


@pytest.mark.needs_db
def test_db_audience_quality_konsisten_dengan_feature(conn):
    """Tier di kartu harus cocok dengan skor di feature -- skornya tidak
    pernah dihitung ulang di L2."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT c.audience_quality_score, c.audience_quality_tier
              FROM l2_gold.kol_profile_card c
             WHERE c.audience_quality_score IS NOT NULL""")
        for skor, tier in cur.fetchall():
            assert tier == mt.klasifikasi_audience_quality(float(skor))
