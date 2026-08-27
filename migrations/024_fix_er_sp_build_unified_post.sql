-- ============================================================================
-- 024 -- Perbaikan engagement_rate di l1_silver.sp_build_unified_post()
-- ============================================================================
--
-- Dua temuan audit 2026-08-24, keduanya di satu function, keduanya belum punya
-- tiket. Backlog SCRUM-490 seluruhnya tentang tabel L2 Gold; tidak ada yang
-- menyentuh L1.
--
--   A. PENYEBUT memakai snapshot follower TERBARU, apa pun tanggal post.
--      Snapshot profil pertama baru 2026-08-14, sedangkan post membentang dari
--      2021-02-18. Akibatnya 97 dari 205 nilai ER dihitung terhadap jumlah
--      follower yang belum dimiliki akun itu saat post tayang.
--      Contoh: jharnabhagwani 2024-04-19 tercatat ER 263,5992% -- mustahil.
--
--   B. PEMBILANG tidak memasukkan Share, padahal definisi bisnis berbunyi
--      Engagement = Likes + Comments + Shares/Reposts/Quotes.
--      TikTok kekurangan 1.056.215 share; Instagram tidak terdampak (0/130).
--
-- YANG DIUBAH -- tiga suntingan pada satu function:
--   1. Satu LATERAL dipecah jadi dua: `prof_id` (username, tanpa batas tanggal)
--      dan `prof_foll` (followers, dibatasi `date <= tanggal tayang`).
--   2. Pembilang ER ditambah `+ COALESCE(src.shares, 0)`.
--   3. Penyebut ER memakai `prof_foll.followers_count`.
--
-- DAMPAK TERUKUR (disimulasikan read-only sebelum migrasi ini ditulis):
--   l1_silver.unified_post.engagement_rate
--     Instagram  115 -> 53   (62 jadi NULL, 53 tetap sama, 0 berubah nilai)
--     TikTok      90 -> 55   (35 jadi NULL,  5 tetap sama, 50 berubah nilai)
--   feature.ig_post_analysis / tt_post_analysis (engagement_rate + rank)
--     Instagram   82 -> 37
--     TikTok      90 -> 55
--
-- YANG TIDAK BERUBAH -- diverifikasi:
--   * is_collaboration tetap 41 (Instagram) dan 0 (TikTok). Disimulasikan:
--     hasilnya identik bahkan bila LATERAL username ikut dibatasi tanggal,
--     karena fallback COALESCE(prof.username, sa.username) menutupinya.
--     Pemisahan LATERAL di sini adalah pengaman, bukan keharusan data.
--   * likes_hidden tetap 15.
--   * Jumlah baris unified_post tetap 221.
--   * l2_gold.kol_metric_daily / kol_metric_monthly TIDAK tersentuh --
--     gold.py tidak pernah membaca unified_post.engagement_rate, ia menghitung
--     engagement-nya sendiri dari kolom mentah. SCRUM-513 aman.
--
-- KEAMANAN
--   * Hanya CREATE OR REPLACE FUNCTION. Tidak ada ALTER TABLE, tidak ada
--     kolom baru, tidak ada DROP, tidak ada DELETE.
--   * Function ini tidak dijalankan oleh migrasi ini. Data baru berubah saat
--     asset Dagster `unified_post` dimaterialisasi.
--   * Pembatalan: CREATE OR REPLACE FUNCTION versi migration 020, lalu
--     materialize ulang. Data pulih persis karena dihitung ulang dari
--     harmonization.
--
-- Jalankan:
--   python apply_migration.py migrations/024_fix_er_sp_build_unified_post.sql --dry-run --yes
--   python apply_migration.py migrations/024_fix_er_sp_build_unified_post.sql --yes
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Penjaga -- pastikan kondisi awal sesuai yang diaudit.
-- ---------------------------------------------------------------------------
DO $penjaga$
DECLARE
    n_fn      int;
    n_post    bigint;
    n_collab  bigint;
    n_hidden  bigint;
BEGIN
    SELECT count(*) INTO n_fn
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_post';
    IF n_fn <> 1 THEN
        RAISE EXCEPTION 'Diharapkan tepat 1 function sp_build_unified_post, ditemukan %.', n_fn;
    END IF;

    SELECT count(*) INTO n_post   FROM l1_silver.unified_post;
    SELECT count(*) INTO n_collab FROM l1_silver.unified_post WHERE is_collaboration;
    SELECT count(*) INTO n_hidden FROM l1_silver.unified_post WHERE likes_hidden;

    RAISE NOTICE 'Kondisi awal: % baris unified_post, % kolaborasi, % likes_hidden.',
                 n_post, n_collab, n_hidden;
END $penjaga$;

-- ---------------------------------------------------------------------------
-- Function -- disalin dari migration 020 dengan tiga suntingan di atas.
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
        src.carousel_media_count, src.is_sponsored, src.likes, src.comments, src.views,
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
        likes = COALESCE(EXCLUDED.likes, l1_silver.unified_post.likes),
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

-- ---------------------------------------------------------------------------
-- Verifikasi -- function terpasang dan memuat perubahan yang dimaksud.
-- ---------------------------------------------------------------------------
DO $verif$
DECLARE
    src text;
BEGIN
    SELECT p.prosrc INTO src
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_post';

    IF src NOT LIKE '%prof_foll.followers_count%' THEN
        RAISE EXCEPTION 'LATERAL follower berbatas tanggal tidak terpasang.';
    END IF;
    IF src NOT LIKE '%COALESCE(src.shares, 0)%' THEN
        RAISE EXCEPTION 'Share tidak masuk pembilang engagement_rate.';
    END IF;
    IF src NOT LIKE '%prof_id.username%' THEN
        RAISE EXCEPTION 'LATERAL identitas tidak terpasang.';
    END IF;
    IF src LIKE '%prof.followers_count%' OR src LIKE '%prof.username%' THEN
        RAISE EXCEPTION 'Masih ada rujukan ke LATERAL lama `prof`.';
    END IF;

    RAISE NOTICE 'Verifikasi lolos: dua LATERAL terpasang, Share masuk pembilang, '
                 'tidak ada sisa rujukan LATERAL lama.';
END $verif$;

COMMIT;
