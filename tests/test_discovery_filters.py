"""Test filter Discovery migration 039: Save Rate, Viral Frequency, Content
Topic, Content Format, Audience Quality, Audience Interest/Location,
Performance Stability, dan Rising Creator.

Pola yang sama dengan test 037/038: ekspresi SQL dijalankan APA ADANYA dengan
`post` diganti klausa VALUES, di sesi read-only. Aturan Python (klasifikasi
topik, tingkat geo, ambang) diuji langsung.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestration"))

import metrics_thresholds as mt  # noqa: E402
from audience_inference import tingkat_geo, topik_konten  # noqa: E402
from kol_orchestration.assets.feature_engagement import (  # noqa: E402
    _FORMAT_NORM, _SAVE_D, _SAVE_N, _SAVE_RATE,
)


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


def _post_values(baris: list[dict]) -> str:
    def sel(v, tipe):
        if v is None:
            return "NULL::" + tipe
        if tipe == "text":
            return "'" + str(v).replace("'", "''") + "'::text"
        return f"{v}::{tipe}"
    potongan = []
    for i, b in enumerate(baris):
        vals = [sel(b.get("likes", 10), "bigint"), sel(b.get("comments", 5), "bigint"),
                sel(b.get("shares", 0), "bigint"), sel(b.get("saved"), "bigint"),
                sel(b.get("views"), "bigint"), sel(b.get("media_type"), "text"),
                sel(b.get("lolos", True), "boolean")]
        if i:
            vals = ["NULL" if v.startswith("NULL") else v.split("::")[0] for v in vals]
        potongan.append("(" + ", ".join(vals) + ")")
    return ("(VALUES " + ", ".join(potongan) +
            ") AS post(likes, comments, shares, saved, views, media_type, lolos)")


def hitung_save(conn, baris):
    sql = f"SELECT {_SAVE_RATE} AS save_rate, {_SAVE_N} AS n, {_SAVE_D} AS d FROM {_post_values(baris)}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return dict(zip(("save_rate", "n", "d"), cur.fetchone()))


# ===========================================================================
# SAVE RATE
# ===========================================================================

def test_save_rate_contoh(conn):
    """saves 5, engagement 100 -> 5%. Penyebutnya like+comment+share."""
    h = hitung_save(conn, [{"likes": 99, "comments": 0, "shares": 1, "saved": 5}])
    assert h["d"] == 100
    assert float(h["save_rate"]) == pytest.approx(5.0)


def test_save_rate_saves_tidak_masuk_penyebut(conn):
    """Penyebutnya SAMA dengan Share Rate. Kalau saves ikut, 5/105 = 4,76%."""
    h = hitung_save(conn, [{"likes": 99, "comments": 0, "shares": 1, "saved": 5}])
    assert float(h["save_rate"]) != pytest.approx(4.7619, abs=1e-3)


def test_save_rate_nol_bukan_null(conn):
    h = hitung_save(conn, [{"likes": 100, "comments": 0, "shares": 0, "saved": 0}])
    assert float(h["save_rate"]) == 0.0


def test_save_rate_null_kalau_platform_tidak_melaporkan(conn):
    """Instagram publik tidak melaporkan saves -- NULL, bukan 0%."""
    h = hitung_save(conn, [{"saved": None} for _ in range(5)])
    assert h["d"] is None and h["save_rate"] is None


def test_save_rate_penyebut_nol_null(conn):
    h = hitung_save(conn, [{"likes": 0, "comments": 0, "shares": 0, "saved": 3}])
    assert h["d"] == 0 and h["save_rate"] is None


def test_save_rate_post_tanpa_saves_tidak_menyumbang_penyebut(conn):
    h = hitung_save(conn, [{"likes": 99, "comments": 0, "shares": 1, "saved": 5},
                           {"likes": 900, "comments": 0, "shares": 0, "saved": None}])
    assert h["d"] == 100


def test_save_rate_beberapa_post_diagregasi(conn):
    h = hitung_save(conn, [{"likes": 99, "comments": 0, "shares": 1, "saved": 5},
                           {"likes": 199, "comments": 0, "shares": 1, "saved": 5}])
    assert h["n"] == 10 and h["d"] == 300


# ===========================================================================
# CONTENT FORMAT
# ===========================================================================

@pytest.mark.parametrize("mentah, harapan", [
    ("CAROUSEL", "Carousel"),
    ("carousel_container", "Carousel"),
    ("Carousel_Container", "Carousel"),   # casing tidak bikin kategori ketiga
    ("  CAROUSEL  ", "Carousel"),
    ("VIDEO", "Video"),
    ("clips", "Video"),
    ("feed", "Image"),
    ("unknown", None),
    (None, None),
])
def test_normalisasi_format(conn, mentah, harapan):
    nilai = "NULL::text" if mentah is None else "'" + mentah + "'::text"
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_FORMAT_NORM} FROM (SELECT {nilai} AS media_type) t")
        assert cur.fetchone()[0] == harapan


def test_format_carousel_tidak_kembar(conn):
    """Inti requirement: dua ejaan yang sama harus jadi SATU kategori."""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT count(DISTINCT {_FORMAT_NORM})
              FROM (VALUES ('CAROUSEL'), ('carousel_container'), ('CAROUSEL_CONTAINER'))
                   AS t(media_type)""")
        assert cur.fetchone()[0] == 1


# ===========================================================================
# CONTENT TOPIC
# ===========================================================================

def test_topik_dari_caption():
    assert topik_konten("Resep ayam sambal pedas", None) == "food"


def test_topik_dari_hashtag():
    assert topik_konten("", ["#skincare", "#glowing"]) == "beauty"


def test_topik_tanpa_bahan_null():
    assert topik_konten(None, None) is None
    assert topik_konten("", []) is None


def test_topik_tidak_menebak_dari_username():
    """Requirement eksplisit: interest/topik tidak boleh ditebak dari nama akun.

    `topik_konten` hanya menerima caption dan hashtag -- tidak ada jalur untuk
    username masuk sama sekali, dan test ini yang menahan penambahannya.
    """
    import inspect
    params = list(inspect.signature(topik_konten).parameters)
    assert params == ["caption", "hashtags"], \
        "topik_konten menerima argumen selain caption/hashtag"


def test_topik_deterministik():
    """Teks yang sama harus selalu memberi topik yang sama."""
    teks = "workout gym fitness harian"
    assert topik_konten(teks, None) == topik_konten(teks, None)


# ===========================================================================
# AUDIENCE LOCATION -- hierarki tidak boleh tercampur
# ===========================================================================

@pytest.mark.parametrize("kunci, harapan", [
    ("Bandung", "city"),
    ("Surabaya", "city"),
    ("Denpasar", "city"),
    ("Jawa Barat", "province"),
    ("Lampung", "province"),
    ("Bali", "province"),      # provinsi, meski ada di leksikon kota
    ("Aceh", "province"),
    ("Jawa", "island"),
    ("Sumatera", "island"),
    ("Madura", "island"),
    (None, "city"),
])
def test_tingkat_geo(kunci, harapan):
    assert tingkat_geo(kunci) == harapan


def test_geo_provinsi_tidak_lagi_dilabeli_kota():
    """Regresi untuk bug nyata: "Bali" dan "Lampung" dulu ditulis geo_level
    'city' dan berdiri sejajar dengan "Bandung"."""
    assert tingkat_geo("Bali") != tingkat_geo("Bandung")
    assert tingkat_geo("Lampung") != tingkat_geo("Surabaya")


# ===========================================================================
# AUDIENCE QUALITY
# ===========================================================================

@pytest.mark.parametrize("skor, harapan", [
    (94.0, mt.TINGKAT_HIGH), (75.0, mt.TINGKAT_HIGH), (74.99, mt.TINGKAT_MEDIUM),
    (50.0, mt.TINGKAT_MEDIUM), (49.99, mt.TINGKAT_LOW), (0.0, mt.TINGKAT_LOW),
    (None, None),
])
def test_audience_quality(skor, harapan):
    assert mt.klasifikasi_audience_quality(skor) == harapan


@pytest.mark.needs_db
@pytest.mark.parametrize("skor", [94.0, 75.0, 74.99, 50.0, 49.99, None])
def test_paritas_audience_quality(conn, skor):
    nilai = "NULL" if skor is None else str(skor)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {mt.sql_audience_quality_tier('t.s')} "
                    f"FROM (SELECT {nilai}::numeric AS s) t")
        assert cur.fetchone()[0] == mt.klasifikasi_audience_quality(skor)


# ===========================================================================
# PERFORMANCE STABILITY
# ===========================================================================

@pytest.mark.parametrize("sd, n, harapan", [
    (0.5, 3, mt.STABIL_HIGH),
    (1.0, 3, mt.STABIL_HIGH),          # batas atas High
    (1.01, 3, mt.STABIL_MEDIUM),
    (3.0, 5, mt.STABIL_MEDIUM),        # batas atas Medium
    (3.01, 5, mt.STABIL_LOW),
    (12.0, 10, mt.STABIL_LOW),
    (0.1, 2, None),                    # < 3 periode -> NULL, bukan High
    (0.1, 0, None),
    (None, 5, None),
    (0.5, None, None),
])
def test_performance_stability(sd, n, harapan):
    assert mt.klasifikasi_stability(sd, n) == harapan


def test_stability_dua_periode_tidak_pernah_high():
    """Dua titik selalu tampak stabil; melabelinya High menjual kekurangan
    data sebagai konsistensi."""
    assert mt.klasifikasi_stability(0.0, 2) is None


@pytest.mark.needs_db
@pytest.mark.parametrize("sd, n", [(0.5, 3), (1.0, 3), (1.01, 3), (3.0, 5),
                                   (3.01, 5), (0.1, 2), (None, 5), (0.5, None)])
def test_paritas_stability(conn, sd, n):
    a = "NULL" if sd is None else str(sd)
    b = "NULL" if n is None else str(n)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {mt.sql_stability('t.sd', 't.n')} "
                    f"FROM (SELECT {a}::numeric AS sd, {b}::int AS n) t")
        assert cur.fetchone()[0] == mt.klasifikasi_stability(sd, n)


@pytest.mark.needs_db
def test_db_er_stddev_bersatuan_poin_persen(conn):
    """Jebakan satuan: `er_followers_daily` FRAKSI, ambang stabilitas PERSEN.

    Kalau konversi x100 hilang, seluruh simpangan baku akan < 0,01 dan semua
    akun tercatat High Stability. Test ini membandingkan kolom tersimpan
    dengan hitungan ulang dari sumbernya.
    """
    with conn.cursor() as cur:
        cur.execute("""
            WITH ulang AS (
              SELECT social_account_id, platform,
                     count(er_followers_daily)::int AS n,
                     round(stddev_samp(er_followers_daily * 100)::numeric, 4) AS sd
                FROM l2_gold.kol_metric_daily GROUP BY 1, 2)
            SELECT count(*) FROM l2_gold.kol_profile_card c
            JOIN ulang u ON u.social_account_id = c.social_account_id
                        AND u.platform = c.platform
             WHERE c.er_stddev_pp IS DISTINCT FROM u.sd
                OR c.er_periods   IS DISTINCT FROM u.n""")
        assert cur.fetchone()[0] == 0


# ===========================================================================
# RISING CREATOR
# ===========================================================================

@pytest.mark.parametrize("growth, harapan", [
    (30.0, True), (10.0, True), (5.0, True),   # batas: >= 5%
    (4.99, False), (0.0, False), (-3.0, False),
    (None, None),
])
def test_rising_creator(growth, harapan):
    assert mt.rising_creator(growth) is harapan


def test_rising_tidak_memakai_ambang_lama_5_5():
    """Requirement eksplisit: ambang 5,5% dari prototype tidak dipakai lagi."""
    assert mt.RISING_MIN == 5.0
    assert mt.rising_creator(5.2) is True


def test_rising_null_bukan_false():
    """False = diukur dan tidak naik cukup. None = Growth belum terukur."""
    assert mt.rising_creator(None) is None


def test_rising_konsisten_dengan_growth_class():
    """Rising memakai batas Medium Growth yang sama, bukan angka sendiri."""
    for g in (5.0, 7.5, 10.0, 30.0):
        assert mt.rising_creator(g) is True
        assert mt.klasifikasi_growth(g) in (mt.GROWTH_MEDIUM, mt.GROWTH_HIGH)
    for g in (4.99, 0.0, -1.0):
        assert mt.rising_creator(g) is False
        assert mt.klasifikasi_growth(g) in (mt.GROWTH_LOW, mt.GROWTH_NEGATIVE)


# ===========================================================================
# DATA NYATA
# ===========================================================================

@pytest.mark.needs_db
def test_db_viral_threshold_tepat_tiga_kali_median(conn):
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT count(*) FROM feature.tt_engagement_analysis
             WHERE viral_threshold_views IS NOT NULL AND median_views IS NOT NULL
               AND abs(viral_threshold_views - median_views * {mt.VIRAL_MULTIPLIER}) > 0.01""")
        assert cur.fetchone()[0] == 0


@pytest.mark.needs_db
def test_db_viral_frequency_dalam_rentang(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card
             WHERE viral_frequency IS NOT NULL
               AND (viral_frequency < 0 OR viral_frequency > 100)""")
        assert cur.fetchone()[0] == 0


@pytest.mark.needs_db
def test_db_format_tidak_ada_kategori_kembar(conn):
    """Setelah normalisasi hanya boleh ada Video/Carousel/Image."""
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT format_dominant FROM l2_gold.kol_profile_card
                        WHERE format_dominant IS NOT NULL ORDER BY 1""")
        assert [r[0] for r in cur.fetchall()] == ["Carousel", "Image", "Video"]


@pytest.mark.needs_db
def test_db_geo_level_terpisah_bersih(conn):
    """Tidak boleh ada nama provinsi yang masih berlabel city."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT geo_level, geo_key FROM l2_gold.audience_geo_daily")
        for level, kunci in cur.fetchall():
            if level == "country":
                continue
            assert level == tingkat_geo(kunci), f"{kunci} berlabel {level}"


@pytest.mark.needs_db
def test_db_sumber_turunan_selalu_ditandai(conn):
    """Topik/minat yang bukan hasil observasi WAJIB punya penanda asal."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card
             WHERE (content_topic IS NOT NULL AND content_topic_source IS NULL)
                OR (audience_interest_top IS NOT NULL
                    AND audience_interest_source IS NULL)""")
        assert cur.fetchone()[0] == 0
        cur.execute("""
            SELECT DISTINCT content_topic_source FROM l2_gold.kol_profile_card
             WHERE content_topic_source IS NOT NULL ORDER BY 1""")
        assert [r[0] for r in cur.fetchall()] == ["content", "creator_category_fallback"]


@pytest.mark.needs_db
def test_db_l2_membawa_apa_adanya_dari_feature_039(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card c
            JOIN feature.tt_engagement_analysis f
              ON f.social_account_id = c.social_account_id
             WHERE c.platform = 'tiktok'
               AND (c.save_rate       IS DISTINCT FROM f.save_rate
                 OR c.viral_frequency IS DISTINCT FROM f.viral_frequency
                 OR c.content_topic   IS DISTINCT FROM f.content_topic
                 OR c.format_dominant IS DISTINCT FROM f.format_dominant)""")
        assert cur.fetchone()[0] == 0
