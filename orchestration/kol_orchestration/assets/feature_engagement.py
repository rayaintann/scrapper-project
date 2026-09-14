"""Feature assets — engagement per akun (Fase 1).

Dua asset, satu per tabel:
    ig_engagement_analysis  -> feature.ig_engagement_analysis
    tt_engagement_analysis  -> feature.tt_engagement_analysis

Keduanya bergrain PER AKUN (`social_account_id`) dan membaca sumber yang sama:
`l1_silver.unified_post` untuk metriknya, `l1_silver.unified_profile` untuk
`followers_count` sebagai penyebut engagement rate.

============================================================================
SAMPEL: dua aturan yang sudah disepakati
============================================================================

    WHERE likes_hidden IS NOT TRUE AND is_collaboration IS NOT TRUE

`likes_hidden`  — Instagram memakai `likes = -1` sebagai sentinel "jumlah like
                  disembunyikan", bukan angka nol. Post-nya dikeluarkan dari
                  sampel, bukan dinolkan.
`is_collaboration` — pemilik asli post berbeda dari akun yang di-scrape, jadi
                  engagement-nya sebagian milik akun lain.

Keduanya sudah berupa KOLOM di `unified_post` (diisi migration 015 dan
`sp_build_unified_post()`), jadi asset ini cukup memfilter — tidak perlu
menurunkan ulang aturannya. Itu sebabnya aturannya dijadikan kolom: satu
definisi, dipakai semua konsumen.

Dampak pada data saat ini: Instagram 82 dari 130 post lolos, TikTok 91 dari 91.

============================================================================
KEPUTUSAN DESAIN
============================================================================

1. SATU SAMPEL UNTUK SEMUA ANGKA DALAM SATU BARIS.
   `posts_analyzed_count`, seluruh `total_*`, dan `engagement_rate` dihitung
   dari sampel yang sama, supaya angka dalam satu baris bisa direkonsiliasi.

2. AKUN TANPA SAMPEL TETAP DAPAT BARIS.
   Agregasi memakai `FILTER (WHERE lolos)` di atas SEMUA post akun, bukan
   `WHERE lolos` di klausa FROM. Akun yang seluruh post-nya terbuang tetap
   muncul dengan `posts_analyzed_count = 0` dan metrik NULL — supaya bedanya
   "sudah dianalisis, hasilnya tidak diketahui" dengan "belum pernah
   dianalisis" tetap terlihat.

3. KOLOM BLOCKED TIDAK DITULIS SAMA SEKALI.
   Tidak disebut di daftar INSERT, jadi tetap NULL. Tidak ditebak, tidak
   dinolkan. Yang dibiarkan NULL:
     ig: total_shares, total_saves  (unified_post.shares/saved 0/130 — actor
         Instagram tidak menyediakannya)
         reel_shares, story_replies, story_exits_rate  (Insights API)
         engagement_trend  (sampel terlalu jarang: 10 post/akun tersebar
                            rata-rata 297 hari)
     tt: engagement_trend  (alasan sama)

4. ER: NULL, BUKAN 0, KALAU TIDAK BISA DIHITUNG.
   Sampel kosong atau followers tidak diketahui -> NULL.
   Kolomnya `numeric(5,2)` (maks 999,99) sehingga hasilnya perlu di-clamp,
   TAPI `LEAST()` MENGABAIKAN argumen NULL — `LEAST(NULL, 999.99)` = 999.99.
   Karena itu clamp dibungkus `CASE WHEN ... IS NULL THEN NULL ELSE LEAST(...)`.
   Tanpa penjaga itu, akun tanpa sampel akan tercatat ber-engagement 999,99%.

5. UPSERT, BUKAN TRUNCATE.
   `ON CONFLICT (social_account_id) DO UPDATE` memakai constraint
   `uq_{ig,tt}_engagement_analysis` (migration 016). Rerun aman dan tidak
   menghapus akun yang kebetulan tidak ikut batch.
   Kolom turunan memakai penugasan LANGSUNG (`= EXCLUDED.x`), bukan
   `COALESCE(EXCLUDED.x, existing.x)`: hasil hitung NULL harus menimpa nilai
   lama, kalau tidak metriknya jadi basi.

6. AGREGASI DI SQL, BUKAN DI PYTHON.
   Data tidak ditarik ke Python lalu dikirim balik. Satu statement
   INSERT ... SELECT mengerjakan semuanya di server.

7. EMPAT METRIK VIEWS PUNYA SAMPELNYA SENDIRI DI ATAS SAMPEL YANG SAMA.
   Avg Views, Median Views, V2F dan L2V ditambahkan lewat migration 036.
   Semuanya tetap berangkat dari `lolos` yang sama (butir 1), tapi masing-
   masing menyempitkannya lagi karena penyebutnya berbeda:

       Avg / Median Views  views > 0
       V2F                 views > 0, followers diketahui dan > 0
       L2V                 views > 0, likes diketahui

   Syaratnya `views > 0`, BUKAN `IS NOT NULL`: di Instagram nilai 0 ternyata
   bukan hasil pengukuran melainkan cara actor melaporkan "tipe media ini
   tidak punya play count". Buktinya ada di blok `_VIEWS_VALID`.

   Penyempitan itu berlaku SIMETRIS di pembilang dan penyebut. Ini melanggar
   butir 1 secara harfiah -- tidak semua angka di satu baris lagi berasal dari
   sampel yang identik -- dan itu disengaja: `views` Instagram hanya ada untuk
   post video, jadi memaksakan satu sampel akan memperlakukan NULL sebagai 0.
   `views_analyzed_count` disimpan supaya penyebut yang dipakai tetap bisa
   dibaca dari baris itu sendiri, sehingga rekonsiliasi tetap mungkin.

   Rumus lengkapnya ada di blok komentar `_VIEW_METRICS` di bawah.
"""

from __future__ import annotations

from dagster import AssetKey, MetadataValue, Output, asset

import sys
from pathlib import Path

from kol_orchestration.resources import PostgresResource

# Root project di sys.path, pola yang sama dipakai audience.py dan
# gold_profile.py -- supaya pengali viral dibaca dari modul ambang alih-alih
# ditulis ulang sebagai angka telanjang di dalam SQL.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from metrics_thresholds import VIRAL_MULTIPLIER  # noqa: E402

GROUP = "feature"
_POST = AssetKey("unified_post")
_PROFILE = AssetKey("unified_profile")


# ---------------------------------------------------------------------------
# CTE bersama: followers per akun + seluruh post platform tsb beserta flag lolos
# ---------------------------------------------------------------------------
def _cte_dasar(platform_key: str) -> str:
    return f"""
    WITH post AS (
        SELECT u.social_account_id, u.likes, u.comments, u.views, u.shares,
               u.saved, u.media_type, u.posted_at,
               -- Sinyal berbayar, dibaca APA ADANYA dari L1. Tidak ada
               -- inferensi dari views tinggi, engagement, atau kata di
               -- caption: kalau platform tidak menyatakannya, jawabannya
               -- NULL. Lihat _PAID_RATIO.
               u.is_sponsored,
               -- followers PADA TANGGAL POST, bukan snapshot terbaru. Pola yang
               -- sama dipakai l2_gold.kol_metric_daily.followers_at_post_date dan
               -- l1_silver.sp_build_unified_post() (migration 024). NULL kalau
               -- post lebih tua dari snapshot profil pertama -- tidak ditebak.
               foll.followers_count,
               -- dua aturan sampel, sudah berupa kolom di unified_post
               (u.likes_hidden IS NOT TRUE AND u.is_collaboration IS NOT TRUE) AS lolos
        FROM l1_silver.unified_post u
        JOIN public.platforms pl
          ON pl.id = u.platform_id AND pl.key = '{platform_key}'
        LEFT JOIN LATERAL (
            SELECT pr.followers_count
            FROM l1_silver.unified_profile pr
            WHERE pr.social_account_id = u.social_account_id
              AND pr.date <= (u.posted_at AT TIME ZONE 'Asia/Jakarta')::date
            ORDER BY pr.date DESC
            LIMIT 1
        ) foll ON true
    )"""


# Engagement sesuai DEFINISI BISNIS: Like + Comment + Share/Repost/Quote.
# Save/Collect TIDAK termasuk. COALESCE per komponen wajib: tanpa itu satu
# komponen NULL membuang seluruh baris dari agregat -- dan `shares` Instagram
# memang selalu NULL, sehingga seluruh ER Instagram akan lenyap.
_ENG = "COALESCE(likes, 0) + COALESCE(comments, 0) + COALESCE(shares, 0)"

# ER per akun: penyebut ADITIF (jumlah followers-pada-tanggal-post tiap post),
# bukan avg(engagement) / followers-terbaru. Pembilang DISELARASKAN dengan
# penyebut -- hanya post yang followers-nya diketahui yang ikut, di kedua sisi.
# Pola yang sama dipakai kol_metric_monthly.engagement_for_er_sum.
_ER_AKUN = f"""round(
                 sum({_ENG}) FILTER (WHERE lolos AND followers_count IS NOT NULL)::numeric
                 / NULLIF(sum(followers_count)
                          FILTER (WHERE lolos AND followers_count IS NOT NULL), 0)
                 * 100, 2)"""


# ---------------------------------------------------------------------------
# Empat metrik views: Avg Views, Median Views, V2F, L2V.
#
# Identik untuk Instagram dan TikTok, jadi ditulis SEKALI dan dipakai dua kali.
# Kalau rumusnya nanti berubah, ia berubah di satu tempat -- alasan yang sama
# kenapa `_ER_AKUN` dan `_ENG` sudah berbentuk konstanta.
#
# ATURAN SAMPEL DASARNYA SAMA dengan ER: `lolos` (bukan likes_hidden, bukan
# kolaborasi). Di atasnya tiap metrik menambah syaratnya sendiri, dan syarat
# itu berlaku SIMETRIS di pembilang dan penyebut.
#
# ===========================================================================
# KENAPA PENYEBUTNYA BUKAN `posts_analyzed_count`
# ===========================================================================
#
# `views` TIDAK selalu ada. Instagram hanya melaporkan `videoPlayCount` untuk
# post video; foto dan carousel ber-`views = NULL`. Membagi dengan jumlah
# SELURUH post sampel sama saja memperlakukan NULL sebagai 0, dan Avg Views
# akun yang banyak posting foto akan tertarik ke bawah secara sistematis --
# bukan karena videonya sepi, tapi karena fotonya ikut dihitung.
#
# Karena itu penyebutnya `views_analyzed_count`, yaitu post lolos sampel yang
# `views IS NOT NULL`. Angkanya disimpan sebagai kolom supaya bisa diaudit dan
# supaya UI bisa menyebut basisnya tanpa query kedua.
#
# ===========================================================================
# NOL DAN NULL SAMA-SAMA BERARTI "TIDAK DIUKUR" DI SUMBER INI
# ===========================================================================
#
#   views IS NULL   tidak dilaporkan            -> tidak ikut ke mana pun
#   views = 0       juga tidak dilaporkan,      -> tidak ikut ke mana pun
#                   hanya datang sebagai nol
#
# Alasan lengkap beserta angka pembuktinya ada di blok `_VIEWS_VALID` di
# bawah. Ringkasnya: di Instagram, `views = 0` hanya muncul pada tipe media
# yang tidak pernah punya views positif satu kali pun.
#
# Efek sampingnya menguntungkan L2V: views tidak akan pernah menjadi penyebut
# nol, karena post seperti itu sudah keluar di level sampel -- sebelum
# pembagian, bukan ditambal sesudahnya.
#
# ===========================================================================
# KENAPA V2F MEMAKAI PENYEBUT ADITIF, BUKAN followers TERBARU
# ===========================================================================
#
# `_cte_dasar` sudah membawa `followers_count` PADA TANGGAL TAYANG tiap post
# (carry-forward snapshot <= posted_at). Memakai followers terbaru untuk post
# lama akan menghukum akun yang bertumbuh: video setahun lalu dibagi followers
# hari ini menghasilkan V2F yang terlalu kecil, dan makin salah makin cepat
# akunnya tumbuh.
#
# Bentuknya SUM(views)/SUM(followers) -- persis pola `_ER_AKUN` -- bukan
# AVG(views/followers). Rata-rata dari rasio memberi bobot sama pada post
# 100 views dan post 10 juta views; rasio dari jumlah memberi bobot sesuai
# ukurannya, dan hanya bentuk ini yang bisa direkonsiliasi dengan
# SUM(views) dan SUM(followers) yang tersimpan di baris yang sama.
#
# Post yang followers-nya TIDAK diketahui dikeluarkan dari KEDUA sisi. Kalau
# hanya dikeluarkan dari penyebut, views-nya tetap menumpuk di pembilang dan
# V2F meledak. `followers_count > 0` menutup akun ber-followers nol.
#
# ===========================================================================
# TANPA CLAMP, TANPA `LEAST`
# ===========================================================================
#
# `engagement_rate` bertipe numeric(5,2) sehingga perlu `LEAST(x, 999.99)`,
# dan clamp itu wajib dibungkus CASE karena `LEAST(NULL, 999.99)` = 999,99 --
# bug yang sudah dua kali muncul di project ini (butir 4 di docstring).
#
# Keempat kolom baru bertipe numeric(18,2)/numeric(12,4) yang muat jauh di
# atas nilai nyata mana pun, jadi tidak ada clamp sama sekali. Kelas bug itu
# tidak bisa muncul di sini.
#
# NULLIF(...) pada tiap penyebut menutup pembagian-dengan-nol: hasilnya NULL,
# yang justru jawaban yang benar ("tidak cukup data"), bukan 0 palsu dan bukan
# error. Postgres numeric tidak punya NaN/Infinity dari pembagian -- ia
# melempar `division_by_zero` -- sehingga NULLIF adalah penjaganya, dan tidak
# ada jalan lain nilai NaN/Infinity bisa masuk ke kolom ini.
# ---------------------------------------------------------------------------

# ===========================================================================
# SATU DEFINISI "VIEWS VALID", DIPAKAI KEEMPAT METRIK
# ===========================================================================
#
# Views dianggap terukur kalau NOT NULL *dan lebih besar dari nol*. Syarat
# kedua itu bukan kehati-hatian berlebihan -- ia dipilih berdasar bukti, dan
# ini buktinya (l1_silver.unified_post, post yang lolos sampel, 2026-09-09):
#
#     platform   media_type            n   views NULL   views=0   views>0
#     instagram  clips                69            0         0        69
#     instagram  carousel_container   68           58        10         0
#     instagram  feed                 22           12        10         0
#     instagram  (null)                6            6         0         0
#     tiktok     VIDEO               289            0         0       289
#     tiktok     CAROUSEL              2            0         0         2
#
# Baca baris carousel dan feed: tipe media itu TIDAK PERNAH menghasilkan views
# positif satu kali pun, dan tipe yang sama mengembalikan NULL (58, 12) maupun
# 0 (10, 10) untuk hal yang persis sama. Artinya `0` di situ bukan "tidak ada
# yang menonton" -- itu "Instagram tidak melaporkan play count untuk tipe ini",
# yang kebetulan datang sebagai angka nol dan bukan sebagai NULL.
#
# Membiarkan nol semu itu masuk = memasukkan NULL sebagai 0, persis yang tidak
# boleh terjadi. Akibatnya terukur pada data sekarang: `febbyrastanty` dan
# `bobbykertanegara` menghasilkan MEDIAN 0 padahal reel mereka rata-rata
# 163.252 dan 124.612 views -- separuh lebih sampel mereka adalah foto yang
# tidak pernah diukur.
#
# `clips` dan seluruh video TikTok tidak terpengaruh: 69/69 dan 291/291
# bernilai positif, jadi tidak ada satu pun views asli yang terbuang.
#
# KALAU SUATU SAAT SUMBERNYA BERUBAH -- misalnya Instagram mulai melaporkan
# 0 yang sungguh berarti nol penonton -- yang perlu diubah HANYA baris di
# bawah ini, dari `views > 0` menjadi `views IS NOT NULL`. Keempat metrik
# ikut berubah bersama karena semuanya membacanya dari sini.
_VIEWS_VALID = "views > 0"

# `views > 0` bernilai NULL untuk views NULL, dan FILTER membuang NULL, jadi
# satu syarat ini sekaligus menutup kasus NULL -- tidak perlu IS NOT NULL lagi.

# Penyebut Avg & Median.
_S_VIEWS = f"lolos AND {_VIEWS_VALID}"

# V2F: tambah syarat followers diketahui dan bukan nol.
_S_V2F = (f"lolos AND {_VIEWS_VALID} "
          "AND followers_count IS NOT NULL AND followers_count > 0")

# L2V: tambah syarat likes diketahui.
_S_L2V = f"lolos AND likes IS NOT NULL AND {_VIEWS_VALID}"

_N_VIEWS = f"count(*) FILTER (WHERE {_S_VIEWS})"

_AVG_VIEWS = f"round(avg(views) FILTER (WHERE {_S_VIEWS}), 2)"

# percentile_cont menginterpolasi, sehingga jumlah post GENAP menghasilkan
# rata-rata dua nilai tengah (4 dan 5 -> 4,5) dan bukan salah satunya. Itu
# definisi median yang dipakai di sini, dan alasan kolomnya berdesimal.
# percentile_disc akan mengembalikan 4 dan diam-diam membuang separuh jawaban.
_MEDIAN_VIEWS = f"""round(
                     (percentile_cont(0.5) WITHIN GROUP (ORDER BY views::float8)
                        FILTER (WHERE {_S_VIEWS}))::numeric, 2)"""

_V2F = f"""round(
             sum(views)           FILTER (WHERE {_S_V2F})::numeric
             / NULLIF(sum(followers_count) FILTER (WHERE {_S_V2F}), 0)
             * 100, 4)"""

_L2V = f"""round(
             sum(likes) FILTER (WHERE {_S_L2V})::numeric
             / NULLIF(sum(views) FILTER (WHERE {_S_L2V}), 0)
             * 100, 4)"""

#: Lima ekspresi, satu daftar, dipakai apa adanya di kedua platform.
_VIEW_METRICS = f"""{_N_VIEWS}      AS views_analyzed_count,
               {_AVG_VIEWS}    AS avg_views,
               {_MEDIAN_VIEWS} AS median_views,
               {_V2F}          AS view_to_follower_ratio,
               {_L2V}          AS like_to_view_ratio"""

#: Kolom yang sama untuk daftar INSERT dan klausa ON CONFLICT.
_VIEW_METRIC_COLS = ("views_analyzed_count", "avg_views", "median_views",
                     "view_to_follower_ratio", "like_to_view_ratio")

_VIEW_METRIC_INSERT = ", ".join(_VIEW_METRIC_COLS)
_VIEW_METRIC_SELECT = ", ".join(f"a.{c}" for c in _VIEW_METRIC_COLS)
# Penugasan LANGSUNG, bukan COALESCE(EXCLUDED.x, existing.x) -- butir 5 di
# docstring. Hasil hitung NULL HARUS menimpa nilai lama; kalau tidak, akun yang
# kehilangan post ber-views akan terus memajang Avg Views basi selamanya.
_VIEW_METRIC_UPDATE = ",\n        ".join(
    f"{c:<25} = EXCLUDED.{c}" for c in _VIEW_METRIC_COLS)


# ===========================================================================
# PAID RATIO, SHARE RATE, POST FREQUENCY  (migration 037)
# ===========================================================================
# Ditulis SEKALI dan dipakai di kedua platform, alasan yang sama dengan
# _VIEW_METRICS: kalau rumusnya berubah, ia berubah di satu tempat.
#
# ATURAN SAMPEL: ketiganya memakai `lolos` -- aturan yang SUDAH ADA dan sudah
# dipakai ER serta keempat metrik views (bukan likes_hidden, bukan kolaborasi).
# Tidak ada aturan sampel baru yang diperkenalkan di sini.
#
# ---------------------------------------------------------------------------
# PAID RATIO -- penyebutnya post yang SINYALNYA DIKETAHUI
# ---------------------------------------------------------------------------
# `is_sponsored` NULL berarti "tidak diketahui", bukan "organik". Memasukkan
# baris NULL ke penyebut akan menekan Paid Ratio ke bawah secara sistematis
# untuk akun yang datanya paling tidak lengkap -- persis kebalikan dari yang
# berguna. Pada data sekarang 10 dari 503 post ber-`is_sponsored` NULL.
#
# Karena itu `paid_signal_count` ikut disimpan: tanpa itu, Paid Ratio 0%
# tidak bisa dibedakan dari "tidak ada satu pun post yang diketahui".
_S_PAID = "lolos AND is_sponsored IS NOT NULL"
_PAID_N = f"count(*) FILTER (WHERE {_S_PAID} AND is_sponsored)"
_PAID_D = f"count(*) FILTER (WHERE {_S_PAID})"
_PAID_RATIO = f"round({_PAID_N}::numeric / NULLIF({_PAID_D}, 0) * 100, 2)"

# ---------------------------------------------------------------------------
# SHARE RATE -- penyebutnya ENGAGEMENT, bukan views
# ---------------------------------------------------------------------------
# Requirement yang berlaku: "Engagement = 100, Shares = 1 -> Share Rate = 1%".
# Jadi penyebutnya engagement, dan engagement memakai definisi bisnis yang
# SUDAH ADA di file ini (`_ENG` = Like + Comment + Share) -- definisi yang
# sama yang dipakai ER, sehingga kedua metrik bercerita tentang hal yang sama.
#
# CATATAN: prototype `AUTOME_2.html` memakai definisi LAIN untuk filter "High
# Share Rate", yaitu `shares/views >= 0,018`. Yang diikuti di sini adalah
# requirement di atas, bukan prototype. Perbedaan itu dilaporkan sebagai hal
# yang perlu diselaraskan, bukan diputuskan diam-diam di dalam kode.
#
# Penyebut disamakan dengan pembilang: hanya post yang `shares`-nya diketahui
# yang ikut di KEDUA sisi. Tanpa itu, akun dengan sebagian post ber-shares
# NULL akan dibagi engagement dari post yang share-nya tidak pernah dilaporkan.
# Instagram publik tidak pernah melaporkan shares sama sekali, jadi seluruh
# akun IG akan ber-share_rate NULL -- dan NULL memang jawaban yang benar.
_S_SHARE = "lolos AND shares IS NOT NULL"
_SHARE_N = f"sum(shares) FILTER (WHERE {_S_SHARE})"
_SHARE_D = f"sum({_ENG}) FILTER (WHERE {_S_SHARE})"
_SHARE_RATE = f"round({_SHARE_N}::numeric / NULLIF({_SHARE_D}, 0) * 100, 4)"

# ---------------------------------------------------------------------------
# POST FREQUENCY -- periode DIUKUR, bukan diasumsikan
# ---------------------------------------------------------------------------
# Penyebutnya rentang nyata dari post pertama sampai terakhir, bukan "30 hari
# terakhir" atau periode tetap lain. Alasannya: sampel post per akun di
# warehouse ini tidak seragam -- ada akun dengan post 2021 dan ada yang hanya
# 2026. Membagi keduanya dengan periode tetap yang sama akan membuat akun
# berdata panjang tampak jauh lebih jarang posting daripada kenyataannya.
#
# Dinormalisasi ke 30 hari supaya angkanya bisa dibaca sebagai "post per
# bulan", satuan yang diminta requirement (monthly view).
#
# NULL kalau rentangnya nol hari -- satu post, atau semua post di hari yang
# sama, tidak menentukan frekuensi apa pun. Menyebutnya "N post/bulan" dari
# satu titik adalah mengarang.
_S_FREQ = "lolos AND posted_at IS NOT NULL"
_FREQ_N = f"count(*) FILTER (WHERE {_S_FREQ})"
_OBS_DAYS = f"""(max(posted_at) FILTER (WHERE {_S_FREQ})::date
                 - min(posted_at) FILTER (WHERE {_S_FREQ})::date)"""
_POST_FREQ = f"round({_FREQ_N}::numeric / NULLIF({_OBS_DAYS}, 0) * 30, 2)"

#: Sembilan ekspresi, satu daftar, dipakai apa adanya di kedua platform.
_CALC_METRICS = f"""{_PAID_RATIO} AS paid_ratio,
               {_PAID_N}     AS paid_posts_count,
               {_PAID_D}     AS paid_signal_count,
               {_SHARE_RATE} AS share_rate,
               {_SHARE_D}    AS share_engagement_base,
               {_SHARE_N}    AS shares_total,
               {_POST_FREQ}  AS post_frequency_monthly,
               {_FREQ_N}     AS post_frequency_count,
               {_OBS_DAYS}   AS observation_days"""

_CALC_METRIC_COLS = ("paid_ratio", "paid_posts_count", "paid_signal_count",
                     "share_rate", "share_engagement_base", "shares_total",
                     "post_frequency_monthly", "post_frequency_count",
                     "observation_days")

_CALC_METRIC_INSERT = ", ".join(_CALC_METRIC_COLS)
_CALC_METRIC_SELECT = ", ".join(f"a.{c}" for c in _CALC_METRIC_COLS)
# Penugasan LANGSUNG, alasan yang sama dengan _VIEW_METRIC_UPDATE: hasil NULL
# harus menimpa nilai lama, bukan dipertahankan diam-diam.
_CALC_METRIC_UPDATE = ",\n        ".join(
    f"{c:<25} = EXCLUDED.{c}" for c in _CALC_METRIC_COLS)


# ===========================================================================
# SAVE RATE, VIRAL FREQUENCY, FORMAT DOMINAN  (migration 039)
# ===========================================================================
# ---------------------------------------------------------------------------
# SAVE RATE -- penyebutnya SAMA dengan Share Rate
# ---------------------------------------------------------------------------
#     saves / (likes + comments + shares) x 100
#
# Penyebutnya engagement, BUKAN views dan BUKAN followers. Dan `saves` sendiri
# TIDAK ikut masuk penyebut: definisi engagement yang berlaku di file ini
# (`_ENG`) memang tidak memasukkan save/collect, dan menambahkannya khusus
# untuk metrik ini akan membuat Save Rate dan Share Rate punya penyebut
# berbeda padahal keduanya menanyakan hal yang sejenis.
#
# Penyebut diselaraskan dengan pembilang, sama seperti Share Rate: hanya post
# yang `saved`-nya diketahui yang ikut di kedua sisi. Instagram publik tidak
# melaporkan saves sama sekali (0 dari 212 post), jadi seluruh akun IG
# ber-save_rate NULL -- dan NULL memang jawabannya, bukan 0.
_S_SAVE = "lolos AND saved IS NOT NULL"
_SAVE_N = f"sum(saved) FILTER (WHERE {_S_SAVE})"
_SAVE_D = f"sum({_ENG}) FILTER (WHERE {_S_SAVE})"
_SAVE_RATE = f"round({_SAVE_N}::numeric / NULLIF({_SAVE_D}, 0) * 100, 4)"

# ---------------------------------------------------------------------------
# VIRAL FREQUENCY -- ambang RELATIF terhadap median akun itu sendiri
# ---------------------------------------------------------------------------
#     viral bila views >= 3 x median views creator
#     viral_frequency = post viral / post ber-views x 100
#
# Pengali relatif, bukan angka views absolut: 100.000 views luar biasa untuk
# akun nano dan biasa saja untuk akun mega, jadi ambang absolut hanya akan
# menemukan akun besar. MEDIAN yang jadi acuan, bukan rata-rata -- rata-rata
# sudah tertarik ke atas oleh post viral yang justru sedang dicari, sehingga
# memakainya akan menyembunyikan gejalanya sendiri.
#
# Penyebutnya post ber-views (`_S_VIEWS`), sama dengan penyebut Avg/Median
# Views: post tanpa views tidak bisa dinilai viral atau tidak, jadi ia keluar
# dari kedua sisi.
#
# Ambangnya ikut disimpan supaya angkanya bisa diperiksa ulang tanpa
# menghitung mediannya lagi.
# Median TIDAK bisa dihitung di dalam FILTER agregat lain -- Postgres
# menolaknya dengan "aggregate functions are not allowed in FILTER". Jadi
# median dihitung satu kali di CTE `ambang_viral`, lalu post dibandingkan
# terhadapnya di CTE `viral`. Dua langkah, bukan satu ekspresi.
SQL_CTE_VIRAL = f"""
    ambang_viral AS (
        SELECT social_account_id,
               (percentile_cont(0.5) WITHIN GROUP (ORDER BY views::float8)
                  FILTER (WHERE {_S_VIEWS})) * {VIRAL_MULTIPLIER} AS ambang
        FROM post GROUP BY 1
    ),
    viral AS (
        SELECT p.social_account_id,
               round(av.ambang::numeric, 2) AS viral_threshold_views,
               count(*) FILTER (WHERE {_S_VIEWS.replace("lolos", "p.lolos").replace("views", "p.views")}
                                  AND p.views >= av.ambang) AS viral_post_count
        FROM post p
        JOIN ambang_viral av USING (social_account_id)
        GROUP BY 1, av.ambang
    )"""

#: Dihitung di SELECT akhir, di mana `viral_post_count` dan penyebutnya
#: (`views_analyzed_count`, penyebut yang sama dipakai Avg/Median Views)
#: sama-sama sudah tersedia sebagai kolom.
_VIRAL_FREQ_SELECT = ("round(v.viral_post_count::numeric "
                      "/ NULLIF(a.views_analyzed_count, 0) * 100, 2)")

# ---------------------------------------------------------------------------
# FORMAT DOMINAN -- normalisasi media_type
# ---------------------------------------------------------------------------
# Nilai mentah di data: 'VIDEO' (TikTok), 'clips' (IG Reels), 'feed' (IG),
# 'carousel_container' (IG), 'CAROUSEL', dan NULL.
#
# 'CAROUSEL' dan 'carousel_container' adalah format yang SAMA ditulis dua
# cara; membiarkannya menghasilkan dua kategori kembar di filter. Casing
# dinormalkan lebih dulu supaya varian huruf besar tidak menambah kategori
# ketiga.
#
# 'VIDEO' dan 'clips' digabung jadi Video: keduanya video, dan yang
# membedakan TikTok dari Reels adalah kolom `platform` yang sudah ada --
# mengulanginya di kolom format hanya menduplikasi informasi yang sama.
#
# Story TIDAK ada di sini, dan itu benar: `ig_stories_apify` bukan sumber yang
# dipakai rantai ini, jadi kategori Story akan selamanya kosong.
_FORMAT_NORM = """CASE lower(btrim(media_type))
        WHEN 'carousel_container' THEN 'Carousel'
        WHEN 'carousel'           THEN 'Carousel'
        WHEN 'video'              THEN 'Video'
        WHEN 'clips'              THEN 'Video'
        WHEN 'feed'               THEN 'Image'
        ELSE NULL
    END"""

#: Format terbanyak per akun. `mode()` mengabaikan NULL, jadi post yang
#: media_type-nya tidak dikenali tidak pernah jadi jawaban -- akun yang
#: SELURUH postnya tidak dikenali mendapat NULL, bukan kategori palsu.
_FORMAT_DOMINAN = (f"mode() WITHIN GROUP (ORDER BY {_FORMAT_NORM}) "
                   f"FILTER (WHERE lolos)")

_METRIK_039 = f"""{_SAVE_RATE}      AS save_rate,
               {_SAVE_N}         AS saves_total,
               {_FORMAT_DOMINAN} AS format_dominant"""

_M039_COLS = ("save_rate", "saves_total", "format_dominant")
_M039_INSERT = ", ".join(_M039_COLS)
_M039_SELECT = ", ".join(f"a.{c}" for c in _M039_COLS)
#: Tiga kolom viral datang dari CTE `viral`, bukan dari `agg`.
_M039_INSERT += ", viral_post_count, viral_frequency, viral_threshold_views"
_M039_SELECT += (", v.viral_post_count, " + _VIRAL_FREQ_SELECT
                 + ", v.viral_threshold_views")
_M039_UPDATE = (",\n        ").join(
    f"{c:<25} = EXCLUDED.{c}" for c in
    _M039_COLS + ("viral_post_count", "viral_frequency", "viral_threshold_views"))


# --- Instagram --------------------------------------------------------------
SQL_IG = _cte_dasar("instagram") + "," + SQL_CTE_VIRAL + f""",
    agg AS (
        SELECT social_account_id,
               count(*) FILTER (WHERE lolos)                                AS n_sampel,
               sum(likes)    FILTER (WHERE lolos)                           AS total_likes,
               sum(comments) FILTER (WHERE lolos)                           AS total_comments,
               sum(views)    FILTER (WHERE lolos AND media_type = 'clips')  AS reel_plays,
               {_ER_AKUN}                                               AS er_mentah,
               -- Avg/Median Views, V2F, L2V. Penyebutnya post ber-views, BUKAN
               -- n_sampel, dan BUKAN hanya 'clips' seperti reel_plays di atas:
               -- kalau sebuah post punya views, views itu nyata apa pun
               -- media_type-nya. Lihat blok _VIEW_METRICS.
               {_VIEW_METRICS},
               {_CALC_METRICS},
               {_METRIK_039}
        FROM post
        GROUP BY 1
    ),
    format AS (
        SELECT social_account_id,
               jsonb_object_agg(media_type,
                   jsonb_build_object('posts', n, 'avg_engagement', avg_eng)
               ) AS format_performance
        FROM (
            SELECT social_account_id, media_type, count(*) AS n,
                   round(avg({_ENG}), 2) AS avg_eng
            FROM post WHERE lolos AND media_type IS NOT NULL
            GROUP BY 1, 2
        ) x GROUP BY 1
    ),
    heatmap AS (
        SELECT social_account_id,
               jsonb_agg(jsonb_build_object(
                   'dow', dow, 'hour', jam, 'posts', n, 'avg_engagement', avg_eng
               ) ORDER BY dow, jam) AS heat
        FROM (
            -- WIB, mengikuti tampilan UI
            SELECT social_account_id,
                   EXTRACT(DOW  FROM posted_at AT TIME ZONE 'Asia/Jakarta')::int AS dow,
                   EXTRACT(HOUR FROM posted_at AT TIME ZONE 'Asia/Jakarta')::int AS jam,
                   count(*) AS n, round(avg({_ENG}), 2) AS avg_eng
            FROM post WHERE lolos AND posted_at IS NOT NULL
            GROUP BY 1, 2, 3
        ) y GROUP BY 1
    )
    INSERT INTO feature.ig_engagement_analysis (
        social_account_id, analyzed_at, posts_analyzed_count,
        total_likes, total_comments, reel_plays,
        engagement_rate, format_performance, best_posting_time_heatmap,
        {_VIEW_METRIC_INSERT},
        {_CALC_METRIC_INSERT},
        {_M039_INSERT},
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): total_shares, total_saves,
        -- reel_shares, story_replies, story_exits_rate, engagement_trend
    )
    SELECT a.social_account_id, now(), a.n_sampel,
           a.total_likes, a.total_comments, a.reel_plays,
           -- LEAST() mengabaikan NULL; penjaga CASE wajib
           CASE WHEN a.er_mentah IS NULL THEN NULL
                ELSE LEAST(a.er_mentah, 999.99) END,
           f.format_performance, h.heat,
           -- Tanpa clamp: tipenya muat, jadi tidak ada LEAST yang bisa salah.
           {_VIEW_METRIC_SELECT},
           {_CALC_METRIC_SELECT},
           {_M039_SELECT},
           now(), now()
    FROM agg a
    LEFT JOIN viral   v USING (social_account_id)
    LEFT JOIN format  f USING (social_account_id)
    LEFT JOIN heatmap h USING (social_account_id)
    ON CONFLICT (social_account_id) DO UPDATE SET
        analyzed_at               = EXCLUDED.analyzed_at,
        posts_analyzed_count      = EXCLUDED.posts_analyzed_count,
        total_likes               = EXCLUDED.total_likes,
        total_comments            = EXCLUDED.total_comments,
        reel_plays                = EXCLUDED.reel_plays,
        engagement_rate           = EXCLUDED.engagement_rate,
        format_performance        = EXCLUDED.format_performance,
        best_posting_time_heatmap = EXCLUDED.best_posting_time_heatmap,
        {_VIEW_METRIC_UPDATE},
        {_CALC_METRIC_UPDATE},
        {_M039_UPDATE},
        updated_at                = now()
"""

# --- TikTok -----------------------------------------------------------------
# Tabelnya tidak punya analyzed_at, format_performance, maupun reel_plays,
# tapi PUNYA total_views/total_shares/total_saves yang Instagram tidak punya.
SQL_TT = _cte_dasar("tiktok") + "," + SQL_CTE_VIRAL + f""",
    agg AS (
        SELECT social_account_id,
               count(*) FILTER (WHERE lolos)      AS n_sampel,
               sum(views)    FILTER (WHERE lolos) AS total_views,
               sum(likes)    FILTER (WHERE lolos) AS total_likes,
               sum(comments) FILTER (WHERE lolos) AS total_comments,
               sum(shares)   FILTER (WHERE lolos) AS total_shares,
               sum(saved)    FILTER (WHERE lolos) AS total_saves,
               {_ER_AKUN} AS er_mentah,
               -- Rumus yang SAMA PERSIS dengan Instagram. Perhatikan bahwa
               -- avg_views TIDAK sama dengan total_views/videos_analyzed_count
               -- di baris yang sama: penyebut yang itu menghitung semua video
               -- lolos sampel, penyebut avg_views hanya yang ber-views.
               -- Pada data TikTok keduanya biasanya sama besar karena views
               -- TikTok terisi 91/91, tapi keduanya tetap dihitung terpisah
               -- supaya satu video tanpa views tidak diam-diam merusak angka.
               {_VIEW_METRICS},
               {_CALC_METRICS},
               {_METRIK_039}
        FROM post
        GROUP BY 1
    ),
    heatmap AS (
        SELECT social_account_id,
               jsonb_agg(jsonb_build_object(
                   'dow', dow, 'hour', jam, 'posts', n, 'avg_engagement', avg_eng
               ) ORDER BY dow, jam) AS heat
        FROM (
            SELECT social_account_id,
                   EXTRACT(DOW  FROM posted_at AT TIME ZONE 'Asia/Jakarta')::int AS dow,
                   EXTRACT(HOUR FROM posted_at AT TIME ZONE 'Asia/Jakarta')::int AS jam,
                   count(*) AS n, round(avg({_ENG}), 2) AS avg_eng
            FROM post WHERE lolos AND posted_at IS NOT NULL
            GROUP BY 1, 2, 3
        ) y GROUP BY 1
    )
    INSERT INTO feature.tt_engagement_analysis (
        social_account_id, videos_analyzed_count,
        total_views, total_likes, total_comments, total_shares, total_saves,
        engagement_rate, best_posting_time_heatmap,
        {_VIEW_METRIC_INSERT},
        {_CALC_METRIC_INSERT},
        {_M039_INSERT},
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): engagement_trend
    )
    SELECT a.social_account_id, a.n_sampel,
           a.total_views, a.total_likes, a.total_comments,
           a.total_shares, a.total_saves,
           CASE WHEN a.er_mentah IS NULL THEN NULL
                ELSE LEAST(a.er_mentah, 999.99) END,
           h.heat,
           {_VIEW_METRIC_SELECT},
           {_CALC_METRIC_SELECT},
           {_M039_SELECT},
           now(), now()
    FROM agg a
    LEFT JOIN viral   v USING (social_account_id)
    LEFT JOIN heatmap h USING (social_account_id)
    ON CONFLICT (social_account_id) DO UPDATE SET
        videos_analyzed_count     = EXCLUDED.videos_analyzed_count,
        total_views               = EXCLUDED.total_views,
        total_likes               = EXCLUDED.total_likes,
        total_comments            = EXCLUDED.total_comments,
        total_shares              = EXCLUDED.total_shares,
        total_saves               = EXCLUDED.total_saves,
        engagement_rate           = EXCLUDED.engagement_rate,
        best_posting_time_heatmap = EXCLUDED.best_posting_time_heatmap,
        {_VIEW_METRIC_UPDATE},
        {_CALC_METRIC_UPDATE},
        {_M039_UPDATE},
        updated_at                = now()
"""


# --- Statistik untuk metadata Dagster ---------------------------------------
def _sql_stats(platform_key: str) -> str:
    return _cte_dasar(platform_key) + f"""
    SELECT count(DISTINCT social_account_id)                          AS akun,
           count(*)                                                   AS post_total,
           count(*) FILTER (WHERE lolos)                              AS post_sampel,
           count(*) FILTER (WHERE NOT lolos)                          AS post_dibuang,
           count(DISTINCT social_account_id) FILTER (WHERE followers_count IS NULL
                                                       OR followers_count = 0)
                                                                      AS akun_tanpa_followers,
           -- Cakupan keempat metrik views. Dilaporkan tiap run supaya kalau
           -- Avg Views kosong untuk banyak akun, penyebabnya kelihatan di
           -- metadata dan tidak perlu ditebak dari UI.
           count(*) FILTER (WHERE {_S_VIEWS})                          AS post_ber_views,
           count(*) FILTER (WHERE lolos AND views IS NULL)             AS post_tanpa_views,
           count(*) FILTER (WHERE lolos AND views = 0)                 AS post_views_nol,
           count(DISTINCT social_account_id)
               FILTER (WHERE {_S_VIEWS})                               AS akun_dapat_avg_views,
           count(DISTINCT social_account_id)
               FILTER (WHERE {_S_V2F})                                 AS akun_dapat_v2f
    FROM post
    """



# ===========================================================================
# TOPIK KONTEN  (migration 039)
# ===========================================================================
# Satu-satunya bagian file ini yang TIDAK berupa SQL, dan itu terpaksa:
# klasifikasinya memakai leksikon `audience_inference.INTEREST` yang hidup di
# Python. Menyalin ratusan kata kunci ke dalam SQL akan membuat dua leksikon
# yang harus dirawat bersamaan -- persis yang dihindari di seluruh file ini.
#
# Jalannya SETELAH upsert utama, sebagai UPDATE terpisah atas tabel yang sama.
# Bukan pipeline baru, bukan tabel baru: satu pass tambahan di asset yang sama.
#
# ATURAN SAMPEL sama dengan metrik lain (`lolos`), dan sumbernya HANYA caption
# + hashtag. Username dan display name tidak pernah dibaca -- "@nasigoreng.id"
# bukan bukti bahwa kontennya tentang makanan.
SQL_POST_UNTUK_TOPIK = """
    SELECT u.social_account_id, u.caption, u.hashtags
      FROM l1_silver.unified_post u
      JOIN public.platforms pl ON pl.id = u.platform_id AND pl.key = %s
     WHERE u.likes_hidden IS NOT TRUE AND u.is_collaboration IS NOT TRUE
"""

#: Kategori roster sebagai CADANGAN, dan hanya kalau tidak satu pun post bisa
#: diklasifikasikan. Ditandai berbeda di `content_topic_source` karena memang
#: bukan hasil klasifikasi konten: kategori creator ditetapkan manusia saat
#: impor roster, dan menyamakannya dengan topik konten akan menyesatkan.
SQL_KATEGORI_FALLBACK = """
    SELECT ksa.social_account_id,
           min(c.taxonomy_key) AS taxonomy_key
      FROM public.kol_social_account ksa
      JOIN public.kol_directory k ON k.id = ksa.kol_id
      JOIN public.kol_categories c ON c.id = ANY(k.category_ids)
     WHERE c.taxonomy_key IS NOT NULL
     GROUP BY 1
"""


def _tulis_topik_konten(conn, platform_key: str, tabel: str) -> dict:
    """Klasifikasi topik per post, ambil modus per akun, tulis ke feature.

    Mengembalikan ringkasan untuk metadata asset.
    """
    from collections import Counter

    from audience_inference import topik_konten

    per_akun: dict = {}
    with conn.cursor() as cur:
        cur.execute(SQL_POST_UNTUK_TOPIK, (platform_key,))
        for sid, caption, hashtags in cur.fetchall():
            if sid is None:
                continue
            t = topik_konten(caption, hashtags)
            if t:
                per_akun.setdefault(str(sid), Counter())[t] += 1

        cur.execute(SQL_KATEGORI_FALLBACK)
        fallback = {str(r[0]): r[1] for r in cur.fetchall()}

        cur.execute(f"SELECT social_account_id FROM {tabel}")
        semua = [str(r[0]) for r in cur.fetchall()]

        baris = []
        for sid in semua:
            hit = per_akun.get(sid)
            if hit:
                # Modus; seri dipecah menurut abjad supaya hasilnya
                # deterministik antar-run, bukan bergantung urutan baris.
                topik = sorted(hit.items(), key=lambda x: (-x[1], x[0]))[0][0]
                baris.append((topik, "content", sum(hit.values()), sid))
            elif fallback.get(sid):
                baris.append((fallback[sid], "creator_category_fallback", 0, sid))
            else:
                # Tidak ditebak. NULL, bukan 'unknown' -- kategori palsu akan
                # ikut muncul di filter seolah sebuah pilihan yang sah.
                baris.append((None, None, 0, sid))

        cur.executemany(
            f"""UPDATE {tabel}
                   SET content_topic = %s, content_topic_source = %s,
                       content_topic_posts = %s, updated_at = now()
                 WHERE social_account_id = %s""",
            baris,
        )
    dari_konten = sum(1 for b in baris if b[1] == "content")
    dari_fallback = sum(1 for b in baris if b[1] == "creator_category_fallback")
    return {"topik_dari_konten": dari_konten,
            "topik_dari_kategori_roster": dari_fallback,
            "topik_tidak_diketahui": len(baris) - dari_konten - dari_fallback}


def _jalankan(postgres: PostgresResource, platform_key: str, sql_upsert: str,
              tabel: str) -> Output:
    """Hitung statistik, jalankan UPSERT, lalu laporkan metadata.

    Sumber kosong TIDAK dianggap gagal: asset selesai dengan 0 baris dan
    metadata yang menjelaskan kenapa. Merah palsu tiap hari membuat orang
    berhenti memperhatikan dashboard.
    """
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_sql_stats(platform_key))
            (akun, post_total, post_sampel, post_dibuang, akun_tanpa_foll,
             post_ber_views, post_tanpa_views, post_views_nol,
             akun_avg_views, akun_v2f) = cur.fetchone()

            if post_total == 0:
                conn.rollback()
                return Output(
                    0,
                    metadata={
                        "tabel": tabel,
                        "baris_ditulis": 0,
                        "catatan": MetadataValue.text(
                            f"Tidak ada post {platform_key} di l1_silver.unified_post — "
                            "tidak ada yang bisa diagregasi. Bukan kegagalan."
                        ),
                    },
                )

            cur.execute(sql_upsert)
            ditulis = cur.rowcount
        # Pass kedua: topik konten. Setelah upsert supaya barisnya sudah
        # ada, dan di dalam transaksi yang SAMA -- kalau klasifikasinya
        # gagal, agregat numeriknya ikut batal, bukan tersimpan separuh.
        ringkas_topik = _tulis_topik_konten(conn, platform_key, tabel)
        conn.commit()
    finally:
        conn.close()

    return Output(
        ditulis,
        metadata={
            **ringkas_topik,
            "tabel": tabel,
            "baris_ditulis": ditulis,
            "akun": akun,
            "post_total": post_total,
            "post_masuk_sampel": post_sampel,
            "post_dibuang_aturan_A_B": post_dibuang,
            "akun_tanpa_followers_ER_null": akun_tanpa_foll,
            # Cakupan Avg/Median Views, V2F, L2V.
            "post_ber_views_penyebut_avg": post_ber_views,
            "post_tanpa_views_tidak_ikut": post_tanpa_views,
            "post_views_nol_ikut_avg_bukan_L2V": post_views_nol,
            "akun_dapat_avg_median_views": akun_avg_views,
            "akun_dapat_v2f": akun_v2f,
        },
    )


@asset(
    name="ig_engagement_analysis",
    group_name=GROUP,
    deps=[_POST, _PROFILE],
    kinds={"postgres"},
    description=(
        "feature.ig_engagement_analysis — engagement per akun Instagram. "
        "Sampel mengecualikan post ber-likes_hidden dan post kolaborasi. "
        "Menghitung juga Avg Views, Median Views, V2F dan L2V; penyebutnya "
        "views_analyzed_count (post ber-views), bukan posts_analyzed_count — "
        "Instagram hanya melaporkan views untuk post video. "
        "total_shares/total_saves/reel_shares/story_*/engagement_trend sengaja "
        "dibiarkan NULL (sumbernya belum ada)."
    ),
)
def ig_engagement_analysis(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "instagram", SQL_IG, "feature.ig_engagement_analysis")


@asset(
    name="tt_engagement_analysis",
    group_name=GROUP,
    deps=[_POST, _PROFILE],
    kinds={"postgres"},
    description=(
        "feature.tt_engagement_analysis — engagement per akun TikTok. "
        "TikTok menyediakan shares dan saved yang Instagram tidak punya. "
        "Menghitung juga Avg Views, Median Views, V2F dan L2V dengan rumus "
        "yang sama persis seperti Instagram. "
        "engagement_trend sengaja dibiarkan NULL (sampel terlalu jarang)."
    ),
)
def tt_engagement_analysis(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "tiktok", SQL_TT, "feature.tt_engagement_analysis")


feature_engagement_assets = [ig_engagement_analysis, tt_engagement_analysis]
