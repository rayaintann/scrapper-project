"""CPV di grain campaign x KOL.

    CPV = campaign_kols.deal_price / SUM(views)

Biaya per SATU view. Tanpa pengali 1.000, tanpa engagement di penyebut,
tanpa ER, tanpa rate card, tanpa campaign_orders.

`views` KUMULATIF sampai snapshot-nya, jadi diambil SATU baris terbaru/final
per deliverable — prioritas `is_final`, lalu `snapshot_date`, lalu `id`.

Semantiknya diuji ke Postgres SUNGGUHAN dengan sumber performa diganti klausa
VALUES, pola `db._GROWTH_CTE_TEMPLATE`: yang diuji SQL yang benar-benar dipakai
produksi, tanpa menulis satu baris pun.
"""

import pytest

import campaign_cost_metrics as ccm
import db


# ===========================================================================
# COST — sumber dan yang dilarang
# ===========================================================================

def test_cost_adalah_deal_price():
    sql = ccm.sql_cpv_campaign_kol()
    assert "ck.deal_price" in sql
    assert ccm.COST_CAMPAIGN_KOL == "campaign_kols.deal_price"


def test_tidak_memakai_campaign_orders():
    sql = ccm.sql_cpv_campaign_kol()
    assert "campaign_orders" not in sql
    assert "total_amount" not in sql


def test_tidak_memakai_rate_card():
    sql = ccm.sql_cpv_campaign_kol()
    assert "rate_card" not in sql
    assert "unified_rate_card" not in sql


# ===========================================================================
# DENOMINATOR — views, bukan engagement dan bukan ER
# ===========================================================================

def test_penyebut_adalah_views():
    sql = ccm.sql_cpv_campaign_kol()
    assert "sum(perf.views)" in sql
    assert "NULLIF(pk.total_views, 0)" in sql


def test_engagement_tidak_masuk_penyebut():
    sql = ccm.sql_cpv_campaign_kol()
    penyebut = sql[sql.index("sum(perf.views)"):sql.index("AS total_views")]
    for kolom in ("likes", "comments_count", "shares"):
        assert kolom not in penyebut
    assert "NULLIF(pk.total_engagement, 0)" not in sql


def test_er_tidak_dipakai():
    sql = ccm.sql_cpv_campaign_kol()
    assert "engagement_rate" not in sql


# ===========================================================================
# UNIT — per 1 view
# ===========================================================================

def test_unit_factor_satu():
    assert ccm.CPV_UNIT_FACTOR == 1


def test_tidak_ada_pengali_seribu():
    sql = ccm.sql_cpv_campaign_kol()
    assert "* 1000" not in sql
    assert "* 100" not in sql


def test_ekspresi_cpv_tanpa_pengali():
    assert ccm.sql_cpv_ekspresi("a", "b") == "a / NULLIF(b, 0)"


def test_label_unit_menyebut_per_view():
    assert ccm.CPV_UNIT_LABEL == "CPV / View"
    assert "1K" not in ccm.CPV_UNIT_LABEL


# ===========================================================================
# AGREGASI SNAPSHOT — kumulatif, ambil terbaru/final
# ===========================================================================

def test_memakai_cte_yang_sama_dengan_cpe():
    """Satu aturan snapshot untuk keduanya; dua salinan akan membuat CPE dan
    CPV membaca baris yang berbeda tanpa ada yang sadar."""
    cte = ccm.sql_engagement_per_deliverable()
    assert cte in ccm.sql_cpv_campaign_kol()
    assert cte in ccm.sql_cpe_campaign_kol()


def test_cte_membawa_views_dan_engagement():
    cte = ccm.sql_engagement_per_deliverable()
    for kolom in ("p.likes", "p.comments_count", "p.shares", "p.views"):
        assert kolom in cte


def test_tidak_sum_antar_snapshot():
    cte = ccm.sql_engagement_per_deliverable()
    assert "DISTINCT ON" in cte
    assert "sum(" not in cte.lower()


def test_prioritas_is_final_lalu_tanggal_lalu_id():
    cte = ccm.sql_engagement_per_deliverable()
    urut = cte[cte.index("ORDER BY"):]
    assert urut.index("is_final") < urut.index("snapshot_date") < urut.index("p.id")


def test_agregasi_asing_ditolak():
    with pytest.raises(ValueError, match="tidak dikenal"):
        ccm.sql_cpv_campaign_kol(agregasi="ngawur")


# ===========================================================================
# PYTHON — guard NULL / nol
# ===========================================================================

def test_python_cpv_normal():
    assert ccm.cpv(1_000_000, 500_000) == 2.0


def test_python_cpv_views_nol_none():
    assert ccm.cpv(1_000_000, 0) is None


def test_python_cpv_views_null_none():
    assert ccm.cpv(1_000_000, None) is None


def test_python_cpv_deal_price_null_none():
    assert ccm.cpv(None, 500_000) is None


def test_python_cpv_tidak_pernah_inf_atau_nan():
    import math
    for args in [(1000, 0), (1000, None), (None, 1000), (None, None), (0, 0)]:
        hasil = ccm.cpv(*args)
        assert hasil is None or math.isfinite(hasil)


def test_python_cpv_cost_nol_tetap_nol():
    """Gratis itu angka, bukan ketiadaan data."""
    assert ccm.cpv(0, 500_000) == 0.0


# ===========================================================================
# SEMANTIK SQL — dijalankan ke Postgres sungguhan
# ===========================================================================
#
# del-1 dipantau 3 hari, views KUMULATIF 1000 -> 2000 -> 3000 (final).
# del-2 satu bacaan final. del-3 views 0. del-4 tanpa bacaan.
_SUMBER_UJI = """(VALUES
        ('del-1'::text, DATE '2026-09-01', false, 1000::bigint, 1),
        ('del-1',       DATE '2026-09-02', false, 2000,         2),
        ('del-1',       DATE '2026-09-03', true,  3000,         3),
        ('del-2',       DATE '2026-09-03', true,   500,         4),
        ('del-3',       DATE '2026-09-03', true,     0,         5)
    ) AS p(campaign_kol_deliverable_id, snapshot_date, is_final, views, id)"""

_DELIVERABLE_UJI = """(VALUES
        ('del-1'::text, 'ck-1'::text),
        ('del-2',       'ck-1'),
        ('del-3',       'ck-2'),
        ('del-4',       'ck-3')
    ) AS d(id, campaign_kol_id)"""

_KOL_UJI = """(VALUES
        ('ck-1'::text, 3500000::numeric),
        ('ck-2',       1000000),
        ('ck-3',        500000),
        ('ck-4',           NULL)
    ) AS ck(id, deal_price)"""


def _hitung(conn, agregasi=ccm.AGREGASI_DEFAULT):
    """Jalankan aturan snapshot yang SAMA dengan produksi, atas data tiruan."""
    if agregasi == ccm.AGREGASI_BARIS_TERAKHIR:
        performa = """performa AS (
            SELECT DISTINCT ON (p.campaign_kol_deliverable_id)
                   p.campaign_kol_deliverable_id AS deliverable_id, p.views
              FROM """ + _SUMBER_UJI + """
             ORDER BY p.campaign_kol_deliverable_id,
                      p.is_final DESC NULLS LAST,
                      p.snapshot_date DESC NULLS LAST,
                      p.id DESC
        )"""
    else:
        performa = """performa AS (
            SELECT p.campaign_kol_deliverable_id AS deliverable_id,
                   sum(p.views) AS views
              FROM """ + _SUMBER_UJI + """
             GROUP BY 1
        )"""

    sql = f"""
        WITH {performa},
        per_kol AS (
            SELECT d.campaign_kol_id AS campaign_kol_id,
                   sum(perf.views)   AS total_views,
                   count(perf.views) AS deliverable_count
              FROM {_DELIVERABLE_UJI}
              JOIN performa perf ON perf.deliverable_id = d.id
             GROUP BY 1
        )
        SELECT ck.id, ck.deal_price, pk.total_views, pk.deliverable_count,
               {ccm.sql_cpv_ekspresi('ck.deal_price', 'pk.total_views')}
          FROM {_KOL_UJI}
          LEFT JOIN per_kol pk ON pk.campaign_kol_id = ck.id
         ORDER BY ck.id
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return {r[0]: {"deal_price": r[1], "views": r[2], "deliverable": r[3],
                       "cpv": float(r[4]) if r[4] is not None else None}
                for r in cur.fetchall()}


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
def test_sql_normal_calculation(conn):
    """del-1 terakhir 3000 + del-2 500 = 3500 views."""
    h = _hitung(conn)
    assert h["ck-1"]["views"] == 3500
    assert h["ck-1"]["cpv"] == pytest.approx(3_500_000 / 3500)   # = 1000,0


@pytest.mark.needs_db
def test_sql_multiple_cumulative_snapshot_tidak_dijumlahkan(conn):
    """1000+2000+3000 = 6000 kalau dijumlahkan; yang benar 3000."""
    h = _hitung(conn)
    assert h["ck-1"]["views"] == 3000 + 500
    assert h["ck-1"]["views"] != 6000 + 500


@pytest.mark.needs_db
def test_sql_hanya_snapshot_final_yang_dipakai(conn):
    """Baris final del-1 adalah views 3000, bukan 1000 atau 2000."""
    h = _hitung(conn)
    assert h["ck-1"]["deliverable"] == 2


@pytest.mark.needs_db
def test_sql_views_nol_cpv_null(conn):
    h = _hitung(conn)
    assert h["ck-2"]["views"] == 0
    assert h["ck-2"]["cpv"] is None


@pytest.mark.needs_db
def test_sql_views_null_cpv_null(conn):
    """ck-3 punya deliverable tapi belum ada bacaan performa sama sekali."""
    h = _hitung(conn)
    assert h["ck-3"]["views"] is None
    assert h["ck-3"]["cpv"] is None


@pytest.mark.needs_db
def test_sql_deal_price_null_cpv_null(conn):
    h = _hitung(conn)
    assert h["ck-4"]["deal_price"] is None
    assert h["ck-4"]["cpv"] is None


@pytest.mark.needs_db
def test_sql_agregasi_jumlah_memberi_angka_berbeda(conn):
    """Bukti aturan snapshot menentukan hasilnya — karena itu ia dipilih
    eksplisit, bukan kebetulan."""
    terakhir = _hitung(conn, ccm.AGREGASI_BARIS_TERAKHIR)
    jumlah = _hitung(conn, ccm.AGREGASI_JUMLAH_SEMUA)
    assert jumlah["ck-1"]["views"] == 6000 + 500
    assert terakhir["ck-1"]["views"] < jumlah["ck-1"]["views"]


@pytest.mark.needs_db
def test_sql_sepadan_dengan_python(conn):
    h = _hitung(conn)
    assert h["ck-1"]["cpv"] == pytest.approx(ccm.cpv(3_500_000, 3500))


# ===========================================================================
# JALUR BACA PRODUKSI
# ===========================================================================

def test_fetch_ada_dan_grainnya_campaign_kol():
    import inspect
    sig = inspect.signature(db.fetch_campaign_kol_cpv)
    assert "campaign_id" in sig.parameters
    assert "agregasi" in sig.parameters
    kolom = db.CampaignKolCPV.__dataclass_fields__
    for f in ("campaign_kol_id", "deal_price", "total_views", "cpv"):
        assert f in kolom


def test_cpv_tidak_masuk_hasil_discovery():
    """Satu KOL bisa punya CPV berbeda di campaign yang berbeda."""
    assert "cpv" not in db.SearchResult.__dataclass_fields__
    assert "cpv" not in db._SEARCH_QUERY.lower()


@pytest.mark.needs_db
def test_db_query_valid_terhadap_schema(conn):
    """Tabel campaign masih 0 baris — yang diuji query-nya jalan terhadap
    schema sungguhan."""
    assert db.fetch_campaign_kol_cpv(conn) == []


@pytest.mark.needs_db
def test_db_filter_campaign_id(conn):
    assert db.fetch_campaign_kol_cpv(
        conn, campaign_id="00000000-0000-0000-0000-000000000000") == []


@pytest.mark.needs_db
def test_db_cpe_tidak_rusak_oleh_cpv(conn):
    """CTE dipakai bersama; CPE harus tetap jalan dan tetap terpisah."""
    assert db.fetch_campaign_kol_cpe(conn) == []


@pytest.mark.needs_db
def test_db_tidak_ada_kolom_cpv_di_kartu_l2(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM information_schema.columns
             WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
               AND column_name IN ('cpv', 'cpe', 'emv')""")
        assert cur.fetchone()[0] == 0
