-- 019_fix_dedup_dan_has_insights.sql
--
-- Memperbaiki tiga blocker yang ditemukan audit Fase 1b. Seluruhnya perubahan
-- LOGIKA di dalam 4 routine -- tidak ada tabel, kolom, index, constraint, atau
-- baris data yang disentuh. Backward-compatible: nama, argumen, dan tipe
-- kembalian keempatnya tidak berubah, jadi semua pemanggil yang ada tetap jalan.
--
-- ============================================================================
-- T2 -- l1_silver.sp_build_unified_post() akan gagal pada snapshot hari kedua
-- ============================================================================
--
-- Sumbernya bergrain (social_account_id, media_id/video_id, DATE); targetnya
-- bergrain (social_account_id, content_id) TANPA date. `INSERT ... SELECT`-nya
-- tidak men-dedup, jadi begitu satu post punya dua tanggal snapshot, satu
-- statement mencoba menyentuh baris konflik yang sama dua kali:
--
--     SQLSTATE 21000: ON CONFLICT DO UPDATE command cannot affect row a
--                     second time
--
-- Sekarang belum meledak hanya karena kebetulan: instagram_post dan tiktok_post
-- masing-masing baru punya SATU tanggal (2026-08-20), 0 post dengan >1 tanggal.
-- Scrape post yang kedua kalinya akan langsung memicunya.
--
-- Perbaikan: bungkus UNION sumber dengan
--     SELECT DISTINCT ON (social_account_id, content_id) *
--     ORDER BY social_account_id, content_id, date DESC, processed_at DESC
-- sehingga yang masuk ke L1 adalah SNAPSHOT TERBARU tiap post.
--
-- Kenapa "terbaru", bukan agregasi: unified_post memang tabel keadaan-terkini
-- per konten, bukan deret waktu -- grain-nya sendiri yang menyatakan itu.
-- Riwayat per tanggal tetap utuh di l0_harmonization dan tidak disentuh.
--
-- ============================================================================
-- T3 -- procedure sync post tidak men-dedup sumber L0-nya
-- ============================================================================
--
-- Risiko yang sama, satu tingkat lebih hulu: kalau l0_raw punya dua baris untuk
-- (akun, media, tanggal) yang sama, `sp_sync_*_post` kena SQLSTATE 21000 juga.
--
-- Ini bukan hipotesis. `l0_raw.tt_profile_apify` SAAT INI punya 5 kombinasi
-- (social_account_id, tanggal) duplikat -- dan sp_sync_tiktok_profile selamat
-- justru karena sudah punya DISTINCT ON. Kedua procedure post tidak punya.
--
-- Perbaikan: pola DISTINCT ON yang sama persis dengan yang sudah dipakai kedua
-- procedure profile, diterapkan ke 4 blok INSERT (apify + official, IG + TT).
-- Pemenangnya baris dengan scraped_at/fetched_at terbaru; `r.id` jadi pemecah
-- seri supaya hasilnya deterministik antar-run.
--
-- ============================================================================
-- T4 -- has_insights bisa dimatikan oleh Apify
-- ============================================================================
--
-- Blok apify menulis literal `false`, BUKAN NULL. Karena merge-nya
-- `COALESCE(EXCLUDED.has_insights, existing)`, maka COALESCE(false, true)
-- = false: apify yang berjalan setelah official di tanggal yang sama akan
-- mematikan bendera Insights, padahal kolom Insights-nya sendiri (reach,
-- profile_views, total_interactions, ...) tetap selamat karena apify
-- menulis NULL untuk semuanya.
--
-- Hasilnya baris yang PUNYA data Insights mengaku tidak punya.
--
-- Perbaikan: jadikan benderanya monoton -- sekali TRUE tetap TRUE.
--     has_insights = COALESCE(EXCLUDED.has_insights, false)
--                 OR COALESCE(existing.has_insights, false)
-- Ini mencerminkan kenyataan: kalau ada sumber yang pernah memberi Insights
-- dan angkanya masih tersimpan, benderanya harus tetap menyala.
--
-- Laten sekarang (ig_profile_official dan ig_media_snapshots_official 0 baris),
-- tapi akan langsung aktif begitu Official API dinyalakan.
--
-- ============================================================================
-- CAKUPAN -- 4 routine, dipilih bukan sembarangan
-- ============================================================================
--
--   l0_harmonization.sp_sync_instagram_post      T3 (2 blok) + T4 (2 tempat)
--   l0_harmonization.sp_sync_tiktok_post         T3 (2 blok)
--   l0_harmonization.sp_sync_instagram_profile   T4 (2 tempat)
--   l1_silver.sp_build_unified_post              T2
--
-- Keempatnya adalah jalur kritis Fase 1b DAN satu-satunya yang sumbernya berisi
-- data. `sp_sync_{ig,tt}_profile` sudah punya DISTINCT ON sejak awal.
--
-- BELUM diperbaiki, dan itu disengaja (lihat catatan di akhir laporan audit):
--   * 9 procedure sync lain juga tidak punya DISTINCT ON, tapi sumber L0-nya
--     semuanya 0 baris sehingga cacatnya tidak bisa aktif.
--   * `sp_sync_roster_rate_card` membaca 7.718 baris nyata dan juga tidak
--     punya DISTINCT ON -- ini yang paling layak jadi migration berikutnya.
--   * Pola has_insights yang sama ada di sp_sync_instagram_story dan
--     sp_sync_instagram_comment; keduanya bersumber dari tabel kosong.
--
-- Memperbaiki 12 procedure sekaligus berarti menulis ulang ~70 KB PL/pgSQL
-- yang tidak bisa diuji karena sumbernya kosong. Risiko salah ketiknya lebih
-- besar daripada cacat laten yang diperbaiki.
--
-- ============================================================================
-- KEAMANAN
-- ============================================================================
--
--   * CREATE OR REPLACE saja -- tidak ada DROP, jadi hak akses, kepemilikan,
--     dan dependency yang ada tidak hilang.
--   * Tanda tangan keempat routine tidak berubah (nama, 0 argumen, tipe
--     kembalian sama), jadi tidak ada pemanggil yang perlu ikut diubah.
--   * Tidak ada tabel/kolom/index/constraint/baris yang disentuh. Migrasi ini
--     tidak mengubah satu baris data pun; efeknya baru terasa saat procedure
--     berikutnya dijalankan.
--   * Body di luar tiga tambalan di atas identik byte-per-byte dengan definisi
--     yang sedang berjalan -- file ini dibangkitkan dari pg_get_functiondef
--     lalu ditambal, bukan diketik ulang.
--
-- Jalankan:
--   python apply_migration.py migrations/019_fix_dedup_dan_has_insights.sql --dry-run --yes
--   python apply_migration.py migrations/019_fix_dedup_dan_has_insights.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga. Pastikan kondisi awal memang yang diaudit.
-- ---------------------------------------------------------------------------
DO $penjaga$
DECLARE
    n_distinct int;
    n_coalesce int;
BEGIN
    -- Kedua procedure post BELUM punya DISTINCT ON (kalau sudah, migrasi
    -- ini sudah pernah jalan).
    SELECT count(*) INTO n_distinct
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization'
      AND p.proname IN ('sp_sync_instagram_post', 'sp_sync_tiktok_post')
      AND p.prosrc ILIKE '%DISTINCT ON%';

    IF n_distinct > 0 THEN
        RAISE EXCEPTION 'DISTINCT ON sudah ada di % procedure post -- '
                        'migrasi 019 sudah pernah dijalankan.', n_distinct;
    END IF;

    -- sp_build_unified_post belum di-dedup.
    SELECT count(*) INTO n_distinct
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_post'
      AND p.prosrc ILIKE '%DISTINCT ON%';

    IF n_distinct > 0 THEN
        RAISE EXCEPTION 'sp_build_unified_post sudah punya DISTINCT ON -- '
                        'migrasi 019 sudah pernah dijalankan.';
    END IF;

    -- Pola has_insights lama masih terpasang.
    SELECT count(*) INTO n_coalesce
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization'
      AND p.proname IN ('sp_sync_instagram_post', 'sp_sync_instagram_profile')
      AND p.prosrc ILIKE '%COALESCE(EXCLUDED.has_insights,%'
      AND p.prosrc NOT ILIKE '%COALESCE(EXCLUDED.has_insights, false)%';

    IF n_coalesce <> 2 THEN
        RAISE EXCEPTION 'Pola has_insights lama ditemukan di % procedure, '
                        'diharapkan 2 -- periksa dulu.', n_coalesce;
    END IF;

    RAISE NOTICE 'Penjaga lolos: 4 routine dalam kondisi awal yang diaudit.';
END $penjaga$;

-- -------------------------------------------------------------------------
-- Langkah 1a -- T3 + T4 : l0_harmonization.sp_sync_instagram_post
-- -------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE l0_harmonization.sp_sync_instagram_post()
 LANGUAGE plpgsql
AS $procedure$
DECLARE
  v_log_id uuid; v_baca bigint := 0; v_masuk bigint := 0; v_sebelum bigint := 0;
BEGIN
  SELECT count(*) INTO v_sebelum FROM l0_harmonization.instagram_post;

  INSERT INTO l0_harmonization.sync_log
    (target_table, source_table, source, sync_date, status, started_at)
  VALUES ('instagram_post','l0_raw.ig_media_snapshots_apify + l0_raw.ig_media_snapshots_official','apify+official', current_date, 'running', now())
  RETURNING id INTO v_log_id;

  -- dari apify
  INSERT INTO l0_harmonization.instagram_post (
    social_account_id, media_id, date, posted_at, media_type, caption, permalink,
    cover_image, video_duration, carousel_media_count, is_sponsored, likes, comments,
    views, shares, reach, saved, total_interactions, reposts, follows, profile_visits,
    reel_avg_watch_time, reel_video_view_total_time, engagement_rate, has_insights,
    shortcode, owner_username, platform_user_id, hashtags, mentions,
    source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id, s.media_id, COALESCE(s.scraped_at, s.fetched_at, now())::date,
    s.posted_at, s.media_type, s.caption, s.permalink, s.cover_image, s.video_duration,
    s.carousel_media_count, s.is_sponsored, s.likes, s.comments, s.views,
    NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
    s.engagement_rate, false,
    x.shortcode, x.owner_username, x.platform_user_id, x.hashtags, x.mentions,
    'apify', 'l0_raw.ig_media_snapshots_apify', s.id,
    COALESCE(s.scraped_at, s.fetched_at, now())
  FROM (
    -- T3: satu baris per (akun, media, tanggal). Tanpa ini, dua hasil scrape
    -- di hari yang sama membuat satu statement menyentuh baris konflik yang
    -- sama dua kali -> SQLSTATE 21000.
    SELECT DISTINCT ON (r.social_account_id, r.media_id,
                        COALESCE(r.scraped_at, r.fetched_at, now())::date) r.*
    FROM l0_raw.ig_media_snapshots_apify r
    WHERE r.social_account_id IS NOT NULL AND r.media_id IS NOT NULL
    ORDER BY r.social_account_id, r.media_id,
             COALESCE(r.scraped_at, r.fetched_at, now())::date,
             r.scraped_at DESC NULLS LAST, r.fetched_at DESC NULLS LAST, r.id
  ) s
  CROSS JOIN LATERAL (
    SELECT
      NULLIF(s.raw_payload->>'shortCode', '')     AS shortcode,
      NULLIF(s.raw_payload->>'ownerUsername', '') AS owner_username,
      NULLIF(s.raw_payload->>'ownerId', '')       AS platform_user_id,
      CASE WHEN jsonb_typeof(s.raw_payload->'hashtags') = 'array' THEN
        (SELECT array_agg(a.t ORDER BY a.ord)
           FROM jsonb_array_elements_text(s.raw_payload->'hashtags')
                WITH ORDINALITY AS a(t, ord)
          WHERE COALESCE(a.t, '') <> '')
      END AS hashtags,
      CASE WHEN jsonb_typeof(s.raw_payload->'mentions') = 'array' THEN
        (SELECT array_agg(ltrim(a.t, '@') ORDER BY a.ord)
           FROM jsonb_array_elements_text(s.raw_payload->'mentions')
                WITH ORDINALITY AS a(t, ord)
          WHERE COALESCE(ltrim(a.t, '@'), '') <> '')
      END AS mentions
  ) x
  WHERE s.social_account_id IS NOT NULL AND s.media_id IS NOT NULL
  ON CONFLICT (social_account_id, media_id, date) DO UPDATE SET
    posted_at = COALESCE(EXCLUDED.posted_at, instagram_post.posted_at),
    media_type = COALESCE(EXCLUDED.media_type, instagram_post.media_type),
    caption = COALESCE(EXCLUDED.caption, instagram_post.caption),
    permalink = COALESCE(EXCLUDED.permalink, instagram_post.permalink),
    cover_image = COALESCE(EXCLUDED.cover_image, instagram_post.cover_image),
    video_duration = COALESCE(EXCLUDED.video_duration, instagram_post.video_duration),
    carousel_media_count = COALESCE(EXCLUDED.carousel_media_count, instagram_post.carousel_media_count),
    is_sponsored = COALESCE(EXCLUDED.is_sponsored, instagram_post.is_sponsored),
    likes = COALESCE(EXCLUDED.likes, instagram_post.likes),
    comments = COALESCE(EXCLUDED.comments, instagram_post.comments),
    views = COALESCE(EXCLUDED.views, instagram_post.views),
    shares = COALESCE(EXCLUDED.shares, instagram_post.shares),
    reach = COALESCE(EXCLUDED.reach, instagram_post.reach),
    saved = COALESCE(EXCLUDED.saved, instagram_post.saved),
    total_interactions = COALESCE(EXCLUDED.total_interactions, instagram_post.total_interactions),
    reposts = COALESCE(EXCLUDED.reposts, instagram_post.reposts),
    follows = COALESCE(EXCLUDED.follows, instagram_post.follows),
    profile_visits = COALESCE(EXCLUDED.profile_visits, instagram_post.profile_visits),
    reel_avg_watch_time = COALESCE(EXCLUDED.reel_avg_watch_time, instagram_post.reel_avg_watch_time),
    reel_video_view_total_time = COALESCE(EXCLUDED.reel_video_view_total_time, instagram_post.reel_video_view_total_time),
    engagement_rate = COALESCE(EXCLUDED.engagement_rate, instagram_post.engagement_rate),
    -- T4: sekali TRUE tetap TRUE. Blok apify menulis literal false (bukan NULL),
    -- jadi COALESCE lama membuat apify yang berjalan belakangan mematikan
    -- bendera Insights padahal kolom Insights-nya sendiri selamat.
    has_insights = COALESCE(EXCLUDED.has_insights, false)
                OR COALESCE(instagram_post.has_insights, false),
    shortcode = COALESCE(EXCLUDED.shortcode, instagram_post.shortcode),
    owner_username = COALESCE(EXCLUDED.owner_username, instagram_post.owner_username),
    platform_user_id = COALESCE(EXCLUDED.platform_user_id, instagram_post.platform_user_id),
    hashtags = COALESCE(EXCLUDED.hashtags, instagram_post.hashtags),
    mentions = COALESCE(EXCLUDED.mentions, instagram_post.mentions),
    source = EXCLUDED.source,
    source_table = EXCLUDED.source_table,
    source_id = EXCLUDED.source_id,
    processed_at = EXCLUDED.processed_at
  WHERE instagram_post.processed_at <= EXCLUDED.processed_at;

  -- dari official (tidak punya raw_payload -> kolom baru NULL)
  INSERT INTO l0_harmonization.instagram_post (
    social_account_id, media_id, date, posted_at, media_type, caption, permalink,
    cover_image, video_duration, carousel_media_count, is_sponsored, likes, comments,
    views, shares, reach, saved, total_interactions, reposts, follows, profile_visits,
    reel_avg_watch_time, reel_video_view_total_time, engagement_rate, has_insights,
    source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id, s.media_id, COALESCE(s.fetched_at, now())::date, s.posted_at,
    s.media_type, s.caption, s.permalink, s.cover_image, s.video_duration,
    s.carousel_media_count, s.is_sponsored, s.likes, s.comments, s.views, s.shares,
    s.reach, s.saved, s.total_interactions, s.reposts, s.follows, s.profile_visits,
    s.reel_avg_watch_time, s.reel_video_view_total_time, s.engagement_rate, true,
    'official', 'l0_raw.ig_media_snapshots_official', s.id, COALESCE(s.fetched_at, now())
  FROM (
    -- T3: sama seperti blok apify di atas.
    SELECT DISTINCT ON (r.social_account_id, r.media_id,
                        COALESCE(r.fetched_at, now())::date) r.*
    FROM l0_raw.ig_media_snapshots_official r
    WHERE r.social_account_id IS NOT NULL AND r.media_id IS NOT NULL
    ORDER BY r.social_account_id, r.media_id,
             COALESCE(r.fetched_at, now())::date,
             r.fetched_at DESC NULLS LAST, r.id
  ) s
  WHERE s.social_account_id IS NOT NULL AND s.media_id IS NOT NULL
  ON CONFLICT (social_account_id, media_id, date) DO UPDATE SET
    posted_at = COALESCE(EXCLUDED.posted_at, instagram_post.posted_at),
    media_type = COALESCE(EXCLUDED.media_type, instagram_post.media_type),
    caption = COALESCE(EXCLUDED.caption, instagram_post.caption),
    permalink = COALESCE(EXCLUDED.permalink, instagram_post.permalink),
    cover_image = COALESCE(EXCLUDED.cover_image, instagram_post.cover_image),
    video_duration = COALESCE(EXCLUDED.video_duration, instagram_post.video_duration),
    carousel_media_count = COALESCE(EXCLUDED.carousel_media_count, instagram_post.carousel_media_count),
    is_sponsored = COALESCE(EXCLUDED.is_sponsored, instagram_post.is_sponsored),
    likes = COALESCE(EXCLUDED.likes, instagram_post.likes),
    comments = COALESCE(EXCLUDED.comments, instagram_post.comments),
    views = COALESCE(EXCLUDED.views, instagram_post.views),
    shares = COALESCE(EXCLUDED.shares, instagram_post.shares),
    reach = COALESCE(EXCLUDED.reach, instagram_post.reach),
    saved = COALESCE(EXCLUDED.saved, instagram_post.saved),
    total_interactions = COALESCE(EXCLUDED.total_interactions, instagram_post.total_interactions),
    reposts = COALESCE(EXCLUDED.reposts, instagram_post.reposts),
    follows = COALESCE(EXCLUDED.follows, instagram_post.follows),
    profile_visits = COALESCE(EXCLUDED.profile_visits, instagram_post.profile_visits),
    reel_avg_watch_time = COALESCE(EXCLUDED.reel_avg_watch_time, instagram_post.reel_avg_watch_time),
    reel_video_view_total_time = COALESCE(EXCLUDED.reel_video_view_total_time, instagram_post.reel_video_view_total_time),
    engagement_rate = COALESCE(EXCLUDED.engagement_rate, instagram_post.engagement_rate),
    -- T4: sekali TRUE tetap TRUE. Blok apify menulis literal false (bukan NULL),
    -- jadi COALESCE lama membuat apify yang berjalan belakangan mematikan
    -- bendera Insights padahal kolom Insights-nya sendiri selamat.
    has_insights = COALESCE(EXCLUDED.has_insights, false)
                OR COALESCE(instagram_post.has_insights, false),
    source = EXCLUDED.source,
    source_table = EXCLUDED.source_table,
    source_id = EXCLUDED.source_id,
    processed_at = EXCLUDED.processed_at
  WHERE instagram_post.processed_at <= EXCLUDED.processed_at;

  SELECT (SELECT count(*) FROM l0_raw.ig_media_snapshots_apify)
       + (SELECT count(*) FROM l0_raw.ig_media_snapshots_official) INTO v_baca;
  SELECT count(*) INTO v_masuk FROM l0_harmonization.instagram_post;

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

-- -------------------------------------------------------------------------
-- Langkah 1b -- T3      : l0_harmonization.sp_sync_tiktok_post
-- -------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE l0_harmonization.sp_sync_tiktok_post()
 LANGUAGE plpgsql
AS $procedure$
DECLARE
  v_log_id uuid; v_baca bigint := 0; v_masuk bigint := 0; v_sebelum bigint := 0;
BEGIN
  SELECT count(*) INTO v_sebelum FROM l0_harmonization.tiktok_post;

  INSERT INTO l0_harmonization.sync_log
    (target_table, source_table, source, sync_date, status, started_at)
  VALUES ('tiktok_post','l0_raw.tt_video_apify + l0_raw.tt_video_official','apify+official', current_date, 'running', now())
  RETURNING id INTO v_log_id;

  -- dari apify
  INSERT INTO l0_harmonization.tiktok_post (
    social_account_id, video_id, date, posted_at, media_type, title, caption,
    permalink, cover_image, video_duration, likes, comments, shares, views,
    engagement_rate,
    owner_username, platform_user_id, hashtags, mentions, saved, is_sponsored,
    carousel_media_count,
    source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id, s.video_id, COALESCE(s.scraped_at, s.fetched_at, now())::date,
    s.posted_at, x.media_type, s.title, s.description, s.share_url, s.cover_image_url,
    s.duration, s.like_count, s.comment_count, s.share_count, s.view_count,
    s.engagement_rate,
    x.owner_username, x.platform_user_id, x.hashtags, x.mentions, x.saved,
    x.is_sponsored, x.carousel_media_count,
    'apify', 'l0_raw.tt_video_apify', s.id,
    COALESCE(s.scraped_at, s.fetched_at, now())
  FROM (
    -- T3: satu baris per (akun, video, tanggal).
    SELECT DISTINCT ON (r.social_account_id, r.video_id,
                        COALESCE(r.scraped_at, r.fetched_at, now())::date) r.*
    FROM l0_raw.tt_video_apify r
    WHERE r.social_account_id IS NOT NULL AND r.video_id IS NOT NULL
    ORDER BY r.social_account_id, r.video_id,
             COALESCE(r.scraped_at, r.fetched_at, now())::date,
             r.scraped_at DESC NULLS LAST, r.fetched_at DESC NULLS LAST, r.id
  ) s
  CROSS JOIN LATERAL (
    SELECT
      -- video biasa -> VIDEO, slideshow/carousel -> CAROUSEL
      CASE WHEN COALESCE((s.raw_payload->>'isSlideshow')::boolean, false)
           THEN 'CAROUSEL' ELSE 'VIDEO' END                    AS media_type,
      NULLIF(s.raw_payload->'authorMeta'->>'name', '')          AS owner_username,
      NULLIF(s.raw_payload->'authorMeta'->>'id', '')            AS platform_user_id,
      CASE WHEN jsonb_typeof(s.raw_payload->'hashtags') = 'array' THEN
        (SELECT array_agg(a.h->>'name' ORDER BY a.ord)
           FROM jsonb_array_elements(s.raw_payload->'hashtags')
                WITH ORDINALITY AS a(h, ord)
          WHERE COALESCE(a.h->>'name', '') <> '')
      END AS hashtags,
      CASE WHEN jsonb_typeof(s.raw_payload->'mentions') = 'array' THEN
        (SELECT array_agg(ltrim(a.t, '@') ORDER BY a.ord)
           FROM jsonb_array_elements_text(s.raw_payload->'mentions')
                WITH ORDINALITY AS a(t, ord)
          WHERE COALESCE(ltrim(a.t, '@'), '') <> '')
      END AS mentions,
      (s.raw_payload->>'collectCount')::bigint                  AS saved,
      CASE WHEN s.raw_payload ? 'isSponsored' OR s.raw_payload ? 'isAd'
           THEN COALESCE((s.raw_payload->>'isSponsored')::boolean, false)
             OR COALESCE((s.raw_payload->>'isAd')::boolean, false)
      END AS is_sponsored,
      CASE WHEN jsonb_typeof(s.raw_payload->'slideshowImageLinks') = 'array'
           THEN jsonb_array_length(s.raw_payload->'slideshowImageLinks')
      END AS carousel_media_count
  ) x
  WHERE s.social_account_id IS NOT NULL AND s.video_id IS NOT NULL
  ON CONFLICT (social_account_id, video_id, date) DO UPDATE SET
    posted_at = COALESCE(EXCLUDED.posted_at, tiktok_post.posted_at),
    media_type = COALESCE(EXCLUDED.media_type, tiktok_post.media_type),
    title = COALESCE(EXCLUDED.title, tiktok_post.title),
    caption = COALESCE(EXCLUDED.caption, tiktok_post.caption),
    permalink = COALESCE(EXCLUDED.permalink, tiktok_post.permalink),
    cover_image = COALESCE(EXCLUDED.cover_image, tiktok_post.cover_image),
    video_duration = COALESCE(EXCLUDED.video_duration, tiktok_post.video_duration),
    likes = COALESCE(EXCLUDED.likes, tiktok_post.likes),
    comments = COALESCE(EXCLUDED.comments, tiktok_post.comments),
    shares = COALESCE(EXCLUDED.shares, tiktok_post.shares),
    views = COALESCE(EXCLUDED.views, tiktok_post.views),
    engagement_rate = COALESCE(EXCLUDED.engagement_rate, tiktok_post.engagement_rate),
    owner_username = COALESCE(EXCLUDED.owner_username, tiktok_post.owner_username),
    platform_user_id = COALESCE(EXCLUDED.platform_user_id, tiktok_post.platform_user_id),
    hashtags = COALESCE(EXCLUDED.hashtags, tiktok_post.hashtags),
    mentions = COALESCE(EXCLUDED.mentions, tiktok_post.mentions),
    saved = COALESCE(EXCLUDED.saved, tiktok_post.saved),
    is_sponsored = COALESCE(EXCLUDED.is_sponsored, tiktok_post.is_sponsored),
    carousel_media_count = COALESCE(EXCLUDED.carousel_media_count, tiktok_post.carousel_media_count),
    source = EXCLUDED.source,
    source_table = EXCLUDED.source_table,
    source_id = EXCLUDED.source_id,
    processed_at = EXCLUDED.processed_at
  WHERE tiktok_post.processed_at <= EXCLUDED.processed_at;

  -- dari official (tidak punya raw_payload -> kolom baru NULL, media_type VIDEO)
  INSERT INTO l0_harmonization.tiktok_post (
    social_account_id, video_id, date, posted_at, media_type, title, caption,
    permalink, cover_image, video_duration, likes, comments, shares, views,
    engagement_rate, source, source_table, source_id, processed_at)
  SELECT
    s.social_account_id, s.video_id, COALESCE(s.fetched_at, now())::date, s.posted_at,
    'VIDEO', s.title, s.description, s.share_url, s.cover_image_url, s.duration,
    s.like_count, s.comment_count, s.share_count, s.view_count, s.engagement_rate,
    'official', 'l0_raw.tt_video_official', s.id, COALESCE(s.fetched_at, now())
  FROM (
    -- T3: sama seperti blok apify di atas.
    SELECT DISTINCT ON (r.social_account_id, r.video_id,
                        COALESCE(r.fetched_at, now())::date) r.*
    FROM l0_raw.tt_video_official r
    WHERE r.social_account_id IS NOT NULL AND r.video_id IS NOT NULL
    ORDER BY r.social_account_id, r.video_id,
             COALESCE(r.fetched_at, now())::date,
             r.fetched_at DESC NULLS LAST, r.id
  ) s
  WHERE s.social_account_id IS NOT NULL AND s.video_id IS NOT NULL
  ON CONFLICT (social_account_id, video_id, date) DO UPDATE SET
    posted_at = COALESCE(EXCLUDED.posted_at, tiktok_post.posted_at),
    media_type = COALESCE(EXCLUDED.media_type, tiktok_post.media_type),
    title = COALESCE(EXCLUDED.title, tiktok_post.title),
    caption = COALESCE(EXCLUDED.caption, tiktok_post.caption),
    permalink = COALESCE(EXCLUDED.permalink, tiktok_post.permalink),
    cover_image = COALESCE(EXCLUDED.cover_image, tiktok_post.cover_image),
    video_duration = COALESCE(EXCLUDED.video_duration, tiktok_post.video_duration),
    likes = COALESCE(EXCLUDED.likes, tiktok_post.likes),
    comments = COALESCE(EXCLUDED.comments, tiktok_post.comments),
    shares = COALESCE(EXCLUDED.shares, tiktok_post.shares),
    views = COALESCE(EXCLUDED.views, tiktok_post.views),
    engagement_rate = COALESCE(EXCLUDED.engagement_rate, tiktok_post.engagement_rate),
    source = EXCLUDED.source,
    source_table = EXCLUDED.source_table,
    source_id = EXCLUDED.source_id,
    processed_at = EXCLUDED.processed_at
  WHERE tiktok_post.processed_at <= EXCLUDED.processed_at;

  SELECT (SELECT count(*) FROM l0_raw.tt_video_apify)
       + (SELECT count(*) FROM l0_raw.tt_video_official) INTO v_baca;
  SELECT count(*) INTO v_masuk FROM l0_harmonization.tiktok_post;

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

-- -------------------------------------------------------------------------
-- Langkah 1c -- T4      : l0_harmonization.sp_sync_instagram_profile
-- -------------------------------------------------------------------------
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

-- -------------------------------------------------------------------------
-- Langkah 1d -- T2      : l1_silver.sp_build_unified_post
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
        has_insights = COALESCE(EXCLUDED.has_insights, l1_silver.unified_post.has_insights),
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


-- ---------------------------------------------------------------------------
-- Langkah 2 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $verif$
DECLARE
    n_dedup_sync  int;
    n_dedup_l1    int;
    n_insights    int;
    n_routine     int;
    n_baris       bigint;
BEGIN
    -- T3: kedua procedure post kini punya DISTINCT ON.
    SELECT count(*) INTO n_dedup_sync
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization'
      AND p.proname IN ('sp_sync_instagram_post', 'sp_sync_tiktok_post')
      AND p.prosrc ILIKE '%DISTINCT ON%';

    -- T2: builder L1 kini punya DISTINCT ON.
    SELECT count(*) INTO n_dedup_l1
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_post'
      AND p.prosrc ILIKE '%DISTINCT ON (u.social_account_id, u.content_id)%';

    -- T4: pola lama sudah tidak tersisa di 2 procedure yang diperbaiki.
    SELECT count(*) INTO n_insights
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization'
      AND p.proname IN ('sp_sync_instagram_post', 'sp_sync_instagram_profile')
      AND p.prosrc ILIKE '%COALESCE(EXCLUDED.has_insights, false)%';

    -- Jumlah routine tidak boleh bertambah/berkurang.
    SELECT count(*) INTO n_routine
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN ('l0_harmonization', 'l1_silver');

    -- Tidak ada data yang berubah.
    SELECT (SELECT count(*) FROM l0_harmonization.instagram_post)
         + (SELECT count(*) FROM l0_harmonization.tiktok_post)
         + (SELECT count(*) FROM l1_silver.unified_post)
      INTO n_baris;

    IF n_dedup_sync <> 2 THEN
        RAISE EXCEPTION 'DISTINCT ON terpasang di % procedure post, seharusnya 2', n_dedup_sync;
    END IF;
    IF n_dedup_l1 <> 1 THEN
        RAISE EXCEPTION 'DISTINCT ON di sp_build_unified_post tidak terpasang';
    END IF;
    IF n_insights <> 2 THEN
        RAISE EXCEPTION 'Pola has_insights baru terpasang di % procedure, seharusnya 2', n_insights;
    END IF;
    IF n_routine <> 24 THEN
        RAISE EXCEPTION 'Jumlah routine %, seharusnya tetap 24', n_routine;
    END IF;
    IF n_baris <> 442 THEN
        RAISE EXCEPTION 'Jumlah baris post berubah jadi % -- seharusnya tetap 442 '
                        '(130 + 91 + 221). Migrasi ini tidak boleh menyentuh data.', n_baris;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: T2 1/1, T3 2/2, T4 2/2, 24 routine utuh, '
                 '442 baris post tidak berubah.';
    RAISE NOTICE 'Efeknya baru terasa saat procedure berikutnya dijalankan; '
                 'migrasi ini tidak mengubah data yang sudah ada.';
END $verif$;

COMMIT;
