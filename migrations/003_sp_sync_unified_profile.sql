-- #####################################################################
-- ##                                                                 ##
-- ##   SUPERSEDED / OBSOLETE  --  JANGAN DIJALANKAN                  ##
-- ##                                                                 ##
-- #####################################################################
--
-- Status   : OBSOLETE sejak cleanup jalur bypass.
-- Diganti  : migrations/006_fix_sp_build_unified_profile.sql
--
-- KENAPA JANGAN DIJALANKAN
--   Script ini membuat l1_silver.sp_sync_unified_profile(), yaitu jalur
--   BYPASS yang membaca l0_raw langsung ke l1_silver.unified_profile,
--   melewati layer l0_harmonization. Procedure tersebut SUDAH DI-DROP
--   dari database dan tidak boleh dibuat ulang.
--
--   Menjalankan file ini akan menghidupkan kembali jalur bypass dan
--   melanggar arsitektur layer yang berlaku.
--
-- JALUR L1 YANG RESMI SEKARANG
--
--     l0_raw
--        |  l0_harmonization.sp_sync_instagram_profile()   (005, 008)
--        |  l0_harmonization.sp_sync_tiktok_profile()      (004, 008)
--        v
--     l0_harmonization
--        |  l1_silver.sp_build_unified_profile()           (006)
--        v
--     l1_silver.unified_profile
--
--   Satu-satunya cara sah mengisi l1_silver.unified_profile adalah:
--       SELECT l1_silver.sp_build_unified_profile();
--
-- CATATAN TAMBAHAN
--   Selain melewati layer harmonization, script di bawah juga memuat
--   business rule is_verified versi LAMA. Aturan yang berlaku sekarang:
--       is_verified = (public.social_account.oauth_token IS NOT NULL)
--   yaitu status akun terhubung/OAuth ke sistem, BUKAN verified badge
--   platform. Aturan itu diterapkan di 006.
--
--   File ini sengaja DIPERTAHANKAN apa adanya sebagai catatan sejarah
--   migrasi. SQL di bawah header ini TIDAK diubah sedikit pun.
--
-- #####################################################################


-- =====================================================================
-- 003_sp_sync_unified_profile.sql
-- L0 (l0_raw profile) -> L1 (l1_silver.unified_profile)
--
-- Mengikuti pola l1_silver.sp_sync_unified_rate_card():
--   - satu PROCEDURE, blok terpisah per platform
--   - JOIN public.platforms ON key (bukan UUID hardcode)
--   - ON CONFLICT (social_account_id, date) DO UPDATE + COALESCE
--   - guard processed_at supaya data lama tidak menimpa data baru
--   - logging ke l0_harmonization.sync_log
--
-- CATATAN sumber:
--   Sengaja membaca l0_raw LANGSUNG, bukan l0_harmonization, karena:
--     * l0_harmonization.tiktok_profile masih 0 baris, dan
--     * sp_sync_tiktok_profile / sp_sync_instagram_profile sudah rusak
--       (mereferensi kolom followers_growth / follows / unfollows /
--        net_follows yang sudah di-DROP dari tabel harmonization).
--   Prosedur ini TIDAK menulis apa pun ke l0_raw / l0_harmonization
--   (selain satu baris audit di sync_log).
--
-- l1_silver.sp_build_unified_profile() yang lama TIDAK diubah.
-- =====================================================================

CREATE OR REPLACE PROCEDURE l1_silver.sp_sync_unified_profile()
LANGUAGE plpgsql
AS $procedure$
DECLARE
  v_log_id  uuid;
  v_ig      bigint := 0;
  v_tt      bigint := 0;
  v_ig_off  bigint := 0;
  v_tt_off  bigint := 0;
BEGIN
  INSERT INTO l0_harmonization.sync_log
    (target_table, source_table, source, sync_date, status, started_at)
  VALUES ('l1_silver.unified_profile',
          'l0_raw.ig_profile_apify + ig_profile_official + tt_profile_apify + tt_profile_official',
          'l0_raw', current_date, 'running', now())
  RETURNING id INTO v_log_id;

  -- ==================================================================
  -- 1) INSTAGRAM - APIFY
  -- ==================================================================
  INSERT INTO l1_silver.unified_profile (
    social_account_id, platform_id, date, username, display_name, bio, avatar_url,
    website, open_id, is_verified, followers_count, following_count, media_count,
    likes_count, reach, profile_views, accounts_engaged, profile_links_taps,
    total_interactions, likes, comments, shares, saves, replies, reposts,
    has_insights, source, source_table, source_id, processed_at, created_at, updated_at)
  SELECT
    s.social_account_id,
    p.id,
    COALESCE(s.scraped_at, s.fetched_at, now())::date,
    ltrim(lower(btrim(split_part(split_part(s.username, '?', 1), '/', 1))), '@'),
    NULLIF(btrim(s.name), ''),
    NULLIF(btrim(s.biography), ''),
    NULLIF(btrim(COALESCE(s.raw_payload->>'profilePicUrlHD',
                          s.raw_payload->>'profilePicUrl')), ''),
    NULLIF(btrim(s.website), ''),
    NULL::varchar,                                             -- open_id: IG tidak punya
    (sa.oauth_token IS NOT NULL),                              -- BUSINESS RULE: connection status
    s.followers_count::bigint,
    s.follows_count::bigint,
    COALESCE(s.media_count, (s.raw_payload->>'postsCount')::int),
    NULL::bigint,                                              -- likes_count: IG tidak punya
    NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,    -- insight fields: official saja
    NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
    NULL::bigint, NULL::bigint, NULL::bigint,
    false,                                                     -- has_insights
    'apify', 'l0_raw.ig_profile_apify', s.id,
    COALESCE(s.scraped_at, s.fetched_at, now()),
    now(), now()
  FROM (
    SELECT DISTINCT ON (r.social_account_id,
                        COALESCE(r.scraped_at, r.fetched_at, now())::date) r.*
    FROM l0_raw.ig_profile_apify r
    WHERE r.social_account_id IS NOT NULL
      AND r.username IS NOT NULL
      AND btrim(r.username) <> ''
    ORDER BY r.social_account_id,
             COALESCE(r.scraped_at, r.fetched_at, now())::date,
             r.scraped_at DESC NULLS LAST, r.fetched_at DESC NULLS LAST, r.id
  ) s
  JOIN public.social_account sa ON sa.id = s.social_account_id      -- jaga FK
  JOIN public.platforms      p  ON p.key = 'instagram'
  ON CONFLICT (social_account_id, date) DO UPDATE SET
    platform_id        = EXCLUDED.platform_id,
    username           = COALESCE(EXCLUDED.username,           unified_profile.username),
    display_name       = COALESCE(EXCLUDED.display_name,       unified_profile.display_name),
    bio                = COALESCE(EXCLUDED.bio,                unified_profile.bio),
    avatar_url         = COALESCE(EXCLUDED.avatar_url,         unified_profile.avatar_url),
    website            = COALESCE(EXCLUDED.website,            unified_profile.website),
    open_id            = COALESCE(EXCLUDED.open_id,            unified_profile.open_id),
    is_verified        = EXCLUDED.is_verified,   -- connection status: selalu definit
    followers_count    = COALESCE(EXCLUDED.followers_count,    unified_profile.followers_count),
    following_count    = COALESCE(EXCLUDED.following_count,    unified_profile.following_count),
    media_count        = COALESCE(EXCLUDED.media_count,        unified_profile.media_count),
    likes_count        = COALESCE(EXCLUDED.likes_count,        unified_profile.likes_count),
    reach              = COALESCE(EXCLUDED.reach,              unified_profile.reach),
    profile_views      = COALESCE(EXCLUDED.profile_views,      unified_profile.profile_views),
    accounts_engaged   = COALESCE(EXCLUDED.accounts_engaged,   unified_profile.accounts_engaged),
    profile_links_taps = COALESCE(EXCLUDED.profile_links_taps, unified_profile.profile_links_taps),
    total_interactions = COALESCE(EXCLUDED.total_interactions, unified_profile.total_interactions),
    likes              = COALESCE(EXCLUDED.likes,              unified_profile.likes),
    comments           = COALESCE(EXCLUDED.comments,           unified_profile.comments),
    shares             = COALESCE(EXCLUDED.shares,             unified_profile.shares),
    saves              = COALESCE(EXCLUDED.saves,              unified_profile.saves),
    replies            = COALESCE(EXCLUDED.replies,            unified_profile.replies),
    reposts            = COALESCE(EXCLUDED.reposts,            unified_profile.reposts),
    has_insights       = COALESCE(EXCLUDED.has_insights,       unified_profile.has_insights),
    source             = EXCLUDED.source,
    source_table       = EXCLUDED.source_table,
    source_id          = EXCLUDED.source_id,
    processed_at       = EXCLUDED.processed_at,
    updated_at         = now()
  WHERE unified_profile.processed_at IS NULL
     OR unified_profile.processed_at <= EXCLUDED.processed_at;

  GET DIAGNOSTICS v_ig = ROW_COUNT;

  -- ==================================================================
  -- 2) TIKTOK - APIFY
  -- ==================================================================
  INSERT INTO l1_silver.unified_profile (
    social_account_id, platform_id, date, username, display_name, bio, avatar_url,
    website, open_id, is_verified, followers_count, following_count, media_count,
    likes_count, reach, profile_views, accounts_engaged, profile_links_taps,
    total_interactions, likes, comments, shares, saves, replies, reposts,
    has_insights, source, source_table, source_id, processed_at, created_at, updated_at)
  SELECT
    s.social_account_id,
    p.id,
    COALESCE(s.scraped_at, s.fetched_at, now())::date,
    ltrim(lower(btrim(split_part(split_part(s.username, '?', 1), '/', 1))), '@'),
    NULLIF(btrim(s.display_name), ''),
    NULLIF(btrim(s.bio_description), ''),
    NULLIF(btrim(COALESCE(s.avatar_url,
                          s.raw_payload->'authorMeta'->>'originalAvatarUrl')), ''),
    NULLIF(btrim(s.raw_payload->'authorMeta'->>'bioLink'), ''),   -- bioLink -> website
    NULL::varchar,                                                -- open_id: hanya dari API resmi
    (sa.oauth_token IS NOT NULL),                              -- BUSINESS RULE: connection status
    s.follower_count::bigint,
    s.following_count::bigint,
    s.video_count,                                                -- video_count -> media_count
    s.likes_count,
    NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,       -- insight fields: TikTok tidak punya
    NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
    NULL::bigint, NULL::bigint, NULL::bigint,
    false,                                                        -- has_insights
    'apify', 'l0_raw.tt_profile_apify', s.id,
    COALESCE(s.scraped_at, s.fetched_at, now()),
    now(), now()
  FROM (
    SELECT DISTINCT ON (r.social_account_id,
                        COALESCE(r.scraped_at, r.fetched_at, now())::date) r.*
    FROM l0_raw.tt_profile_apify r
    WHERE r.social_account_id IS NOT NULL
      AND r.username IS NOT NULL
      AND btrim(r.username) <> ''
    ORDER BY r.social_account_id,
             COALESCE(r.scraped_at, r.fetched_at, now())::date,
             r.scraped_at DESC NULLS LAST, r.fetched_at DESC NULLS LAST, r.id
  ) s
  JOIN public.social_account sa ON sa.id = s.social_account_id
  JOIN public.platforms      p  ON p.key = 'tiktok'
  ON CONFLICT (social_account_id, date) DO UPDATE SET
    platform_id     = EXCLUDED.platform_id,
    username        = COALESCE(EXCLUDED.username,        unified_profile.username),
    display_name    = COALESCE(EXCLUDED.display_name,    unified_profile.display_name),
    bio             = COALESCE(EXCLUDED.bio,             unified_profile.bio),
    avatar_url      = COALESCE(EXCLUDED.avatar_url,      unified_profile.avatar_url),
    website         = COALESCE(EXCLUDED.website,         unified_profile.website),
    open_id         = COALESCE(EXCLUDED.open_id,         unified_profile.open_id),
    is_verified     = EXCLUDED.is_verified,   -- connection status: selalu definit
    followers_count = COALESCE(EXCLUDED.followers_count, unified_profile.followers_count),
    following_count = COALESCE(EXCLUDED.following_count, unified_profile.following_count),
    media_count     = COALESCE(EXCLUDED.media_count,     unified_profile.media_count),
    likes_count     = COALESCE(EXCLUDED.likes_count,     unified_profile.likes_count),
    has_insights    = COALESCE(EXCLUDED.has_insights,    unified_profile.has_insights),
    source          = EXCLUDED.source,
    source_table    = EXCLUDED.source_table,
    source_id       = EXCLUDED.source_id,
    processed_at    = EXCLUDED.processed_at,
    updated_at      = now()
  WHERE unified_profile.processed_at IS NULL
     OR unified_profile.processed_at <= EXCLUDED.processed_at;

  GET DIAGNOSTICS v_tt = ROW_COUNT;

  -- ==================================================================
  -- 3) INSTAGRAM - OFFICIAL  (0 baris hari ini; disiapkan untuk nanti)
  --    Official membawa insight metrics yang tidak ada di Apify.
  -- ==================================================================
  INSERT INTO l1_silver.unified_profile (
    social_account_id, platform_id, date, username, display_name, bio, avatar_url,
    website, open_id, is_verified, followers_count, following_count, media_count,
    likes_count, reach, profile_views, accounts_engaged, profile_links_taps,
    total_interactions, likes, comments, shares, saves, replies, reposts,
    has_insights, source, source_table, source_id, processed_at, created_at, updated_at)
  SELECT
    s.social_account_id,
    p.id,
    COALESCE(s.fetched_at, now())::date,
    ltrim(lower(btrim(split_part(split_part(s.username, '?', 1), '/', 1))), '@'),
    NULLIF(btrim(s.name), ''),
    NULLIF(btrim(s.biography), ''),
    NULL::text,                       -- ig_profile_official tidak punya avatar_url
    NULLIF(btrim(s.website), ''),
    NULL::varchar,
    (sa.oauth_token IS NOT NULL),     -- BUSINESS RULE: connection status
    s.followers_count::bigint,
    s.follows_count::bigint,
    s.media_count,
    NULL::bigint,
    s.reach::bigint, s.views::bigint, s.accounts_engaged::bigint,
    s.profile_links_taps::bigint, s.total_interactions::bigint,
    s.likes::bigint, s.comments::bigint, s.shares::bigint,
    s.saves::bigint, s.replies::bigint, s.reposts::bigint,
    true,                             -- has_insights
    'official', 'l0_raw.ig_profile_official', s.id,
    COALESCE(s.fetched_at, now()),
    now(), now()
  FROM (
    SELECT DISTINCT ON (r.social_account_id, COALESCE(r.fetched_at, now())::date) r.*
    FROM l0_raw.ig_profile_official r
    WHERE r.social_account_id IS NOT NULL
    ORDER BY r.social_account_id, COALESCE(r.fetched_at, now())::date,
             r.fetched_at DESC NULLS LAST, r.id
  ) s
  JOIN public.social_account sa ON sa.id = s.social_account_id
  JOIN public.platforms      p  ON p.key = 'instagram'
  ON CONFLICT (social_account_id, date) DO UPDATE SET
    platform_id        = EXCLUDED.platform_id,
    username           = COALESCE(EXCLUDED.username,           unified_profile.username),
    display_name       = COALESCE(EXCLUDED.display_name,       unified_profile.display_name),
    bio                = COALESCE(EXCLUDED.bio,                unified_profile.bio),
    website            = COALESCE(EXCLUDED.website,            unified_profile.website),
    followers_count    = COALESCE(EXCLUDED.followers_count,    unified_profile.followers_count),
    following_count    = COALESCE(EXCLUDED.following_count,    unified_profile.following_count),
    media_count        = COALESCE(EXCLUDED.media_count,        unified_profile.media_count),
    reach              = COALESCE(EXCLUDED.reach,              unified_profile.reach),
    profile_views      = COALESCE(EXCLUDED.profile_views,      unified_profile.profile_views),
    accounts_engaged   = COALESCE(EXCLUDED.accounts_engaged,   unified_profile.accounts_engaged),
    profile_links_taps = COALESCE(EXCLUDED.profile_links_taps, unified_profile.profile_links_taps),
    total_interactions = COALESCE(EXCLUDED.total_interactions, unified_profile.total_interactions),
    likes              = COALESCE(EXCLUDED.likes,              unified_profile.likes),
    comments           = COALESCE(EXCLUDED.comments,           unified_profile.comments),
    shares             = COALESCE(EXCLUDED.shares,             unified_profile.shares),
    saves              = COALESCE(EXCLUDED.saves,              unified_profile.saves),
    replies            = COALESCE(EXCLUDED.replies,            unified_profile.replies),
    reposts            = COALESCE(EXCLUDED.reposts,            unified_profile.reposts),
    has_insights       = true,
    source             = EXCLUDED.source,
    source_table       = EXCLUDED.source_table,
    source_id          = EXCLUDED.source_id,
    processed_at       = EXCLUDED.processed_at,
    updated_at         = now()
  WHERE unified_profile.processed_at IS NULL
     OR unified_profile.processed_at <= EXCLUDED.processed_at;

  GET DIAGNOSTICS v_ig_off = ROW_COUNT;

  -- ==================================================================
  -- 4) TIKTOK - OFFICIAL  (0 baris hari ini; disiapkan untuk nanti)
  --    Satu-satunya sumber open_id yang sah.
  -- ==================================================================
  INSERT INTO l1_silver.unified_profile (
    social_account_id, platform_id, date, username, display_name, bio, avatar_url,
    website, open_id, is_verified, followers_count, following_count, media_count,
    likes_count, has_insights, source, source_table, source_id, processed_at,
    created_at, updated_at)
  SELECT
    s.social_account_id,
    p.id,
    COALESCE(s.fetched_at, now())::date,
    sa.username,                      -- tt_profile_official tidak punya kolom username
    NULLIF(btrim(s.display_name), ''),
    NULLIF(btrim(s.bio_description), ''),
    NULLIF(btrim(s.avatar_url), ''),
    NULL::text,
    NULLIF(btrim(s.open_id), ''),
    (sa.oauth_token IS NOT NULL),     -- BUSINESS RULE: connection status
    s.follower_count::bigint,
    s.following_count::bigint,
    s.video_count,
    s.likes_count,
    false,
    'official', 'l0_raw.tt_profile_official', s.id,
    COALESCE(s.fetched_at, now()),
    now(), now()
  FROM (
    SELECT DISTINCT ON (r.social_account_id, COALESCE(r.fetched_at, now())::date) r.*
    FROM l0_raw.tt_profile_official r
    WHERE r.social_account_id IS NOT NULL
    ORDER BY r.social_account_id, COALESCE(r.fetched_at, now())::date,
             r.fetched_at DESC NULLS LAST, r.id
  ) s
  JOIN public.social_account sa ON sa.id = s.social_account_id
  JOIN public.platforms      p  ON p.key = 'tiktok'
  ON CONFLICT (social_account_id, date) DO UPDATE SET
    platform_id     = EXCLUDED.platform_id,
    username        = COALESCE(EXCLUDED.username,        unified_profile.username),
    display_name    = COALESCE(EXCLUDED.display_name,    unified_profile.display_name),
    bio             = COALESCE(EXCLUDED.bio,             unified_profile.bio),
    avatar_url      = COALESCE(EXCLUDED.avatar_url,      unified_profile.avatar_url),
    open_id         = COALESCE(EXCLUDED.open_id,         unified_profile.open_id),
    is_verified     = EXCLUDED.is_verified,   -- connection status: selalu definit
    followers_count = COALESCE(EXCLUDED.followers_count, unified_profile.followers_count),
    following_count = COALESCE(EXCLUDED.following_count, unified_profile.following_count),
    media_count     = COALESCE(EXCLUDED.media_count,     unified_profile.media_count),
    likes_count     = COALESCE(EXCLUDED.likes_count,     unified_profile.likes_count),
    source          = EXCLUDED.source,
    source_table    = EXCLUDED.source_table,
    source_id       = EXCLUDED.source_id,
    processed_at    = EXCLUDED.processed_at,
    updated_at      = now()
  WHERE unified_profile.processed_at IS NULL
     OR unified_profile.processed_at <= EXCLUDED.processed_at;

  GET DIAGNOSTICS v_tt_off = ROW_COUNT;

  UPDATE l0_harmonization.sync_log
  SET status        = 'success',
      rows_read     = (SELECT count(*) FROM l0_raw.ig_profile_apify)
                    + (SELECT count(*) FROM l0_raw.tt_profile_apify)
                    + (SELECT count(*) FROM l0_raw.ig_profile_official)
                    + (SELECT count(*) FROM l0_raw.tt_profile_official),
      rows_inserted = v_ig + v_tt + v_ig_off + v_tt_off,
      finished_at   = now(),
      duration_seconds = EXTRACT(EPOCH FROM (now() - started_at))
  WHERE id = v_log_id;

EXCEPTION WHEN OTHERS THEN
  UPDATE l0_harmonization.sync_log
  SET status='failed', error_message=SQLERRM, finished_at=now()
  WHERE id = v_log_id;
  RAISE;
END $procedure$;
