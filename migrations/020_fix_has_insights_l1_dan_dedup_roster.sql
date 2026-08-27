-- 020_fix_has_insights_l1_dan_dedup_roster.sql
--
-- Lanjutan migration 019: membereskan sisa T4 di layer L1 (T4b) dan satu-satunya
-- procedure sync bersumber-nyata yang masih tanpa dedup.
--
-- Seperti 019, seluruhnya perubahan LOGIKA di dalam 3 routine. Tidak ada tabel,
-- kolom, index, constraint, atau baris data yang disentuh. Backward-compatible:
-- nama, argumen, dan tipe kembalian ketiganya tidak berubah.
--
-- ============================================================================
-- T4b -- has_insights masih bisa dimatikan di layer L1
-- ============================================================================
--
-- Migration 019 membuat has_insights monoton di l0_harmonization, tapi kedua
-- builder L1 masih memakai pola lama:
--
--     has_insights = COALESCE(EXCLUDED.has_insights, existing.has_insights)
--
-- Untuk `unified_post` ini BISA DIJANGKAU lewat pipeline biasa dan sudah
-- dibuktikan dengan menjalankannya:
--
--     L1 sesudah snapshot D1 (official):   has_insights=True   reach=999
--     L1 sesudah snapshot D2 (apify):      has_insights=False  reach=999
--
-- Bendera mati sementara angkanya bertahan -- baris yang PUNYA data Insights
-- mengaku tidak punya. Penyebabnya: DISTINCT ON dari 019 memilih snapshot
-- TERBARU, dan snapshot terbaru yang cuma dari Apify membawa has_insights=false.
--
-- Perlu dicatat jujur: 019-lah yang membuat jalur ini bisa dijangkau. Sebelumnya
-- dua tanggal snapshot langsung menabrak SQLSTATE 21000, jadi skenarionya tidak
-- pernah sampai terjadi. COALESCE-nya sendiri sudah rapuh sejak awal.
--
-- Untuk `unified_profile` jangkauannya LEBIH RENDAH: grain sumber dan target
-- sama-sama (akun, tanggal) sehingga tidak ada penciutan, dan sesudah 019
-- l0_harmonization tidak bisa lagi menurunkan benderanya sendiri. Uji langsung
-- menunjukkan pembalikan hanya terjadi kalau baris harmonization diubah manual.
-- Tetap diperbaiki karena: ia ada di jalur data Fase 1b, kontradiksi yang sama
-- secara struktur mungkin terjadi, dan biayanya satu baris.
--
-- Perbaikan (pola yang sama dengan 019):
--     has_insights = COALESCE(EXCLUDED.has_insights, false)
--                 OR COALESCE(existing.has_insights, false)
--
-- ============================================================================
-- T3 -- sp_sync_roster_rate_card tanpa dedup, sumbernya 7.718 baris nyata
-- ============================================================================
--
-- Satu baris roster mekar jadi 14 post_type lewat CROSS JOIN LATERAL (VALUES...),
-- dan grain targetnya (social_account_id, post_type). Jadi DUA baris roster untuk
-- akun yang sama menghasilkan 14 kunci konflik kembar dalam satu statement ->
-- SQLSTATE 21000.
--
-- Kondisi sekarang (diverifikasi 2026-08-21):
--     l0_raw.kol_roster_import          7.718 baris
--     social_account_id NULL              224  (sudah dibuang WHERE)
--     duplikat (akun, platform)             0  <- aman HARI INI
--     akun yang lintas platform             0
--     instagram 3.407 baris / 3.407 akun unik
--     tiktok    4.087 baris / 4.087 akun unik
--
-- Nol duplikat itu properti data hari ini, bukan jaminan: tidak ada constraint
-- yang mencegah unggahan roster berikutnya menambah baris kedua untuk akun yang
-- sama. Inilah satu-satunya procedure sync bersumber-BERISI yang masih tanpa
-- DISTINCT ON, dan ia memberi makan 9.210 baris rate card.
--
-- Perbaikan: DISTINCT ON di grain KELUARAN (akun, post_type), pemenangnya baris
-- roster dengan created_at terbaru, `r.id` sebagai pemecah seri.
--
-- Kenapa di grain keluaran, bukan per baris roster: kalau unggahan baru
-- mengosongkan satu harga, harga lama untuk post_type itu tetap terpakai.
-- Itu BUKAN aturan baru -- WHERE-nya memang sudah membuang harga NULL/0 dan
-- ON CONFLICT-nya sudah COALESCE(EXCLUDED.fee, existing.fee). Migrasi ini hanya
-- mencegah crash; aturan merge-nya tidak diubah sama sekali.
--
-- ============================================================================
-- CAKUPAN -- 3 routine
-- ============================================================================
--
--   l1_silver.sp_build_unified_post          T4b  (terbukti bisa dijangkau)
--   l1_silver.sp_build_unified_profile       T4b  (jalur Fase 1b, berlapis)
--   l0_harmonization.sp_sync_roster_rate_card T3  (2 blok INSERT)
--
-- SENGAJA TIDAK diubah:
--   * sp_build_unified_story dan sp_build_unified_comment punya pola
--     has_insights yang sama, TAPI sumbernya 0 baris (instagram_story 0,
--     instagram_comment 0, tiktok_comment 0), targetnya 0 baris, dan keduanya
--     di luar cakupan Fase 1b. Tidak bisa diuji, jadi tidak diubah.
--   * 9 procedure sync lain masih tanpa DISTINCT ON; semua sumbernya 0 baris.
--   * sp_sync_instagram_story dan sp_sync_instagram_comment punya pola
--     has_insights lama di layer harmonization; sumbernya juga 0 baris.
--
-- ============================================================================
-- KEAMANAN
-- ============================================================================
--
--   * CREATE OR REPLACE saja -- tidak ada DROP, hak akses dan kepemilikan utuh.
--   * Tanda tangan ketiga routine tidak berubah.
--   * Tidak ada data yang disentuh; efeknya baru terasa saat procedure
--     berikutnya dijalankan.
--   * Body di luar tambalan identik byte-per-byte dengan definisi yang sedang
--     berjalan -- file ini dibangkitkan dari pg_get_functiondef lalu ditambal.
--
-- Jalankan:
--   python apply_migration.py migrations/020_fix_has_insights_l1_dan_dedup_roster.sql --dry-run --yes
--   python apply_migration.py migrations/020_fix_has_insights_l1_dan_dedup_roster.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga.
-- ---------------------------------------------------------------------------
DO $penjaga$
DECLARE
    n_pola_lama int;
    n_dedup     int;
    n_019       int;
BEGIN
    -- 019 harus sudah terpasang (020 adalah lanjutannya).
    SELECT count(*) INTO n_019
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization'
      AND p.proname IN ('sp_sync_instagram_post', 'sp_sync_tiktok_post')
      AND p.prosrc ILIKE '%DISTINCT ON%';
    IF n_019 <> 2 THEN
        RAISE EXCEPTION 'Migration 019 belum terpasang (% dari 2 procedure post '
                        'punya DISTINCT ON). Terapkan 019 lebih dulu.', n_019;
    END IF;

    -- Kedua builder L1 masih memakai pola has_insights lama.
    SELECT count(*) INTO n_pola_lama
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver'
      AND p.proname IN ('sp_build_unified_post', 'sp_build_unified_profile')
      AND p.prosrc ILIKE '%COALESCE(EXCLUDED.has_insights,%'
      AND p.prosrc NOT ILIKE '%COALESCE(EXCLUDED.has_insights, false)%';
    IF n_pola_lama <> 2 THEN
        RAISE EXCEPTION 'Pola has_insights lama ada di % builder L1, diharapkan 2 -- '
                        'migrasi 020 mungkin sudah pernah dijalankan.', n_pola_lama;
    END IF;

    -- roster belum punya DISTINCT ON.
    SELECT count(*) INTO n_dedup
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization' AND p.proname = 'sp_sync_roster_rate_card'
      AND p.prosrc ILIKE '%DISTINCT ON%';
    IF n_dedup <> 0 THEN
        RAISE EXCEPTION 'sp_sync_roster_rate_card sudah punya DISTINCT ON -- '
                        'migrasi 020 sudah pernah dijalankan.';
    END IF;

    RAISE NOTICE 'Penjaga lolos: 019 terpasang, 3 routine dalam kondisi awal.';
END $penjaga$;

-- -------------------------------------------------------------------------
-- Langkah 1a -- T4b : l1_silver.sp_build_unified_post
-- -------------------------------------------------------------------------
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
        -- engagement_rate: DIHITUNG, bukan lagi diambil dari src.
        -- Kolom engagement_rate di layer harmonization selalu NULL (actor tidak
        -- mengembalikannya, 0/221 di semua layer), jadi tidak ada nilai yang hilang.
        CASE
            WHEN src.likes IS NULL OR src.likes = -1
              OR prof.followers_count IS NULL OR prof.followers_count = 0 THEN NULL
            ELSE round((src.likes + COALESCE(src.comments, 0))::numeric
                       / prof.followers_count * 100, 4)
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
              OR COALESCE(prof.username, sa.username) IS NULL THEN NULL
            ELSE (ltrim(lower(btrim(src.username)), '@')
                  IS DISTINCT FROM
                  ltrim(lower(btrim(split_part(split_part(
                      COALESCE(prof.username, sa.username), '?', 1), '/', 1))), '@'))
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
    -- Profil terbaru akun, untuk followers dan username pemilik.
    -- LEFT JOIN, BUKAN inner: akun yang punya post tapi belum punya baris profil
    -- (kasus `inul.d` TikTok) tidak boleh hilang dari hasil.
    LEFT JOIN LATERAL (
        SELECT pr.username, pr.followers_count
        FROM l1_silver.unified_profile pr
        WHERE pr.social_account_id = sa.id
        ORDER BY pr.date DESC
        LIMIT 1
    ) prof ON true
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

-- -------------------------------------------------------------------------
-- Langkah 1b -- T4b : l1_silver.sp_build_unified_profile
-- -------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION l1_silver.sp_build_unified_profile()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    INSERT INTO l1_silver.unified_profile (
        social_account_id, platform_id, date, username, display_name, bio, avatar_url,
        website, open_id, is_verified, followers_count, following_count, media_count,
        likes_count, reach, profile_views, accounts_engaged, profile_links_taps,
        total_interactions, likes, comments, shares, saves, replies, reposts,
        has_insights, source, source_table, source_id, processed_at,
        platform_user_id, profile_url, is_private, tier, followers_growth
    )
    SELECT
        sa.id, sa.platform_id, src.date, src.username, src.display_name, src.bio,
        src.avatar_url, src.website, src.open_id,
        (sa.oauth_token IS NOT NULL),          -- BUSINESS RULE: connection status
        src.followers_count,
        src.following_count, src.media_count, src.likes_count, src.reach, src.profile_views,
        src.accounts_engaged, src.profile_links_taps, src.total_interactions, src.likes,
        src.comments, src.shares, src.saves, src.replies, src.reposts, src.has_insights,
        src.source, src.source_table, src.source_id, src.processed_at,
        src.platform_user_id, src.profile_url, src.is_private,
        -- tier: klasifikasi followers_count memakai ambang public.kol_tiers.
        -- followers_count NULL -> NULL. Di bawah min_followers terendah
        -- (mis. < 1.000) tidak cocok baris mana pun, jadi jatuh ke tier
        -- terendah lewat COALESCE, mengikuti perilaku TIER() di UI.
        CASE WHEN src.followers_count IS NULL THEN NULL ELSE COALESCE(
            (SELECT t.name FROM public.kol_tiers t
              WHERE src.followers_count >= t.min_followers
                AND (t.max_followers IS NULL OR src.followers_count <= t.max_followers)
              ORDER BY t.min_followers DESC LIMIT 1),
            (SELECT t.name FROM public.kol_tiers t ORDER BY t.min_followers ASC LIMIT 1)
        ) END,
        -- followers_growth: persen perubahan followers terhadap SNAPSHOT
        -- SEBELUMNYA milik akun yang sama, yaitu baris dengan `date` terdekat
        -- yang lebih kecil. NULL kalau belum ada snapshot pembanding, kalau
        -- followers sebelumnya NULL atau 0 (pembagian tidak terdefinisi), atau
        -- kalau followers sekarang NULL. Tidak ada tebakan, tidak ada 0.
        CASE
            WHEN src.prev_followers_count IS NULL
              OR src.prev_followers_count = 0
              OR src.followers_count IS NULL THEN NULL
            ELSE round((src.followers_count - src.prev_followers_count)::numeric
                       / src.prev_followers_count * 100, 4)
        END
    FROM (
        -- Lapisan window: menghitung followers snapshot sebelumnya per akun.
        -- Sumbernya layer harmonization, BUKAN unified_profile, karena:
        --   * kedua tabel harmonization bergrain (social_account_id, date) dengan
        --     UNIQUE dan ON CONFLICT yang sama, jadi riwayatnya sama lengkapnya;
        --   * satu statement INSERT tidak bisa melihat baris yang sedang
        --     dimasukkannya sendiri, sehingga lookup ke unified_profile akan
        --     memberi hasil berbeda antara backfill sekali jalan dan pengisian
        --     bertahap. Memakai src membuat hasilnya deterministik.
        SELECT u.*,
               LAG(u.followers_count) OVER (
                   PARTITION BY u.social_account_id ORDER BY u.date
               ) AS prev_followers_count
        FROM (
            -- Instagram: avatar_url kini tersedia (migration 007); open_id & likes_count tetap tidak ada
            SELECT social_account_id, date, username, name AS display_name, biography AS bio,
                   avatar_url, website, NULL::varchar AS open_id,
                   followers_count, follows_count AS following_count,
                   media_count, NULL::bigint AS likes_count, reach, profile_views,
                   accounts_engaged, profile_links_taps, total_interactions, likes, comments,
                   shares, saves, replies, reposts, has_insights, source, source_table,
                   source_id, processed_at,
                   platform_user_id, profile_url, is_private
            FROM l0_harmonization.instagram_profile
            UNION ALL
            -- TikTok: website kini tersedia (migration 007); insight metrics tetap tidak ada
            SELECT social_account_id, date, username, display_name, bio_description AS bio,
                   avatar_url, website, open_id,
                   follower_count, following_count, video_count AS media_count, likes_count,
                   NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
                   NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
                   NULL::bigint, NULL::bigint, NULL::boolean, source, source_table,
                   source_id, processed_at,
                   platform_user_id, profile_url, is_private
            FROM l0_harmonization.tiktok_profile
        ) u
    ) src
    JOIN public.social_account sa ON sa.id = src.social_account_id
    ON CONFLICT (social_account_id, date) DO UPDATE SET
        username = COALESCE(EXCLUDED.username, l1_silver.unified_profile.username),
        display_name = COALESCE(EXCLUDED.display_name, l1_silver.unified_profile.display_name),
        bio = COALESCE(EXCLUDED.bio, l1_silver.unified_profile.bio),
        avatar_url = COALESCE(EXCLUDED.avatar_url, l1_silver.unified_profile.avatar_url),
        website = COALESCE(EXCLUDED.website, l1_silver.unified_profile.website),
        open_id = COALESCE(EXCLUDED.open_id, l1_silver.unified_profile.open_id),
        is_verified = EXCLUDED.is_verified,   -- connection status: selalu definit
        followers_count = COALESCE(EXCLUDED.followers_count, l1_silver.unified_profile.followers_count),
        following_count = COALESCE(EXCLUDED.following_count, l1_silver.unified_profile.following_count),
        media_count = COALESCE(EXCLUDED.media_count, l1_silver.unified_profile.media_count),
        likes_count = COALESCE(EXCLUDED.likes_count, l1_silver.unified_profile.likes_count),
        reach = COALESCE(EXCLUDED.reach, l1_silver.unified_profile.reach),
        profile_views = COALESCE(EXCLUDED.profile_views, l1_silver.unified_profile.profile_views),
        accounts_engaged = COALESCE(EXCLUDED.accounts_engaged, l1_silver.unified_profile.accounts_engaged),
        profile_links_taps = COALESCE(EXCLUDED.profile_links_taps, l1_silver.unified_profile.profile_links_taps),
        total_interactions = COALESCE(EXCLUDED.total_interactions, l1_silver.unified_profile.total_interactions),
        likes = COALESCE(EXCLUDED.likes, l1_silver.unified_profile.likes),
        comments = COALESCE(EXCLUDED.comments, l1_silver.unified_profile.comments),
        shares = COALESCE(EXCLUDED.shares, l1_silver.unified_profile.shares),
        saves = COALESCE(EXCLUDED.saves, l1_silver.unified_profile.saves),
        replies = COALESCE(EXCLUDED.replies, l1_silver.unified_profile.replies),
        reposts = COALESCE(EXCLUDED.reposts, l1_silver.unified_profile.reposts),
        -- T4b: sekali TRUE tetap TRUE. Dengan COALESCE biasa, snapshot
        -- terbaru yang tanpa Insights mematikan bendera padahal kolom
        -- Insights-nya sendiri bertahan (COALESCE di baris-baris di atas),
        -- sehingga baris yang PUNYA angka Insights mengaku tidak punya.
        has_insights = COALESCE(EXCLUDED.has_insights, false)
                    OR COALESCE(l1_silver.unified_profile.has_insights, false),
        platform_user_id = COALESCE(EXCLUDED.platform_user_id, l1_silver.unified_profile.platform_user_id),
        profile_url = COALESCE(EXCLUDED.profile_url, l1_silver.unified_profile.profile_url),
        is_private = COALESCE(EXCLUDED.is_private, l1_silver.unified_profile.is_private),
        tier = EXCLUDED.tier,   -- turunan followers_count: selalu ikut nilai terbaru
        -- Turunan juga: tanpa penugasan langsung, hasil hitung NULL akan
        -- mempertahankan nilai lama dan metriknya jadi basi.
        followers_growth = EXCLUDED.followers_growth,
        processed_at = EXCLUDED.processed_at,
        updated_at = now()
    WHERE EXCLUDED.processed_at >= l1_silver.unified_profile.processed_at
       OR l1_silver.unified_profile.processed_at IS NULL;
END;
$function$;

-- -------------------------------------------------------------------------
-- Langkah 1c -- T3  : l0_harmonization.sp_sync_roster_rate_card
-- -------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE l0_harmonization.sp_sync_roster_rate_card()
 LANGUAGE plpgsql
AS $procedure$
DECLARE
  v_log_id uuid;
  v_baca   bigint := 0;
  v_lewat  bigint := 0;
  v_ig     bigint := 0;
  v_tt     bigint := 0;
BEGIN
  SELECT count(*) INTO v_baca FROM l0_raw.kol_roster_import;

  INSERT INTO l0_harmonization.sync_log
    (target_table, source_table, source, sync_date, status, started_at)
  VALUES ('instagram_rate_card + tiktok_rate_card',
          'l0_raw.kol_roster_import', 'uploader',
          current_date, 'running', now())
  RETURNING id INTO v_log_id;

  -- -------------------------------------------------------------------
  -- Rate card Instagram
  --
  -- Kolom social_account_id di tabel rate card menunjuk ke
  -- public.social_account, jadi yang dipakai r.social_account_id.
  -- Lihat CATATAN 1.
  -- -------------------------------------------------------------------
  INSERT INTO l0_harmonization.instagram_rate_card (
    social_account_id, post_type, fee, currency,
    source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id,
    s.post_type,
    s.harga::numeric,
    'IDR',
    'uploader',
    'l0_raw.kol_roster_import',
    s.source_id,
    s.processed_at
  FROM (
    -- T3: satu baris per (akun, post_type). Tiap baris roster mekar jadi 14
    -- post_type, jadi DUA baris roster untuk akun yang sama menghasilkan 14
    -- kunci konflik kembar dalam satu statement -> SQLSTATE 21000.
    --
    -- Dedup di grain KELUARAN (akun, post_type), bukan di grain baris roster:
    -- kalau unggahan baru mengosongkan satu harga, harga lama untuk post_type
    -- itu tetap terpakai. Itu memang perilaku yang sudah ada -- WHERE di bawah
    -- sudah membuang harga NULL/0 dan ON CONFLICT-nya sudah
    -- COALESCE(EXCLUDED.fee, ...). Migrasi ini hanya mencegah crash, TIDAK
    -- mengubah aturan merge.
    SELECT DISTINCT ON (r.social_account_id, x.post_type)
           r.social_account_id,
           x.post_type,
           x.harga,
           r.id                             AS source_id,
           COALESCE(r.created_at, now())    AS processed_at
  FROM l0_raw.kol_roster_import r
  JOIN public.platforms p ON p.id = r.platform_id AND p.key = 'instagram'
  CROSS JOIN LATERAL (VALUES
    ('story',           r.story_price),
    ('story_session',   r.story_session_price),
    ('feed_photo',      r.feed_photo_price),
    ('feed_video',      r.feed_video_price),
    ('reel',            r.reel_price),
    ('live',            r.live_price),
    ('owning_asset',    r.owning_asset_price),
    ('tap_link',        r.tap_link_price),
    ('link_in_bio',     r.link_in_bio_price),
    ('live_attendance', r.live_attendance_price),
    ('host',            r.host_price),
    ('comment',         r.comment_price),
    ('photoshoot',      r.photoshoot_price),
    ('other',           r.other_price)
  ) AS x(post_type, harga)
  WHERE r.social_account_id IS NOT NULL
    AND x.harga IS NOT NULL
    AND x.harga::numeric > 0
    ORDER BY r.social_account_id, x.post_type,
             COALESCE(r.created_at, now()) DESC NULLS LAST, r.id
  ) s
  ON CONFLICT (social_account_id, post_type) DO UPDATE SET
    fee          = COALESCE(EXCLUDED.fee, instagram_rate_card.fee),
    currency     = EXCLUDED.currency,
    source       = EXCLUDED.source,
    source_table = EXCLUDED.source_table,
    source_id    = EXCLUDED.source_id,
    processed_at = EXCLUDED.processed_at
  WHERE instagram_rate_card.processed_at < EXCLUDED.processed_at;

  GET DIAGNOSTICS v_ig = ROW_COUNT;

  -- -------------------------------------------------------------------
  -- Rate card TikTok
  -- -------------------------------------------------------------------
  INSERT INTO l0_harmonization.tiktok_rate_card (
    social_account_id, post_type, fee, currency,
    source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id,
    s.post_type,
    s.harga::numeric,
    'IDR',
    'uploader',
    'l0_raw.kol_roster_import',
    s.source_id,
    s.processed_at
  FROM (
    -- T3: satu baris per (akun, post_type). Tiap baris roster mekar jadi 14
    -- post_type, jadi DUA baris roster untuk akun yang sama menghasilkan 14
    -- kunci konflik kembar dalam satu statement -> SQLSTATE 21000.
    --
    -- Dedup di grain KELUARAN (akun, post_type), bukan di grain baris roster:
    -- kalau unggahan baru mengosongkan satu harga, harga lama untuk post_type
    -- itu tetap terpakai. Itu memang perilaku yang sudah ada -- WHERE di bawah
    -- sudah membuang harga NULL/0 dan ON CONFLICT-nya sudah
    -- COALESCE(EXCLUDED.fee, ...). Migrasi ini hanya mencegah crash, TIDAK
    -- mengubah aturan merge.
    SELECT DISTINCT ON (r.social_account_id, x.post_type)
           r.social_account_id,
           x.post_type,
           x.harga,
           r.id                             AS source_id,
           COALESCE(r.created_at, now())    AS processed_at
  FROM l0_raw.kol_roster_import r
  JOIN public.platforms p ON p.id = r.platform_id AND p.key = 'tiktok'
  CROSS JOIN LATERAL (VALUES
    ('story',           r.story_price),
    ('story_session',   r.story_session_price),
    ('feed_photo',      r.feed_photo_price),
    ('feed_video',      r.feed_video_price),
    ('reel',            r.reel_price),
    ('live',            r.live_price),
    ('owning_asset',    r.owning_asset_price),
    ('tap_link',        r.tap_link_price),
    ('link_in_bio',     r.link_in_bio_price),
    ('live_attendance', r.live_attendance_price),
    ('host',            r.host_price),
    ('comment',         r.comment_price),
    ('photoshoot',      r.photoshoot_price),
    ('other',           r.other_price)
  ) AS x(post_type, harga)
  WHERE r.social_account_id IS NOT NULL
    AND x.harga IS NOT NULL
    AND x.harga::numeric > 0
    ORDER BY r.social_account_id, x.post_type,
             COALESCE(r.created_at, now()) DESC NULLS LAST, r.id
  ) s
  ON CONFLICT (social_account_id, post_type) DO UPDATE SET
    fee          = COALESCE(EXCLUDED.fee, tiktok_rate_card.fee),
    currency     = EXCLUDED.currency,
    source       = EXCLUDED.source,
    source_table = EXCLUDED.source_table,
    source_id    = EXCLUDED.source_id,
    processed_at = EXCLUDED.processed_at
  WHERE tiktok_rate_card.processed_at < EXCLUDED.processed_at;

  GET DIAGNOSTICS v_tt = ROW_COUNT;

  SELECT count(*) INTO v_lewat
  FROM l0_raw.kol_roster_import r
  WHERE r.social_account_id IS NULL OR r.platform_id IS NULL;

  UPDATE l0_harmonization.sync_log
  SET status='success', rows_read=v_baca,
      rows_inserted=v_ig + v_tt, rows_skipped=v_lewat,
      finished_at=now(),
      duration_seconds=EXTRACT(EPOCH FROM (now()-started_at))
  WHERE id=v_log_id;

EXCEPTION WHEN OTHERS THEN
  UPDATE l0_harmonization.sync_log
  SET status='failed', error_message=SQLERRM, finished_at=now()
  WHERE id=v_log_id;
  RAISE;
END $procedure$;


-- ---------------------------------------------------------------------------
-- Langkah 2 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $verif$
DECLARE
    n_or      int;
    n_dedup   int;
    n_lama    int;
    n_routine int;
    n_baris   bigint;
BEGIN
    SELECT count(*) INTO n_or
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver'
      AND p.proname IN ('sp_build_unified_post', 'sp_build_unified_profile')
      AND p.prosrc ILIKE '%COALESCE(EXCLUDED.has_insights, false)%';

    SELECT count(*) INTO n_dedup
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization' AND p.proname = 'sp_sync_roster_rate_card'
      AND p.prosrc ILIKE '%DISTINCT ON (r.social_account_id, x.post_type)%';

    -- story/comment SENGAJA masih pola lama; dipastikan tidak ikut berubah.
    SELECT count(*) INTO n_lama
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver'
      AND p.proname IN ('sp_build_unified_story', 'sp_build_unified_comment')
      AND p.prosrc ILIKE '%COALESCE(EXCLUDED.has_insights,%'
      AND p.prosrc NOT ILIKE '%COALESCE(EXCLUDED.has_insights, false)%';

    SELECT count(*) INTO n_routine
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN ('l0_harmonization', 'l1_silver');

    SELECT (SELECT count(*) FROM l0_harmonization.instagram_rate_card)
         + (SELECT count(*) FROM l0_harmonization.tiktok_rate_card)
         + (SELECT count(*) FROM l1_silver.unified_post)
         + (SELECT count(*) FROM l1_silver.unified_profile)
      INTO n_baris;

    IF n_or <> 2 THEN
        RAISE EXCEPTION 'OR-merge terpasang di % builder L1, seharusnya 2', n_or;
    END IF;
    IF n_dedup <> 1 THEN
        RAISE EXCEPTION 'DISTINCT ON di sp_sync_roster_rate_card tidak terpasang';
    END IF;
    IF n_lama <> 2 THEN
        RAISE EXCEPTION 'story/comment seharusnya TETAP pola lama (2), ditemukan % -- '
                        'migrasi ini tidak boleh menyentuh keduanya.', n_lama;
    END IF;
    IF n_routine <> 24 THEN
        RAISE EXCEPTION 'Jumlah routine %, seharusnya tetap 24', n_routine;
    END IF;
    IF n_baris <> 11402 THEN
        RAISE EXCEPTION 'Jumlah baris berubah jadi % -- seharusnya tetap 11402 '
                        '(4019 + 5191 + 221 + 1971).', n_baris;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: T4b 2/2, T3 roster 1/1, story+comment tetap '
                 'pola lama, 24 routine utuh, 11402 baris tidak berubah.';
END $verif$;

COMMIT;
