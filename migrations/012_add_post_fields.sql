-- =====================================================================
-- 012_add_post_fields.sql
--
-- Menambah kolom Post yang dibutuhkan UI Autometric tapi belum sampai L1.
-- Referensi UI: app/Autometric-KOL-Module.html
--   - POSTS10 / POSTPOOL  (Creator Performance Report + post detail modal)
--   - CONTENT             (Discovery Content: search caption/keyword, filter)
--
-- Jalur tetap: l0_raw -> l0_harmonization -> l1_silver.unified_post
-- TIDAK menyentuh social_account_id / platform_id.
--
-- ---------------------------------------------------------------------
-- PRINSIP
-- ---------------------------------------------------------------------
--  * Semua kolom di bawah DIRECT dari raw_payload. Nol agregasi.
--    Metric turunan (avg likes, performance score, ranking, posting
--    frequency, engagement rate) tetap milik L2 Feature.
--  * Field yang tidak tersedia dari public scraping DIBIARKAN NULL,
--    tidak di-set 0: reach, impressions, profile_visits, follows,
--    reposts, reel_avg_watch_time, reel_video_view_total_time,
--    shares Instagram, saved Instagram, engagement_rate.
--    NULL berarti "tidak tersedia", 0 berarti "nol" — keduanya beda.
--  * likes = -1 (Instagram menyembunyikan like, 15/130 baris) TIDAK
--    diubah di L0/harmonization/L1. Sentinel dipertahankan apa adanya.
--    Perlakuan sebagai NULL/excluded adalah urusan L2.
--
-- Semua ADD COLUMN nullable tanpa default -> tidak me-rewrite tabel,
-- tidak menyentuh baris existing, reversibel dengan DROP COLUMN.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- A. l0_harmonization.instagram_post  (+5)
--
--    shortcode         raw_payload->>'shortCode'          130/130
--    owner_username    raw_payload->>'ownerUsername'      130/130
--    platform_user_id  raw_payload->>'ownerId'            130/130
--    hashtags          raw_payload->'hashtags'   text[]    39/130
--    mentions          raw_payload->'mentions'   text[]    45/130
--
--    Catatan owner_username: 41/130 post adalah kolaborasi (ownerUsername
--    != social_account.username). Sudah diverifikasi 41/41 bahwa akun yang
--    di-track selalu ada di coauthorProducers, jadi atribusi post BENAR.
--    Kolom ini disimpan supaya L2 bisa memutuskan apakah post kolaborasi
--    ikut dihitung dalam engagement rate.
-- ---------------------------------------------------------------------
ALTER TABLE l0_harmonization.instagram_post
  ADD COLUMN IF NOT EXISTS shortcode        varchar(64),
  ADD COLUMN IF NOT EXISTS owner_username   varchar(255),
  ADD COLUMN IF NOT EXISTS platform_user_id varchar(64),
  ADD COLUMN IF NOT EXISTS hashtags         text[],
  ADD COLUMN IF NOT EXISTS mentions         text[];

-- ---------------------------------------------------------------------
-- B. l0_harmonization.tiktok_post  (+7)
--
--    owner_username       authorMeta->>'name'              91/91
--    platform_user_id     authorMeta->>'id'                91/91
--    hashtags             hashtags[].name    text[]        39/91
--    mentions             mentions           text[]        26/91
--    saved                collectCount                     91/91
--    is_sponsored         isSponsored OR isAd              91/91  (10 true)
--    carousel_media_count len(slideshowImageLinks)          2/91
--
--    saved: tiktok_post belum punya kolom ini sama sekali, padahal actor
--    clockworks/tiktok-scraper mengembalikan collectCount di SEMUA baris.
--    Ini satu-satunya metric "saves" yang benar-benar tersedia dari
--    scraping publik (Instagram tidak mengekspos saves).
--
--    hashtags: 58/91 baris punya array hashtags, tapi hanya 39 yang punya
--    minimal satu name non-kosong — 19 baris berisi [{"name":""}] saja.
--    Yang kosong disimpan NULL, bukan array kosong, supaya konsisten
--    dengan aturan "NULL = tidak tersedia".
-- ---------------------------------------------------------------------
ALTER TABLE l0_harmonization.tiktok_post
  ADD COLUMN IF NOT EXISTS owner_username       varchar(255),
  ADD COLUMN IF NOT EXISTS platform_user_id     varchar(64),
  ADD COLUMN IF NOT EXISTS hashtags             text[],
  ADD COLUMN IF NOT EXISTS mentions             text[],
  ADD COLUMN IF NOT EXISTS saved                bigint,
  ADD COLUMN IF NOT EXISTS is_sponsored         boolean,
  ADD COLUMN IF NOT EXISTS carousel_media_count integer;

-- ---------------------------------------------------------------------
-- C. l1_silver.unified_post  (+5)
--
--    username          DIRECT dari harmonization.owner_username
--    platform_user_id  DIRECT dari harmonization
--    shortcode         DIRECT — Instagram saja. TikTok tidak punya konsep
--                      shortcode; video_id sudah menjadi identifier di URL.
--    hashtags          DIRECT
--    mentions          DIRECT
--
--    username + platform_user_id mengikuti pola yang SUDAH dipakai
--    l1_silver.unified_profile (kedua kolom itu sudah ada di sana),
--    jadi L1 tetap konsisten: identitas ikut didenormalisasi ke row.
--
--    saved / is_sponsored / carousel_media_count TIDAK di-ALTER di sini —
--    kolomnya sudah ada di unified_post, hanya cabang TikTok di
--    sp_build_unified_post yang selama ini mengirim NULL hardcoded.
--    Itu diperbaiki di 013.
-- ---------------------------------------------------------------------
ALTER TABLE l1_silver.unified_post
  ADD COLUMN IF NOT EXISTS username         varchar(255),
  ADD COLUMN IF NOT EXISTS platform_user_id varchar(64),
  ADD COLUMN IF NOT EXISTS shortcode        varchar(64),
  ADD COLUMN IF NOT EXISTS hashtags         text[],
  ADD COLUMN IF NOT EXISTS mentions         text[];

-- Index pendukung UI: search hashtag di Discovery Content, dan
-- "latest N posts" per akun di Creator Performance Report.
CREATE INDEX IF NOT EXISTS ix_unified_post_hashtags
  ON l1_silver.unified_post USING gin (hashtags);
CREATE INDEX IF NOT EXISTS ix_unified_post_account_posted
  ON l1_silver.unified_post (social_account_id, posted_at DESC);

COMMIT;
