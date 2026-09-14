"""EMV (Earned Media Value) — rentang nilai media dari engagement.

RUANG LINGKUP
=============
Modul ini HANYA menghitung. Ia tidak membaca database, tidak menulis kolom,
dan tidak menambah tabel. EMV adalah turunan murni dari engagement yang sudah
ada, jadi menyimpannya sebagai kolom berarti menyimpan angka yang bisa basi
tanpa ada yang tahu -- itu sebabnya tidak ada migration yang menyertai file
ini.

RUMUS
=====
    Engagement = likes + comments
    EMV min    = Engagement x 500 IDR
    EMV max    = Engagement x 2.000 IDR

Rentang, bukan satu angka. Rp500 dan Rp2.000 adalah batas bawah dan batas atas
nilai satu engagement yang disepakati; menampilkan satu titik saja akan
menyembunyikan bahwa selisih keduanya EMPAT KALI LIPAT.

KENAPA `shares` TIDAK IKUT
==========================
Ini keputusan yang disengaja, dan sengaja berbeda dari engagement yang dipakai
CPE.

`shares` hanya terisi di TikTok. Dari 503 post di `l2_gold.post_metric`, 291
post TikTok punya `shares` dan 212 post Instagram TIDAK -- bukan nol, tapi
tidak diketahui: post Instagram masuk lewat Apify, yang tidak punya field
`shares` sama sekali, dan `l0_raw.ig_media_snapshots_official` (sumber
Insights yang akan memuatnya) masih 0 baris.

Selama itu tidak berubah, memasukkan `shares` berarti engagement TikTok
dihitung dari tiga komponen sementara Instagram dari dua. EMV Instagram jadi
terlihat lebih rendah semata karena platformnya tidak mengirim satu field --
bukan karena kontennya berkinerja lebih buruk. Untuk metric yang dipakai
membandingkan kreator lintas platform, bias itu lebih merusak daripada
manfaat menambah komponen yang kontribusinya ~2,9% (diukur dari TikTok, satu-
satunya tempat ia bisa diukur).

Konsekuensinya: engagement EMV di sini TIDAK sama dengan
`campaign_cost_metrics.total_engagement` (yang memakai likes + comments +
shares untuk CPE). Perbedaan itu nyata dan dijaga test, bukan kelalaian.
Dengan hanya likes + comments, kedua platform diukur dengan penggaris yang
sama dan tidak ada lagi angka "batas bawah" yang perlu diberi penanda.

`saves`, `clicks`, `views`, `reach` dan `impressions` juga tidak masuk:
`saves` punya masalah cakupan yang sama dengan `shares`, `clicks` tidak ada di
DB, dan tiga sisanya jangkauan -- bukan interaksi.

KEADAAN YANG TIDAK BOLEH DIANGGAP NOL
=====================================
`likes_hidden` -- Instagram mengizinkan kreator menyembunyikan jumlah like.
Baris seperti itu menyimpan `likes = -1` sebagai penanda, BUKAN nilai. Ada 22
baris begini di `l2_gold.post_metric`. Menjumlahkannya apa adanya menghasilkan
engagement yang berkurang satu; memperlakukan -1 sebagai 0 menghasilkan
engagement yang mengaku terukur padahal tidak. Keduanya salah, jadi EMV baris
itu `None` -- tidak terukur, dan terbaca sebagai tidak terukur.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "EMV_MIN_PER_ENGAGEMENT",
    "EMV_MAX_PER_ENGAGEMENT",
    "MATA_UANG",
    "KOMPONEN_EMV",
    "DIKELUARKAN_DARI_EMV",
    "TOOLTIP_KALKULASI",
    "EmvPost",
    "engagement_untuk_emv",
    "emv_min",
    "emv_max",
    "emv_rentang",
    "sql_engagement_emv",
    "sql_emv_min",
    "sql_emv_max",
    "sql_emv_per_post",
    "sql_emv_per_kol",
    "ringkasan",
]


# ===========================================================================
# 1. Konstanta
# ===========================================================================
#: Batas bawah nilai satu engagement, rupiah.
EMV_MIN_PER_ENGAGEMENT = 500

#: Batas atas nilai satu engagement, rupiah.
EMV_MAX_PER_ENGAGEMENT = 2000

#: EMV selalu rupiah. Rate card di `l1_silver.unified_rate_card` juga IDR
#: (8.856 baris, satu-satunya currency), jadi tidak ada konversi di mana pun.
MATA_UANG = "IDR"

#: Yang dijumlahkan jadi engagement. HANYA dua -- lihat docstring modul.
KOMPONEN_EMV = ("likes", "comments")

#: Yang SENGAJA dikeluarkan, supaya penolakannya terbaca, bukan tersirat.
#: `shares` ada di sini karena cakupannya timpang antar platform, bukan karena
#: ia bukan engagement.
DIKELUARKAN_DARI_EMV = (
    "shares", "saves", "clicks", "views", "reach", "impressions",
)

#: Teks siap pakai untuk tooltip di dashboard. Ditaruh di sini supaya kalau
#: angkanya berubah, kalimatnya ikut berubah dari satu tempat yang sama.
TOOLTIP_KALKULASI = (
    "EMV dihitung berdasarkan Likes + Comments. "
    "CPE yang digunakan Rp500-Rp2.000 per engagement."
)


# ===========================================================================
# 2. Perhitungan
# ===========================================================================
def engagement_untuk_emv(
    likes: int | float | None,
    comments: int | float | None,
    likes_hidden: bool | None = False,
) -> float | None:
    """Engagement yang layak dipakai EMV, atau None kalau tidak terukur.

    None dikembalikan pada dua keadaan, dan HANYA dua:

    - `likes_hidden` benar, atau `likes` negatif. Jumlah like tidak diketahui,
      jadi totalnya tidak diketahui. Tidak ada tebakan yang jujur di sini.
    - Kedua komponen None. Tidak ada yang pernah diukur.

    Selain itu, komponen None dihitung 0.
    """
    if likes_hidden or (likes is not None and likes < 0):
        return None
    if likes is None and comments is None:
        return None
    return float(likes or 0) + float(comments or 0)


def emv_min(engagement: int | float | None) -> float | None:
    """Batas bawah EMV. None kalau engagement tidak terukur."""
    if engagement is None:
        return None
    return float(engagement) * EMV_MIN_PER_ENGAGEMENT


def emv_max(engagement: int | float | None) -> float | None:
    """Batas atas EMV. None kalau engagement tidak terukur."""
    if engagement is None:
        return None
    return float(engagement) * EMV_MAX_PER_ENGAGEMENT


def emv_rentang(
    engagement: int | float | None,
) -> tuple[float | None, float | None]:
    """`(emv_min, emv_max)` sekaligus, supaya keduanya tidak pernah terpisah."""
    return emv_min(engagement), emv_max(engagement)


@dataclass(frozen=True)
class EmvPost:
    """EMV satu post."""

    post_id: str
    social_account_id: str | None
    platform: str | None
    post_date: str | None
    likes: int | None
    comments: int | None
    likes_hidden: bool
    engagement: int | None
    emv_min: float | None
    emv_max: float | None
    mata_uang: str = MATA_UANG


# ===========================================================================
# 3. Ekspresi SQL
# ===========================================================================
# Dipakai supaya perhitungan yang sama bisa jalan di dalam query, tanpa
# menarik 503 baris ke Python hanya untuk dikalikan dua konstanta.
def sql_engagement_emv(alias: str = "m") -> str:
    """Engagement untuk EMV sebagai ekspresi SQL.

    `likes_hidden` dan `likes < 0` dipetakan ke NULL -- bukan ke 0 -- supaya
    baris yang tidak terukur tetap terbaca tidak terukur sampai ke hasil query.
    """
    return (
        f"CASE WHEN {alias}.likes_hidden IS TRUE OR {alias}.likes < 0 THEN NULL"
        f" ELSE coalesce({alias}.likes, 0) + coalesce({alias}.comments, 0) END"
    )


def sql_emv_min(ekspresi_engagement: str) -> str:
    """`engagement x 500`."""
    return f"({ekspresi_engagement}) * {EMV_MIN_PER_ENGAGEMENT}"


def sql_emv_max(ekspresi_engagement: str) -> str:
    """`engagement x 2000`."""
    return f"({ekspresi_engagement}) * {EMV_MAX_PER_ENGAGEMENT}"


#: Sumber tunggal EMV. Bukan TSDB, bukan rate card, bukan campaign cost.
SUMBER_EMV = "l2_gold.post_metric"

#: Dilarang jadi sumber EMV. Dipakai test sebagai penjaga.
SUMBER_TERLARANG = (
    "tsdb",
    "campaign_kols.deal_price",
    "campaign_kol_deliverables.subtotal",
    "campaign_orders.total_amount",
    "unified_rate_card.fee",
)


def sql_emv_per_post(filter_platform: bool = True) -> str:
    """EMV per post, grain paling halus yang datanya benar-benar ada.

    Tidak ada join: `l2_gold.post_metric` sudah memuat likes, comments,
    `likes_hidden` dan platform di baris yang sama.
    """
    eng = sql_engagement_emv("m")
    where = "WHERE (%(platform)s IS NULL OR m.platform = %(platform)s)" if filter_platform else ""
    return f"""
SELECT m.id,
       m.social_account_id,
       m.platform,
       m.post_date,
       m.likes,
       m.comments,
       coalesce(m.likes_hidden, false) AS likes_hidden,
       {eng} AS engagement,
       {sql_emv_min(eng)} AS emv_min,
       {sql_emv_max(eng)} AS emv_max
  FROM {SUMBER_EMV} m
  {where}
 ORDER BY m.post_date DESC NULLS LAST, m.id
""".strip()


def sql_emv_per_kol() -> str:
    """EMV per akun, dijumlahkan dari post yang engagement-nya TERUKUR.

    Post yang `likes_hidden` tidak ikut -- bukan dianggap nol. Jumlahnya
    dilaporkan terpisah lewat `post_tak_terukur` supaya pembaca tahu berapa
    banyak yang ditinggalkan, bukan menebak.
    """
    eng = sql_engagement_emv("m")
    return f"""
SELECT m.social_account_id,
       m.platform,
       count(*)                                        AS post_total,
       count({eng})                                    AS post_terukur,
       count(*) - count({eng})                         AS post_tak_terukur,
       sum({eng})                                      AS engagement,
       sum({eng}) * {EMV_MIN_PER_ENGAGEMENT}           AS emv_min,
       sum({eng}) * {EMV_MAX_PER_ENGAGEMENT}           AS emv_max
  FROM {SUMBER_EMV} m
 WHERE (%(social_account_id)s IS NULL
        OR m.social_account_id = %(social_account_id)s)
 GROUP BY m.social_account_id, m.platform
 ORDER BY sum({eng}) DESC NULLS LAST
""".strip()


def ringkasan() -> dict[str, object]:
    """Ringkasan definisi, dipakai dokumentasi, tooltip dan test."""
    return {
        "komponen": KOMPONEN_EMV,
        "dikeluarkan": DIKELUARKAN_DARI_EMV,
        "min_per_engagement": EMV_MIN_PER_ENGAGEMENT,
        "max_per_engagement": EMV_MAX_PER_ENGAGEMENT,
        "mata_uang": MATA_UANG,
        "sumber": SUMBER_EMV,
        "tooltip": TOOLTIP_KALKULASI,
    }
