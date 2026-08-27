-- =====================================================================
-- 010_sync_procedures_with_profile_metrics.sql
--
-- Lanjutan migration 009. Setelah kolom baru ada di layer harmonization,
-- procedure sinkronisasi harus ikut mengisinya supaya baris BARU dari
-- ingest berikutnya tidak kembali NULL. Backfill di 009 hanya menutup
-- baris yang sudah ada saat ini.
--
-- Isi kedua procedure sama persis dengan 008, HANYA menambah 3 kolom di
-- masing-masing:
--   platform_user_id  IG raw_payload->>'id'        TT authorMeta.id
--   profile_url       IG raw_payload->>'url'       TT authorMeta.profileUrl
--   is_private        IG raw_payload->>'private'   TT authorMeta.privateAccount
--
-- Blok 'official' memakai NULL untuk ketiganya karena tabel
-- l0_raw.ig_profile_official / tt_profile_official tidak menyediakan
-- sumbernya. Klausa COALESCE di DO UPDATE menjaga nilai dari apify
-- supaya tidak tertimpa NULL.
--
-- TIDAK menulis ke l0_raw. TIDAK membuat tabel baru.
-- TIDAK menyentuh l1_silver.
-- =====================================================================

CREATE OR REPLACE PROCEDURE l0_harmonization.sp_sync_instagram_profile()
LANGUAGE plpgsql
AS $procedure$
DECLARE
  v_log_id  uuid;
  v_baca    bigint := 0;
  v_masuk   bigint := 0;
  v_sebelum bigint := 0;
BEGIN
  SELECT count(*) INTO v_sebelum FROM l0_harmonization.instagram_profile;

  INSERT INTO l0_harmonization.sync_log
    (target_table, source_table, source, sync_date, status, started_at)
  VALUES ('instagram_profile',
          'l0_raw.ig_profile_apify + l0_raw.ig_profile_official',
          'apify+official', current_date, 'running', now())
  RETURNING id INTO v_log_id;

  -- ------------------------------------------------------------------
  -- dari apify
  -- ------------------------------------------------------------------
  INSERT INTO l0_harmonization.instagram_profile (
    social_account_id, date, username, name, biography, website, avatar_url,
    platform_user_id, profile_url, is_private,
    followers_count, follows_count, media_count,
    reach, profile_views, accounts_engaged, profile_links_taps,
    total_interactions, likes, comments, shares, saves, replies, reposts,
    has_insights, source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id,
    COALESCE(s.scraped_at, s.fetched_at, now())::date,
    s.username,
    s.name,
    s.biography,
    s.website,
    NULLIF(btrim(COALESCE(s.raw_payload->>'profilePicUrlHD',
                          s.raw_payload->>'profilePicUrl')), ''),   -- avatar_url
    NULLIF(btrim(s.raw_payload->>'id'), ''),      -- platform_user_id
    NULLIF(btrim(s.raw_payload->>'url'), ''),     -- profile_url
    (s.raw_payload->>'private')::boolean,         -- is_private
    s.followers_count,
    s.follows_count,
    s.media_count,
    NULL, NULL, NULL, NULL,     -- reach, profile_views, accounts_engaged, profile_links_taps
    NULL, NULL, NULL, NULL,     -- total_interactions, likes, comments, shares
    NULL, NULL, NULL,           -- saves, replies, reposts   (insight: official saja)
    false,                      -- has_insights
    'apify', 'l0_raw.ig_profile_apify', s.id,
    COALESCE(s.scraped_at, s.fetched_at, now())
  FROM (
    SELECT DISTINCT ON (r.social_account_id,
                        COALESCE(r.scraped_at, r.fetched_at, now())::date) r.*
    FROM l0_raw.ig_profile_apify r
    WHERE r.social_account_id IS NOT NULL
    ORDER BY r.social_account_id,
             COALESCE(r.scraped_at, r.fetched_at, now())::date,
             r.scraped_at DESC NULLS LAST, r.fetched_at DESC NULLS LAST, r.id
  ) s
  ON CONFLICT (social_account_id, date) DO UPDATE SET
    username           = COALESCE(EXCLUDED.username,           instagram_profile.username),
    name               = COALESCE(EXCLUDED.name,               instagram_profile.name),
    biography          = COALESCE(EXCLUDED.biography,          instagram_profile.biography),
    website            = COALESCE(EXCLUDED.website,            instagram_profile.website),
    avatar_url         = COALESCE(EXCLUDED.avatar_url,         instagram_profile.avatar_url),
    platform_user_id   = COALESCE(EXCLUDED.platform_user_id,   instagram_profile.platform_user_id),
    profile_url        = COALESCE(EXCLUDED.profile_url,        instagram_profile.profile_url),
    is_private         = COALESCE(EXCLUDED.is_private,         instagram_profile.is_private),
    followers_count    = COALESCE(EXCLUDED.followers_count,    instagram_profile.followers_count),
    follows_count      = COALESCE(EXCLUDED.follows_count,      instagram_profile.follows_count),
    media_count        = COALESCE(EXCLUDED.media_count,        instagram_profile.media_count),
    reach              = COALESCE(EXCLUDED.reach,              instagram_profile.reach),
    profile_views      = COALESCE(EXCLUDED.profile_views,      instagram_profile.profile_views),
    accounts_engaged   = COALESCE(EXCLUDED.accounts_engaged,   instagram_profile.accounts_engaged),
    profile_links_taps = COALESCE(EXCLUDED.profile_links_taps, instagram_profile.profile_links_taps),
    total_interactions = COALESCE(EXCLUDED.total_interactions, instagram_profile.total_interactions),
    likes              = COALESCE(EXCLUDED.likes,              instagram_profile.likes),
    comments           = COALESCE(EXCLUDED.comments,           instagram_profile.comments),
    shares             = COALESCE(EXCLUDED.shares,             instagram_profile.shares),
    saves              = COALESCE(EXCLUDED.saves,              instagram_profile.saves),
    replies            = COALESCE(EXCLUDED.replies,            instagram_profile.replies),
    reposts            = COALESCE(EXCLUDED.reposts,            instagram_profile.reposts),
    has_insights       = COALESCE(EXCLUDED.has_insights,       instagram_profile.has_insights),
    source             = EXCLUDED.source,
    source_table       = EXCLUDED.source_table,
    source_id          = EXCLUDED.source_id,
    processed_at       = EXCLUDED.processed_at
  WHERE instagram_profile.processed_at < EXCLUDED.processed_at;

  -- ------------------------------------------------------------------
  -- dari official  (0 baris hari ini; sumber insight metrics)
  -- ------------------------------------------------------------------
  INSERT INTO l0_harmonization.instagram_profile (
    social_account_id, date, username, name, biography, website, avatar_url,
    platform_user_id, profile_url, is_private,
    followers_count, follows_count, media_count,
    reach, profile_views, accounts_engaged, profile_links_taps,
    total_interactions, likes, comments, shares, saves, replies, reposts,
    has_insights, source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id,
    COALESCE(s.fetched_at, now())::date,
    s.username,
    s.name,
    s.biography,
    s.website,
    NULL::text,                 -- avatar_url: ig_profile_official tidak punya sumbernya
    NULL::varchar,              -- platform_user_id: tidak tersedia di official
    NULL::text,                 -- profile_url: tidak tersedia di official
    NULL::boolean,              -- is_private: tidak tersedia di official
    s.followers_count,
    s.follows_count,
    s.media_count,
    s.reach,
    s.views,                    -- views -> profile_views
    s.accounts_engaged,
    s.profile_links_taps,
    s.total_interactions,
    s.likes, s.comments, s.shares, s.saves, s.replies, s.reposts,
    true,                       -- has_insights
    'official', 'l0_raw.ig_profile_official', s.id,
    COALESCE(s.fetched_at, now())
  FROM (
    SELECT DISTINCT ON (r.social_account_id, COALESCE(r.fetched_at, now())::date) r.*
    FROM l0_raw.ig_profile_official r
    WHERE r.social_account_id IS NOT NULL
    ORDER BY r.social_account_id, COALESCE(r.fetched_at, now())::date,
             r.fetched_at DESC NULLS LAST, r.id
  ) s
  ON CONFLICT (social_account_id, date) DO UPDATE SET
    username           = COALESCE(EXCLUDED.username,           instagram_profile.username),
    name               = COALESCE(EXCLUDED.name,               instagram_profile.name),
    biography          = COALESCE(EXCLUDED.biography,          instagram_profile.biography),
    website            = COALESCE(EXCLUDED.website,            instagram_profile.website),
    avatar_url         = COALESCE(EXCLUDED.avatar_url,         instagram_profile.avatar_url),
    platform_user_id   = COALESCE(EXCLUDED.platform_user_id,   instagram_profile.platform_user_id),
    profile_url        = COALESCE(EXCLUDED.profile_url,        instagram_profile.profile_url),
    is_private         = COALESCE(EXCLUDED.is_private,         instagram_profile.is_private),
    followers_count    = COALESCE(EXCLUDED.followers_count,    instagram_profile.followers_count),
    follows_count      = COALESCE(EXCLUDED.follows_count,      instagram_profile.follows_count),
    media_count        = COALESCE(EXCLUDED.media_count,        instagram_profile.media_count),
    reach              = COALESCE(EXCLUDED.reach,              instagram_profile.reach),
    profile_views      = COALESCE(EXCLUDED.profile_views,      instagram_profile.profile_views),
    accounts_engaged   = COALESCE(EXCLUDED.accounts_engaged,   instagram_profile.accounts_engaged),
    profile_links_taps = COALESCE(EXCLUDED.profile_links_taps, instagram_profile.profile_links_taps),
    total_interactions = COALESCE(EXCLUDED.total_interactions, instagram_profile.total_interactions),
    likes              = COALESCE(EXCLUDED.likes,              instagram_profile.likes),
    comments           = COALESCE(EXCLUDED.comments,           instagram_profile.comments),
    shares             = COALESCE(EXCLUDED.shares,             instagram_profile.shares),
    saves              = COALESCE(EXCLUDED.saves,              instagram_profile.saves),
    replies            = COALESCE(EXCLUDED.replies,            instagram_profile.replies),
    reposts            = COALESCE(EXCLUDED.reposts,            instagram_profile.reposts),
    has_insights       = COALESCE(EXCLUDED.has_insights,       instagram_profile.has_insights),
    source             = EXCLUDED.source,
    source_table       = EXCLUDED.source_table,
    source_id          = EXCLUDED.source_id,
    processed_at       = EXCLUDED.processed_at
  WHERE instagram_profile.processed_at < EXCLUDED.processed_at;

  SELECT (SELECT count(*) FROM l0_raw.ig_profile_apify)
       + (SELECT count(*) FROM l0_raw.ig_profile_official) INTO v_baca;
  SELECT count(*) INTO v_masuk FROM l0_harmonization.instagram_profile;

  UPDATE l0_harmonization.sync_log
  SET status='success', rows_read=v_baca, rows_inserted=v_masuk - v_sebelum,
      rows_updated=v_sebelum, finished_at=now(),
      duration_seconds=EXTRACT(EPOCH FROM (now()-started_at))
  WHERE id=v_log_id;

EXCEPTION WHEN OTHERS THEN
  UPDATE l0_harmonization.sync_log
  SET status='failed', error_message=SQLERRM, finished_at=now()
  WHERE id=v_log_id;
  RAISE;
END $procedure$;


CREATE OR REPLACE PROCEDURE l0_harmonization.sp_sync_tiktok_profile()
LANGUAGE plpgsql
AS $procedure$
DECLARE
  v_log_id  uuid;
  v_baca    bigint := 0;
  v_masuk   bigint := 0;
  v_sebelum bigint := 0;
BEGIN
  SELECT count(*) INTO v_sebelum FROM l0_harmonization.tiktok_profile;

  INSERT INTO l0_harmonization.sync_log
    (target_table, source_table, source, sync_date, status, started_at)
  VALUES ('tiktok_profile',
          'l0_raw.tt_profile_apify + l0_raw.tt_profile_official',
          'apify+official', current_date, 'running', now())
  RETURNING id INTO v_log_id;

  -- ------------------------------------------------------------------
  -- dari apify
  -- ------------------------------------------------------------------
  INSERT INTO l0_harmonization.tiktok_profile (
    social_account_id, date, username, open_id, display_name, bio_description,
    avatar_url, website, platform_user_id, profile_url, is_private,
    is_verified, follower_count, following_count, likes_count,
    video_count, source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id,
    COALESCE(s.scraped_at, s.fetched_at, now())::date,
    s.username,
    NULL,                       -- open_id hanya tersedia dari TikTok API resmi
    s.display_name,
    s.bio_description,
    s.avatar_url,
    CASE                        -- website <- authorMeta.bioLink, dinormalisasi
      WHEN btrim(COALESCE(s.raw_payload->'authorMeta'->>'bioLink', '')) = '' THEN NULL
      WHEN btrim(s.raw_payload->'authorMeta'->>'bioLink') ~* '^https?://'
        THEN btrim(s.raw_payload->'authorMeta'->>'bioLink')
      ELSE 'https://' || btrim(s.raw_payload->'authorMeta'->>'bioLink')
    END,
    NULLIF(btrim(s.raw_payload->'authorMeta'->>'id'), ''),          -- platform_user_id
    NULLIF(btrim(s.raw_payload->'authorMeta'->>'profileUrl'), ''),  -- profile_url
    (s.raw_payload->'authorMeta'->>'privateAccount')::boolean,      -- is_private
    s.is_verified,              -- badge platform, apa adanya dari L0
    s.follower_count,
    s.following_count,
    s.likes_count,
    s.video_count,
    'apify', 'l0_raw.tt_profile_apify', s.id,
    COALESCE(s.scraped_at, s.fetched_at, now())
  FROM (
    SELECT DISTINCT ON (r.social_account_id,
                        COALESCE(r.scraped_at, r.fetched_at, now())::date) r.*
    FROM l0_raw.tt_profile_apify r
    WHERE r.social_account_id IS NOT NULL
    ORDER BY r.social_account_id,
             COALESCE(r.scraped_at, r.fetched_at, now())::date,
             r.scraped_at DESC NULLS LAST, r.fetched_at DESC NULLS LAST, r.id
  ) s
  ON CONFLICT (social_account_id, date) DO UPDATE SET
    username        = COALESCE(EXCLUDED.username,        tiktok_profile.username),
    open_id         = COALESCE(EXCLUDED.open_id,         tiktok_profile.open_id),
    display_name    = COALESCE(EXCLUDED.display_name,    tiktok_profile.display_name),
    bio_description = COALESCE(EXCLUDED.bio_description, tiktok_profile.bio_description),
    avatar_url      = COALESCE(EXCLUDED.avatar_url,      tiktok_profile.avatar_url),
    website         = COALESCE(EXCLUDED.website,         tiktok_profile.website),
    platform_user_id= COALESCE(EXCLUDED.platform_user_id,tiktok_profile.platform_user_id),
    profile_url     = COALESCE(EXCLUDED.profile_url,     tiktok_profile.profile_url),
    is_private      = COALESCE(EXCLUDED.is_private,      tiktok_profile.is_private),
    is_verified     = COALESCE(EXCLUDED.is_verified,     tiktok_profile.is_verified),
    follower_count  = COALESCE(EXCLUDED.follower_count,  tiktok_profile.follower_count),
    following_count = COALESCE(EXCLUDED.following_count, tiktok_profile.following_count),
    likes_count     = COALESCE(EXCLUDED.likes_count,     tiktok_profile.likes_count),
    video_count     = COALESCE(EXCLUDED.video_count,     tiktok_profile.video_count),
    source          = EXCLUDED.source,
    source_table    = EXCLUDED.source_table,
    source_id       = EXCLUDED.source_id,
    processed_at    = EXCLUDED.processed_at
  WHERE tiktok_profile.processed_at < EXCLUDED.processed_at;

  -- ------------------------------------------------------------------
  -- dari official  (0 baris hari ini; satu-satunya sumber open_id)
  -- ------------------------------------------------------------------
  INSERT INTO l0_harmonization.tiktok_profile (
    social_account_id, date, username, open_id, display_name, bio_description,
    avatar_url, website, platform_user_id, profile_url, is_private,
    is_verified, follower_count, following_count, likes_count,
    video_count, source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id,
    COALESCE(s.fetched_at, now())::date,
    NULL,                       -- tt_profile_official tidak punya kolom username
    s.open_id,
    s.display_name,
    s.bio_description,
    s.avatar_url,
    NULL::text,                 -- website: tt_profile_official tidak punya sumbernya
    NULL::varchar,              -- platform_user_id: tidak tersedia di official
    NULL::text,                 -- profile_url: tidak tersedia di official
    NULL::boolean,              -- is_private: tidak tersedia di official
    s.is_verified,
    s.follower_count,
    s.following_count,
    s.likes_count,
    s.video_count,
    'official', 'l0_raw.tt_profile_official', s.id,
    COALESCE(s.fetched_at, now())
  FROM (
    SELECT DISTINCT ON (r.social_account_id, COALESCE(r.fetched_at, now())::date) r.*
    FROM l0_raw.tt_profile_official r
    WHERE r.social_account_id IS NOT NULL
    ORDER BY r.social_account_id, COALESCE(r.fetched_at, now())::date,
             r.fetched_at DESC NULLS LAST, r.id
  ) s
  ON CONFLICT (social_account_id, date) DO UPDATE SET
    username        = COALESCE(EXCLUDED.username,        tiktok_profile.username),
    open_id         = COALESCE(EXCLUDED.open_id,         tiktok_profile.open_id),
    display_name    = COALESCE(EXCLUDED.display_name,    tiktok_profile.display_name),
    bio_description = COALESCE(EXCLUDED.bio_description, tiktok_profile.bio_description),
    avatar_url      = COALESCE(EXCLUDED.avatar_url,      tiktok_profile.avatar_url),
    website         = COALESCE(EXCLUDED.website,         tiktok_profile.website),
    platform_user_id= COALESCE(EXCLUDED.platform_user_id,tiktok_profile.platform_user_id),
    profile_url     = COALESCE(EXCLUDED.profile_url,     tiktok_profile.profile_url),
    is_private      = COALESCE(EXCLUDED.is_private,      tiktok_profile.is_private),
    is_verified     = COALESCE(EXCLUDED.is_verified,     tiktok_profile.is_verified),
    follower_count  = COALESCE(EXCLUDED.follower_count,  tiktok_profile.follower_count),
    following_count = COALESCE(EXCLUDED.following_count, tiktok_profile.following_count),
    likes_count     = COALESCE(EXCLUDED.likes_count,     tiktok_profile.likes_count),
    video_count     = COALESCE(EXCLUDED.video_count,     tiktok_profile.video_count),
    source          = EXCLUDED.source,
    source_table    = EXCLUDED.source_table,
    source_id       = EXCLUDED.source_id,
    processed_at    = EXCLUDED.processed_at
  WHERE tiktok_profile.processed_at < EXCLUDED.processed_at;

  SELECT (SELECT count(*) FROM l0_raw.tt_profile_apify)
       + (SELECT count(*) FROM l0_raw.tt_profile_official) INTO v_baca;
  SELECT count(*) INTO v_masuk FROM l0_harmonization.tiktok_profile;

  UPDATE l0_harmonization.sync_log
  SET status='success', rows_read=v_baca, rows_inserted=v_masuk - v_sebelum,
      rows_updated=v_sebelum, finished_at=now(),
      duration_seconds=EXTRACT(EPOCH FROM (now()-started_at))
  WHERE id=v_log_id;

EXCEPTION WHEN OTHERS THEN
  UPDATE l0_harmonization.sync_log
  SET status='failed', error_message=SQLERRM, finished_at=now()
  WHERE id=v_log_id;
  RAISE;
END $procedure$;
