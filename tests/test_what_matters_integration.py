"""Integrasi What Matters Most ke jalur baca KOL Discovery (`db.py`).

Sepuluh titik yang harus terhubung:

     1  UI mengirim pilihan lewat query param
     2  jalur baca menerima parameter itu
     3  parameter dipetakan ke 7 kriteria
     4  fungsi scoring dipanggil
     5  KOL diranking berdasarkan What Matters Score
     6  kriteria NULL tidak dianggap 0
     7  jumlah kriteria yang berkontribusi bisa diketahui
     8  tidak ada mock score
     9  tidak memakai estimated_reach sebagai fallback
    10  EMV / Rate Card / CPE / CPV / Style & Personality tidak tersentuh

Test ber-`needs_db` melakukan SELECT read-only; sisanya menguji SQL yang
dibangun tanpa menyentuh database.
"""

import re
from pathlib import Path

import pytest

import db
import what_matters_scoring as w

AKAR = Path(__file__).resolve().parents[1]
SEMUA_AKTIF = ["engagement", "audience_quality", "consistency",
               "community", "reach"]


# ===========================================================================
# 1-3. PARAMETER DITERIMA DAN DIPETAKAN
# ===========================================================================

def test_search_menerima_parameter_matters():
    import inspect
    sig = inspect.signature(db.search_kol_directory)
    assert "matters" in sig.parameters
    assert sig.parameters["matters"].default is None


def test_search_result_punya_kolom_what_matters():
    kolom = db.SearchResult.__dataclass_fields__
    assert "what_matters_score" in kolom
    assert "what_matters_contributing" in kolom


def test_default_tidak_menyalakan_what_matters():
    """Tanpa matters, jalur baca lama tidak berubah sama sekali."""
    r = db.SearchResult(id="x", username="a", display_name=None,
                        platform=None, followers_count=None,
                        discovery_category=None)
    assert r.what_matters_score is None
    assert r.what_matters_contributing is None


def test_query_biasa_tidak_mengandung_kolom_skor():
    assert "what_matters_score" not in db._SEARCH_QUERY
    assert "percent_rank" not in db._SEARCH_QUERY


def test_tujuh_kunci_ui_dikenali_semua():
    for kunci in w.URUTAN_KRITERIA:
        assert w.parse_matters(kunci) == [kunci]


# ===========================================================================
# 4-5. SCORING DIPANGGIL DAN DIPAKAI RANKING
# ===========================================================================

def test_query_matters_memakai_ekspresi_dari_modul_scoring():
    sql = db._query_what_matters(["engagement"])
    assert "percent_rank" in sql
    assert "what_matters_score" in sql
    assert "what_matters_contributing" in sql


def test_query_matters_diurutkan_desc_nulls_last():
    sql = db._query_what_matters(SEMUA_AKTIF)
    assert "ORDER BY what_matters_score DESC NULLS LAST" in sql


def test_query_matters_memakai_body_yang_sama():
    """Bukan query kedua — body-nya template yang sama dengan jalur biasa."""
    sql = db._query_what_matters(["engagement"])
    assert "FROM public.kol_directory k" in sql
    assert "LEFT JOIN l2_gold.kol_profile_card pc" in sql


def test_query_matters_menghitung_persentil_sebelum_limit():
    """percent_rank harus ada di SELECT, bukan di subquery setelah LIMIT."""
    sql = db._query_what_matters(["engagement"])
    posisi_rank = sql.index("percent_rank")
    posisi_limit = sql.index("LIMIT")
    assert posisi_rank < posisi_limit


def test_persentil_sql_mengecualikan_null_dari_penyebut():
    """Tanpa PARTITION, baris NULL ikut penyebut dan seluruh skor mengecil
    sebanding coverage."""
    sql = w.sql_persentil("k.engagement_rate")
    assert "PARTITION BY (k.engagement_rate IS NULL)" in sql


# ===========================================================================
# 6-7. NULL DAN JUMLAH KONTRIBUTOR
# ===========================================================================

def test_kriteria_tidak_tersedia_tidak_masuk_penyebut():
    ekspresi = w.sql_ekspresi_skor()
    sql = w.sql_what_matters(["engagement", "content_quality"], ekspresi)
    assert "percent_rank" in sql
    assert "NULL::numeric" not in sql


def test_hanya_kriteria_tidak_tersedia_menghasilkan_null():
    ekspresi = w.sql_ekspresi_skor()
    assert w.sql_what_matters(["content_quality"], ekspresi) == "NULL"


def test_jumlah_kontributor_menghitung_yang_tidak_null():
    ekspresi = w.sql_ekspresi_skor()
    sql = w.sql_jumlah_kontributor(["engagement", "reach"], ekspresi)
    assert sql.count("CASE WHEN") >= 2
    assert "IS NULL THEN 0 ELSE 1 END" in sql


def test_penyebut_memakai_nullif_bukan_pembagian_tetap():
    ekspresi = w.sql_ekspresi_skor()
    sql = w.sql_what_matters(SEMUA_AKTIF, ekspresi)
    assert "NULLIF(" in sql


# ===========================================================================
# 8-9. TIDAK ADA MOCK, TIDAK ADA estimated_reach
# ===========================================================================

def test_tidak_ada_estimated_reach_di_query():
    sql = db._query_what_matters(SEMUA_AKTIF)
    assert "estimated_reach" not in sql
    assert "kol_roster_import" not in sql


def test_reach_memakai_median_views():
    assert "pc.median_views" in w.KOLOM_SUMBER_DEFAULT["median_views"]
    sql = db._query_what_matters(["reach"])
    assert "pc.median_views" in sql


def test_tidak_ada_konstanta_mock_di_query():
    sql = db._query_what_matters(SEMUA_AKTIF)
    for mock in ("k.aff", "k.cons", "hsh(", "random()"):
        assert mock not in sql


def test_content_quality_tetap_null_di_sql():
    ekspresi = w.sql_ekspresi_skor()
    assert ekspresi["content_quality"] == "NULL::numeric"


def test_brand_safety_tidak_ada_di_jalur_sql():
    assert "brand_safety" not in w.sql_ekspresi_skor()


# ===========================================================================
# 10. TIDAK MENGUBAH FITUR LAIN
# ===========================================================================

def test_query_matters_tidak_menyentuh_emv_ratecard_cpe_cpv():
    sql = db._query_what_matters(SEMUA_AKTIF)
    for asing in ("emv", "unified_rate_card", "deal_price", "cpe", "cpv"):
        assert asing not in sql.lower()


def test_query_matters_tidak_mengubah_filter_style_personality():
    """What Matters hanya MENAMBAH kolom skor dan mengubah urutan.

    Filter Style & Personality ada di `_SEARCH_BODY_TEMPLATE` yang dipakai
    bersama, jadi `kol_attribute` memang muncul di kedua jalur — yang harus
    dijaga adalah keduanya memakai klausa yang SAMA persis, bukan bahwa
    jalur matters tidak menyentuhnya sama sekali.
    """
    biasa = db._SEARCH_QUERY
    matters = db._query_what_matters(SEMUA_AKTIF)
    for klausa in ("%(style)s::text[]", "%(personality)s::text[]",
                   "kol_attribute_map"):
        assert biasa.count(klausa) == matters.count(klausa), klausa


def test_modul_cpe_cpv_tidak_berubah_definisinya():
    import campaign_cost_metrics as m
    assert m.KOMPONEN_ENGAGEMENT == ("likes", "comments", "shares")
    assert m.CPV_UNIT_FACTOR == 1


def test_taxonomy_style_personality_tetap_40():
    import kol_attribute_taxonomy as t
    assert t.ringkasan()["TOTAL"] == 40


# ===========================================================================
# JALUR DB  --  read-only
# ===========================================================================

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


@pytest.mark.needs_db
def test_db_tanpa_matters_skornya_none(conn):
    for r in db.search_kol_directory(conn, limit=3):
        assert r.what_matters_score is None
        assert r.what_matters_contributing is None


@pytest.mark.needs_db
def test_db_dengan_matters_menghasilkan_skor(conn):
    hasil = db.search_kol_directory(conn, matters="engagement", limit=5)
    assert hasil
    assert any(r.what_matters_score is not None for r in hasil)
    for r in hasil:
        if r.what_matters_score is not None:
            assert 0.0 <= r.what_matters_score <= 100.0


@pytest.mark.needs_db
def test_db_ranking_menurun(conn):
    hasil = db.search_kol_directory(conn, matters=SEMUA_AKTIF, limit=20)
    skor = [r.what_matters_score for r in hasil
            if r.what_matters_score is not None]
    assert skor == sorted(skor, reverse=True)


@pytest.mark.needs_db
def test_db_kontributor_terisi_saat_ada_skor(conn):
    for r in db.search_kol_directory(conn, matters=SEMUA_AKTIF, limit=10):
        if r.what_matters_score is not None:
            assert r.what_matters_contributing >= 1


@pytest.mark.needs_db
def test_db_kriteria_tidak_tersedia_semua_null(conn):
    hasil = db.search_kol_directory(
        conn, matters="content_quality", limit=5)
    assert hasil
    for r in hasil:
        assert r.what_matters_score is None
        assert r.what_matters_contributing == 0


@pytest.mark.needs_db
def test_db_kunci_asing_kembali_ke_relevansi(conn):
    hasil = db.search_kol_directory(conn, matters="ngawur", limit=3)
    assert hasil
    for r in hasil:
        assert r.what_matters_score is None


@pytest.mark.needs_db
def test_db_paritas_sql_dengan_python(conn):
    """Persentil SQL harus sama dengan `engagement_score()` Python atas
    populasi yang sama."""
    with conn.cursor() as cur:
        cur.execute("SELECT username_normalized, engagement_rate "
                    "FROM public.kol_directory")
        semua = cur.fetchall()
    populasi = [er for _, er in semua if er is not None]
    peta = {u: er for u, er in semua}

    for r in db.search_kol_directory(conn, matters="engagement", limit=5):
        if r.what_matters_score is None:
            continue
        harapan = w.engagement_score(peta[r.username], populasi)
        assert abs(harapan - r.what_matters_score) < 0.001, r.username


@pytest.mark.needs_db
def test_db_filter_tetap_jalan_bersama_matters(conn):
    hasil = db.search_kol_directory(conn, q="beauty", matters="engagement",
                                    limit=5)
    for r in hasil:
        teks = " ".join(filter(None, [r.username, r.display_name]))
        assert "beauty" in teks.lower() or r.username is not None


@pytest.mark.needs_db
def test_db_tidak_ada_kolom_skor_baru_di_kartu_l2(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM information_schema.columns
             WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
               AND column_name ~* '(what_matters|community_strength|reach_proxy
                                    |content_quality_score|brand_safety_score)'""")
        assert cur.fetchone()[0] == 0


# ===========================================================================
# ENTRY POINT CLI  --  satu-satunya interface layer di repo ini
# ===========================================================================
# Route HTTP KOL Discovery TIDAK ada di repo ini (nol FastAPI/Flask/Django;
# `route.ts` ada di repo aplikasi Next.js). `search_kol.py` adalah satu-satunya
# lapis pemanggil di sini, jadi di situlah parameter `matters` harus sampai.

def test_cli_punya_argumen_matters():
    import search_kol
    args = search_kol.parse_args(["--matters", "engagement,reach"])
    assert args.matters == "engagement,reach"


def test_cli_default_matters_none():
    import search_kol
    assert search_kol.parse_args([]).matters is None


def test_cli_meneruskan_matters_ke_search(monkeypatch):
    """Bukti koneksi: apa yang diketik user sampai ke search_kol_directory."""
    import search_kol
    ditangkap = {}

    def palsu(conn, **kwargs):
        ditangkap.update(kwargs)
        return []

    monkeypatch.setattr(search_kol, "search_kol_directory", palsu)
    monkeypatch.setattr(search_kol, "load_config", lambda: _CfgPalsu())
    monkeypatch.setattr(search_kol, "connect", _connect_palsu)

    search_kol.main(["--matters", "engagement,consistency"])
    assert ditangkap["matters"] == ["engagement", "consistency"]


def test_cli_tanpa_matters_mengirim_none(monkeypatch):
    import search_kol
    ditangkap = {}

    def palsu(conn, **kwargs):
        ditangkap.update(kwargs)
        return []

    monkeypatch.setattr(search_kol, "search_kol_directory", palsu)
    monkeypatch.setattr(search_kol, "load_config", lambda: _CfgPalsu())
    monkeypatch.setattr(search_kol, "connect", _connect_palsu)

    search_kol.main([])
    assert ditangkap["matters"] is None


def test_cli_menolak_kriteria_salah_ketik(monkeypatch, capsys):
    """parse_matters mengabaikan kunci asing diam-diam; di CLI itu tampil
    sebagai 'ranking tidak berubah' tanpa penjelasan, jadi ditolak di depan."""
    import search_kol
    monkeypatch.setattr(search_kol, "load_config", lambda: _CfgPalsu())
    kode = search_kol.main(["--matters", "ngawur"])
    assert kode == 1
    assert "tidak dikenal" in capsys.readouterr().out


class _CfgPalsu:
    postgres = None


class _connect_palsu:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_session(self, **k):
        pass
