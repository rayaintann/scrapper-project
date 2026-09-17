-- 049_unified_post_hidden_likes_null.sql
--
-- Like yang disembunyikan Instagram (sentinel likesCount = -1) disimpan sebagai
-- NULL di l1_silver.unified_post.likes, bukan -1.
--
-- ============================================================================
-- MASALAH (audit 17 Sep 2026)
-- ============================================================================
--
--   sp_build_unified_post (migrasi 024) menyalin src.likes apa adanya, jadi 22
--   baris L1 menyimpan likes = -1. Pembaca yang menjumlahkan likes tanpa
--   memfilter likes_hidden (mis. SUM(p.likes) di autometric kolMeasured.ts)
--   ikut mengurangi total. L2 post_metric menyalin -1 yang sama (diperbaiki di
--   gold_post.py pada perubahan yang sama).
--
--   Upsert memakai `likes = COALESCE(EXCLUDED.likes, likes)`, sehingga NULL baru
--   saja tidak cukup: -1 lama akan bertahan. Karena itu ON CONFLICT ikut diubah.
--
-- ============================================================================
-- PERUBAHAN (hanya dua, sisanya salinan persis migrasi 024)
-- ============================================================================
--
--   1. INSERT: likes = CASE WHEN src.likes = -1 THEN NULL ELSE src.likes END
--   2. ON CONFLICT: likes = NULL bila likes_hidden, selain itu
--      NULLIF(COALESCE(baru, lama), -1)
--
--   likes_hidden TETAP diturunkan dari src.likes (harmonization masih membawa
--   -1 sebagai penanda sumber), jadi tidak ada informasi yang hilang.
--   engagement_rate per post sudah NULL untuk post ini sejak migrasi 024.
--
-- BACKFILL: migrasi ini hanya mengganti function. 22 baris lama dibersihkan
-- dengan menjalankan ulang builder (SELECT l1_silver.sp_build_unified_post(),
-- atau asset unified_post), BUKAN dengan UPDATE manual. Guard upsert
-- `processed_at >=` meloloskan baris dengan processed_at yang sama.
--
-- Menjalankan:
--   python apply_migration.py migrations/049_unified_post_hidden_likes_null.sql --dry-run --yes
--   python apply_migration.py migrations/049_unified_post_hidden_likes_null.sql --yes

BEGIN;

DO $penjaga$
DECLARE
    n_fn     int;
    n_hidden bigint;
    n_neg    bigint;
BEGIN
    SELECT count(*) INTO n_fn
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_post';
    IF n_fn <> 1 THEN
        RAISE EXCEPTION 'Diharapkan tepat 1 function sp_build_unified_post, ditemukan %.', n_fn;
    END IF;

    SELECT count(*) FILTER (WHERE likes_hidden), count(*) FILTER (WHERE likes < 0)
      INTO n_hidden, n_neg
    FROM l1_silver.unified_post;
    RAISE NOTICE 'Kondisi awal: % baris likes_hidden, % baris likes < 0.', n_hidden, n_neg;
END $penjaga$;

-- ---------------------------------------------------------------------------
-- Function: salinan migrasi 024 dengan dua suntingan di atas.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION l1_silver.sp_build_unified_post()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- Tiga kolom turunan (likes_hidden, is_collaboration, engagement_rate)
    -- dihitung di sini memakai logic yang sama persis dengan migration 015,
    -- supaya baris yang masuk lewat function ini tidak lagi NULL.
    INSERT INTO l1_silver.unified_post (
        social_account_id, platform_id, content_id, date, posted_at, media_type,
        title, caption, permalink, cover_image, video_duration, carousel_media_count,
        is_sponsored, likes, comments, views, shares, reach, saved, total_interactions,
        reposts, follows, profile_visits, reel_avg_watch_time, reel_video_view_total_time,
        engagement_rate, has_insights,
        username, platform_user_id, shortcode, hashtags, mentions,
        source, source_table, source_id, processed_at,
        likes_hidden, is_collaboration
    )
    SELECT
        sa.id, sa.platform_id, src.content_id, src.date, src.posted_at, src.media_type,
        src.title, src.caption, src.permalink, src.cover_image, src.video_duration,
        src.carousel_media_count, src.is_sponsored,
        -- likes: sentinel -1 (like disembunyikan) disimpan sebagai NULL (migrasi 049).
        -- Penandanya tetap ada di likes_hidden, yang dihitung dari src.likes di bawah.
        CASE WHEN src.likes = -1 THEN NULL ELSE src.likes END,
        src.comments, src.views,
        src.shares, src.reach, src.saved, src.total_interactions, src.reposts, src.follows,
        src.profile_visits, src.reel_avg_watch_time, src.reel_video_view_total_time,
        -- engagement_rate: DIHITUNG di sini.
        --
        -- DEFINISI BISNIS: Engagement = Like + Comment + Share/Repost/Quote.
        -- Save/Collect TIDAK termasuk. `reposts` belum disebut karena kolomnya
        -- 0/221 di L1; kalau nanti terisi, tinggal ditambahkan ke pembilang.
        -- Instagram belum punya `shares` (0/130) sehingga COALESCE-nya jadi 0 --
        -- itu keterbatasan sumber, bukan pilihan rumus.
        --
        -- PENYEBUT: followers PADA TANGGAL POST (prof_foll), bukan snapshot
        -- terbaru. Pola yang sama sudah terbukti benar di
        -- l2_gold.kol_metric_daily.followers_at_post_date. Kalau tidak ada
        -- snapshot pada/sebelum tanggal tayang, hasilnya NULL -- tidak ditebak.
        CASE
            WHEN src.likes IS NULL OR src.likes = -1
              OR prof_foll.followers_count IS NULL
              OR prof_foll.followers_count = 0 THEN NULL
            ELSE round((src.likes + COALESCE(src.comments, 0)
                        + COALESCE(src.shares, 0))::numeric
                       / prof_foll.followers_count * 100, 4)
        END,
        src.has_insights,
        src.username, src.platform_user_id, src.shortcode, src.hashtags, src.mentions,
        src.source, src.source_table, src.source_id, src.processed_at,
        -- likes_hidden: sentinel Instagram untuk jumlah like yang disembunyikan.
        CASE WHEN src.likes IS NULL THEN NULL ELSE (src.likes = -1) END,
        -- is_collaboration: pemilik asli post berbeda dari pemilik akun.
        -- NULL bila salah satu sisi tidak diketahui - `IS DISTINCT FROM` sendirian
        -- akan salah di sini karena mengembalikan TRUE saat satu sisi NULL.
        -- COALESCE ke sa.username ditulis DI SINI, bukan di dalam LATERAL:
        -- kalau akun belum punya baris unified_profile, LATERAL-nya mengembalikan
        -- nol baris sehingga fallback di dalamnya tidak pernah dieksekusi.
        CASE
            WHEN src.username IS NULL
              OR COALESCE(prof_id.username, sa.username) IS NULL THEN NULL
            ELSE (ltrim(lower(btrim(src.username)), '@')
                  IS DISTINCT FROM
                  ltrim(lower(btrim(split_part(split_part(
                      COALESCE(prof_id.username, sa.username), '?', 1), '/', 1))), '@'))
        END
    FROM (
      -- T2: grain sumber (akun, konten, TANGGAL) diciutkan ke grain target
      -- (akun, konten). Tanpa DISTINCT ON, post yang punya dua tanggal
      -- snapshot membuat satu statement menyentuh baris konflik yang sama
      -- dua kali -> SQLSTATE 21000. Yang dipilih: snapshot TERBARU.
      SELECT DISTINCT ON (u.social_account_id, u.content_id) u.*
      FROM (
        SELECT social_account_id, media_id AS content_id, date, posted_at, media_type,
               NULL::text AS title, caption, permalink, cover_image, video_duration,
               carousel_media_count, is_sponsored, likes, comments, views, shares, reach,
               saved, total_interactions, reposts, follows, profile_visits,
               reel_avg_watch_time, reel_video_view_total_time, engagement_rate,
               has_insights,
               owner_username AS username, platform_user_id, shortcode, hashtags, mentions,
               source, source_table, source_id, processed_at
        FROM l0_harmonization.instagram_post
        UNION ALL
        SELECT social_account_id, video_id AS content_id, date, posted_at, media_type,
               title, caption, permalink, cover_image, video_duration,
               carousel_media_count, is_sponsored, likes, comments, views, shares,
               NULL::bigint AS reach, saved, NULL::bigint AS total_interactions,
               NULL::bigint AS reposts, NULL::bigint AS follows,
               NULL::bigint AS profile_visits, NULL::numeric AS reel_avg_watch_time,
               NULL::bigint AS reel_video_view_total_time, engagement_rate,
               NULL::boolean AS has_insights,
               owner_username AS username, platform_user_id,
               NULL::varchar AS shortcode, hashtags, mentions,
               source, source_table, source_id, processed_at
        FROM l0_harmonization.tiktok_post
      ) u
      ORDER BY u.social_account_id, u.content_id,
               u.date DESC NULLS LAST, u.processed_at DESC NULLS LAST
    ) src
    JOIN public.social_account sa ON sa.id = src.social_account_id
    -- LATERAL 1 -- IDENTITAS pemilik akun, untuk deteksi post kolaborasi.
    -- SENGAJA TIDAK dibatasi tanggal: username bukan besaran yang bergantung
    -- waktu, dan membatasinya akan membuat post lama kehilangan pembanding.
    -- LEFT JOIN, BUKAN inner: akun yang punya post tapi belum punya baris profil
    -- (kasus `inul.d` TikTok) tidak boleh hilang dari hasil.
    LEFT JOIN LATERAL (
        SELECT pr.username
        FROM l1_silver.unified_profile pr
        WHERE pr.social_account_id = sa.id
        ORDER BY pr.date DESC
        LIMIT 1
    ) prof_id ON true
    -- LATERAL 2 -- FOLLOWERS pada tanggal post, untuk penyebut engagement_rate.
    -- Dibatasi `pr.date <= tanggal tayang` supaya post lama tidak dibagi dengan
    -- jumlah follower yang belum dimiliki akun itu saat post tayang.
    -- Dipisah dari LATERAL 1 karena keduanya butuh aturan waktu yang berbeda.
    LEFT JOIN LATERAL (
        SELECT pr.followers_count
        FROM l1_silver.unified_profile pr
        WHERE pr.social_account_id = sa.id
          AND pr.date <= (src.posted_at AT TIME ZONE 'Asia/Jakarta')::date
        ORDER BY pr.date DESC
        LIMIT 1
    ) prof_foll ON true
    ON CONFLICT (social_account_id, content_id) DO UPDATE SET
        date = COALESCE(EXCLUDED.date, l1_silver.unified_post.date),
        posted_at = COALESCE(EXCLUDED.posted_at, l1_silver.unified_post.posted_at),
        media_type = COALESCE(EXCLUDED.media_type, l1_silver.unified_post.media_type),
        title = COALESCE(EXCLUDED.title, l1_silver.unified_post.title),
        caption = COALESCE(EXCLUDED.caption, l1_silver.unified_post.caption),
        permalink = COALESCE(EXCLUDED.permalink, l1_silver.unified_post.permalink),
        cover_image = COALESCE(EXCLUDED.cover_image, l1_silver.unified_post.cover_image),
        video_duration = COALESCE(EXCLUDED.video_duration, l1_silver.unified_post.video_duration),
        carousel_media_count = COALESCE(EXCLUDED.carousel_media_count, l1_silver.unified_post.carousel_media_count),
        is_sponsored = COALESCE(EXCLUDED.is_sponsored, l1_silver.unified_post.is_sponsored),
        -- migrasi 049: like tersembunyi selalu NULL. NULLIF membersihkan -1 lama
        -- yang kalau tidak akan bertahan lewat COALESCE.
        likes = CASE WHEN EXCLUDED.likes_hidden IS TRUE THEN NULL
                     ELSE NULLIF(COALESCE(EXCLUDED.likes, l1_silver.unified_post.likes), -1)
                END,
        comments = COALESCE(EXCLUDED.comments, l1_silver.unified_post.comments),
        views = COALESCE(EXCLUDED.views, l1_silver.unified_post.views),
        shares = COALESCE(EXCLUDED.shares, l1_silver.unified_post.shares),
        reach = COALESCE(EXCLUDED.reach, l1_silver.unified_post.reach),
        saved = COALESCE(EXCLUDED.saved, l1_silver.unified_post.saved),
        total_interactions = COALESCE(EXCLUDED.total_interactions, l1_silver.unified_post.total_interactions),
        reposts = COALESCE(EXCLUDED.reposts, l1_silver.unified_post.reposts),
        follows = COALESCE(EXCLUDED.follows, l1_silver.unified_post.follows),
        profile_visits = COALESCE(EXCLUDED.profile_visits, l1_silver.unified_post.profile_visits),
        reel_avg_watch_time = COALESCE(EXCLUDED.reel_avg_watch_time, l1_silver.unified_post.reel_avg_watch_time),
        reel_video_view_total_time = COALESCE(EXCLUDED.reel_video_view_total_time, l1_silver.unified_post.reel_video_view_total_time),
        -- Tiga kolom turunan di bawah SENGAJA tidak memakai COALESCE.
        -- Dengan COALESCE, hasil hitung NULL akan mempertahankan nilai lama, dan
        -- metriknya jadi basi: post yang like-nya berubah jadi disembunyikan akan
        -- tetap menyimpan engagement_rate lama. Kolom turunan harus selalu ikut
        -- nilai terbaru - pola yang sama dipakai `tier` di sp_build_unified_profile.
        engagement_rate = EXCLUDED.engagement_rate,
        likes_hidden = EXCLUDED.likes_hidden,
        is_collaboration = EXCLUDED.is_collaboration,
        -- T4b: sekali TRUE tetap TRUE. Dengan COALESCE biasa, snapshot
        -- terbaru yang tanpa Insights mematikan bendera padahal kolom
        -- Insights-nya sendiri bertahan (COALESCE di baris-baris di atas),
        -- sehingga baris yang PUNYA angka Insights mengaku tidak punya.
        has_insights = COALESCE(EXCLUDED.has_insights, false)
                    OR COALESCE(l1_silver.unified_post.has_insights, false),
        username = COALESCE(EXCLUDED.username, l1_silver.unified_post.username),
        platform_user_id = COALESCE(EXCLUDED.platform_user_id, l1_silver.unified_post.platform_user_id),
        shortcode = COALESCE(EXCLUDED.shortcode, l1_silver.unified_post.shortcode),
        hashtags = COALESCE(EXCLUDED.hashtags, l1_silver.unified_post.hashtags),
        mentions = COALESCE(EXCLUDED.mentions, l1_silver.unified_post.mentions),
        processed_at = EXCLUDED.processed_at,
        updated_at = now()
    WHERE EXCLUDED.processed_at >= l1_silver.unified_post.processed_at
       OR l1_silver.unified_post.processed_at IS NULL;
END;
$function$;

DO $verif$
DECLARE
    src text;
BEGIN
    SELECT p.prosrc INTO src
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_post';

    IF src NOT LIKE '%CASE WHEN src.likes = -1 THEN NULL ELSE src.likes END%' THEN
        RAISE EXCEPTION 'INSERT likes belum menormalkan -1 menjadi NULL.';
    END IF;
    IF src NOT LIKE '%EXCLUDED.likes_hidden IS TRUE THEN NULL%' THEN
        RAISE EXCEPTION 'ON CONFLICT likes belum menormalkan -1 menjadi NULL.';
    END IF;
    IF src NOT LIKE '%prof_foll.followers_count%' OR src NOT LIKE '%prof_id.username%' THEN
        RAISE EXCEPTION 'Logic migrasi 024 hilang dari function.';
    END IF;

    RAISE NOTICE 'Verifikasi lolos: likes tersembunyi disimpan NULL.';
END $verif$;

COMMIT;
