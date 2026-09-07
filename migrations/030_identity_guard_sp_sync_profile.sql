-- =====================================================================
-- 030_identity_guard_sp_sync_profile.sql
-- Identity guard di l0_harmonization: hasil scrape hanya naik kalau
-- identitas akunnya cocok dengan anchor di public.kol_directory.
--
-- MASALAH YANG DIPERBAIKI
--   Pencocokan scrape selama ini murni lewat string username
--   (apify_tiktok.py mengirim {"profiles": [username]}). Kalau KOL ganti
--   username -- atau username lamanya dipakai akun lain -- actor
--   mengembalikan akun yang BERBEDA, dan hasilnya tersimpan sebagai fakta.
--
--   Audit 2026-09-07 menemukan 7 kasus terbukti, antara lain:
--     shanijkt48         directory 2.400.000 -> scrape 3.098
--                        (nickName "user05173090348" = default TikTok,
--                         bio "No bio yet", 22 video)
--     tasyadinikafajar3  directory   340.000 -> scrape 1.215
--                        (bio akunnya sendiri berbunyi "Second @Tasyadinikafajar")
--
--   Tanpa gerbang ini, snapshot semacam itu ikut menghasilkan Growth palsu
--   dan merusak Tier.
--
-- ATURAN (tanpa ambang follower sama sekali)
--   anchor NULL       -> LOLOS. Belum ada yang bisa dibantah (unanchored).
--   anchor = scraped  -> LOLOS.
--   anchor <> scraped -> baris TIDAK naik ke harmonization.
--
--   Identitas ditentukan oleh platform_user_id, BUKAN oleh besar-kecilnya
--   perubahan followers. Tidak ada threshold -90% atau sejenisnya.
--
-- L0 TIDAK DISENTUH
--   Gerbang ada satu lapis di ATAS L0. Baris yang ditolak tetap tersimpan
--   utuh di l0_raw.*_profile_apify sebagai jejak audit. Tidak ada DELETE,
--   tidak ada UPDATE ke L0.
--
-- YANG SENGAJA TIDAK DIGUBAH
--   Cabang sumber `official` (l0_raw.tt_profile_official /
--   ig_profile_official) TIDAK diberi gerbang, karena:
--     * keduanya 0 baris hari ini, jadi nol dampak; dan
--     * identitasnya ada di namespace lain -- tt_profile_official hanya
--       punya `open_id` (identitas OAuth TikTok, bukan authorMeta.id), dan
--       ig_profile_official tidak punya kolom identitas platform sama sekali.
--   Memasang gerbang dengan field yang salah lebih berbahaya daripada
--   tidak memasangnya. Perlu audit tersendiri sebelum cabang itu dipakai.
--
-- TIDAK ADA PERUBAHAN SCHEMA
--   Hanya CREATE OR REPLACE dua prosedur. Tidak ada tabel/kolom baru.
--   Mengikuti pola migration 004/005/024/027.
--
-- URUTAN
--   Jalankan SETELAH 032 (backfill anchor). Gerbang tanpa anchor tidak
--   melindungi apa pun -- semua baris jatuh ke cabang "anchor NULL".
--
-- DAMPAK TERUKUR (query read-only, 2026-09-07)
--   Pada data yang ada sekarang            : 0 baris ditolak
--   Simulasi setelah 101 anchor terpasang  : 118 baris anchored, 0 ditolak
--   -> memasang gerbang tidak mengubah data yang sudah ada.
--
-- ROLLBACK
--   Jalankan ulang definisi lama kedua prosedur. Definisi lama bisa diambil
--   dari commit sebelum migration ini, atau dari pg_get_functiondef() pada
--   database yang belum dimigrasi. Tidak ada data yang hilang.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 1. TikTok  -- identitas dari raw_payload->'authorMeta'->>'id'
-- ---------------------------------------------------------------------
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
    LEFT JOIN public.kol_social_account ksa ON ksa.social_account_id = r.social_account_id
    LEFT JOIN public.kol_directory      kd  ON kd.id = ksa.kol_id
    WHERE r.social_account_id IS NOT NULL
      -- IDENTITY GUARD (migration 030)
      --   anchor NULL      -> lolos (unanchored, belum ada yang bisa dibantah)
      --   anchor = scraped -> lolos
      --   anchor <> scraped-> baris TIDAK naik. L0 tetap utuh (append-only).
      AND (kd.platform_user_id IS NULL
           OR kd.platform_user_id = r.raw_payload->'authorMeta'->>'id')
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

-- ---------------------------------------------------------------------
-- 2. Instagram -- identitas dari raw_payload->>'id'
-- ---------------------------------------------------------------------
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
    LEFT JOIN public.kol_social_account ksa ON ksa.social_account_id = r.social_account_id
    LEFT JOIN public.kol_directory      kd  ON kd.id = ksa.kol_id
    WHERE r.social_account_id IS NOT NULL
      -- IDENTITY GUARD (migration 030)
      --   anchor NULL      -> lolos (unanchored, belum ada yang bisa dibantah)
      --   anchor = scraped -> lolos
      --   anchor <> scraped-> baris TIDAK naik. L0 tetap utuh (append-only).
      AND (kd.platform_user_id IS NULL
           OR kd.platform_user_id = NULLIF(btrim(r.raw_payload->>'id'), ''))
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
    -- T4: sekali TRUE tetap TRUE (lihat catatan di sp_sync_instagram_post).
    has_insights       = COALESCE(EXCLUDED.has_insights, false)
                      OR COALESCE(instagram_profile.has_insights, false),
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
    -- T4: sekali TRUE tetap TRUE (lihat catatan di sp_sync_instagram_post).
    has_insights       = COALESCE(EXCLUDED.has_insights, false)
                      OR COALESCE(instagram_profile.has_insights, false),
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

-- ---------------------------------------------------------------------
-- Verifikasi: kedua prosedur harus memuat gerbangnya.
-- ---------------------------------------------------------------------
DO $verifikasi$
DECLARE
  n_guard int;
BEGIN
  SELECT count(*) INTO n_guard
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'l0_harmonization'
    AND p.proname IN ('sp_sync_tiktok_profile', 'sp_sync_instagram_profile')
    AND position('IDENTITY GUARD (migration 030)' IN pg_get_functiondef(p.oid)) > 0;

  IF n_guard <> 2 THEN
    RAISE EXCEPTION 'Identity guard hanya terpasang di % dari 2 prosedur', n_guard;
  END IF;

  RAISE NOTICE 'OK: identity guard terpasang di 2 prosedur.';
END $verifikasi$;

COMMIT;
