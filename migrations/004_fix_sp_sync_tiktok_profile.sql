-- =====================================================================
-- 004_fix_sp_sync_tiktok_profile.sql
-- Perbaikan l0_harmonization.sp_sync_tiktok_profile()
--
-- Flow yang dipertahankan:
--   l0_raw -> l0_harmonization -> l1_silver   (TIDAK bypass)
--
-- DUA BUG pada versi lama yang diperbaiki di sini:
--
--   BUG 1 - kolom sudah di-DROP
--     Versi lama menulis ke kolom `followers_growth`, yang sudah tidak ada
--     lagi di l0_harmonization.tiktok_profile (terverifikasi lewat
--     pg_attribute.attisdropped pada attnum 14).
--     Akibat: CALL selalu gagal dengan
--       ERROR: column "followers_growth" of relation "tiktok_profile"
--              does not exist
--     Itulah sebabnya tiktok_profile masih 0 baris.
--     -> kolom tersebut dibuang dari INSERT dan dari klausa DO UPDATE.
--
--   BUG 2 - duplikat dalam satu batch
--     l0_raw.tt_profile_apify punya 5 grup duplikat pada kunci
--     (social_account_id, date) = 7 baris berlebih. Versi lama membaca
--     tabel itu apa adanya, sehingga ON CONFLICT DO UPDATE akan gagal:
--       ERROR: ON CONFLICT DO UPDATE command cannot affect row a second time
--     -> ditambahkan pre-dedup DISTINCT ON, ambil scraped_at terbaru.
--        (Isi duplikatnya identik; min(follower_count)=max(follower_count)
--         di setiap grup, jadi tidak ada data yang hilang.)
--
-- Selain dua hal itu, struktur mengikuti persis pola
-- l0_harmonization.sp_sync_instagram_profile(): sync_log di awal,
-- blok apify lalu blok official, guard processed_at, penghitung baris,
-- dan EXCEPTION handler yang menandai 'failed' lalu RAISE.
--
-- TIDAK membuat tabel baru. TIDAK menulis apa pun ke l0_raw.
-- =====================================================================

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
    avatar_url, is_verified, follower_count, following_count, likes_count,
    video_count, source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id,
    COALESCE(s.scraped_at, s.fetched_at, now())::date,
    s.username,
    NULL,                       -- open_id hanya tersedia dari TikTok API resmi
    s.display_name,
    s.bio_description,
    s.avatar_url,
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
    avatar_url, is_verified, follower_count, following_count, likes_count,
    video_count, source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id,
    COALESCE(s.fetched_at, now())::date,
    NULL,                       -- tt_profile_official tidak punya kolom username
    s.open_id,
    s.display_name,
    s.bio_description,
    s.avatar_url,
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
