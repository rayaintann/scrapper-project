-- =====================================================================
-- 011_build_unified_profile_with_metrics.sql
--
-- Lanjutan 009 + 010. Memetakan metric Profile baru ke L1.
-- Sumber tetap l0_harmonization (jalur resmi, TIDAK bypass).
--
-- Perubahan terhadap 006 — HANYA menambah 4 kolom:
--
--   platform_user_id  DIRECT dari l0_harmonization.*.platform_user_id
--   profile_url       DIRECT dari l0_harmonization.*.profile_url
--   is_private        DIRECT dari l0_harmonization.*.is_private
--   tier              CALCULATED dari followers_count x public.kol_tiers
--
-- FORMULA tier (didokumentasikan):
--     tier = nama baris kol_tiers dengan min_followers TERBESAR yang
--            masih <= followers_count, dan max_followers >= followers_count
--            (atau max_followers NULL untuk tier teratas).
--     followers_count IS NULL            -> tier NULL
--     followers_count < min terendah     -> tier terendah ('Nano')
--   Ambang dibaca dari tabel, tidak di-hardcode, sehingga kalau
--   kol_tiers berubah, L1 ikut berubah setelah procedure dijalankan lagi.
--
-- Di ON CONFLICT, tier memakai EXCLUDED langsung (bukan COALESCE) karena
-- tier adalah turunan followers_count: kalau followers berubah, tier
-- harus ikut berubah. Tiga kolom lain tetap COALESCE seperti pola lama.
--
-- is_verified TIDAK diubah: tetap (social_account.oauth_token IS NOT NULL).
-- TIDAK membuat tabel baru. TIDAK menulis ke l0_raw / l0_harmonization.
-- TIDAK menghidupkan kembali sp_sync_unified_profile().
-- =====================================================================

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
        platform_user_id, profile_url, is_private, tier
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
        ) END
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
        has_insights = COALESCE(EXCLUDED.has_insights, l1_silver.unified_profile.has_insights),
        platform_user_id = COALESCE(EXCLUDED.platform_user_id, l1_silver.unified_profile.platform_user_id),
        profile_url = COALESCE(EXCLUDED.profile_url, l1_silver.unified_profile.profile_url),
        is_private = COALESCE(EXCLUDED.is_private, l1_silver.unified_profile.is_private),
        tier = EXCLUDED.tier,   -- turunan followers_count: selalu ikut nilai terbaru
        processed_at = EXCLUDED.processed_at,
        updated_at = now()
    WHERE EXCLUDED.processed_at >= l1_silver.unified_profile.processed_at
       OR l1_silver.unified_profile.processed_at IS NULL;
END;
$function$;
