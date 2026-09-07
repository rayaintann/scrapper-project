-- =====================================================================
-- 031_connected_rule_and_column_comments.sql
--
-- DUA HAL, KEDUANYA TANPA PERUBAHAN SCHEMA:
--   1. Melengkapi business rule Connected di l1_silver.sp_build_unified_profile()
--   2. Menambahkan COMMENT ON COLUMN supaya arti `is_verified` tidak
--      tertukar lagi antar lapisan.
--
-- ---------------------------------------------------------------------
-- 1. BUSINESS RULE CONNECTED
-- ---------------------------------------------------------------------
--   Definisi resmi (keputusan mentor):
--     social_account.platform_user_id IS NOT NULL
--     AND social_account.oauth_token  IS NOT NULL
--
--   Yang dipakai prosedur sebelum migration ini hanya separuhnya:
--     (sa.oauth_token IS NOT NULL)
--
--   Hari ini hasilnya kebetulan sama -- kedua kolom 0 terisi dari 7.496
--   baris, jadi keduanya menghasilkan 0 Connected. Perbaikan ini mencegah
--   akun yang punya oauth_token TANPA platform_user_id salah dihitung
--   sebagai Connected begitu OAuth benar-benar berjalan.
--
--   Ini BUKAN badge verified platform. Lihat butir 2.
--
-- ---------------------------------------------------------------------
-- 2. KENAPA COMMENT INI PERLU
-- ---------------------------------------------------------------------
--   Nama kolom `is_verified` berarti DUA HAL BERBEDA di lapisan berbeda:
--
--     l0_raw.tt_profile_apify.is_verified            -> badge platform (131 true)
--     l0_harmonization.tiktok_profile.is_verified    -> badge platform (124 true)
--     l1_silver.unified_profile.is_verified          -> CONNECTED aplikasi (0 true)
--     l2_gold.kol_profile_card.is_verified           -> CONNECTED aplikasi (0 true)
--
--   Nilainya TIDAK bocor antar lapisan: L1 menghitung ulang dari
--   public.social_account dan tidak pernah membaca kolom harmonization.
--   Jadi tidak ada kerusakan data -- yang berbahaya adalah namanya.
--
--   Audit 2026-09-07 sempat salah membaca ini sebagai bug transform.
--   Comment di bawah ada supaya kekeliruan itu tidak terulang.
--
--   Kolom TIDAK di-rename: rename berarti perubahan schema tanpa
--   requirement, dan akan memutus setiap pembaca yang sudah ada.
--
--   Badge verified platform tetap dibiarkan di L0/harmonization apa adanya
--   dan TIDAK dipetakan ke is_verified aplikasi.
--
-- ROLLBACK
--   Jalankan ulang definisi lama sp_build_unified_profile() dan
--   COMMENT ON COLUMN ... IS NULL untuk keenam kolom.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. Business rule Connected
-- ---------------------------------------------------------------------
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
        (sa.platform_user_id IS NOT NULL
         AND sa.oauth_token IS NOT NULL),     -- BUSINESS RULE: connection status
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

-- ---------------------------------------------------------------------
-- 2. Comment penjelas -- tidak mengubah struktur maupun data
-- ---------------------------------------------------------------------
COMMENT ON COLUMN l0_raw.tt_profile_apify.is_verified IS
  'Badge verified PLATFORM TikTok (authorMeta.verified). BUKAN Connected aplikasi. Tidak dibaca L1.';

COMMENT ON COLUMN l0_harmonization.tiktok_profile.is_verified IS
  'Badge verified PLATFORM TikTok. BUKAN Connected aplikasi. Tidak dibaca L1.';

COMMENT ON COLUMN l1_silver.unified_profile.is_verified IS
  'CONNECTED aplikasi: social_account.platform_user_id IS NOT NULL AND oauth_token IS NOT NULL. '
  'BUKAN badge platform -- badge platform ada di L0/harmonization dengan nama kolom yang sama.';

COMMENT ON COLUMN l2_gold.kol_profile_card.is_verified IS
  'CONNECTED aplikasi, disalin apa adanya dari l1_silver.unified_profile.is_verified. BUKAN badge platform.';

COMMENT ON COLUMN public.social_account.connected IS
  'Kolom lama, NOT NULL DEFAULT false, tidak pernah diisi. BUKAN definisi Connected. '
  'Patokan resmi: platform_user_id IS NOT NULL AND oauth_token IS NOT NULL.';

COMMENT ON COLUMN public.kol_directory.platform_user_id IS
  'Identity anchor untuk memvalidasi hasil scrape (migration 030). BUKAN bukti Connected -- '
  'Connected dinilai dari public.social_account, bukan dari kolom ini.';

-- ---------------------------------------------------------------------
-- Verifikasi
-- ---------------------------------------------------------------------
DO $verifikasi$
DECLARE
  n_rule int;
  n_comment int;
BEGIN
  SELECT count(*) INTO n_rule
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_profile'
    AND position('sa.platform_user_id IS NOT NULL' IN pg_get_functiondef(p.oid)) > 0
    AND position('sa.oauth_token IS NOT NULL'      IN pg_get_functiondef(p.oid)) > 0;

  IF n_rule <> 1 THEN
    RAISE EXCEPTION 'Business rule Connected tidak terpasang di sp_build_unified_profile()';
  END IF;

  SELECT count(*) INTO n_comment
  FROM pg_description d
  JOIN pg_class c   ON c.oid = d.objoid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid
  WHERE (n.nspname, c.relname, a.attname) IN (
          ('l0_raw','tt_profile_apify','is_verified'),
          ('l0_harmonization','tiktok_profile','is_verified'),
          ('l1_silver','unified_profile','is_verified'),
          ('l2_gold','kol_profile_card','is_verified'),
          ('public','social_account','connected'),
          ('public','kol_directory','platform_user_id'));

  IF n_comment <> 6 THEN
    RAISE EXCEPTION 'Comment terpasang di % dari 6 kolom', n_comment;
  END IF;

  RAISE NOTICE 'OK: business rule Connected + 6 comment terpasang.';
END $verifikasi$;

COMMIT;
