"""CPE di grain campaign x KOL.

    CPE = campaign_kols.deal_price / (likes + comments_count + shares)

Biaya per SATU engagement. Tanpa pengali, tanpa views, tanpa ER.

Semantiknya diuji ke Postgres SUNGGUHAN dengan sumber performa diganti klausa
VALUES — pola `db._GROWTH_CTE_TEMPLATE`. Yang diuji jadi SQL yang benar-benar
dipakai produksi, tanpa menulis satu baris pun ke database.
"""

import pytest

import campaign_cost_metrics as ccm
import db


# ===========================================================================
# COST — sumber dan yang dilarang
# ===========================================================================

def test_cost_campaign_kol_adalah_deal_price():
    assert ccm.COST_CAMPAIGN_KOL == "campaign_kols.deal_price"


def test_total_amount_dilarang_jadi_cost_kol():
    """Satu order bisa mencakup beberapa creator dan sudah termasuk platform
    fee serta pajak; membaginya rata mengarang biaya."""
    assert "campaign_orders.total_amount" in ccm.COST_TERLARANG
    sql = ccm.sql_cpe_campaign_kol()
    assert "campaign_orders" not in sql


def test_rate_card_tidak_dipakai_sebagai_cost_campaign():
    sql = ccm.sql_cpe_campaign_kol()
    assert "unified_rate_card" not in sql
    assert "rate_card_snapshot" not in sql


def test_deliverable_subtotal_tidak_dipakai_di_grain_kol():
    """subtotal bergrain deliverable; mencampurnya dengan deal_price berarti
    dua level cost dalam satu angka."""
    sql = ccm.sql_cpe_campaign_kol()
    assert "d.subtotal" not in sql
    assert "unit_price" not in sql


# ===========================================================================
# DENOMINATOR — Like + Comment + Share, bukan yang lain
# ===========================================================================

def test_denominator_tepat_tiga_komponen():
    assert ccm.KOMPONEN_ENGAGEMENT == ("likes", "comments", "shares")


def test_views_tidak_masuk_denominator():
    """CTE `performa` dipakai bersama CPV, jadi ia MEMBAWA `views` --
    yang harus dijaga adalah views tidak masuk PENYEBUT CPE.
    """
    sql = ccm.sql_cpe_campaign_kol()
    penyebut = sql[sql.index("sum("):sql.index("AS total_engagement")]
    assert "views" not in penyebut
    assert "perf.likes" in penyebut
    assert "delta_views" not in sql
    # dan pembaginya memang total_engagement, bukan views
    assert "NULLIF(pk.total_engagement, 0)" in sql
    assert "NULLIF(pk.total_views, 0)" not in sql


def test_er_tidak_dipakai_sebagai_denominator():
    sql = ccm.sql_cpe_campaign_kol()
    assert "engagement_rate" not in sql


def test_total_engagement_bawaan_tidak_dipakai():
    """`campaign_kols.total_engagement` dan
    `campaign_content_performance.total_engagement` tidak berkomentar dan
    tabelnya 0 baris — tidak ada yang menyatakan isinya L+C+S."""
    sql = ccm.sql_cpe_campaign_kol()
    assert "ck.total_engagement" not in sql
    assert "p.total_engagement" not in sql


def test_sql_menjumlahkan_ketiga_kolom():
    sql = ccm.sql_cpe_campaign_kol()
    for kolom in ("perf.likes", "perf.comments_count", "perf.shares"):
        assert kolom in sql


# ===========================================================================
# GUARD — NULL, nol, tanpa inf/NaN
# ===========================================================================

def test_pembagian_memakai_nullif():
    assert ccm.sql_cpe_ekspresi("a", "b") == "a / NULLIF(b, 0)"


def test_tidak_ada_pengali():
    sql = ccm.sql_cpe_campaign_kol()
    assert "* 1000" not in sql
    assert "* 100" not in sql


def test_python_cpe_nol_engagement_none():
    assert ccm.cpe(1_000_000, 0, 0, 0) is None


def test_python_cpe_deal_price_none():
    assert ccm.cpe(None, 10, 5, 2) is None


def test_python_cpe_tidak_pernah_inf_atau_nan():
    import math
    for args in [(1000, 0, 0, 0), (1000, None, None, None), (0, 0, 0, 0),
                 (None, None, None, None)]:
        hasil = ccm.cpe(*args)
        assert hasil is None or math.isfinite(hasil)


def test_python_cpe_menghitung_benar():
    # 1.250.000 / (100 + 20 + 5) = 10.000
    assert ccm.cpe(1_250_000, 100, 20, 5) == 10_000.0


# ===========================================================================
# AGREGASI SNAPSHOT — konvensinya belum dikonfirmasi, jadi jadi parameter
# ===========================================================================

def test_dua_aturan_agregasi_tersedia():
    assert ccm.AGREGASI_SNAPSHOT_SAH == (
        ccm.AGREGASI_BARIS_TERAKHIR, ccm.AGREGASI_JUMLAH_SEMUA)


def test_default_memakai_snapshot_terbaru_karena_kolomnya_kumulatif():
    """Keputusan bisnis: likes/comments_count/shares KUMULATIF sampai
    snapshot-nya, jadi CPE memakai satu baris terbaru/final."""
    assert ccm.AGREGASI_DEFAULT == ccm.AGREGASI_BARIS_TERAKHIR


def test_urutan_prioritas_is_final_lalu_tanggal_lalu_id():
    sql = ccm.sql_engagement_per_deliverable()
    urut = sql[sql.index("ORDER BY"):]
    assert urut.index("is_final") < urut.index("snapshot_date") < urut.index("p.id")


def test_tidak_menjumlahkan_antar_snapshot_di_jalur_default():
    """Menjumlahkan akan menghitung satu deliverable sebanyak hari pantauan."""
    sql = ccm.sql_engagement_per_deliverable()
    assert "sum(" not in sql.lower()
    assert "DISTINCT ON" in sql


def test_agregasi_asing_ditolak_bukan_diabaikan():
    with pytest.raises(ValueError, match="tidak dikenal"):
        ccm.sql_cpe_campaign_kol(agregasi="ngawur")


def test_baris_terakhir_memakai_distinct_on():
    sql = ccm.sql_engagement_per_deliverable(
        agregasi=ccm.AGREGASI_BARIS_TERAKHIR)
    assert "DISTINCT ON (p.campaign_kol_deliverable_id)" in sql
    assert "p.is_final DESC NULLS LAST" in sql


def test_jumlah_semua_memakai_group_by():
    sql = ccm.sql_engagement_per_deliverable(
        agregasi=ccm.AGREGASI_JUMLAH_SEMUA)
    assert "GROUP BY 1" in sql
    assert "DISTINCT ON" not in sql


# ===========================================================================
# SEMANTIK SQL — dijalankan ke Postgres sungguhan
# ===========================================================================
#
# del-1 dipantau 3 hari (kumulatif menaik). del-2 satu bacaan final.
# del-3 shares NULL (Instagram). del-4 tanpa bacaan sama sekali.
_SUMBER_UJI = """(VALUES
        ('del-1'::text, DATE '2026-09-01', false, 100::bigint,  10::bigint,  5::bigint, 1000::bigint, 1),
        ('del-1',       DATE '2026-09-02', false, 200,          20,          9,         2000,         2),
        ('del-1',       DATE '2026-09-03', true,  300,          30,         12,         3000,         3),
        ('del-2',       DATE '2026-09-03', true,   50,           5,          2,          500,         4),
        ('del-3',       DATE '2026-09-03', true,   80,           8,       NULL,          800,         5)
    ) AS p(campaign_kol_deliverable_id, snapshot_date, is_final,
           likes, comments_count, shares, views, id)"""

_DELIVERABLE_UJI = """(VALUES
        ('del-1'::text, 'ck-1'::text),
        ('del-2',       'ck-1'),
        ('del-3',       'ck-2'),
        ('del-4',       'ck-3')
    ) AS d(id, campaign_kol_id)"""

_KOL_UJI = """(VALUES
        ('ck-1'::text, 3000000::numeric),
        ('ck-2',       1000000),
        ('ck-3',        500000),
        ('ck-4',           NULL)
    ) AS ck(id, deal_price)"""


def _hitung(conn, agregasi=ccm.AGREGASI_DEFAULT):
    """Jalankan CTE yang SAMA dengan produksi atas data tiruan."""
    performa = ccm.sql_engagement_per_deliverable(_SUMBER_UJI, agregasi)
    jumlah = ("COALESCE(perf.likes, 0) + COALESCE(perf.comments_count, 0) "
              "+ COALESCE(perf.shares, 0)")
    ada = ("perf.likes IS NOT NULL OR perf.comments_count IS NOT NULL "
           "OR perf.shares IS NOT NULL")
    sql = f"""
        WITH {performa},
        per_kol AS (
            SELECT d.campaign_kol_id AS campaign_kol_id,
                   sum({jumlah}) FILTER (WHERE {ada})  AS total_engagement,
                   count(*)      FILTER (WHERE {ada})  AS deliverable_count,
                   count(perf.shares)                  AS deliverable_shares
              FROM {_DELIVERABLE_UJI}
              JOIN performa perf ON perf.deliverable_id = d.id
             GROUP BY 1
        )
        SELECT ck.id, ck.deal_price, pk.total_engagement,
               pk.deliverable_count, pk.deliverable_shares,
               {ccm.sql_cpe_ekspresi('ck.deal_price', 'pk.total_engagement')}
          FROM {_KOL_UJI}
          LEFT JOIN per_kol pk ON pk.campaign_kol_id = ck.id
         ORDER BY ck.id
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return {r[0]: {"deal_price": r[1], "engagement": r[2],
                       "deliverable": r[3], "shares_ada": r[4],
                       "cpe": float(r[5]) if r[5] is not None else None}
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
def test_sql_tidak_double_count_snapshot(conn):
    """del-1 punya 3 snapshot; hanya baris terakhir yang dipakai.

    Menjumlahkan ketiganya akan memberi 100+200+300 = 600 likes, bukan 300.
    """
    h = _hitung(conn)
    # del-1 terakhir: 300+30+12 = 342 ; del-2: 50+5+2 = 57
    assert h["ck-1"]["engagement"] == 342 + 57
    assert h["ck-1"]["deliverable"] == 2


@pytest.mark.needs_db
def test_sql_cpe_dihitung_benar(conn):
    h = _hitung(conn)
    assert h["ck-1"]["cpe"] == pytest.approx(3_000_000 / 399)


@pytest.mark.needs_db
def test_sql_multiple_deliverable_dijumlahkan(conn):
    """ck-1 punya dua deliverable; keduanya masuk, masing-masing sekali."""
    h = _hitung(conn)
    assert h["ck-1"]["deliverable"] == 2


@pytest.mark.needs_db
def test_sql_shares_null_dilaporkan_bukan_disembunyikan(conn):
    """del-3 shares NULL (Instagram tidak mengembalikannya).

    Ia dihitung 0 di penjumlahan, TAPI `deliverable_shares` melaporkan bahwa
    tidak ada satu pun deliverable yang shares-nya terukur.
    """
    h = _hitung(conn)
    assert h["ck-2"]["engagement"] == 80 + 8      # shares NULL -> tidak menambah
    assert h["ck-2"]["deliverable"] == 1
    assert h["ck-2"]["shares_ada"] == 0           # <- penandanya


@pytest.mark.needs_db
def test_sql_shares_terukur_dilaporkan(conn):
    h = _hitung(conn)
    assert h["ck-1"]["shares_ada"] == 2           # del-1 dan del-2 punya shares


@pytest.mark.needs_db
def test_sql_tanpa_bacaan_performa_cpe_null(conn):
    """ck-3 punya deliverable tapi belum ada bacaan sama sekali."""
    h = _hitung(conn)
    assert h["ck-3"]["engagement"] is None
    assert h["ck-3"]["cpe"] is None


@pytest.mark.needs_db
def test_sql_deal_price_null_cpe_null(conn):
    h = _hitung(conn)
    assert h["ck-4"]["deal_price"] is None
    assert h["ck-4"]["cpe"] is None


@pytest.mark.needs_db
def test_sql_agregasi_jumlah_memberi_angka_berbeda(conn):
    """Bukti bahwa aturan agregasi memang menentukan hasilnya — karena itu ia
    parameter, bukan pilihan diam-diam."""
    terakhir = _hitung(conn, ccm.AGREGASI_BARIS_TERAKHIR)
    jumlah = _hitung(conn, ccm.AGREGASI_JUMLAH_SEMUA)
    assert jumlah["ck-1"]["engagement"] > terakhir["ck-1"]["engagement"]


@pytest.mark.needs_db
def test_sql_python_sepadan(conn):
    """CPE dari SQL harus sama dengan `ccm.cpe()` atas angka yang sama."""
    h = _hitung(conn)
    py = ccm.cpe(3_000_000, 300 + 50, 30 + 5, 12 + 2)
    assert h["ck-1"]["cpe"] == pytest.approx(py)


# ===========================================================================
# JALUR BACA PRODUKSI
# ===========================================================================

def test_fetch_ada_dan_grainnya_campaign_kol():
    import inspect
    sig = inspect.signature(db.fetch_campaign_kol_cpe)
    assert "campaign_id" in sig.parameters
    assert "agregasi" in sig.parameters
    kolom = db.CampaignKolCPE.__dataclass_fields__
    assert "campaign_kol_id" in kolom and "cpe" in kolom
    assert "deliverable_shares" in kolom


def test_cpe_tidak_masuk_hasil_discovery():
    """CPE bergrain (campaign, KOL); Discovery bergrain KOL. Satu KOL bisa
    ikut banyak campaign dengan deal_price berbeda, jadi CPE bukan satu angka
    yang menempel pada kreator."""
    assert "cpe" not in db.SearchResult.__dataclass_fields__
    assert "cpe" not in db._SEARCH_QUERY.lower()


@pytest.mark.needs_db
def test_db_query_valid_terhadap_schema(conn):
    """Tabel campaign masih 0 baris, jadi hasilnya kosong — yang diuji di sini
    query-nya berjalan terhadap schema sungguhan."""
    assert db.fetch_campaign_kol_cpe(conn) == []


@pytest.mark.needs_db
def test_db_filter_campaign_id(conn):
    hasil = db.fetch_campaign_kol_cpe(
        conn, campaign_id="00000000-0000-0000-0000-000000000000")
    assert hasil == []


@pytest.mark.needs_db
def test_db_tidak_ada_kolom_cpe_di_kartu_l2(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM information_schema.columns
             WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
               AND column_name IN ('cpe', 'cpv', 'emv')""")
        assert cur.fetchone()[0] == 0
