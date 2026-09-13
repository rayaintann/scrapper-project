"""What Matters Most — 7 kriteria, normalisasi, dan aturan NULL.

Yang dijaga test ini, berurutan sesuai daftar wajib:

     1  ketujuh kriteria punya mapping jelas
     2  normalisasi menghasilkan 0..100
     3  NULL tidak berubah jadi 0
     4  Strong Engagement memakai ER
     5  Audience Quality memakai source yang benar
     6  Consistent Performance tidak memakai k.cons mock
     7  High Reach tidak memakai estimated_reach
     8  High Reach memakai views sebagai proxy
     9  Community berlabel PROXY
    10  Content Quality tidak menghasilkan mock score
    11  Brand Safety tidak memakai fake sentiment
    12  What Matters Score = rata-rata kriteria terpilih
    13  kriteria NULL keluar dari penyebut
    14  semua kriteria NULL -> final NULL
    15  ranking DESC NULLS LAST
    16  tidak ada kolom skor baru di l2_gold.kol_profile_card
"""

from pathlib import Path

import pytest

import what_matters_scoring as w

AKAR = Path(__file__).resolve().parents[1]

#: populasi contoh untuk metric berbasis persentil
POP_ER = [0.5, 1.0, 2.0, 4.0, 8.0, 223.41]
POP_VIEWS = [679, 10_000, 344_739, 638_034, 136_309_208]


# ===========================================================================
# 1. MAPPING KETUJUH KRITERIA
# ===========================================================================

def test_tepat_tujuh_kriteria():
    assert len(w.KRITERIA) == 7
    assert len(w.URUTAN_KRITERIA) == 7
    assert set(w.URUTAN_KRITERIA) == set(w.KRITERIA)


@pytest.mark.parametrize("kunci,nama", [
    ("engagement", "Strong Engagement"),
    ("audience_quality", "High Audience Quality"),
    ("consistency", "Consistent Performance"),
    ("community", "Strong Company/Community"),
    ("reach", "High Reach"),
    ("content_quality", "Content Quality"),
    ("brand_safety", "Brand Safety"),
])
def test_mapping_kunci_ke_nama(kunci, nama):
    assert w.KRITERIA[kunci]["nama"] == nama


def test_setiap_kriteria_punya_sifat_dan_catatan():
    for kunci, isi in w.KRITERIA.items():
        assert isi["sifat"] in (w.REAL, w.PROXY, w.TIDAK_TERSEDIA), kunci
        assert isi["catatan"], kunci
        assert isi["skor"], kunci


def test_parse_matters_dari_query_param():
    assert w.parse_matters("engagement,consistency,brand_safety") == [
        "engagement", "consistency", "brand_safety"]


def test_parse_matters_mengabaikan_kunci_asing_dan_duplikat():
    assert w.parse_matters("engagement, engagement ,ngawur") == ["engagement"]
    assert w.parse_matters("") == []
    assert w.parse_matters(None) == []


# ===========================================================================
# 2. NORMALISASI 0..100
# ===========================================================================

def test_klem_membatasi_ke_nol_seratus():
    assert w.klem(-5) == 0.0
    assert w.klem(150) == 100.0
    assert w.klem(42) == 42.0


def test_persentil_selalu_dalam_nol_seratus():
    for nilai in [-100, 0, 0.5, 8.0, 223.41, 10_000]:
        skor = w.persentil_ke_skor(nilai, POP_ER)
        assert 0.0 <= skor <= 100.0, (nilai, skor)


def test_persentil_terbesar_dapat_seratus_terkecil_dapat_nol():
    assert w.persentil_ke_skor(223.41, POP_ER) == 100.0
    assert w.persentil_ke_skor(0.5, POP_ER) == 0.0


def test_outlier_ekstrem_tidak_menghancurkan_skala():
    """ER 223% cuma jadi peringkat teratas; ia tidak menekan yang lain ke nol.

    Inilah alasan persentil dipilih di atas normalisasi linear terhadap max.
    """
    tengah = w.persentil_ke_skor(4.0, POP_ER)
    assert 40.0 <= tengah <= 80.0
    # linear terhadap max akan memberi 4/223.41*100 = 1,79
    assert tengah > 10.0


def test_semua_skor_kriteria_dalam_rentang():
    skor = [
        w.engagement_score(4.0, POP_ER),
        w.audience_quality_score(94, 100),
        w.consistency_score("High Stability", "High"),
        w.community_strength_score(94, 4.0, POP_ER),
        w.reach_proxy_score(344_739, POP_VIEWS),
    ]
    for s in skor:
        assert s is not None and 0.0 <= s <= 100.0, s


# ===========================================================================
# 3. NULL TIDAK BERUBAH JADI NOL
# ===========================================================================

def test_null_tetap_null_bukan_nol():
    assert w.klem(None) is None
    assert w.persentil_ke_skor(None, POP_ER) is None
    assert w.engagement_score(None, POP_ER) is None
    assert w.audience_quality_score(None, None) is None
    assert w.consistency_score(None, None) is None
    assert w.community_strength_score(None, None, POP_ER) is None
    assert w.reach_proxy_score(None, POP_VIEWS) is None


def test_nilai_nol_berbeda_dari_null():
    """ER 0 adalah pengukuran; ER NULL adalah ketiadaan pengukuran."""
    assert w.engagement_score(0.0, POP_ER) is not None
    assert w.engagement_score(None, POP_ER) is None


def test_populasi_kosong_menghasilkan_null_bukan_nol():
    assert w.persentil_ke_skor(5.0, []) is None
    assert w.persentil_ke_skor(5.0, [None, None]) is None


# ===========================================================================
# 4. STRONG ENGAGEMENT  <- ER
# ===========================================================================

def test_engagement_memakai_kol_directory_engagement_rate():
    assert w.KRITERIA["engagement"]["sumber"] == (
        "public.kol_directory.engagement_rate",)
    assert w.KRITERIA["engagement"]["sifat"] == w.REAL


def test_engagement_lebih_tinggi_skornya_lebih_tinggi():
    assert w.engagement_score(8.0, POP_ER) > w.engagement_score(1.0, POP_ER)


# ===========================================================================
# 5. AUDIENCE QUALITY  <- source yang benar
# ===========================================================================

def test_audience_quality_sumbernya_dua_kolom_kartu_l2():
    assert w.KRITERIA["audience_quality"]["sumber"] == (
        "l2_gold.kol_profile_card.audience_quality_score",
        "l2_gold.kol_profile_card.authenticity_score")


def test_audience_quality_rata_rata_kalau_keduanya_ada():
    assert w.audience_quality_score(80, 60) == 70.0


def test_audience_quality_pakai_yang_tersedia_kalau_satu_null():
    assert w.audience_quality_score(80, None) == 80.0
    assert w.audience_quality_score(None, 60) == 60.0


def test_audience_quality_keduanya_null_jadi_null():
    assert w.audience_quality_score(None, None) is None


def test_audience_quality_tidak_dinormalisasi_ulang():
    """Keduanya sudah 0..100 di sumbernya; menormalisasi ulang akan
    menghilangkan artinya."""
    assert w.audience_quality_score(94, 94) == 94.0


# ===========================================================================
# 6. CONSISTENT PERFORMANCE  --  bukan k.cons mock
# ===========================================================================

def test_consistency_tidak_memakai_kcons_mock():
    sumber = " ".join(w.KRITERIA["consistency"]["sumber"])
    assert "k.cons" not in sumber
    assert "performance_stability" in sumber
    assert "post_frequency_reliability" in sumber
    assert "hash" in w.KRITERIA["consistency"]["catatan"].lower()


def test_consistency_lebih_stabil_skornya_lebih_tinggi():
    tinggi = w.consistency_score("High Stability", "High")
    sedang = w.consistency_score("Medium Stability", "Medium")
    rendah = w.consistency_score("Low Stability", "Low")
    assert tinggi == 100.0
    assert rendah == 0.0
    assert rendah < sedang < tinggi


def test_consistency_arah_inverse_sudah_benar_lewat_label():
    """`er_stddev_pp` kecil = stabil. Arah itu SUDAH dibalik oleh
    metrics_thresholds.klasifikasi_stability, jadi modul ini memakai
    labelnya, bukan angka mentahnya -- supaya tidak ada definisi kedua."""
    import metrics_thresholds as mt
    # SD kecil -> High Stability -> skor tertinggi
    label_sd_kecil = mt.klasifikasi_stability(0.023, 5)
    label_sd_besar = mt.klasifikasi_stability(4.0, 5)
    assert w.consistency_score(label_sd_kecil, None) > \
           w.consistency_score(label_sd_besar, None)


def test_consistency_label_ordinal_konsisten_dengan_metrics_thresholds():
    import metrics_thresholds as mt
    assert set(w.TINGKAT_STABILITAS) == set(mt.NILAI_STABILITAS)


def test_consistency_satu_label_null_tetap_dihitung():
    assert w.consistency_score("High Stability", None) == 100.0
    assert w.consistency_score(None, "Low") == 0.0


def test_consistency_label_tak_dikenal_jadi_null():
    assert w.consistency_score("Ngawur", None) is None


# ===========================================================================
# 7-8. HIGH REACH  --  views proxy, bukan estimated_reach
# ===========================================================================

def test_reach_tidak_memakai_estimated_reach():
    sumber = " ".join(w.KRITERIA["reach"]["sumber"])
    assert "estimated_reach" not in sumber
    assert "kol_roster_import" not in sumber


def test_reach_memakai_median_views_sebagai_proxy():
    assert w.KRITERIA["reach"]["sumber"] == (
        "l2_gold.kol_profile_card.median_views",)
    assert w.KRITERIA["reach"]["sifat"] == w.PROXY


def test_reach_ditandai_berbasis_views_bukan_insights():
    catatan = w.KRITERIA["reach"]["catatan"].lower()
    assert "views" in catatan
    assert "estimated_reach" in catatan


def test_reach_views_null_jadi_null():
    assert w.reach_proxy_score(None, POP_VIEWS) is None


def test_reach_views_lebih_besar_skornya_lebih_tinggi():
    assert w.reach_proxy_score(136_309_208, POP_VIEWS) > \
           w.reach_proxy_score(679, POP_VIEWS)


def test_docstring_modul_menyebut_estimated_reach_tidak_dipakai():
    doc = w.reach_proxy_score.__doc__
    assert "estimated_reach" in doc
    assert "Insights" in doc


# ===========================================================================
# 9. COMMUNITY  --  PROXY, dan tidak double-count authenticity
# ===========================================================================

def test_community_ditandai_proxy():
    assert w.KRITERIA["community"]["sifat"] == w.PROXY
    assert "PROXY" in w.KRITERIA["community"]["catatan"]


def test_community_tidak_mengklaim_ukuran_komunitas():
    catatan = w.KRITERIA["community"]["catatan"].lower()
    assert "bukan ukuran komunitas" in catatan


def test_community_tidak_double_count_authenticity():
    """`audience_quality_score` = rata-rata follower_quality dan
    authenticity (audience_inference.py:1102). Memakai keduanya lagi
    sebagai komponen terpisah akan memberi authenticity 50% bobot efektif."""
    sumber = " ".join(w.KRITERIA["community"]["sumber"])
    assert "authenticity_score" not in sumber
    assert "audience_quality_score" in sumber


def test_community_bobot_totalnya_satu():
    assert w.BOBOT_COMMUNITY_KUALITAS + w.BOBOT_COMMUNITY_ER == 1.0


def test_community_menggabungkan_kualitas_dan_engagement():
    tinggi = w.community_strength_score(90, 223.41, POP_ER)
    rendah = w.community_strength_score(50, 0.5, POP_ER)
    assert tinggi > rendah


def test_community_satu_komponen_null_tetap_menghasilkan_skor():
    assert w.community_strength_score(80, None, POP_ER) == 80.0
    assert w.community_strength_score(None, 223.41, POP_ER) == 100.0


def test_community_keduanya_null_jadi_null():
    assert w.community_strength_score(None, None, POP_ER) is None


# ===========================================================================
# 10. CONTENT QUALITY  --  tidak boleh menghasilkan mock score
# ===========================================================================

def test_content_quality_selalu_null():
    assert w.content_quality_score() is None
    assert w.content_quality_score("Carousel", "food", 5.0) is None


def test_content_quality_ditandai_tidak_tersedia():
    assert w.KRITERIA["content_quality"]["sifat"] == w.TIDAK_TERSEDIA
    assert w.KRITERIA["content_quality"]["sumber"] == ()


def test_content_quality_tidak_memberi_skor_karena_field_terisi():
    """format_dominant dan content_topic tidak punya urutan kualitas."""
    for format_dominan in ("Carousel", "Video", "Image"):
        assert w.content_quality_score(format_dominan) is None


# ===========================================================================
# 11. BRAND SAFETY  --  tidak memakai sentiment palsu
# ===========================================================================

def test_brand_safety_selalu_null():
    assert w.brand_safety_score() is None
    assert w.brand_safety_score(100, "food", 90) is None


def test_brand_safety_ditandai_tidak_tersedia():
    assert w.KRITERIA["brand_safety"]["sifat"] == w.TIDAK_TERSEDIA
    assert w.KRITERIA["brand_safety"]["sumber"] == ()


def test_brand_safety_tidak_membuat_sentiment_baru():
    sumber_modul = (AKAR / "what_matters_scoring.py").read_text(encoding="utf-8")
    kode = "\n".join(b for b in sumber_modul.splitlines()
                     if not b.lstrip().startswith("#"))
    for dilarang in ("def sentiment", "def toxicity", "SENTIMENT_", "TOXICITY_"):
        assert dilarang not in kode


def test_dua_kriteria_tidak_tersedia_tetap_terdaftar():
    """Supaya UI bisa menampilkannya nonaktif dengan alasannya, bukan
    menyembunyikannya."""
    tidak_aktif = [k for k in w.URUTAN_KRITERIA
                   if w.KRITERIA[k]["sifat"] == w.TIDAK_TERSEDIA]
    assert tidak_aktif == ["content_quality", "brand_safety"]
    assert len(w.KRITERIA_AKTIF) == 5


# ===========================================================================
# 12-14. WHAT MATTERS SCORE
# ===========================================================================

def test_what_matters_rata_rata_kriteria_terpilih():
    skor = {"engagement": 85.0, "consistency": 72.0, "brand_safety": 90.0}
    hasil = w.what_matters_score(
        skor, ["engagement", "consistency", "brand_safety"])
    assert round(hasil, 2) == 82.33


def test_what_matters_hanya_menghitung_yang_dipilih():
    skor = {"engagement": 100.0, "consistency": 0.0, "reach": 50.0}
    assert w.what_matters_score(skor, ["engagement"]) == 100.0
    assert w.what_matters_score(skor, ["engagement", "consistency"]) == 50.0


def test_null_dikeluarkan_dari_penyebut():
    """(80 + 60) / 2 = 70, BUKAN (80 + 60 + 0) / 3 = 46,67."""
    skor = {"engagement": 80.0, "consistency": 60.0, "reach": None}
    hasil = w.what_matters_score(skor, ["engagement", "consistency", "reach"])
    assert hasil == 70.0


def test_null_tidak_menghukum_kol():
    """KOL dengan satu kriteria NULL tidak boleh kalah dari KOL yang sama
    nilainya tapi datanya lengkap-lengkap rendah."""
    lengkap_rendah = w.what_matters_score(
        {"engagement": 80.0, "reach": 10.0}, ["engagement", "reach"])
    sebagian_tinggi = w.what_matters_score(
        {"engagement": 80.0, "reach": None}, ["engagement", "reach"])
    assert sebagian_tinggi > lengkap_rendah


def test_semua_kriteria_null_hasilnya_null():
    skor = {"engagement": None, "consistency": None}
    assert w.what_matters_score(skor, ["engagement", "consistency"]) is None


def test_tidak_memilih_kriteria_hasilnya_null():
    assert w.what_matters_score({"engagement": 90.0}, []) is None


def test_kriteria_tidak_tersedia_selalu_keluar_dari_penyebut():
    """content_quality dan brand_safety selalu NULL, jadi memilih keduanya
    tidak boleh menurunkan skor."""
    skor = {"engagement": 90.0, "content_quality": None, "brand_safety": None}
    hasil = w.what_matters_score(
        skor, ["engagement", "content_quality", "brand_safety"])
    assert hasil == 90.0


# ===========================================================================
# 15. RANKING  DESC NULLS LAST
# ===========================================================================

def test_order_by_desc_nulls_last():
    assert "DESC" in w.SQL_ORDER_BY
    assert "NULLS LAST" in w.SQL_ORDER_BY


def test_urutan_ranking_null_di_bawah():
    baris = [("a", 82.3), ("b", None), ("c", 91.0), ("d", 40.0)]
    urut = sorted(baris, key=lambda r: (r[1] is None, -(r[1] or 0)))
    assert [r[0] for r in urut] == ["c", "a", "d", "b"]


# ===========================================================================
# 16. TIDAK ADA KOLOM SKOR BARU  (struktur + DB)
# ===========================================================================

NAMA_SKOR_TERLARANG = (
    "what_matters_score", "community_strength_score", "content_quality_score",
    "brand_safety_score", "reach_proxy_score", "engagement_score",
    "consistency_score",
)


def test_tidak_ada_migration_yang_menambah_kolom_skor():
    for sql_file in (AKAR / "migrations").glob("*.sql"):
        isi = sql_file.read_text(encoding="utf-8")
        ddl = "\n".join(b for b in isi.splitlines()
                        if not b.lstrip().startswith("--"))
        if "kol_profile_card" not in ddl:
            continue
        for nama in NAMA_SKOR_TERLARANG:
            assert f"ADD COLUMN IF NOT EXISTS {nama}" not in ddl, sql_file.name
            assert f"ADD COLUMN {nama}" not in ddl, sql_file.name


@pytest.mark.needs_db
def test_db_tidak_ada_kolom_skor_di_kartu_l2(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
               AND column_name = ANY(%s)""", (list(NAMA_SKOR_TERLARANG),))
        ada = [r[0] for r in cur.fetchall()]
    assert not ada, f"kolom skor What Matters muncul di kartu L2: {ada}"


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


# ===========================================================================
# PARITAS PYTHON <-> SQL
# ===========================================================================

def test_sql_persentil_memakai_percent_rank():
    sql = w.sql_persentil("engagement_rate")
    assert "percent_rank() OVER" in sql
    assert "ORDER BY engagement_rate" in sql
    assert "IS NULL THEN NULL" in sql


def test_sql_persentil_mengecualikan_null_dari_penyebut():
    """Sepadan dengan `persentil_ke_skor`, yang membuang None dari populasi.

    Tanpa PARTITION, baris NULL ikut penyebut `percent_rank()` dan seluruh
    skor mengecil sebanding coverage: dengan ER terisi 23%, kreator ber-ER
    tertinggi mendapat 23 alih-alih 100.
    """
    sql = w.sql_persentil("engagement_rate")
    assert "PARTITION BY (engagement_rate IS NULL)" in sql


def test_sql_ordinal_sepadan_dengan_python():
    sql = w.sql_ordinal("performance_stability", w.TINGKAT_STABILITAS)
    for label in w.TINGKAT_STABILITAS:
        angka = w._ordinal_ke_skor(label, w.TINGKAT_STABILITAS)
        assert f"'{label}' THEN {angka}" in sql
    assert "ELSE NULL" in sql


def test_sql_rata_rata_memakai_nullif_pada_penyebut():
    sql = w.sql_rata_rata_tersedia("a", "b")
    assert "NULLIF(" in sql
    assert "COALESCE(a, 0)" in sql


def test_sql_what_matters_mengeluarkan_kriteria_tidak_tersedia():
    kolom = {k: k + "_col" for k in w.KRITERIA}
    sql = w.sql_what_matters(
        ["engagement", "content_quality", "brand_safety"], kolom)
    assert "engagement_col" in sql
    assert "content_quality_col" not in sql
    assert "brand_safety_col" not in sql


def test_sql_what_matters_tanpa_kriteria_valid_jadi_null():
    kolom = {k: k + "_col" for k in w.KRITERIA}
    assert w.sql_what_matters(["content_quality"], kolom) == "NULL"
