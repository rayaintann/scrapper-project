-- =====================================================================
-- 006_fix_sp_build_unified_profile.sql
-- Perbaikan l1_silver.sp_build_unified_profile()
--
-- Flow yang dipertahankan:
--   l0_raw -> l0_harmonization -> l1_silver   (TIDAK bypass)
--   Sumber tetap l0_harmonization.instagram_profile + tiktok_profile.
--
-- YANG DIUBAH — HANYA is_verified
--
--   Versi lama memetakan badge verified platform ke L1:
--     - Instagram: instagram_profile tidak punya kolom is_verified sama
--       sekali, jadi versi lama menulis NULL::boolean.
--     - TikTok   : mengambil tiktok_profile.is_verified apa adanya
--       (badge platform: 925 false / 115 true).
--
--   BUSINESS RULE (keputusan mentor):
--     is_verified = status akun KOL sudah terhubung/OAuth ke sistem kita
--                 = (public.social_account.oauth_token IS NOT NULL)
--
--   Badge platform TIDAK BOLEH dipakai sebagai is_verified L1. Karena itu
--   kolom is_verified dibuang seluruhnya dari subquery `src`, supaya tidak
--   ada jalan bagi nilai badge untuk bocor ke L1. Nilainya dihitung di
--   SELECT terluar dari `sa`, yang memang sudah di-JOIN untuk mengambil
--   sa.id dan sa.platform_id.
--
--   Badge platform tetap tersimpan apa adanya di layer harmonization
--   (l0_harmonization.tiktok_profile.is_verified) — harmonization adalah
--   salinan setia L0; business rule hanya berlaku di L1.
--
--   Di klausa ON CONFLICT, is_verified memakai EXCLUDED langsung, BUKAN
--   COALESCE. Ekspresi (oauth_token IS NOT NULL) tidak pernah NULL, dan
--   connection status harus mengikuti kondisi terkini: kalau sebuah akun
--   di-disconnect, COALESCE akan membuatnya terkunci di 'true' selamanya.
--
-- TIDAK ADA perubahan lain. Kolom, sumber, urutan UNION, guard
-- processed_at, dan seluruh klausa COALESCE lainnya sama persis dengan
-- versi lama.
--
-- REVISI setelah migration 007 (kolom baru di layer harmonization):
--   - l0_harmonization.instagram_profile.avatar_url  -> unified_profile.avatar_url
--   - l0_harmonization.tiktok_profile.website        -> unified_profile.website
--   Versi 006 sebelumnya menulis NULL::text untuk kedua field itu karena
--   kolomnya memang belum ada. Sekarang dibaca langsung dari harmonization,
--   sehingga unified_profile bisa dibangun ulang dari kosong tanpa
--   kehilangan data (sebelumnya akan kehilangan 931 avatar IG + 488
--   website TikTok).
--
--   Catatan bentuk data: website TikTok dari harmonization sudah
--   dinormalisasi berskema https:// oleh migration 007, sedangkan nilai
--   yang ada di L1 sekarang berasal dari jalur bypass yang belum
--   dinormalisasi. Jadi UPSERT ini akan MEMPERBAIKI baris tersebut,
--   bukan merusaknya.
--
-- TIDAK membuat tabel baru. TIDAK menulis ke l0_raw maupun
-- l0_harmonization. TIDAK menyentuh sp_sync_unified_profile() (bypass).
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
        has_insights, source, source_table, source_id, processed_at
    )
    SELECT
        sa.id, sa.platform_id, src.date, src.username, src.display_name, src.bio,
        src.avatar_url, src.website, src.open_id,
        (sa.oauth_token IS NOT NULL),          -- BUSINESS RULE: connection status
        src.followers_count,
        src.following_count, src.media_count, src.likes_count, src.reach, src.profile_views,
        src.accounts_engaged, src.profile_links_taps, src.total_interactions, src.likes,
        src.comments, src.shares, src.saves, src.replies, src.reposts, src.has_insights,
        src.source, src.source_table, src.source_id, src.processed_at
    FROM (
        -- Instagram: avatar_url kini tersedia (migration 007); open_id & likes_count tetap tidak ada
        SELECT social_account_id, date, username, name AS display_name, biography AS bio,
               avatar_url, website, NULL::varchar AS open_id,
               followers_count, follows_count AS following_count,
               media_count, NULL::bigint AS likes_count, reach, profile_views,
               accounts_engaged, profile_links_taps, total_interactions, likes, comments,
               shares, saves, replies, reposts, has_insights, source, source_table,
               source_id, processed_at
        FROM l0_harmonization.instagram_profile
        UNION ALL
        -- TikTok: website kini tersedia (migration 007); insight metrics tetap tidak ada
        SELECT social_account_id, date, username, display_name, bio_description AS bio,
               avatar_url, website, open_id,
               follower_count, following_count, video_count AS media_count, likes_count,
               NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
               NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
               NULL::bigint, NULL::bigint, NULL::boolean, source, source_table,
               source_id, processed_at
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
        processed_at = EXCLUDED.processed_at,
        updated_at = now()
    WHERE EXCLUDED.processed_at >= l1_silver.unified_profile.processed_at
       OR l1_silver.unified_profile.processed_at IS NULL;
END;
$function$;
