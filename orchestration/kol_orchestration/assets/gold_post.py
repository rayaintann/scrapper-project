"""Asset L2 Gold — grain KONTEN dan grain FORMAT-per-hari.

Dua asset, keduanya membaca L1 (tidak berantai satu sama lain):

    post_metric          -> l2_gold.post_metric            (SCRUM-515)
    content_format_daily -> l2_gold.content_format_daily   (SCRUM-517/518)

`post_metric` bergrain (social_account_id, platform, content_id) — satu baris
per konten. Membaca `l1_silver.unified_post` (fakta + metrik mentah),
`feature.{ig,tt}_post_analysis` (rank, top_hashtags), dan
`l1_silver.unified_profile` (follower carry-forward untuk ER).

`content_format_daily` bergrain (social_account_id, platform, metric_date,
media_type) — `kol_metric_daily` dengan satu dimensi tambahan. Membaca
`l1_silver.unified_post` + `l1_silver.unified_profile`.

Dipisahkan dari `gold.py` mengikuti pemisahan yang sudah ada di sana: `gold.py`
berisi rekap per AKUN (harian, bulanan), `gold_profile.py` yang per PROFIL, dan
modul ini yang bergrain KONTEN dan FORMAT. Perbedaan grain itulah alasan
tabel-tabelnya ada masing-masing.

============================================================================
KEPUTUSAN DESAIN — post_metric
============================================================================

1. `post_date` DARI `posted_at` DALAM WIB, sama seperti `kol_metric_daily`.
   Bukan dari `unified_post.date` — kolom itu tanggal SCRAPE. Kalau keduanya
   memakai sumber tanggal berbeda, `post_metric` tidak akan pernah bisa
   direkonsiliasi terhadap `kol_metric_daily`, dan dua angka berbeda untuk hal
   yang sama adalah persis yang mau dihindari tabel L2.

2. SEMUA POST DAPAT BARIS. TIDAK ADA YANG DISARING.
   477 dari 477 baris `unified_post` masuk (semuanya punya `posted_at`,
   `social_account_id`, dan `content_id`). Post ber-`likes_hidden` (18) atau
   `is_collaboration` (43) TETAP ditulis — mengikuti `feature_post.py` butir 1,
   dan mengikuti maksud DDL-nya sendiri: kedua flag itu memang jadi kolom di
   tabel ini "supaya konsumen bisa menyaring sendiri dengan aturan yang sama
   seperti kol_metric_daily, tanpa harus kembali ke L1".

   Konsekuensinya harus diketahui pembaca tabel: menjumlahkan `engagement_owned`
   seluruh baris TIDAK sama dengan `kol_metric_daily.engagement_sum`. Untuk
   rekonsiliasi, saring dulu:

       WHERE likes_hidden IS NOT TRUE AND is_collaboration IS NOT TRUE

3. `engagement_owned` = Like + Comment + Share. SAVE TIDAK IKUT.
   Komentar DDL migration 023 menulis "likes+comments+shares+saves", tapi itu
   ditulis SEBELUM definisi engagement diperbaiki di `gold.py` butir 6: Save
   adalah tindakan pribadi, bukan penyebaran ulang, jadi bukan komponen
   Engagement. Rumus lama membuat TikTok kelebihan 2.639.563 di 60/60 baris
   `kol_metric_daily`.

   Yang dipakai di sini definisi yang sudah diperbaiki, BUKAN komentar DDL-nya.
   Alasannya: `engagement_owned` sejajar dengan `engagement_sum` di
   `kol_metric_daily`, dan `engagement_public` sejajar dengan
   `engagement_public_sum`. Kalau rumusnya berbeda, dua tabel L2 akan melaporkan
   angka engagement berbeda untuk post yang sama. `saves` tetap disimpan penuh
   di kolomnya sendiri, jadi tidak ada informasi yang hilang — siapa pun yang
   memang menginginkan definisi lama bisa menjumlahkannya sendiri.

4. `er_followers` HANYA UNTUK POST YANG LOLOS ATURAN SAMPEL.
   Beda perlakuan dengan butir 2, dan sengaja: `engagement_owned` adalah
   penjumlahan fakta, sedangkan ER adalah RASIO terhadap follower AKUN INI.
   Pada post kolaborasi sebagian like datang dari audiens akun lain sementara
   penyebutnya tetap follower akun ini — angkanya bukan "kurang lengkap",
   melainkan salah. Persis alasan `feature_post.py` butir 2 meng-NULL-kan
   `engagement_rate` untuk post yang sama.

   Follower diambil carry-forward: snapshot `unified_profile` TERAKHIR dengan
   `date <= post_date`. Pola dan alasannya sama dengan `gold.py` butir 3.

5. `rank_in_account` DAN `top_hashtags` DIAMBIL DARI LAYER FEATURE, TIDAK
   DIHITUNG ULANG.
   `feature.{ig,tt}_post_analysis` sudah menghitung keduanya dan cocok 1:1
   dengan `unified_post` (186/186 IG, 291/291 TT) lewat `content_id` ->
   `media_id` / `video_id`. Menghitung ulang peringkat di sini hanya membuka
   peluang dua peringkat berbeda untuk post yang sama.

   Cakupannya memang belum penuh dan itu diteruskan apa adanya, bukan ditambal:
   `rank` terisi 45/186 (IG) dan 95/291 (TT) — hanya post yang lolos sampel DAN
   punya ER yang dapat peringkat; `top_hashtags` 70/186 dan 237/291.

   Join-nya lewat LATERAL ber-`UNION ALL` yang di-guard `platform`, bukan dua
   LEFT JOIN terpisah lalu di-COALESCE: sebuah `content_id` Instagram tidak
   boleh ikut tercocokkan ke tabel TikTok hanya karena nilainya kebetulan sama.

6. KOLOM BLOCKED TIDAK DITULIS SAMA SEKALI (tetap NULL). Tidak ditebak,
   tidak dinolkan. Cakupan sumbernya diukur, bukan diperkirakan:
     reach, er_reach            `unified_post.reach` 0/477 — butuh Insights API
     reposts                    `unified_post.reposts` 0/477
     avg_watch_time_seconds     `feature.*_post_analysis` 0/186 dan 0/291
     completion_rate            `feature.tt_post_analysis` 0/291

7. UPSERT DENGAN PENJAGA `IS DISTINCT FROM`, bukan TRUNCATE + INSERT.
   Sama seperti seluruh asset L2 lain: baris yang isinya tidak berubah tidak
   ditulis ulang, jadi `updated_at` menandai perubahan sungguhan dan rerun
   benar-benar idempoten.

============================================================================
KEPUTUSAN DESAIN — content_format_daily
============================================================================

1. RUMUSNYA SENGAJA SALINAN PERSIS `kol_metric_daily`, HANYA DITAMBAH SATU
   DIMENSI.
   Aturan sampel, carry-forward follower, definisi engagement, penjaga
   `posts_in_sample = 0`, dan ER sebagai fraksi 0..1 semuanya identik. Itu yang
   membuat tabel ini bisa direkonsiliasi: menjumlahkan seluruh `media_type`
   pada satu (akun, platform, tanggal) harus menghasilkan baris
   `kol_metric_daily` yang sama persis. Kalau salah satu rumusnya menyimpang,
   perbandingan "Reels vs Carousel" tidak akan pernah menjumlah ke total harian
   yang sudah ditampilkan UI.

   Rekonsiliasi itu tidak dianggap sudah benar begitu saja — ia dihitung ulang
   setiap materialize lewat `SQL_REKONSILIASI` dan hasilnya masuk metadata.

2. `media_type` DIPAKAI APA ADANYA, TIDAK DINORMALISASI.
   Instagram `clips` (89) / `carousel_container` (67) / `feed` (22), TikTok
   `VIDEO` (289) / `CAROUSEL` (2). Memetakannya ke label bersama ("Video",
   "Carousel") adalah keputusan produk yang belum ada — mengarangnya di sini
   akan mengunci pemetaan itu di data, bukan di UI tempat ia bisa diubah.

3. `media_type` KOSONG JADI `'unknown'`, BUKAN DIBUANG.
   8 post Instagram punya `media_type` NULL. Kolom `media_type` di tabel target
   NOT NULL dan ikut jadi kunci unik, jadi harus ada keputusan eksplisit.

   Membuang 8 baris itu akan diam-diam merusak butir 1 — total per hari tidak
   lagi menjumlah ke `kol_metric_daily` untuk akun-hari yang bersangkutan, dan
   tidak ada apa pun di tabel yang menunjukkan kenapa. `'unknown'` menjaga
   penjumlahannya tetap tepat dan mengatakan terus terang bahwa formatnya
   belum diketahui. Ini bukan menebak format; ini menamai ketidaktahuan.

   UI sebaiknya memperlakukan `'unknown'` seperti bucket `unknown` di tabel
   audiens: ditampilkan apa adanya atau disembunyikan, tidak dibagi rata ke
   format lain.

4. KOLOM BLOCKED TIDAK DITULIS: `reach_sum`, `er_reach_daily`
   (`unified_post.reach` 0/477).
"""

from __future__ import annotations

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

GROUP = "l2_gold"
_POST = AssetKey("unified_post")
_PROFILE = AssetKey("unified_profile")
_IG_POST_ANALYSIS = AssetKey("ig_post_analysis")
_TT_POST_ANALYSIS = AssetKey("tt_post_analysis")


# ===========================================================================
# post_metric — satu baris per konten (SCRUM-515)
# ===========================================================================

_CTE_POST = """
    WITH post AS (
        SELECT u.social_account_id,
               pl.key                                          AS platform,
               u.content_id,
               u.posted_at,
               (u.posted_at AT TIME ZONE 'Asia/Jakarta')::date  AS post_date,
               u.media_type,
               u.is_sponsored,
               u.permalink,
               u.likes_hidden,
               u.is_collaboration,
               u.likes, u.comments, u.shares, u.saved AS saves, u.views,
               -- aturan sampel yang sama dengan kol_metric_daily; di sini
               -- dipakai HANYA untuk er_followers, bukan untuk membuang baris
               (u.likes_hidden IS NOT TRUE
                AND u.is_collaboration IS NOT TRUE)             AS lolos
        FROM l1_silver.unified_post u
        JOIN public.platforms pl ON pl.id = u.platform_id
        WHERE u.posted_at IS NOT NULL
          AND u.social_account_id IS NOT NULL
          AND u.content_id IS NOT NULL
    ),
    dengan_feature AS (
        SELECT p.*,
               f.rank_in_account,
               f.top_hashtags
        FROM post p
        LEFT JOIN LATERAL (
            -- UNION ALL yang di-guard `platform`, bukan dua LEFT JOIN lalu
            -- di-COALESCE: content_id Instagram tidak boleh tercocokkan ke
            -- tabel TikTok hanya karena nilainya kebetulan sama.
            SELECT ig.rank AS rank_in_account, ig.top_hashtags
            FROM feature.ig_post_analysis ig
            WHERE p.platform = 'instagram'
              AND ig.social_account_id = p.social_account_id
              AND ig.media_id = p.content_id
            UNION ALL
            SELECT tt.rank, tt.top_hashtags
            FROM feature.tt_post_analysis tt
            WHERE p.platform = 'tiktok'
              AND tt.social_account_id = p.social_account_id
              AND tt.video_id = p.content_id
        ) f ON true
    ),
    dengan_follower AS (
        SELECT d.*,
               cf.followers_count AS followers_at_post_date
        FROM dengan_feature d
        LEFT JOIN LATERAL (
            -- carry-forward: snapshot TERAKHIR yang tidak melewati post_date
            SELECT pr.followers_count
            FROM l1_silver.unified_profile pr
            WHERE pr.social_account_id = d.social_account_id
              AND pr.date <= d.post_date
            ORDER BY pr.date DESC
            LIMIT 1
        ) cf ON true
    ),
    final AS (
        SELECT d.*,
               -- DEFINISI BISNIS: Like + Comment + Share. Save TIDAK ikut
               -- (lihat butir 3 di docstring). Komponen NULL dianggap 0 —
               -- di sini aman karena likes & comments terisi 477/477.
               COALESCE(d.likes, 0) + COALESCE(d.comments, 0)
                                    + COALESCE(d.shares, 0)     AS engagement_owned,
               COALESCE(d.likes, 0) + COALESCE(d.comments, 0)   AS engagement_public
        FROM dengan_follower d
    )"""

SQL_UPSERT_POST = _CTE_POST + """
    INSERT INTO l2_gold.post_metric (
        social_account_id, platform, content_id,
        posted_at, post_date, media_type, is_sponsored, permalink,
        likes_hidden, is_collaboration,
        likes, comments, shares, saves, views,
        engagement_owned, engagement_public,
        followers_at_post_date, er_followers,
        rank_in_account, top_hashtags,
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): reach, er_reach, reposts,
        -- avg_watch_time_seconds, completion_rate
    )
    SELECT f.social_account_id, f.platform, f.content_id,
           f.posted_at, f.post_date, f.media_type, f.is_sponsored, f.permalink,
           f.likes_hidden, f.is_collaboration,
           f.likes, f.comments, f.shares, f.saves, f.views,
           f.engagement_owned, f.engagement_public,
           f.followers_at_post_date,
           -- ER hanya untuk post yang lolos sampel: rasio terhadap follower
           -- akun ini tidak bermakna untuk post kolaborasi
           CASE WHEN NOT f.lolos
                     OR f.followers_at_post_date IS NULL
                     OR f.followers_at_post_date = 0
                THEN NULL
                ELSE round(f.engagement_owned::numeric / f.followers_at_post_date, 8)
           END,
           f.rank_in_account, f.top_hashtags,
           now(), now()
    FROM final f
    ON CONFLICT (social_account_id, platform, content_id) DO UPDATE SET
        posted_at              = EXCLUDED.posted_at,
        post_date              = EXCLUDED.post_date,
        media_type             = EXCLUDED.media_type,
        is_sponsored           = EXCLUDED.is_sponsored,
        permalink              = EXCLUDED.permalink,
        likes_hidden           = EXCLUDED.likes_hidden,
        is_collaboration       = EXCLUDED.is_collaboration,
        likes                  = EXCLUDED.likes,
        comments               = EXCLUDED.comments,
        shares                 = EXCLUDED.shares,
        saves                  = EXCLUDED.saves,
        views                  = EXCLUDED.views,
        engagement_owned       = EXCLUDED.engagement_owned,
        engagement_public      = EXCLUDED.engagement_public,
        followers_at_post_date = EXCLUDED.followers_at_post_date,
        er_followers           = EXCLUDED.er_followers,
        rank_in_account        = EXCLUDED.rank_in_account,
        top_hashtags           = EXCLUDED.top_hashtags,
        updated_at             = now()
    -- Penjaga: baris yang isinya tidak berubah tidak ditulis ulang, jadi
    -- updated_at menandai perubahan nyata dan rerun benar-benar idempoten.
    WHERE post_metric.posted_at        IS DISTINCT FROM EXCLUDED.posted_at
       OR post_metric.post_date        IS DISTINCT FROM EXCLUDED.post_date
       OR post_metric.media_type       IS DISTINCT FROM EXCLUDED.media_type
       OR post_metric.is_sponsored     IS DISTINCT FROM EXCLUDED.is_sponsored
       OR post_metric.permalink        IS DISTINCT FROM EXCLUDED.permalink
       OR post_metric.likes_hidden     IS DISTINCT FROM EXCLUDED.likes_hidden
       OR post_metric.is_collaboration IS DISTINCT FROM EXCLUDED.is_collaboration
       OR post_metric.likes            IS DISTINCT FROM EXCLUDED.likes
       OR post_metric.comments         IS DISTINCT FROM EXCLUDED.comments
       OR post_metric.shares           IS DISTINCT FROM EXCLUDED.shares
       OR post_metric.saves            IS DISTINCT FROM EXCLUDED.saves
       OR post_metric.views            IS DISTINCT FROM EXCLUDED.views
       OR post_metric.engagement_owned IS DISTINCT FROM EXCLUDED.engagement_owned
       OR post_metric.engagement_public
                                       IS DISTINCT FROM EXCLUDED.engagement_public
       OR post_metric.followers_at_post_date
                                       IS DISTINCT FROM EXCLUDED.followers_at_post_date
       OR post_metric.er_followers     IS DISTINCT FROM EXCLUDED.er_followers
       OR post_metric.rank_in_account  IS DISTINCT FROM EXCLUDED.rank_in_account
       OR post_metric.top_hashtags     IS DISTINCT FROM EXCLUDED.top_hashtags
"""

# `::bigint` pada tiap sum() WAJIB: SUM(bigint) di PostgreSQL mengembalikan
# `numeric` -> Decimal di Python, dan Dagster menolak Decimal sebagai metadata.
SQL_STATS_POST = _CTE_POST + """
    SELECT count(*)                                              AS baris,
           count(DISTINCT social_account_id)                      AS akun,
           count(*) FILTER (WHERE platform = 'instagram')         AS baris_ig,
           count(*) FILTER (WHERE platform = 'tiktok')            AS baris_tt,
           count(*) FILTER (WHERE NOT lolos)                      AS post_tersaring,
           count(followers_at_post_date)                          AS dapat_follower,
           count(rank_in_account)                                 AS dapat_rank,
           count(top_hashtags)                                    AS dapat_hashtag,
           sum(engagement_owned)::bigint                          AS engagement_total,
           min(post_date)                                         AS tgl_awal,
           max(post_date)                                         AS tgl_akhir
    FROM final
    """


def _jalankan_post_metric(postgres: PostgresResource) -> Output:
    """Bangun l2_gold.post_metric dari L1 + layer feature.

    SENGAJA tanpa try/except: kalau SQL-nya gagal, asset harus ikut gagal.
    Sumber kosong TIDAK dianggap gagal — selesai dengan 0 baris dan penjelasan.
    """
    tabel = "l2_gold.post_metric"
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM l2_gold.post_metric")
            sebelum = cur.fetchone()[0]

            cur.execute(SQL_STATS_POST)
            (baris, akun, baris_ig, baris_tt, post_tersaring, dapat_follower,
             dapat_rank, dapat_hashtag, engagement_total,
             tgl_awal, tgl_akhir) = cur.fetchone()

            if baris == 0:
                conn.rollback()
                return Output(
                    0,
                    metadata={
                        "tabel": tabel,
                        "baris_ditulis": 0,
                        "catatan": MetadataValue.text(
                            "Tidak ada post ber-posted_at & content_id di "
                            "l1_silver.unified_post — tidak ada yang bisa "
                            "diproyeksikan. Bukan kegagalan."
                        ),
                    },
                )

            cur.execute(SQL_UPSERT_POST)
            ditulis = cur.rowcount

            cur.execute("SELECT count(*) FROM l2_gold.post_metric")
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
            "baris_instagram": baris_ig,
            "baris_tiktok": baris_tt,
            "rentang_tanggal": f"{tgl_awal} .. {tgl_akhir}",
            "post_tidak_lolos_sampel_er_null": post_tersaring,
            "baris_dapat_follower_carry_forward": dapat_follower,
            "baris_dapat_rank_dari_feature": dapat_rank,
            "baris_dapat_top_hashtags": dapat_hashtag,
            "engagement_owned_total": engagement_total,
            "rekonsiliasi": MetadataValue.text(
                "Semua post ditulis, termasuk yang likes_hidden/is_collaboration. "
                "Untuk menyamakan dengan kol_metric_daily, saring dulu: "
                "WHERE likes_hidden IS NOT TRUE AND is_collaboration IS NOT TRUE."
            ),
            "kolom_sengaja_null": MetadataValue.text(
                "reach & er_reach (unified_post.reach 0/477 — butuh Insights "
                "API); reposts (0/477); avg_watch_time_seconds & "
                "completion_rate (feature.*_post_analysis 0 terisi)."
            ),
        },
    )


@asset(
    name="post_metric",
    group_name=GROUP,
    deps=[_POST, _PROFILE, _IG_POST_ANALYSIS, _TT_POST_ANALYSIS],
    kinds={"postgres"},
    description=(
        "l2_gold.post_metric — metrik per konten lintas platform, grain "
        "(social_account_id, platform, content_id). post_date = tanggal TAYANG "
        "(posted_at, WIB). SEMUA post ditulis, termasuk yang likes_hidden atau "
        "is_collaboration; kedua flag ikut disimpan supaya konsumen menyaring "
        "sendiri. engagement_owned = Like+Comment+Share (Save TIDAK ikut, sama "
        "seperti kol_metric_daily). er_followers fraksi 0..1 dan HANYA diisi "
        "untuk post yang lolos aturan sampel. rank_in_account & top_hashtags "
        "diteruskan dari feature.*_post_analysis, tidak dihitung ulang. "
        "reach/er_reach/reposts/avg_watch_time_seconds/completion_rate sengaja NULL."
    ),
)
def post_metric(postgres: PostgresResource) -> Output:
    return _jalankan_post_metric(postgres)


# ===========================================================================
# content_format_daily — kol_metric_daily + dimensi media_type (SCRUM-517/518)
# ===========================================================================

_CTE_FORMAT = """
    WITH post AS (
        SELECT u.social_account_id,
               pl.key                                             AS platform,
               (u.posted_at AT TIME ZONE 'Asia/Jakarta')::date     AS metric_date,
               -- media_type apa adanya; yang kosong dinamai 'unknown' supaya
               -- barisnya tidak hilang dan total per hari tetap menjumlah ke
               -- kol_metric_daily (lihat butir 3 di docstring)
               COALESCE(NULLIF(btrim(u.media_type), ''), 'unknown') AS media_type,
               u.likes, u.comments, u.shares, u.saved, u.views,
               (u.likes_hidden IS NOT TRUE
                AND u.is_collaboration IS NOT TRUE)                AS lolos
        FROM l1_silver.unified_post u
        JOIN public.platforms pl ON pl.id = u.platform_id
        WHERE u.posted_at IS NOT NULL
          AND u.social_account_id IS NOT NULL
    ),
    harian AS (
        SELECT social_account_id, platform, metric_date, media_type,
               count(*)                                  AS post_count,
               count(*) FILTER (WHERE lolos)              AS posts_in_sample,
               -- tanpa COALESCE: NULL kalau sumbernya memang tidak tersedia
               sum(likes)    FILTER (WHERE lolos)         AS likes_sum,
               sum(comments) FILTER (WHERE lolos)         AS comments_sum,
               sum(shares)   FILTER (WHERE lolos)         AS shares_sum,
               sum(saved)    FILTER (WHERE lolos)         AS saves_sum,
               sum(views)    FILTER (WHERE lolos)         AS views_sum
        FROM post
        GROUP BY 1, 2, 3, 4
    ),
    dengan_follower AS (
        SELECT h.*,
               cf.followers_count AS followers_at_post_date
        FROM harian h
        LEFT JOIN LATERAL (
            -- carry-forward, identik dengan kol_metric_daily
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
               -- Rumus identik dengan kol_metric_daily. Save TIDAK ikut.
               -- Keseluruhannya NULL kalau tidak ada sampel sama sekali: 0
               -- berarti "tidak ada interaksi", bukan "tidak ada sampel".
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

SQL_UPSERT_FORMAT = _CTE_FORMAT + """
    INSERT INTO l2_gold.content_format_daily (
        social_account_id, platform, metric_date, media_type,
        post_count, posts_in_sample,
        likes_sum, comments_sum, shares_sum, saves_sum, views_sum,
        engagement_sum, engagement_public_sum,
        followers_denom_sum, er_followers_daily,
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): reach_sum, er_reach_daily
    )
    SELECT f.social_account_id, f.platform, f.metric_date, f.media_type,
           f.post_count, f.posts_in_sample,
           f.likes_sum, f.comments_sum, f.shares_sum, f.saves_sum, f.views_sum,
           f.engagement_sum, f.engagement_public_sum,
           f.followers_denom_sum,
           CASE WHEN f.followers_denom_sum IS NULL OR f.followers_denom_sum = 0
                     OR f.engagement_sum IS NULL
                THEN NULL
                ELSE round(f.engagement_sum::numeric / f.followers_denom_sum, 8)
           END,
           now(), now()
    FROM final f
    ON CONFLICT (social_account_id, platform, metric_date, media_type) DO UPDATE SET
        post_count            = EXCLUDED.post_count,
        posts_in_sample       = EXCLUDED.posts_in_sample,
        likes_sum             = EXCLUDED.likes_sum,
        comments_sum          = EXCLUDED.comments_sum,
        shares_sum            = EXCLUDED.shares_sum,
        saves_sum             = EXCLUDED.saves_sum,
        views_sum             = EXCLUDED.views_sum,
        engagement_sum        = EXCLUDED.engagement_sum,
        engagement_public_sum = EXCLUDED.engagement_public_sum,
        followers_denom_sum   = EXCLUDED.followers_denom_sum,
        er_followers_daily    = EXCLUDED.er_followers_daily,
        updated_at            = now()
    WHERE content_format_daily.post_count      IS DISTINCT FROM EXCLUDED.post_count
       OR content_format_daily.posts_in_sample IS DISTINCT FROM EXCLUDED.posts_in_sample
       OR content_format_daily.likes_sum       IS DISTINCT FROM EXCLUDED.likes_sum
       OR content_format_daily.comments_sum    IS DISTINCT FROM EXCLUDED.comments_sum
       OR content_format_daily.shares_sum      IS DISTINCT FROM EXCLUDED.shares_sum
       OR content_format_daily.saves_sum       IS DISTINCT FROM EXCLUDED.saves_sum
       OR content_format_daily.views_sum       IS DISTINCT FROM EXCLUDED.views_sum
       OR content_format_daily.engagement_sum  IS DISTINCT FROM EXCLUDED.engagement_sum
       OR content_format_daily.engagement_public_sum
                                               IS DISTINCT FROM EXCLUDED.engagement_public_sum
       OR content_format_daily.followers_denom_sum
                                               IS DISTINCT FROM EXCLUDED.followers_denom_sum
       OR content_format_daily.er_followers_daily
                                               IS DISTINCT FROM EXCLUDED.er_followers_daily
"""

SQL_STATS_FORMAT = _CTE_FORMAT + """
    SELECT count(*)                                              AS baris,
           count(DISTINCT social_account_id)                      AS akun,
           count(DISTINCT media_type)                             AS format_unik,
           sum(post_count)::bigint                                AS post_total,
           sum(posts_in_sample)::bigint                           AS post_sampel,
           (sum(post_count) - sum(posts_in_sample))::bigint       AS post_tersaring,
           count(*) FILTER (WHERE media_type = 'unknown')         AS baris_format_unknown,
           count(*) FILTER (WHERE posts_in_sample = 0)            AS baris_tanpa_sampel,
           count(followers_denom_sum)                             AS dapat_penyebut_er,
           min(metric_date)                                       AS tgl_awal,
           max(metric_date)                                       AS tgl_akhir
    FROM final
    """

# Rekonsiliasi terhadap kol_metric_daily. Bukan hiasan: inilah yang membuktikan
# butir 1 benar-benar berlaku, dan ia dijalankan tiap kali asset materialize.
# FULL OUTER JOIN, bukan INNER: akun-hari yang hanya ada di salah satu tabel
# justru kasus yang paling perlu ketahuan.
SQL_REKONSILIASI = """
    SELECT count(*) AS baris_tidak_cocok
    FROM (
        SELECT social_account_id, platform, metric_date,
               sum(post_count)      AS post_count,
               sum(posts_in_sample) AS posts_in_sample,
               sum(engagement_sum)  AS engagement_sum
        FROM l2_gold.content_format_daily
        GROUP BY 1, 2, 3
    ) f
    FULL OUTER JOIN l2_gold.kol_metric_daily k
      USING (social_account_id, platform, metric_date)
    WHERE f.post_count      IS DISTINCT FROM k.post_count
       OR f.posts_in_sample IS DISTINCT FROM k.posts_in_sample
       OR f.engagement_sum  IS DISTINCT FROM k.engagement_sum
    """


def _jalankan_content_format(postgres: PostgresResource) -> Output:
    """Bangun l2_gold.content_format_daily dari L1.

    SENGAJA tanpa try/except: kalau SQL-nya gagal, asset harus ikut gagal.
    """
    tabel = "l2_gold.content_format_daily"
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM l2_gold.content_format_daily")
            sebelum = cur.fetchone()[0]

            cur.execute(SQL_STATS_FORMAT)
            (baris, akun, format_unik, post_total, post_sampel, post_tersaring,
             baris_unknown, baris_tanpa_sampel, dapat_penyebut,
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

            cur.execute(SQL_UPSERT_FORMAT)
            ditulis = cur.rowcount

            cur.execute("SELECT count(*) FROM l2_gold.content_format_daily")
            sesudah = cur.fetchone()[0]

            # Dihitung SETELAH upsert, di transaksi yang sama.
            cur.execute(SQL_REKONSILIASI)
            tidak_cocok = cur.fetchone()[0]
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
            "format_unik": format_unik,
            "rentang_tanggal": f"{tgl_awal} .. {tgl_akhir}",
            "post_total": post_total,
            "post_masuk_sampel": post_sampel,
            "post_tersaring_likes_hidden_kolaborasi": post_tersaring,
            "baris_media_type_unknown": baris_unknown,
            "baris_tanpa_sampel_metrik_null": baris_tanpa_sampel,
            "baris_dapat_penyebut_er": dapat_penyebut,
            "rekonsiliasi_vs_kol_metric_daily": (
                "cocok" if tidak_cocok == 0
                else f"{tidak_cocok} akun-hari TIDAK cocok"
            ),
            "kolom_sengaja_null": MetadataValue.text(
                "reach_sum & er_reach_daily — unified_post.reach 0/477, butuh "
                "Insights API."
            ),
        },
    )


@asset(
    name="content_format_daily",
    group_name=GROUP,
    deps=[_POST, _PROFILE],
    kinds={"postgres"},
    description=(
        "l2_gold.content_format_daily — performa per format konten per hari, "
        "grain (social_account_id, platform, metric_date, media_type). Rumusnya "
        "identik dengan kol_metric_daily plus satu dimensi, jadi menjumlahkan "
        "seluruh media_type pada satu akun-hari menghasilkan baris "
        "kol_metric_daily yang sama persis — rekonsiliasi itu diperiksa tiap "
        "materialize. media_type dipakai apa adanya (IG: clips/carousel_container/"
        "feed, TT: VIDEO/CAROUSEL); yang kosong dinamai 'unknown' agar barisnya "
        "tidak hilang. reach_sum & er_reach_daily sengaja NULL."
    ),
)
def content_format_daily(postgres: PostgresResource) -> Output:
    return _jalankan_content_format(postgres)


gold_post_assets = [post_metric, content_format_daily]
