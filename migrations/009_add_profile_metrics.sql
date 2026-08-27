-- =====================================================================
-- 009_add_profile_metrics.sql
--
-- Menambah metric Profile yang dibutuhkan UI tapi belum ada di L1.
-- Referensi UI: app/Autometric-KOL-Module.html
--
-- Jalur tetap: l0_raw -> l0_harmonization -> l1_silver.unified_profile
-- TIDAK menghidupkan kembali sp_sync_unified_profile() (bypass, sudah di-drop).
--
-- ---------------------------------------------------------------------
-- KOLOM YANG DITAMBAHKAN
-- ---------------------------------------------------------------------
--
-- A. l0_harmonization.instagram_profile + tiktok_profile  (3 kolom, DIRECT)
--    Sama seperti kasus avatar_url/website di 007: datanya SUDAH ADA di
--    l0_raw tapi terkubur di raw_payload dan tidak pernah di-flatten.
--
--      platform_user_id  IG: raw_payload->>'id'                    931/931
--                        TT: raw_payload->'authorMeta'->>'id'    1047/1047
--      profile_url       IG: raw_payload->>'url'                   931/931
--                        TT: authorMeta->>'profileUrl'           1047/1047
--      is_private        IG: raw_payload->>'private'               931/931
--                        TT: authorMeta->>'privateAccount'       1047/1047
--
--    Ketiganya bermakna IDENTIK di kedua platform, jadi disatukan jadi
--    satu kolom (aturan penyatuan IG+TikTok).
--
-- B. l1_silver.unified_profile  (4 kolom)
--      platform_user_id  DIRECT dari harmonization
--      profile_url       DIRECT dari harmonization
--      is_private        DIRECT dari harmonization
--      tier              CALCULATED di L1 dari followers_count
--
-- ---------------------------------------------------------------------
-- KENAPA `tier` DIHITUNG DI L1, BUKAN DI HARMONIZATION
-- ---------------------------------------------------------------------
--   tier bukan data mentah dari platform, melainkan klasifikasi bisnis
--   turunan followers_count. Layer harmonization adalah salinan setia L0,
--   jadi tier tidak punya tempat di sana. Menghitungnya sekali di L1
--   memastikan Instagram dan TikTok memakai ambang yang sama persis.
--
--   Ambangnya TIDAK di-hardcode: dibaca dari public.kol_tiers, yang sudah
--   ada di database dan nilainya identik dengan fungsi TIER() di UI:
--
--     kol_tiers                        UI TIER()
--     Nano      1.000 -     9.999      < 10K      -> 'Nano'
--     Micro    10.000 -    49.999      >= 10K     -> 'Micro'
--     Mid-tier 50.000 -    99.999      >= 50K     -> 'Mid-tier'
--     Macro   100.000 -   999.999      >= 100K    -> 'Macro'
--     Mega  1.000.000 -       NULL     >= 1M      -> 'Mega'
--
--   Perilaku batas (didokumentasikan, mengikuti UI):
--     - followers_count IS NULL          -> tier NULL   (4 baris IG)
--     - followers_count < 1.000          -> tier 'Nano' (53 baris)
--       kol_tiers tidak punya baris untuk < 1.000, sedangkan UI
--       memetakannya ke 'Nano'. Supaya L1 dan UI tidak berbeda, dipakai
--       fallback ke tier dengan min_followers terkecil.
--
-- ---------------------------------------------------------------------
-- YANG SENGAJA TIDAK DISATUKAN
-- ---------------------------------------------------------------------
--   IG raw_payload->>'isBusinessAccount'  (234 true / 693 false)
--   TT authorMeta->>'ttSeller'            ( 87 true / 960 false)
--
--   Keduanya TIDAK bermakna sama: isBusinessAccount = akun profesional
--   Instagram; ttSeller = penjual TikTok Shop. Menyatukannya jadi satu
--   kolom account_type akan menghasilkan data yang menyesatkan, jadi
--   keduanya dilewati sampai ada keputusan bisnis.
--
-- ---------------------------------------------------------------------
-- KEAMANAN
-- ---------------------------------------------------------------------
--   * ADD COLUMN nullable bersifat aditif, tidak menulis ulang baris lama.
--   * IF NOT EXISTS -> idempotent.
--   * Backfill hanya menyentuh KOLOM BARU dan hanya kalau masih NULL.
--   * Join backfill lewat source_id -> l0_raw.id (0 orphan, terverifikasi).
--   * TIDAK menulis apa pun ke l0_raw. TIDAK membuat tabel baru.
-- =====================================================================

-- ---------------------------------------------------------------------
-- A1) STRUKTUR — l0_harmonization
-- ---------------------------------------------------------------------
ALTER TABLE l0_harmonization.instagram_profile
  ADD COLUMN IF NOT EXISTS platform_user_id varchar,
  ADD COLUMN IF NOT EXISTS profile_url      text,
  ADD COLUMN IF NOT EXISTS is_private       boolean;

ALTER TABLE l0_harmonization.tiktok_profile
  ADD COLUMN IF NOT EXISTS platform_user_id varchar,
  ADD COLUMN IF NOT EXISTS profile_url      text,
  ADD COLUMN IF NOT EXISTS is_private       boolean;

COMMENT ON COLUMN l0_harmonization.instagram_profile.platform_user_id IS
  'ID numerik akun di Instagram. Sumber: l0_raw.ig_profile_apify.raw_payload->>''id''.';
COMMENT ON COLUMN l0_harmonization.instagram_profile.profile_url IS
  'URL profil publik. Sumber: l0_raw.ig_profile_apify.raw_payload->>''url''.';
COMMENT ON COLUMN l0_harmonization.instagram_profile.is_private IS
  'Akun privat. Sumber: l0_raw.ig_profile_apify.raw_payload->>''private''.';

COMMENT ON COLUMN l0_harmonization.tiktok_profile.platform_user_id IS
  'ID numerik akun di TikTok. Sumber: l0_raw.tt_profile_apify.raw_payload->''authorMeta''->>''id''. '
  'Catatan: ini user id, BUKAN open_id dari TikTok OAuth.';
COMMENT ON COLUMN l0_harmonization.tiktok_profile.profile_url IS
  'URL profil publik. Sumber: l0_raw.tt_profile_apify.raw_payload->''authorMeta''->>''profileUrl''.';
COMMENT ON COLUMN l0_harmonization.tiktok_profile.is_private IS
  'Akun privat. Sumber: l0_raw.tt_profile_apify.raw_payload->''authorMeta''->>''privateAccount''.';

-- ---------------------------------------------------------------------
-- A2) BACKFILL — Instagram
-- ---------------------------------------------------------------------
UPDATE l0_harmonization.instagram_profile h
SET platform_user_id = COALESCE(h.platform_user_id, NULLIF(btrim(r.raw_payload->>'id'), '')),
    profile_url      = COALESCE(h.profile_url,      NULLIF(btrim(r.raw_payload->>'url'), '')),
    is_private       = COALESCE(h.is_private,       (r.raw_payload->>'private')::boolean)
FROM l0_raw.ig_profile_apify r
WHERE r.id = h.source_id
  AND h.source_table = 'l0_raw.ig_profile_apify'
  AND (h.platform_user_id IS NULL OR h.profile_url IS NULL OR h.is_private IS NULL);

-- ---------------------------------------------------------------------
-- A3) BACKFILL — TikTok
-- ---------------------------------------------------------------------
UPDATE l0_harmonization.tiktok_profile h
SET platform_user_id = COALESCE(h.platform_user_id, NULLIF(btrim(r.raw_payload->'authorMeta'->>'id'), '')),
    profile_url      = COALESCE(h.profile_url,      NULLIF(btrim(r.raw_payload->'authorMeta'->>'profileUrl'), '')),
    is_private       = COALESCE(h.is_private,       (r.raw_payload->'authorMeta'->>'privateAccount')::boolean)
FROM l0_raw.tt_profile_apify r
WHERE r.id = h.source_id
  AND h.source_table = 'l0_raw.tt_profile_apify'
  AND (h.platform_user_id IS NULL OR h.profile_url IS NULL OR h.is_private IS NULL);

-- ---------------------------------------------------------------------
-- B) STRUKTUR — l1_silver.unified_profile
-- ---------------------------------------------------------------------
ALTER TABLE l1_silver.unified_profile
  ADD COLUMN IF NOT EXISTS platform_user_id varchar,
  ADD COLUMN IF NOT EXISTS profile_url      text,
  ADD COLUMN IF NOT EXISTS is_private       boolean,
  ADD COLUMN IF NOT EXISTS tier             varchar(20);

COMMENT ON COLUMN l1_silver.unified_profile.platform_user_id IS
  'ID akun di platform. IG: raw id; TikTok: authorMeta.id (bukan open_id).';
COMMENT ON COLUMN l1_silver.unified_profile.profile_url IS
  'URL profil publik, dari l0_harmonization.';
COMMENT ON COLUMN l1_silver.unified_profile.is_private IS
  'Akun privat. IG private / TikTok privateAccount (makna identik).';
COMMENT ON COLUMN l1_silver.unified_profile.tier IS
  'Tier KOL hasil klasifikasi followers_count memakai ambang public.kol_tiers. '
  'followers_count NULL -> NULL; di bawah min_followers terendah -> tier terendah (Nano), mengikuti UI.';
