-- =====================================================================
-- 005_fix_sp_sync_instagram_profile.sql
-- Perbaikan l0_harmonization.sp_sync_instagram_profile()
--
-- Flow yang dipertahankan:
--   l0_raw -> l0_harmonization -> l1_silver   (TIDAK bypass)
--
-- Bug-nya SATU KELAS dengan sp_sync_tiktok_profile (lihat 004):
--
--   BUG 1 - kolom sudah di-DROP
--     Versi lama menulis ke 4 kolom yang sudah tidak ada lagi di
--     l0_harmonization.instagram_profile:
--         follows, unfollows, net_follows, followers_growth
--     (terverifikasi lewat pg_attribute.attisdropped pada attnum 22-25).
--     Akibat: CALL selalu gagal dengan
--       ERROR: column "follows" of relation "instagram_profile"
--              does not exist
--     -> keempatnya dibuang dari INSERT dan dari klausa DO UPDATE.
--
--   BUG 2 - tidak ada pre-dedup
--     Sama seperti TikTok: kalau satu akun punya lebih dari satu snapshot
--     pada tanggal yang sama, ON CONFLICT DO UPDATE akan gagal dengan
--       ERROR: ON CONFLICT DO UPDATE command cannot affect row a second time
--     Hari ini l0_raw.ig_profile_apify kebetulan 0 duplikat, tapi
--     DISTINCT ON tetap dipasang supaya konsisten dengan versi TikTok dan
--     tahan terhadap re-ingest berikutnya.
--
-- KENAPA 3 BARIS TERTINGGAL (928 dari 931):
--   Bukan karena filter apa pun. Harmonization terakhir jalan
--   2026-08-14 09:50:14, sementara 3 baris "Restricted profile"
--   (bekasi.terkini, infodepok24, infojkt24) baru masuk l0_raw pada
--   2026-08-18 04:49:33 lewat re-ingest. Saat itu procedure sudah rusak
--   karena BUG 1, jadi tidak pernah bisa dijalankan ulang.
--   Setelah perbaikan ini ketiganya ikut masuk -> 931.
--
-- CATATAN guard processed_at:
--   Klausa WHERE instagram_profile.processed_at < EXCLUDED.processed_at
--   dipertahankan apa adanya dari pola lama. Efeknya: 928 baris yang
--   sudah ada TIDAK tersentuh (processed_at mereka 09:50:14, lebih baru
--   daripada scraped_at 08:16:09), dan hanya 3 baris baru yang di-INSERT.
--
-- TIDAK membuat tabel baru. TIDAK menulis apa pun ke l0_raw.
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
    social_account_id, date, username, name, biography, website,
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
    social_account_id, date, username, name, biography, website,
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
