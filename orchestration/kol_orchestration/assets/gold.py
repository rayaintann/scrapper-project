"""Asset L2 Gold — rekap harian dan bulanan per KOL.

Dua asset, berantai:

    kol_metric_daily   -> l2_gold.kol_metric_daily     (SCRUM-513)
    kol_metric_monthly -> l2_gold.kol_metric_monthly   (SCRUM-516)

`kol_metric_daily` bergrain (social_account_id, platform, metric_date) dan
membaca `l1_silver.unified_post` + `l1_silver.unified_profile`.

`kol_metric_monthly` bergrain (social_account_id, platform, month_start) dan
membaca HANYA `kol_metric_daily` — tidak pernah kembali ke L1. Keputusan
desainnya ada di blok komentar tersendiri di bawah, sebelum `_CTE_BULANAN`.

============================================================================
KEPUTUSAN DESAIN — kol_metric_daily
============================================================================

1. `metric_date` DARI `posted_at`, BUKAN `date`.
   `unified_post.date` adalah tanggal SCRAPE — seluruh 221 baris bernilai
   2026-08-20, jadi memakainya menghasilkan tabel "harian" dengan satu tanggal.
   `posted_at` punya 68 tanggal berbeda (2021-02-18 s.d. 2026-08-20).

   Dikonversi ke WIB lebih dulu (`AT TIME ZONE 'Asia/Jakarta'`), mengikuti
   konvensi referensi. Bukan formalitas: konversi itu memindahkan 2 baris
   Instagram ke tanggal berbeda (98 -> 100 pasangan akun-tanggal).

2. DIGERAKKAN POST, BUKAN `FULL OUTER JOIN` DENGAN PROFIL.
   `sp_build_brand_metric_daily()` di autometric_v2 memakai FULL OUTER JOIN
   supaya hari tanpa post tapi ada pergerakan follower tetap dapat baris —
   masuk akal di sana, snapshot profilnya harian dan kontinu (31 dari 57
   barisnya memang hari tanpa post).

   Data kita tidak begitu: 1.949 dari 1.971 akun berprofil TIDAK punya post
   sama sekali. FULL OUTER JOIN akan menghasilkan ~92% baris kosong yang
   menyiratkan deret waktu yang tidak ada. Jadi cakupannya dibatasi ke
   akun-hari yang benar-benar punya konten: 160 baris, semuanya bermakna.

   Kalau nanti scraping profil sudah harian dan menjangkau akun yang sama,
   beralih ke FULL OUTER JOIN cuma perubahan satu klausa di CTE `harian`.

3. FOLLOWER LEWAT CARRY-FORWARD, BUKAN SNAPSHOT TANGGAL-SAMA.
   Diuji langsung pada data nyata:

       snapshot tanggal sama (pola brand_metric_daily) : 10 dari 160 (6%)
       carry-forward (pola post_metric.followers_on_post_day) : 61 dari 160 (38%)

   Enam kali lebih baik. Ambil `followers_count` dari snapshot `unified_profile`
   TERAKHIR dengan `date <= metric_date`. NULL kalau post lebih tua dari
   snapshot pertama — persis yang didokumentasikan referensi.

4. ATURAN SAMPEL YANG SUDAH BERLAKU IKUT DIPAKAI.
   Post ber-`likes_hidden` atau `is_collaboration` dikeluarkan dari SELURUH
   `*_sum` lewat `FILTER (WHERE lolos)`, tapi tetap dihitung di `post_count`.
   Itu sebabnya ada `posts_in_sample` — pola yang sama dengan
   `posts_analyzed_count` di `ig_engagement_analysis`.

   Bukan teori: `raffinagita1717` pada 2026-08-19 punya 6 post, hanya 2 layak.

5. NULL, BUKAN 0, UNTUK SUMBER YANG TIDAK TERSEDIA.
   Referensi membungkus semua dengan `COALESCE(...,0)` — aman di sana karena
   L1-nya terisi. Di sini `shares_sum = 0` untuk Instagram akan berbunyi
   "tidak ada yang membagikan", padahal artinya "tidak diketahui".

   `SUM()` Postgres sudah melakukan hal yang benar tanpa `COALESCE`:
   mengembalikan NULL kalau semua input NULL. Jadi `shares_sum` otomatis NULL
   untuk Instagram (0/130 di sumber) dan terisi untuk TikTok (91/91).

6. ENGAGEMENT MENGIKUTI DEFINISI BISNIS: `Like + Comment + Share/Repost/Quote`.
   Save/Collect TIDAK termasuk. Menyimpan post adalah tindakan pribadi, bukan
   penyebaran ulang, jadi bukan bagian dari Engagement. `saves_sum` tetap
   dihitung dan disimpan di kolomnya sendiri sebagai metrik terpisah — yang
   dihentikan hanya penjumlahannya ke `engagement_sum`.

   Sebelum perbaikan ini rumusnya `likes + comments + shares + saves`, disalin
   dari `sp_build_brand_metric_daily()` di database referensi. Instagram tidak
   terdampak (shares & saves 0/130), TikTok kelebihan 2.639.563 di 60/60 baris
   — rata-rata +3,73%, maksimum +12,41%.

   Konsekuensi yang perlu diketahui: Instagram tetap belum punya komponen
   Share sampai Insights API tersambung, jadi `engagement_sum` Instagram
   efektif hanya `likes + comments` dan understated terhadap definisi.

6b. `engagement_sum` NULL KALAU TIDAK ADA SAMPEL.
   Rumus engagement memakai `COALESCE` per komponen (mengikuti referensi:
   "komponen NULL dianggap 0"), jadi tanpa penjaga ia akan menghasilkan 0
   untuk hari yang seluruh post-nya tersaring — dan 0 berarti "tidak ada
   interaksi", bukan "tidak ada sampel". Ini ketahuan saat menghitung contoh
   dari data nyata, bukan dari membaca kode.

   Karena itu seluruh blok engagement dibungkus
   `CASE WHEN posts_in_sample = 0 THEN NULL ELSE ... END`.

7. ER SEBAGAI FRAKSI 0..1, BUKAN PERSEN.
   Mengikuti konvensi `er_*` referensi, yang secara eksplisit menandai
   `engagement_rate` skala persen sebagai "legacy, jangan dipakai". Namanya
   (`er_followers_daily`, bukan `engagement_rate`) yang membedakannya dari
   kolom persen di layer feature.

   Komponen additive-nya ikut disimpan: rentang N hari WAJIB dihitung
   `SUM(engagement_sum) / SUM(followers_denom_sum)`, bukan rata-rata kolom
   harian — rasio tidak additive.

8. KOLOM BLOCKED TIDAK DITULIS SAMA SEKALI.
   `reach_sum`, `er_reach_daily`, `reposts_sum`, `followers_growth` tidak
   disebut di daftar INSERT, jadi tetap NULL. Tidak ditebak, tidak dinolkan.
   Sumbernya masing-masing 0/221, 0/221, dan 0/1.971.

9. UPSERT DENGAN PENJAGA `IS DISTINCT FROM`.
   Menyalin pola `sp_build_brand_metric_daily()`: baris yang isinya tidak
   berubah TIDAK ditulis ulang, sehingga `updated_at` menandai perubahan
   sungguhan dan rerun benar-benar idempoten.

10. AGREGASI DI SQL, DI L2.
    Satu statement `INSERT ... SELECT` mengerjakan semuanya di server. Tidak
    ada kolom baru di L1, tidak ada procedure baru, tidak ada asset lain yang
    disentuh.
"""

from __future__ import annotations

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

GROUP = "l2_gold"
_POST = AssetKey("unified_post")
_PROFILE = AssetKey("unified_profile")


# ---------------------------------------------------------------------------
# CTE bersama untuk statistik dan upsert
# ---------------------------------------------------------------------------
_CTE = """
    WITH post AS (
        SELECT u.social_account_id,
               pl.key                                             AS platform,
               (u.posted_at AT TIME ZONE 'Asia/Jakarta')::date     AS metric_date,
               u.likes, u.comments, u.shares, u.saved, u.views,
               -- dua aturan sampel, sudah berupa kolom di unified_post
               (u.likes_hidden IS NOT TRUE
                AND u.is_collaboration IS NOT TRUE)                AS lolos
        FROM l1_silver.unified_post u
        JOIN public.platforms pl ON pl.id = u.platform_id
        WHERE u.posted_at IS NOT NULL
          AND u.social_account_id IS NOT NULL
    ),
    harian AS (
        SELECT social_account_id, platform, metric_date,
               count(*)                                  AS post_count,
               count(*) FILTER (WHERE lolos)              AS posts_in_sample,
               -- tanpa COALESCE: NULL kalau sumbernya memang tidak tersedia
               sum(likes)    FILTER (WHERE lolos)         AS likes_sum,
               sum(comments) FILTER (WHERE lolos)         AS comments_sum,
               sum(shares)   FILTER (WHERE lolos)         AS shares_sum,
               sum(saved)    FILTER (WHERE lolos)         AS saves_sum,
               sum(views)    FILTER (WHERE lolos)         AS views_sum
        FROM post
        GROUP BY 1, 2, 3
    ),
    dengan_follower AS (
        SELECT h.*,
               cf.followers_count AS followers_at_post_date
        FROM harian h
        LEFT JOIN LATERAL (
            -- carry-forward: snapshot TERAKHIR yang tidak melewati metric_date
            SELECT pr.followers_count
            FROM l1_silver.unified_profile pr
            WHERE pr.social_account_id = h.social_account_id
              AND pr.date <= h.metric_date
            ORDER BY pr.date DESC
            LIMIT 1
        ) cf ON true
    ),
    final AS (
        SELECT d.*,
               -- engagement: DEFINISI BISNIS = Like + Comment + Share/Repost/Quote.
               -- Save/Collect SENGAJA TIDAK IKUT -- menyimpan post adalah tindakan
               -- pribadi, bukan penyebaran ulang, jadi bukan bagian Engagement.
               -- `saves_sum` tetap disimpan sebagai metrik tersendiri di kolomnya.
               -- Komponen NULL dianggap 0, TAPI keseluruhannya NULL kalau tidak
               -- ada sampel sama sekali.
               CASE WHEN d.posts_in_sample = 0 THEN NULL
                    ELSE COALESCE(d.likes_sum, 0) + COALESCE(d.comments_sum, 0)
                       + COALESCE(d.shares_sum, 0)
               END AS engagement_sum,
               CASE WHEN d.posts_in_sample = 0 THEN NULL
                    ELSE COALESCE(d.likes_sum, 0) + COALESCE(d.comments_sum, 0)
               END AS engagement_public_sum,
               CASE WHEN d.posts_in_sample = 0 OR d.followers_at_post_date IS NULL
                    THEN NULL
                    ELSE d.followers_at_post_date * d.posts_in_sample
               END AS followers_denom_sum
        FROM dengan_follower d
    )"""

SQL_UPSERT = _CTE + """
    INSERT INTO l2_gold.kol_metric_daily (
        social_account_id, platform, metric_date,
        post_count, posts_in_sample,
        likes_sum, comments_sum, shares_sum, saves_sum, views_sum,
        engagement_sum, engagement_public_sum,
        followers_at_post_date, followers_denom_sum, er_followers_daily,
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): reach_sum, er_reach_daily,
        -- reposts_sum, followers_growth
    )
    SELECT f.social_account_id, f.platform, f.metric_date,
           f.post_count, f.posts_in_sample,
           f.likes_sum, f.comments_sum, f.shares_sum, f.saves_sum, f.views_sum,
           f.engagement_sum, f.engagement_public_sum,
           f.followers_at_post_date, f.followers_denom_sum,
           CASE WHEN f.followers_denom_sum IS NULL OR f.followers_denom_sum = 0
                     OR f.engagement_sum IS NULL
                THEN NULL
                ELSE round(f.engagement_sum::numeric / f.followers_denom_sum, 8)
           END,
           now(), now()
    FROM final f
    ON CONFLICT (social_account_id, platform, metric_date) DO UPDATE SET
        post_count             = EXCLUDED.post_count,
        posts_in_sample        = EXCLUDED.posts_in_sample,
        likes_sum              = EXCLUDED.likes_sum,
        comments_sum           = EXCLUDED.comments_sum,
        shares_sum             = EXCLUDED.shares_sum,
        saves_sum              = EXCLUDED.saves_sum,
        views_sum              = EXCLUDED.views_sum,
        engagement_sum         = EXCLUDED.engagement_sum,
        engagement_public_sum  = EXCLUDED.engagement_public_sum,
        followers_at_post_date = EXCLUDED.followers_at_post_date,
        followers_denom_sum    = EXCLUDED.followers_denom_sum,
        er_followers_daily     = EXCLUDED.er_followers_daily,
        updated_at             = now()
    -- Penjaga dari sp_build_brand_metric_daily(): baris yang isinya tidak
    -- berubah tidak ditulis ulang, jadi updated_at menandai perubahan nyata.
    WHERE kol_metric_daily.post_count        IS DISTINCT FROM EXCLUDED.post_count
       OR kol_metric_daily.posts_in_sample   IS DISTINCT FROM EXCLUDED.posts_in_sample
       OR kol_metric_daily.likes_sum         IS DISTINCT FROM EXCLUDED.likes_sum
       OR kol_metric_daily.comments_sum      IS DISTINCT FROM EXCLUDED.comments_sum
       OR kol_metric_daily.shares_sum        IS DISTINCT FROM EXCLUDED.shares_sum
       OR kol_metric_daily.saves_sum         IS DISTINCT FROM EXCLUDED.saves_sum
       OR kol_metric_daily.views_sum         IS DISTINCT FROM EXCLUDED.views_sum
       OR kol_metric_daily.engagement_sum    IS DISTINCT FROM EXCLUDED.engagement_sum
       OR kol_metric_daily.engagement_public_sum
                                             IS DISTINCT FROM EXCLUDED.engagement_public_sum
       OR kol_metric_daily.followers_at_post_date
                                             IS DISTINCT FROM EXCLUDED.followers_at_post_date
       OR kol_metric_daily.followers_denom_sum
                                             IS DISTINCT FROM EXCLUDED.followers_denom_sum
       OR kol_metric_daily.er_followers_daily
                                             IS DISTINCT FROM EXCLUDED.er_followers_daily
"""

SQL_STATS = _CTE + """
    -- `::bigint` pada tiap sum() BUKAN kosmetik: SUM(bigint) di PostgreSQL
    -- mengembalikan `numeric`, yang sampai ke Python sebagai Decimal, dan
    -- Decimal ditolak Dagster sebagai nilai metadata. count() aman karena
    -- sudah bigint.
    SELECT count(*)                                                  AS baris,
           count(DISTINCT social_account_id)                          AS akun,
           sum(post_count)::bigint                                    AS post_total,
           sum(posts_in_sample)::bigint                               AS post_sampel,
           (sum(post_count) - sum(posts_in_sample))::bigint           AS post_tersaring,
           count(*) FILTER (WHERE posts_in_sample = 0)                AS hari_tanpa_sampel,
           count(followers_at_post_date)                              AS dapat_follower,
           count(*) - count(followers_at_post_date)                   AS follower_null,
           min(metric_date)                                           AS tgl_awal,
           max(metric_date)                                           AS tgl_akhir
    FROM final
    """


def _jalankan(postgres: PostgresResource) -> Output:
    """Hitung statistik, jalankan UPSERT, lalu laporkan metadata.

    SENGAJA tanpa try/except: kalau SQL-nya gagal, asset harus ikut gagal.
    Sumber kosong TIDAK dianggap gagal — selesai dengan 0 baris dan penjelasan.
    """
    tabel = "l2_gold.kol_metric_daily"
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM l2_gold.kol_metric_daily")
            sebelum = cur.fetchone()[0]

            cur.execute(SQL_STATS)
            (baris, akun, post_total, post_sampel, post_tersaring,
             hari_tanpa_sampel, dapat_follower, follower_null,
             tgl_awal, tgl_akhir) = cur.fetchone()

            if baris == 0:
                conn.rollback()
                return Output(
                    0,
                    metadata={
                        "tabel": tabel,
                        "baris_ditulis": 0,
                        "catatan": MetadataValue.text(
                            "Tidak ada post ber-posted_at di l1_silver.unified_post — "
                            "tidak ada yang bisa diagregasi. Bukan kegagalan."
                        ),
                    },
                )

            cur.execute(SQL_UPSERT)
            ditulis = cur.rowcount

            cur.execute("SELECT count(*) FROM l2_gold.kol_metric_daily")
            sesudah = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return Output(
        sesudah,
        metadata={
            "tabel": tabel,
            "baris_sebelum": sebelum,
            "baris_sesudah": sesudah,
            "baris_disentuh_upsert": ditulis,
            "akun": akun,
            "rentang_tanggal": f"{tgl_awal} .. {tgl_akhir}",
            "post_total": post_total,
            "post_masuk_sampel": post_sampel,
            "post_tersaring_likes_hidden_kolaborasi": post_tersaring,
            "hari_tanpa_sampel_metrik_null": hari_tanpa_sampel,
            "baris_dapat_follower_carry_forward": dapat_follower,
            "baris_follower_null_post_lebih_tua": follower_null,
            "kolom_sengaja_null": MetadataValue.text(
                "reach_sum & er_reach_daily (unified_post.reach 0/221 — butuh "
                "Insights API); reposts_sum (0/221, IG-only); followers_growth "
                "(0/1.971 — tiap akun baru punya satu snapshot)."
            ),
        },
    )


@asset(
    name="kol_metric_daily",
    group_name=GROUP,
    deps=[_POST, _PROFILE],
    kinds={"postgres"},
    description=(
        "l2_gold.kol_metric_daily — rekap harian per KOL per platform, grain "
        "(social_account_id, platform, metric_date). metric_date = tanggal TAYANG "
        "(posted_at, WIB), bukan tanggal scrape. Metrik hanya dari post yang lolos "
        "aturan sampel; follower diambil carry-forward dari snapshot profil "
        "terakhir <= metric_date. er_followers_daily adalah fraksi 0..1. "
        "reach/reposts/followers_growth sengaja dibiarkan NULL."
    ),
)
def kol_metric_daily(postgres: PostgresResource) -> Output:
    return _jalankan(postgres)


# ===========================================================================
# kol_metric_monthly — rekap bulanan (SCRUM-516)
# ===========================================================================
#
# Sumbernya HANYA `l2_gold.kol_metric_daily`. Tidak mengagregasi ulang dari
# l1_silver: kalau rumusnya ditulis dua kali, dua-duanya harus ikut berubah
# setiap kali definisi metrik berubah, dan cepat atau lambat angkanya berbeda.
#
# KEPUTUSAN DESAIN
#
# 1. SUM TANPA `COALESCE`, sama seperti asset harian.
#    Sebulan penuh NULL tetap NULL. `shares_sum` akan NULL untuk seluruh
#    akun-bulan Instagram (35/35), terisi untuk seluruh TikTok.
#
# 2. `followers_eom` = SNAPSHOT HARI TERAKHIR, bukan rata-rata.
#    `DISTINCT ON (akun, platform, bulan) ORDER BY metric_date DESC` — pola
#    yang sama dipakai `syn_twitter_monthly_profile_metric()` (`last_followers`)
#    dan `syn_tiktok_profile_monthly()` (`MAX(latest_followers)`).
#
# 3. ER BULANAN DIHITUNG ULANG, TIDAK PERNAH `AVG` DARI HARIAN.
#    Dua referensi monthly di socmed_report saling bertentangan soal ini:
#    `syn_twitter_monthly_profile_metric()` memakai `AVG(er_aggregate)`,
#    sedangkan `syn_tiktok_profile_monthly()` menghitung ulang
#    `engagement / NULLIF(followers,0)`. Glosarium Autometric §10.2 menyebut
#    yang pertama sebagai pelanggaran kontrak. Diuji pada data kita: 18 dari 18
#    bulan menghasilkan angka berbeda, selisih rata-rata 0,88 poin persen dan
#    terbesar 8,17 poin persen. Yang dipakai di sini pola TikTok.
#
# 4. PEMBILANG ER DISELARASKAN DENGAN PENYEBUTNYA.
#    Bahkan `SUM(engagement_sum) / SUM(followers_denom_sum)` masih salah:
#    engagement ada untuk semua hari bersampel, tapi denominator hanya untuk
#    hari yang follower-nya diketahui. Pada cristiano Agustus 2026 itu
#    membagi engagement 3 hari dengan denominator 1 hari — 0,0998 alih-alih
#    0,0181, salah 5,5 kali lipat; 11 dari 18 bulan terdampak.
#
#        engagement_for_er_sum = SUM(engagement_sum)
#                                FILTER (WHERE followers_denom_sum IS NOT NULL)
#
#    `engagement_sum` tetap total sebenarnya; `engagement_for_er_sum` yang
#    sebanding dengan penyebut. Keduanya disimpan.
#
# 5. TIDAK ADA KOLOM MONTH-OVER-MONTH.
#    Data kita rata-rata 2,9-3,3 hari aktif per bulan dan bulannya tidak
#    berurutan, jadi `LAG()` akan membandingkan Agustus dengan bulan tersedia
#    sebelumnya yang bisa saja beberapa bulan lebih awal.
#
# 6. UPSERT DENGAN PENJAGA `IS DISTINCT FROM`, bukan TRUNCATE + INSERT.
#    Kedua referensi monthly memakai TRUNCATE; itu menghapus riwayat bulan yang
#    kebetulan tidak ikut batch dan membuat kegagalan di tengah meninggalkan
#    tabel kosong.

_CTE_BULANAN = """
    WITH bulanan AS (
        SELECT k.social_account_id,
               k.platform,
               date_trunc('month', k.metric_date)::date       AS month_start,
               count(*)                                        AS active_days,
               sum(k.post_count)                               AS post_count,
               sum(k.posts_in_sample)                          AS posts_in_sample,
               -- tanpa COALESCE: sebulan penuh NULL tetap NULL
               sum(k.likes_sum)                                AS likes_sum,
               sum(k.comments_sum)                             AS comments_sum,
               sum(k.shares_sum)                               AS shares_sum,
               sum(k.saves_sum)                                AS saves_sum,
               sum(k.views_sum)                                AS views_sum,
               sum(k.engagement_sum)                           AS engagement_sum,
               sum(k.engagement_public_sum)                    AS engagement_public_sum,
               sum(k.followers_denom_sum)                      AS followers_denom_sum,
               -- pembilang ER: HANYA hari yang penyebutnya diketahui
               sum(k.engagement_sum) FILTER (WHERE k.followers_denom_sum IS NOT NULL)
                                                               AS engagement_for_er_sum
        FROM l2_gold.kol_metric_daily k
        GROUP BY 1, 2, 3
    ),
    akhir_bulan AS (
        -- snapshot follower dari baris harian TERAKHIR dalam bulan itu
        SELECT DISTINCT ON (social_account_id, platform, date_trunc('month', metric_date))
               social_account_id,
               platform,
               date_trunc('month', metric_date)::date AS month_start,
               followers_at_post_date                  AS followers_eom
        FROM l2_gold.kol_metric_daily
        WHERE followers_at_post_date IS NOT NULL
        ORDER BY social_account_id, platform,
                 date_trunc('month', metric_date), metric_date DESC
    ),
    final AS (
        SELECT b.*, a.followers_eom
        FROM bulanan b
        LEFT JOIN akhir_bulan a USING (social_account_id, platform, month_start)
    )"""

SQL_UPSERT_BULANAN = _CTE_BULANAN + """
    INSERT INTO l2_gold.kol_metric_monthly (
        social_account_id, platform, month_start,
        year, month, month_year, quarter, year_quarter,
        active_days, post_count, posts_in_sample,
        likes_sum, comments_sum, shares_sum, saves_sum, views_sum,
        engagement_sum, engagement_public_sum,
        followers_eom, followers_denom_sum, engagement_for_er_sum,
        er_followers_monthly,
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): reach_sum, er_reach_monthly,
        -- reposts_sum, followers_growth
    )
    SELECT f.social_account_id, f.platform, f.month_start,
           EXTRACT(YEAR    FROM f.month_start)::int,
           EXTRACT(MONTH   FROM f.month_start)::int,
           to_char(f.month_start, 'YYYY-MM'),
           EXTRACT(QUARTER FROM f.month_start)::int,
           to_char(f.month_start, 'YYYY') || 'Q' || to_char(f.month_start, 'Q'),
           f.active_days, f.post_count, f.posts_in_sample,
           f.likes_sum, f.comments_sum, f.shares_sum, f.saves_sum, f.views_sum,
           f.engagement_sum, f.engagement_public_sum,
           f.followers_eom, f.followers_denom_sum, f.engagement_for_er_sum,
           CASE WHEN f.followers_denom_sum IS NULL OR f.followers_denom_sum = 0
                     OR f.engagement_for_er_sum IS NULL
                THEN NULL
                ELSE round(f.engagement_for_er_sum::numeric / f.followers_denom_sum, 8)
           END,
           now(), now()
    FROM final f
    ON CONFLICT (social_account_id, platform, month_start) DO UPDATE SET
        year                  = EXCLUDED.year,
        month                 = EXCLUDED.month,
        month_year            = EXCLUDED.month_year,
        quarter               = EXCLUDED.quarter,
        year_quarter          = EXCLUDED.year_quarter,
        active_days           = EXCLUDED.active_days,
        post_count            = EXCLUDED.post_count,
        posts_in_sample       = EXCLUDED.posts_in_sample,
        likes_sum             = EXCLUDED.likes_sum,
        comments_sum          = EXCLUDED.comments_sum,
        shares_sum            = EXCLUDED.shares_sum,
        saves_sum             = EXCLUDED.saves_sum,
        views_sum             = EXCLUDED.views_sum,
        engagement_sum        = EXCLUDED.engagement_sum,
        engagement_public_sum = EXCLUDED.engagement_public_sum,
        followers_eom         = EXCLUDED.followers_eom,
        followers_denom_sum   = EXCLUDED.followers_denom_sum,
        engagement_for_er_sum = EXCLUDED.engagement_for_er_sum,
        er_followers_monthly  = EXCLUDED.er_followers_monthly,
        updated_at            = now()
    WHERE kol_metric_monthly.active_days     IS DISTINCT FROM EXCLUDED.active_days
       OR kol_metric_monthly.post_count      IS DISTINCT FROM EXCLUDED.post_count
       OR kol_metric_monthly.posts_in_sample IS DISTINCT FROM EXCLUDED.posts_in_sample
       OR kol_metric_monthly.likes_sum       IS DISTINCT FROM EXCLUDED.likes_sum
       OR kol_metric_monthly.comments_sum    IS DISTINCT FROM EXCLUDED.comments_sum
       OR kol_metric_monthly.shares_sum      IS DISTINCT FROM EXCLUDED.shares_sum
       OR kol_metric_monthly.saves_sum       IS DISTINCT FROM EXCLUDED.saves_sum
       OR kol_metric_monthly.views_sum       IS DISTINCT FROM EXCLUDED.views_sum
       OR kol_metric_monthly.engagement_sum  IS DISTINCT FROM EXCLUDED.engagement_sum
       OR kol_metric_monthly.engagement_public_sum
                                             IS DISTINCT FROM EXCLUDED.engagement_public_sum
       OR kol_metric_monthly.followers_eom   IS DISTINCT FROM EXCLUDED.followers_eom
       OR kol_metric_monthly.followers_denom_sum
                                             IS DISTINCT FROM EXCLUDED.followers_denom_sum
       OR kol_metric_monthly.engagement_for_er_sum
                                             IS DISTINCT FROM EXCLUDED.engagement_for_er_sum
       OR kol_metric_monthly.er_followers_monthly
                                             IS DISTINCT FROM EXCLUDED.er_followers_monthly
"""

# `::bigint` pada tiap sum() wajib: SUM(bigint) di PostgreSQL mengembalikan
# `numeric` -> Decimal di Python, dan Dagster menolak Decimal sebagai metadata.
# Ini persis bug yang menjatuhkan materialize pertama kol_metric_daily.
SQL_STATS_BULANAN = _CTE_BULANAN + """
    SELECT count(*)                                            AS baris,
           count(DISTINCT social_account_id)                    AS akun,
           sum(post_count)::bigint                              AS post_total,
           sum(posts_in_sample)::bigint                         AS post_sampel,
           sum(active_days)::bigint                             AS hari_aktif,
           count(followers_eom)                                 AS bulan_dapat_follower,
           count(engagement_for_er_sum)                         AS bulan_dapat_pembilang_er,
           count(*) FILTER (WHERE engagement_sum IS DISTINCT FROM engagement_for_er_sum
                              AND followers_denom_sum IS NOT NULL)
                                                                AS bulan_pembilang_diselaraskan,
           min(month_start)                                     AS bulan_awal,
           max(month_start)                                     AS bulan_akhir
    FROM final
    """


def _jalankan_bulanan(postgres: PostgresResource) -> Output:
    """Agregasi kol_metric_daily -> kol_metric_monthly.

    SENGAJA tanpa try/except: kalau SQL-nya gagal, asset harus ikut gagal.
    """
    tabel = "l2_gold.kol_metric_monthly"
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM l2_gold.kol_metric_monthly")
            sebelum = cur.fetchone()[0]

            cur.execute(SQL_STATS_BULANAN)
            (baris, akun, post_total, post_sampel, hari_aktif, bulan_follower,
             bulan_pembilang, bulan_selaras, bulan_awal, bulan_akhir) = cur.fetchone()

            if baris == 0:
                conn.rollback()
                return Output(
                    0,
                    metadata={
                        "tabel": tabel,
                        "baris_ditulis": 0,
                        "catatan": MetadataValue.text(
                            "l2_gold.kol_metric_daily kosong — tidak ada yang bisa "
                            "diagregasi. Bukan kegagalan."
                        ),
                    },
                )

            cur.execute(SQL_UPSERT_BULANAN)
            ditulis = cur.rowcount

            cur.execute("SELECT count(*) FROM l2_gold.kol_metric_monthly")
            sesudah = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return Output(
        sesudah,
        metadata={
            "tabel": tabel,
            "sumber": "l2_gold.kol_metric_daily (tidak mengagregasi ulang dari L1)",
            "baris_sebelum": sebelum,
            "baris_sesudah": sesudah,
            "baris_disentuh_upsert": ditulis,
            "akun": akun,
            "rentang_bulan": f"{bulan_awal} .. {bulan_akhir}",
            "hari_aktif_total": hari_aktif,
            "post_total": post_total,
            "post_masuk_sampel": post_sampel,
            "bulan_dapat_followers_eom": bulan_follower,
            "bulan_dapat_pembilang_er": bulan_pembilang,
            "bulan_pembilang_er_diselaraskan": bulan_selaras,
            "kolom_sengaja_null": MetadataValue.text(
                "reach_sum, er_reach_monthly, reposts_sum, followers_growth — "
                "keempatnya 100% NULL di kol_metric_daily."
            ),
        },
    )


@asset(
    name="kol_metric_monthly",
    group_name=GROUP,
    deps=[AssetKey("kol_metric_daily")],
    kinds={"postgres"},
    description=(
        "l2_gold.kol_metric_monthly — rekap bulanan per KOL per platform, grain "
        "(social_account_id, platform, month_start). Diagregasi HANYA dari "
        "l2_gold.kol_metric_daily. followers_eom adalah snapshot hari terakhir, "
        "bukan rata-rata. er_followers_monthly dihitung dari "
        "engagement_for_er_sum / followers_denom_sum — pembilang dibatasi ke hari "
        "yang penyebutnya diketahui, dan TIDAK PERNAH rata-rata ER harian. "
        "Tidak ada kolom month-over-month; bulan datanya belum berurutan."
    ),
)
def kol_metric_monthly(postgres: PostgresResource) -> Output:
    return _jalankan_bulanan(postgres)


gold_assets = [kol_metric_daily, kol_metric_monthly]
