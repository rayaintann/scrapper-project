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


# ===========================================================================
# 5. CPE DI GRAIN CAMPAIGN x KOL
# ===========================================================================
# Struktur yang dipakai, seluruhnya SUDAH ADA:
#
#     campaign_kols                  deal_price      <- cost, 1 baris per KOL
#       | 1:N
#     campaign_kol_deliverables      campaign_kol_id
#       | 1:N
#     campaign_content_performance   likes, comments_count, shares
#                                    snapshot_date, is_final
#
# `campaign_kols.total_engagement` SENGAJA tidak dipakai meski satu kolom dan
# tanpa join: isinya tidak berkomentar, tabelnya 0 baris, dan tidak ada apa pun
# yang menyatakan ia Like+Comment+Share. Definisi yang disepakati menyebut
# ketiganya eksplisit, jadi ketiganya yang dijumlahkan.
#
# --------------------------------------------------------------------------
# AGREGASI SNAPSHOT -- SUDAH DIPUTUSKAN
# --------------------------------------------------------------------------
# `campaign_content_performance` bergrain per-deliverable per-`snapshot_date`.
#
# KEPUTUSAN BISNIS: `likes`, `comments_count`, dan `shares` adalah KUMULATIF
# sampai snapshot-nya. Karena itu CPE mengambil SATU baris terbaru/final per
# deliverable, dan TIDAK MENJUMLAHKAN antar snapshot -- satu deliverable yang
# dipantau tiga hari akan terhitung tiga kali kalau dijumlahkan.
#
# Urutan prioritasnya: `is_final`, lalu `snapshot_date`, lalu `id` sebagai
# tie-break supaya hasilnya deterministik.
#
# Keputusan itu sejalan dengan bentuk tabelnya: ada `delta_views` dan
# `delta_engagement` DI SAMPING `views` dan `total_engagement`, dan kolom delta
# hanya perlu ada kalau kolom dasarnya kumulatif.
AGREGASI_BARIS_TERAKHIR = "baris_terakhir_per_deliverable"

#: TIDAK BERLAKU untuk `campaign_content_performance` -- kolomnya kumulatif,
#: jadi menjumlahkan antar snapshot menghasilkan angka yang terlalu besar.
#: Dipertahankan hanya supaya `sql_engagement_per_deliverable()` tetap bisa
#: dipakai atas sumber PERIODIK kalau nanti ada, dan supaya test bisa
#: menunjukkan bahwa memilih aturan yang salah memang mengubah hasilnya.
AGREGASI_JUMLAH_SEMUA = "jumlah_semua_baris"

AGREGASI_SNAPSHOT_SAH = (AGREGASI_BARIS_TERAKHIR, AGREGASI_JUMLAH_SEMUA)

#: Aturan yang berlaku untuk CPE. Bukan tebakan -- ini keputusan bisnis.
AGREGASI_DEFAULT = AGREGASI_BARIS_TERAKHIR

#: Sumber performa. Dibuat parameter dengan alasan yang sama seperti
#: `db._GROWTH_CTE_TEMPLATE`: test menyuntikkan klausa VALUES sebagai
#: pengganti, jadi yang diuji SQL yang benar-benar dipakai produksi -- tanpa
#: menulis satu baris pun. Pengganti harus menyediakan kolom
#: `campaign_kol_deliverable_id`, `likes`, `comments_count`, `shares`,
#: `snapshot_date`, `is_final`, beralias `p`.
SUMBER_PERFORMA_DEFAULT = "public.campaign_content_performance p"


def sql_engagement_per_deliverable(
    sumber: str = SUMBER_PERFORMA_DEFAULT,
    agregasi: str = AGREGASI_DEFAULT,
) -> str:
    """CTE `performa`: satu baris performa per deliverable.

    Inilah tempat double-count dicegah. Satu deliverable yang dipantau 5 hari
    punya 5 baris; menjumlahkan semuanya membuat angkanya 5x lipat.

    Membawa `likes`, `comments_count`, `shares` (penyebut CPE) DAN `views`
    (penyebut CPV) sekaligus, supaya aturan snapshot hidup di satu tempat.
    Dua salinan aturan yang sama adalah cara tercepat membuat CPE dan CPV
    memakai baris yang berbeda tanpa ada yang sadar.
    """
    if agregasi not in AGREGASI_SNAPSHOT_SAH:
        raise ValueError(
            f"agregasi {agregasi!r} tidak dikenal; pilih salah satu dari "
            f"{AGREGASI_SNAPSHOT_SAH}")

    if agregasi == AGREGASI_BARIS_TERAKHIR:
        # `is_final` didahulukan; kalau belum ada baris penutup, pakai
        # snapshot terbaru. Deterministik lewat tie-break ke id.
        return f"""performa AS (
        SELECT DISTINCT ON (p.campaign_kol_deliverable_id)
               p.campaign_kol_deliverable_id AS deliverable_id,
               p.likes, p.comments_count, p.shares, p.views
          FROM {sumber}
         ORDER BY p.campaign_kol_deliverable_id,
                  p.is_final DESC NULLS LAST,
                  p.snapshot_date DESC NULLS LAST,
                  p.id DESC
    )"""
    return f"""performa AS (
        SELECT p.campaign_kol_deliverable_id AS deliverable_id,
               sum(p.likes)          AS likes,
               sum(p.comments_count) AS comments_count,
               sum(p.shares)         AS shares,
               sum(p.views)          AS views
          FROM {sumber}
         GROUP BY 1
    )"""


def sql_cpe_campaign_kol(
    sumber: str = SUMBER_PERFORMA_DEFAULT,
    agregasi: str = AGREGASI_DEFAULT,
) -> str:
    """CPE per campaign x KOL, dari struktur yang sudah ada.

    Mengembalikan satu baris per `campaign_kols.id`, dengan:

        deal_price          cost, apa adanya dari campaign_kols
        total_engagement    SUM(likes + comments_count + shares)
        cpe                 deal_price / total_engagement, per 1 engagement
        deliverable_count   berapa deliverable yang punya bacaan performa
        deliverable_shares  berapa di antaranya yang `shares`-nya TIDAK NULL

    `deliverable_shares` bukan hiasan. Instagram tidak mengembalikan shares,
    jadi NULL di sana berarti "tidak diukur", bukan "nol". Angka ini membuat
    perbedaan itu terlihat oleh pembaca, alih-alih tersembunyi di dalam
    penjumlahan.

    Kalau KETIGA komponen NULL untuk seluruh deliverable, `total_engagement`
    NULL -- bukan 0 -- sehingga `cpe` ikut NULL. Nol engagement yang TERUKUR
    tetap menghasilkan NULL juga, lewat NULLIF: biaya dibagi nol bukan angka
    besar, melainkan angka yang tidak ada.
    """
    komponen = ("perf.likes", "perf.comments_count", "perf.shares")
    jumlah = " + ".join(f"COALESCE({k}, 0)" for k in komponen)
    ada_satu_pun = " OR ".join(f"{k} IS NOT NULL" for k in komponen)

    return f"""WITH {sql_engagement_per_deliverable(sumber, agregasi)},
    per_kol AS (
        SELECT d.campaign_kol_id                                  AS campaign_kol_id,
               sum({jumlah}) FILTER (WHERE {ada_satu_pun})        AS total_engagement,
               count(*)      FILTER (WHERE {ada_satu_pun})        AS deliverable_count,
               count(perf.shares)                                 AS deliverable_shares
          FROM public.campaign_kol_deliverables d
          JOIN performa perf ON perf.deliverable_id = d.id
         GROUP BY 1
    )
    SELECT ck.id                AS campaign_kol_id,
           ck.campaign_id,
           ck.agency_kol_account_id,
           ck.deal_price,
           ck.currency,
           pk.total_engagement,
           pk.deliverable_count,
           pk.deliverable_shares,
           {sql_cpe_ekspresi('ck.deal_price', 'pk.total_engagement')} AS cpe
      FROM public.campaign_kols ck
      LEFT JOIN per_kol pk ON pk.campaign_kol_id = ck.id
     WHERE (%(campaign_id)s::uuid IS NULL OR ck.campaign_id = %(campaign_id)s)
     ORDER BY cpe ASC NULLS LAST, ck.id"""


def sql_cpe_ekspresi(cost: str, engagement: str) -> str:
    """`cost / engagement` dengan guard. Dipakai query di atas dan bisa
    dipakai ulang di tempat lain tanpa menyalin NULLIF-nya."""
    return f"{cost} / NULLIF({engagement}, 0)"


# ===========================================================================
# 6. CPV DI GRAIN CAMPAIGN x KOL
# ===========================================================================
# Struktur, sumber cost, dan aturan snapshot PERSIS sama dengan CPE di atas --
# yang berbeda hanya penyebutnya:
#
#     CPE  ->  likes + comments_count + shares
#     CPV  ->  views
#
# Karena itu keduanya memakai CTE `performa` yang SAMA. `views` juga kumulatif
# sampai snapshot-nya, jadi aturan "satu baris terbaru/final per deliverable"
# berlaku tanpa perkecualian: menjumlahkan antar snapshot akan menghitung satu
# post sebanyak jumlah hari ia dipantau.


def sql_cpv_ekspresi(cost: str, views: str) -> str:
    """`cost / views` -- biaya per SATU view.

    `CPV_UNIT_FACTOR` = 1, jadi tidak ada pengali yang muncul di SQL. Kalau
    suatu saat ada yang mengubahnya, pengalinya ikut tercetak di sini dan
    perubahan itu terlihat, bukan tersembunyi.
    """
    dasar = f"{cost} / NULLIF({views}, 0)"
    return dasar if CPV_UNIT_FACTOR == 1 else f"({dasar}) * {CPV_UNIT_FACTOR}"


def sql_cpv_campaign_kol(
    sumber: str = SUMBER_PERFORMA_DEFAULT,
    agregasi: str = AGREGASI_DEFAULT,
) -> str:
    """CPV per campaign x KOL, dari struktur yang sudah ada.

    Satu baris per `campaign_kols.id`:

        deal_price          cost, apa adanya dari campaign_kols
        total_views         SUM(views) atas satu baris terbaru per deliverable
        cpv                 deal_price / total_views, per 1 view
        deliverable_count   berapa deliverable yang punya bacaan views

    `total_views` NULL -- bukan 0 -- kalau tidak satu deliverable pun punya
    bacaan views. Nol view yang TERUKUR juga menghasilkan CPV NULL lewat
    NULLIF: biaya dibagi nol bukan angka besar, melainkan angka yang tidak ada.
    """
    return f"""WITH {sql_engagement_per_deliverable(sumber, agregasi)},
    per_kol AS (
        SELECT d.campaign_kol_id                             AS campaign_kol_id,
               sum(perf.views)                               AS total_views,
               count(perf.views)                             AS deliverable_count
          FROM public.campaign_kol_deliverables d
          JOIN performa perf ON perf.deliverable_id = d.id
         GROUP BY 1
    )
    SELECT ck.id                AS campaign_kol_id,
           ck.campaign_id,
           ck.agency_kol_account_id,
           ck.deal_price,
           ck.currency,
           pk.total_views,
           pk.deliverable_count,
           {sql_cpv_ekspresi('ck.deal_price', 'pk.total_views')} AS cpv
      FROM public.campaign_kols ck
      LEFT JOIN per_kol pk ON pk.campaign_kol_id = ck.id
     WHERE (%(campaign_id)s::uuid IS NULL OR ck.campaign_id = %(campaign_id)s)
     ORDER BY cpv ASC NULLS LAST, ck.id"""
