-- =====================================================================
-- 013_sync_procedures_with_post_fields.sql
--
-- Mengalirkan kolom yang ditambahkan 012 dari raw_payload sampai L1.
-- Memperbaiki procedure EXISTING -- tidak membuat procedure baru.
--
--   l0_harmonization.sp_sync_instagram_post()
--   l0_harmonization.sp_sync_tiktok_post()
--   l1_silver.sp_build_unified_post()
--
-- ---------------------------------------------------------------------
-- PERUBAHAN PERILAKU YANG PERLU DIPERHATIKAN: `<` menjadi `<=`
-- ---------------------------------------------------------------------
-- Kedua procedure harmonization memakai penjaga
--     WHERE <tabel>.processed_at < EXCLUDED.processed_at
-- pada ON CONFLICT DO UPDATE. processed_at berasal dari scraped_at di L0,
-- yang TIDAK berubah saat procedure di-rerun atas data yang sama. Dengan
-- `<` yang ketat, rerun tidak akan pernah memicu DO UPDATE, sehingga
-- 5 + 7 kolom baru dari 012 akan tetap NULL selamanya untuk 221 baris
-- yang sudah ada.
--
-- Diubah menjadi `<=` supaya rerun bersifat refresh yang idempoten.
-- Aman karena seluruh DO UPDATE SET memakai COALESCE(EXCLUDED.x, existing.x):
-- menjalankannya ulang atas data identik menghasilkan baris yang identik.
-- Ini juga menyamakan harmonization dengan l1_silver.sp_build_unified_post()
-- yang memang sudah memakai `>=`.
--
-- ---------------------------------------------------------------------
-- NORMALISASI YANG DILAKUKAN (dan alasannya)
-- ---------------------------------------------------------------------
--  * TikTok mentions datang berprefiks '@' ('@tokoclippers'), Instagram
--    tidak ('irwansyah_15'). Prefiks '@' dibuang supaya satu kolom L1
--    punya arti yang sama di kedua platform.
--    Catatan: sebagian mention TikTok berisi display name, bukan handle
--    (mis. '@Ibnu Wardani'). Itu memang yang dikembalikan actor; tidak
--    ditebak-tebak menjadi handle.
--  * TikTok hashtags berbentuk [{"name": "..."}]; 19/58 baris hanya
--    berisi {"name": ""}. Nilai kosong dibuang. Kalau tidak ada yang
--    tersisa, hasilnya NULL (bukan array kosong) supaya konsisten dengan
--    aturan "NULL = tidak tersedia".
--  * is_sponsored TikTok = isSponsored OR isAd. NULL kalau kedua key
--    memang tidak ada di payload -- tidak di-default ke false.
--  * media_type TikTok berhenti di-hardcode 'VIDEO':
--      isSlideshow = true  -> 'CAROUSEL'
--      selain itu          -> 'VIDEO'
--
-- ---------------------------------------------------------------------
-- YANG SENGAJA TIDAK DISENTUH
-- ---------------------------------------------------------------------
--  * likes = -1 dibiarkan apa adanya di semua layer.
--  * engagement_rate tidak dihitung di L1 -- itu metric L2/feature.
--  * reach / impressions / profile_visits / follows / reposts /
--    reel_avg_watch_time / reel_video_view_total_time / shares IG /
--    saved IG tetap NULL. Tidak diisi 0.
--  * Cabang `official` di kedua procedure tidak diubah logikanya; tabel
--    l0_raw.*_official tidak punya kolom raw_payload, jadi kolom baru
--    diisi NULL di sana. Kedua tabel itu memang masih 0 baris.
--  * social_account_id dan platform_id tidak dihitung ulang. L1 tetap
--    mengambil platform_id dari public.social_account lewat JOIN existing.
-- =====================================================================

BEGIN;

-- =====================================================================
-- 1. l0_harmonization.sp_sync_instagram_post()
-- =====================================================================
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
  FROM l0_raw.ig_media_snapshots_apify s
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
    has_insights = COALESCE(EXCLUDED.has_insights, instagram_post.has_insights),
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
  FROM l0_raw.ig_media_snapshots_official s
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
    has_insights = COALESCE(EXCLUDED.has_insights, instagram_post.has_insights),
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


-- =====================================================================
-- 2. l0_harmonization.sp_sync_tiktok_post()
-- =====================================================================
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
  FROM l0_raw.tt_video_apify s
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
  FROM l0_raw.tt_video_official s
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


-- =====================================================================
-- 3. l1_silver.sp_build_unified_post()
--
-- Perubahan terhadap versi sebelumnya:
--   + username, platform_user_id, shortcode, hashtags, mentions diteruskan
--   + cabang TikTok berhenti mengirim NULL hardcoded untuk is_sponsored,
--     carousel_media_count, dan saved -- ketiganya sekarang datang dari
--     l0_harmonization.tiktok_post
--   + shortcode di cabang TikTok tetap NULL (TikTok tidak punya shortcode)
--
-- Yang TIDAK berubah:
--   * JOIN ke public.social_account dan pengambilan platform_id dari sana
--   * conflict target (social_account_id, content_id)
--   * reach / total_interactions / reposts / follows / profile_visits /
--     reel_* tetap NULL untuk TikTok, dan tetap dari harmonization untuk IG
-- =====================================================================
CREATE OR REPLACE FUNCTION l1_silver.sp_build_unified_post()
RETURNS void
LANGUAGE plpgsql
AS $function$
BEGIN
    INSERT INTO l1_silver.unified_post (
        social_account_id, platform_id, content_id, date, posted_at, media_type,
        title, caption, permalink, cover_image, video_duration, carousel_media_count,
        is_sponsored, likes, comments, views, shares, reach, saved, total_interactions,
        reposts, follows, profile_visits, reel_avg_watch_time, reel_video_view_total_time,
        engagement_rate, has_insights,
        username, platform_user_id, shortcode, hashtags, mentions,
        source, source_table, source_id, processed_at
    )
    SELECT
        sa.id, sa.platform_id, src.content_id, src.date, src.posted_at, src.media_type,
        src.title, src.caption, src.permalink, src.cover_image, src.video_duration,
        src.carousel_media_count, src.is_sponsored, src.likes, src.comments, src.views,
        src.shares, src.reach, src.saved, src.total_interactions, src.reposts, src.follows,
        src.profile_visits, src.reel_avg_watch_time, src.reel_video_view_total_time,
        src.engagement_rate, src.has_insights,
        src.username, src.platform_user_id, src.shortcode, src.hashtags, src.mentions,
        src.source, src.source_table, src.source_id, src.processed_at
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
    ) src
    JOIN public.social_account sa ON sa.id = src.social_account_id
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
        engagement_rate = COALESCE(EXCLUDED.engagement_rate, l1_silver.unified_post.engagement_rate),
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

COMMIT;
