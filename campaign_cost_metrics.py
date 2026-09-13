"""CPE dan CPV — definisi tunggal, dua bentuk.

============================================================================
KENAPA FILE INI ADA
============================================================================

CPE dan CPV punya sejarah definisi yang saling bertabrakan. Sebelum keputusan
13 September 2026, tiga sumber mengatakan tiga hal berbeda:

    Excel  KOL_Database.AP   CPE = Rate ÷ (Avg Views × ER% ÷ 100)
           KOL_Database.AO   CPV = Rate ÷ Avg Views              (per 1 view)
    Backlog                  CPE = fee ÷ total_engagement
    UI     AUTOME_2.html     cpe = dibaca apa adanya dari backend
                             cpv = rate / views * 1000           (per 1K view)

Selisih CPV antara Excel dan UI adalah **1.000×**. Itu bukan beda format —
itu angka yang salah tiga digit. File ini ada supaya definisinya hidup di satu
tempat dan tidak bisa berbeda antara Python, SQL, dan UI.

Pola dan alasannya sama persis dengan `metrics_thresholds.py`.

============================================================================
KEPUTUSAN YANG DIPAKAI  (13 September 2026)
============================================================================

    Total Engagement  =  Like + Comment + Share
    CPE               =  Cost ÷ Total Engagement
    CPV               =  Cost ÷ Views                  <- PER 1 VIEW, tanpa ×1000

`Save`, `Reach`, dan `Views` SENGAJA tidak masuk penyebut CPE. Itu keputusan
eksplisit, bukan kelalaian — jadi kalau nanti ada yang menambahkannya, ia
harus mengubah `KOMPONEN_ENGAGEMENT` di bawah dan test akan memaksa dia sadar.

Catatan yang perlu diketahui, bukan untuk diam-diam diperbaiki: penyebut ini
BEDA dari `transform.py`, yang menghitung engagement rate roster sebagai
`AVG(likes + comments)` tanpa shares. Keduanya dibiarkan apa adanya karena
mengubah ER roster akan menggeser 1.736 nilai yang sudah dipakai filter dan
ranking — di luar lingkup task ini.

============================================================================
KENAPA TIDAK ADA FUNGSI EMV DI SINI
============================================================================

EMV sengaja TIDAK diimplementasikan. Bukan karena lupa.

Satu-satunya formula EMV yang tertulis adalah
`Reach × CPM ÷ 1000 × Multiplier` (migrations/FEATURE_METRICS_BACKLOG.md:249),
dan ketiga masukannya tidak tersedia:

    Reach       0 terisi di seluruh jalur; kelima tabel Insights 0 baris
    CPM         0 kolom di 101 tabel; tidak ada nilai di repo mana pun
    Multiplier  0 kolom, 0 nilai, 0 sebutan bernilai

Angka Rp9.000 yang sempat diusulkan sebagai EMV BUKAN EMV. Di Excel ia
bernama `CAL_VALUE_PER_ENG`, berlabel "Value per engagement (IDR)", dan
keterangannya sendiri berbunyi "used by Estimated ROI". Ketiga puluh formula
yang merujuknya seluruhnya ada di kolom `KOL_Database.AS` — Estimated ROI.
Tidak satu pun menyebut EMV.

Menulis fungsi EMV di sini berarti mengarang metric. Jangan.

============================================================================
NULL BUKAN NOL
============================================================================

Penyebut nol dan penyebut kosong sama-sama menghasilkan None. Nol engagement
berarti "sudah diukur, hasilnya nol" — dan biaya dibagi nol bukan angka besar,
melainkan angka yang tidak ada. Mengembalikan 0 akan membuat kreator tanpa
engagement terlihat sebagai yang paling murah.
"""

from __future__ import annotations

# ===========================================================================
# 1. TOTAL ENGAGEMENT  =  Like + Comment + Share
# ===========================================================================
#: Komponen penyebut CPE. Ubah di sini kalau definisinya berubah — dan hanya
#: di sini. `sql_total_engagement()` ikut, dan test membandingkan keduanya.
KOMPONEN_ENGAGEMENT = ("likes", "comments", "shares")

#: Yang SENGAJA dikeluarkan, supaya penolakannya terbaca, bukan tersirat.
DIKELUARKAN_DARI_ENGAGEMENT = ("saves", "reach", "views")


def total_engagement(
    likes: int | float | None,
    comments: int | float | None,
    shares: int | float | None,
) -> float | None:
    """Like + Comment + Share.

    None kalau KETIGANYA None — itu berarti tidak ada yang pernah diukur.
    Kalau sebagian terisi, yang None dihitung 0: satu platform yang tidak
    mengembalikan `shares` (Instagram) tidak boleh membuat seluruh engagement
    jadi tidak diketahui.
    """
    if likes is None and comments is None and shares is None:
        return None
    return float(likes or 0) + float(comments or 0) + float(shares or 0)


# ===========================================================================
# 2. CPE  =  Cost ÷ Total Engagement
# ===========================================================================
# Sumber cost per grain — ditetapkan dari audit schema, bukan dipilih bebas:
#
#   campaign x KOL   public.campaign_kols.deal_price
#                    sebaris dengan total_engagement -> tanpa join
#   deliverable      public.campaign_kol_deliverables.subtotal
#                    sebaris dengan FK yang dipakai campaign_content_performance
#   discovery        l1_silver.unified_rate_card.fee
#
# `public.campaign_orders.total_amount` TIDAK BOLEH dipakai: itu nilai
# checkout satu order (subtotal -> promo -> platform fee -> pajak) yang bisa
# mencakup beberapa creator sekaligus.
COST_CAMPAIGN_KOL = "campaign_kols.deal_price"
COST_DELIVERABLE = "campaign_kol_deliverables.subtotal"
COST_DISCOVERY = "l1_silver.unified_rate_card.fee"

#: Dilarang jadi sumber cost per KOL. Dipakai test sebagai penjaga.
COST_TERLARANG = ("campaign_orders.total_amount", "campaign_orders.subtotal")


def cpe(
    cost: int | float | None,
    likes: int | float | None,
    comments: int | float | None,
    shares: int | float | None,
) -> float | None:
    """Biaya per engagement. None kalau cost atau engagement tidak tersedia."""
    if cost is None:
        return None
    eng = total_engagement(likes, comments, shares)
    if eng is None or eng == 0:
        return None
    return float(cost) / eng


# ===========================================================================
# 3. CPV  =  Cost ÷ Views          <- PER 1 VIEW
# ===========================================================================
#: Faktor unit CPV. **1 = per satu view.** Keputusan 13 September 2026.
#:
#: Prototype memakai `rate / views * 1000` dengan label "CPV / 1K views".
#: Itu ditinggalkan. Konstanta ini ada supaya angka 1000 tidak bisa masuk
#: kembali diam-diam lewat salah satu jalur — test menguji nilainya.
CPV_UNIT_FACTOR = 1

#: Label yang WAJIB dipakai UI. Angka CPV tanpa satuan adalah cara paling
#: mudah mengulang kesalahan 1.000×.
CPV_UNIT_LABEL = "CPV / View"


def cpv(cost: int | float | None, views: int | float | None) -> float | None:
    """Biaya per satu view. None kalau cost atau views tidak tersedia."""
    if cost is None or views is None or views == 0:
        return None
    return float(cost) / float(views) * CPV_UNIT_FACTOR


# ===========================================================================
# 4. BENTUK KEDUA: ekspresi SQL
# ===========================================================================
# NULLIF pada penyebut menutup dua hal sekaligus: division by zero, dan
# semantik "nol bukan murah". Keduanya jadi NULL.

def sql_total_engagement(
    likes: str = "likes",
    comments: str = "comments",
    shares: str = "shares",
) -> str:
    """`Like + Comment + Share`, NULL kalau ketiganya NULL."""
    return (
        f"CASE WHEN {likes} IS NULL AND {comments} IS NULL AND {shares} IS NULL "
        f"THEN NULL ELSE "
        f"COALESCE({likes}, 0) + COALESCE({comments}, 0) + COALESCE({shares}, 0) "
        f"END"
    )


def sql_cpe(
    cost: str,
    likes: str = "likes",
    comments: str = "comments",
    shares: str = "shares",
) -> str:
    """`cost ÷ (like + comment + share)`, NULL kalau penyebut NULL atau 0."""
    return f"{cost} / NULLIF({sql_total_engagement(likes, comments, shares)}, 0)"


def sql_cpv(cost: str, views: str = "views") -> str:
    """`cost ÷ views` — per SATU view. Tidak ada pengali 1000."""
    if CPV_UNIT_FACTOR == 1:
        return f"{cost} / NULLIF({views}, 0)"
    return f"{cost} / NULLIF({views}, 0) * {CPV_UNIT_FACTOR}"
