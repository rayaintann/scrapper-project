-- =====================================================================
-- 034_remove_tier_fallback_p01.sql
-- P-01: followers < 1.000 dan followers NULL TIDAK BOLEH mendapat tier.
--
-- MASALAH
--   l1_silver.sp_build_unified_profile() menjatuhkan followers di bawah
--   ambang terendah ke tier TERENDAH lewat COALESCE:
--
--       COALESCE(
--         (SELECT t.name FROM kol_tiers WHERE followers >= min ...),
--         (SELECT t.name FROM kol_tiers ORDER BY min_followers ASC LIMIT 1)
--       )                                    ^^^ fallback ini
--
--   Akibatnya 54 akun ber-followers 0-733 tersimpan sebagai 'Nano' di
--   l1_silver.unified_profile dan ikut turun ke l2_gold.kol_profile_card.
--   Terukur pada audit 2026-09-07.
--
-- KENAPA ALASAN ASLINYA SUDAH TIDAK BERLAKU
--   Migration 009 menulis alasan fallback itu:
--     "kol_tiers tidak punya baris untuk < 1.000, sedangkan UI
--      memetakannya ke 'Nano'. Supaya L1 dan UI tidak berbeda."
--
--   UI SEKARANG TIDAK BEGITU. src/lib/discover/kolDirectory.ts memakai
--   LEFT JOIN public.kol_tiers tanpa fallback apa pun, sehingga
--   followers < 1.000 sudah menghasilkan tier NULL di Discovery.
--   Terukur: UI 0 baris bocor, L1/L2 54 baris bocor.
--
--   Jadi membuang fallback ini MENGEMBALIKAN kesetaraan L1 <-> UI,
--   bukan merusaknya. Arah perbaikannya berbalik dari 2 tahun lalu
--   karena UI-nya yang berubah, bukan karena keputusannya berubah.
--
-- TIDAK MEMBUAT TIER BARU
--   Tidak ada 'Unclassified' maupun 'Unknown'. followers < 1.000 dan
--   followers NULL sama-sama menghasilkan tier NULL, dan populasi itu
--   (526 KOL) dihitung terpisah oleh pemakai data, bukan diberi label.
--
-- YANG TIDAK BERUBAH
--   Seluruh isi prosedur lain identik dengan migration 031 -- termasuk
--   business rule Connected (platform_user_id + oauth_token) dan rumus
--   followers_growth. File ini diturunkan langsung dari definisi 031
--   dengan MENGHAPUS cabang COALESCE saja, supaya tidak ada perubahan
--   lain yang menyelinap.
--
-- URUTAN
--   Jalankan SETELAH migration 033 (perbaikan ambang kol_tiers), lalu
--   jalankan transform_chain_job supaya L1 dan L2 ikut diperbarui.
--   Migration ini hanya mengganti definisi; data lama baru berubah
--   setelah prosedurnya dijalankan.
--
-- ROLLBACK
--   Jalankan ulang definisi migration 031, atau file cadangan
--   rollback_034_sp_build_unified_profile.sql yang diambil sebelum
--   migration ini dijalankan.
-- =====================================================================

BEGIN;

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
        -- followers_count NULL          -> tier NULL.
        -- followers_count < 1.000       -> tier NULL (P-01). Tidak cocok
        --   baris kol_tiers mana pun, dan sejak migration 034 TIDAK LAGI
        --   dijatuhkan ke tier terendah. Lihat header migration 034.
        CASE WHEN src.followers_count IS NULL THEN NULL ELSE
            (SELECT t.name FROM public.kol_tiers t
              WHERE src.followers_count >= t.min_followers
                AND (t.max_followers IS NULL OR src.followers_count <= t.max_followers)
              ORDER BY t.min_followers DESC LIMIT 1)
        END,
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
-- Verifikasi
-- ---------------------------------------------------------------------
DO $verifikasi$
DECLARE
  d text;
BEGIN
  SELECT pg_get_functiondef(p.oid) INTO d
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_profile';

  IF d IS NULL THEN
    RAISE EXCEPTION 'l1_silver.sp_build_unified_profile() tidak ditemukan';
  END IF;

  -- 1. fallback tier terendah harus HILANG
  IF position('ORDER BY t.min_followers ASC LIMIT 1' IN d) > 0 THEN
    RAISE EXCEPTION 'Fallback tier terendah masih ada di prosedur';
  END IF;

  -- 2. pencarian tier normal harus TETAP ADA
  IF position('ORDER BY t.min_followers DESC LIMIT 1' IN d) = 0 THEN
    RAISE EXCEPTION 'Pencarian tier dari kol_tiers hilang -- prosedur rusak';
  END IF;

  -- 3. business rule Connected dari migration 031 harus utuh
  IF position('sa.platform_user_id IS NOT NULL' IN d) = 0
     OR position('sa.oauth_token IS NOT NULL' IN d) = 0 THEN
    RAISE EXCEPTION 'Business rule Connected (migration 031) ikut hilang';
  END IF;

  -- 4. rumus followers_growth harus utuh
  IF position('src.prev_followers_count' IN d) = 0 THEN
    RAISE EXCEPTION 'Rumus followers_growth ikut hilang';
  END IF;

  RAISE NOTICE 'OK: fallback tier dibuang; Connected rule dan rumus growth utuh.';
END $verifikasi$;

COMMIT;
