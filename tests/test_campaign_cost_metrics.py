"""CPE dan CPV — keputusan 13 September 2026.

    Total Engagement = Like + Comment + Share
    CPE              = Cost / Total Engagement
    CPV              = Cost / Views          <- PER 1 VIEW, tanpa x1000

Test ini menjaga tiga hal sekaligus: rumusnya benar, penyebut nol/NULL tidak
meledak, dan pengali 1000 yang lama TIDAK bisa masuk kembali.
"""

import re
from pathlib import Path

import pytest

import campaign_cost_metrics as m

AKAR = Path(__file__).resolve().parents[1]


# ===========================================================================
# TOTAL ENGAGEMENT  =  Like + Comment + Share
# ===========================================================================

def test_total_engagement_menjumlah_tiga_komponen():
    assert m.total_engagement(100, 20, 5) == 125.0


def test_total_engagement_komponennya_persis_like_comment_share():
    assert m.KOMPONEN_ENGAGEMENT == ("likes", "comments", "shares")


@pytest.mark.parametrize("dikeluarkan", ["saves", "reach", "views"])
def test_save_reach_views_tidak_masuk_penyebut(dikeluarkan):
    """Keputusan eksplisit, bukan kelalaian."""
    assert dikeluarkan not in m.KOMPONEN_ENGAGEMENT
    assert dikeluarkan in m.DIKELUARKAN_DARI_ENGAGEMENT


def test_total_engagement_sebagian_null_dihitung_nol():
    """Instagram tidak mengembalikan shares; itu tidak boleh membatalkan
    seluruh engagement."""
    assert m.total_engagement(100, 20, None) == 120.0
    assert m.total_engagement(None, 20, 5) == 25.0


def test_total_engagement_ketiganya_null_hasilnya_none():
    assert m.total_engagement(None, None, None) is None


def test_total_engagement_nol_tetap_nol_bukan_none():
    """Nol adalah pengukuran; None adalah ketiadaan pengukuran."""
    assert m.total_engagement(0, 0, 0) == 0.0


# ===========================================================================
# CPE
# ===========================================================================

def test_cpe_membagi_cost_dengan_total_engagement():
    # 1.250.000 / (100 + 20 + 5) = 10.000
    assert m.cpe(1_250_000, 100, 20, 5) == 10_000.0


def test_cpe_memakai_shares_bukan_mengabaikannya():
    tanpa_share = m.cpe(1000, 100, 0, 0)
    dengan_share = m.cpe(1000, 100, 0, 100)
    assert dengan_share < tanpa_share


def test_cpe_zero_engagement_none_bukan_error():
    assert m.cpe(1_000_000, 0, 0, 0) is None


def test_cpe_engagement_null_none():
    assert m.cpe(1_000_000, None, None, None) is None


def test_cpe_cost_null_none():
    assert m.cpe(None, 100, 20, 5) is None


def test_cpe_tidak_pernah_division_by_zero():
    for args in [(1000, 0, 0, 0), (1000, None, None, None), (0, 0, 0, 0)]:
        assert m.cpe(*args) is None


def test_cpe_cost_nol_tetap_menghasilkan_nol():
    """Gratis itu angka, bukan ketiadaan data."""
    assert m.cpe(0, 100, 20, 5) == 0.0


# ===========================================================================
# CPV  --  PER 1 VIEW
# ===========================================================================

def test_cpv_unit_factor_satu():
    assert m.CPV_UNIT_FACTOR == 1


def test_cpv_membagi_cost_dengan_views():
    # 1.000.000 / 500.000 = 2 rupiah per view
    assert m.cpv(1_000_000, 500_000) == 2.0


def test_cpv_hasilnya_per_satu_view_bukan_per_seribu():
    """Penjaga utama terhadap kesalahan 1.000x."""
    hasil = m.cpv(1_000_000, 500_000)
    assert hasil == 2.0
    assert hasil != 2000.0


def test_cpv_zero_views_none_bukan_error():
    assert m.cpv(1_000_000, 0) is None


def test_cpv_views_null_none():
    assert m.cpv(1_000_000, None) is None


def test_cpv_cost_null_none():
    assert m.cpv(None, 500_000) is None


def test_cpv_label_menyebut_per_view():
    assert m.CPV_UNIT_LABEL == "CPV / View"
    assert "1K" not in m.CPV_UNIT_LABEL


# ===========================================================================
# PARITAS PYTHON <-> SQL
# ===========================================================================

def test_sql_total_engagement_menyebut_tiga_komponen():
    sql = m.sql_total_engagement()
    for kolom in m.KOMPONEN_ENGAGEMENT:
        assert kolom in sql
    for kolom in m.DIKELUARKAN_DARI_ENGAGEMENT:
        assert kolom not in sql


def test_sql_cpe_memakai_nullif_pada_penyebut():
    sql = m.sql_cpe("deal_price")
    assert "NULLIF(" in sql
    assert "deal_price" in sql


def test_sql_cpv_tidak_mengandung_pengali_seribu():
    """Kalau seseorang mengembalikan x1000, test ini yang menangkapnya."""
    sql = m.sql_cpv("deal_price")
    assert "1000" not in sql
    assert "NULLIF(views, 0)" in sql


def test_sql_cpv_bentuknya_cost_bagi_views():
    assert m.sql_cpv("deal_price", "views") == "deal_price / NULLIF(views, 0)"


# ===========================================================================
# SUMBER COST
# ===========================================================================

def test_cost_source_per_grain_sesuai_audit():
    assert m.COST_CAMPAIGN_KOL == "campaign_kols.deal_price"
    assert m.COST_DELIVERABLE == "campaign_kol_deliverables.subtotal"
    assert m.COST_DISCOVERY == "l1_silver.unified_rate_card.fee"


def test_campaign_orders_total_amount_dilarang_jadi_cost_per_kol():
    """Itu nilai checkout satu order: bisa mencakup beberapa creator, dan
    sudah termasuk platform fee dan pajak."""
    assert "campaign_orders.total_amount" in m.COST_TERLARANG
    for terlarang in m.COST_TERLARANG:
        assert terlarang not in (
            m.COST_CAMPAIGN_KOL, m.COST_DELIVERABLE, m.COST_DISCOVERY)


# ===========================================================================
# EMV  --  PENJAGA TERHADAP METRIC KARANGAN
# ===========================================================================

def test_tidak_ada_fungsi_emv_yang_dikarang():
    """EMV belum punya formula yang didukung evidence.

    `Reach x CPM / 1000 x Multiplier` adalah satu-satunya formula tertulis,
    dan ketiga masukannya tidak tersedia: reach 0 terisi di seluruh jalur,
    CPM 0 kolom, multiplier 0 kolom. Selama itu belum berubah, modul ini
    tidak boleh punya fungsi EMV.
    """
    assert not hasattr(m, "emv")
    assert not hasattr(m, "earned_media_value")


def test_tidak_ada_konstanta_9000_di_modul_biaya():
    """Rp9.000 adalah CAL_VALUE_PER_ENG milik Estimated ROI, BUKAN EMV.

    Di Excel ia berlabel "Value per engagement (IDR)" dengan keterangan
    "used by Estimated ROI", dan seluruh 30 formula yang merujuknya ada di
    kolom Estimated ROI. Memakainya sebagai EMV akan mengarang metric.
    """
    sumber = (AKAR / "campaign_cost_metrics.py").read_text(encoding="utf-8")
    kode = "\n".join(
        baris for baris in sumber.splitlines()
        if not baris.lstrip().startswith("#")
    )
    # buang docstring modul supaya penjelasannya sendiri tidak ikut terbaca
    kode = re.sub(r'^""".*?"""', "", kode, flags=re.S)
    assert not re.search(r"\b9000\b", kode)
    assert not re.search(r"\bCPM\b\s*=", kode)
    assert not re.search(r"\bMULTIPLIER\b\s*=", kode)
