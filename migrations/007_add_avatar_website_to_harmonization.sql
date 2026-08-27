-- =====================================================================
-- 007_add_avatar_website_to_harmonization.sql
--
-- Menutup kesenjangan struktur di layer harmonization:
--   l0_harmonization.instagram_profile  + kolom avatar_url
--   l0_harmonization.tiktok_profile     + kolom website
--
-- LATAR BELAKANG
--   Sampai sekarang kedua field itu tidak punya kolom flat, baik di
--   l0_raw maupun di l0_harmonization. Datanya SUDAH ADA di L0, tapi
--   terkubur di dalam raw_payload (JSONB) dan tidak pernah di-flatten
--   waktu ingest:
--     - IG avatar  : raw_payload->>'profilePicUrlHD' / 'profilePicUrl'
--     - TT website : raw_payload->'authorMeta'->>'bioLink'
--
--   Akibatnya l1_silver.unified_profile.avatar_url (Instagram) dan
--   .website (TikTok) tidak bisa diisi lewat jalur harmonization, dan
--   1.419 nilai yang ada sekarang di L1 hanya bertahan karena klausa
--   COALESCE melindunginya dari jalur bypass yang akan dibuang.
--
--   Struktur sekarang juga ganjil: TikTok punya avatar_url tapi tidak
--   punya website; Instagram justru sebaliknya. Setelah migration ini
--   keduanya punya keduanya.
--
-- KENAPA AMAN
--   * ADD COLUMN nullable bersifat aditif: tidak menulis ulang baris
--     yang sudah ada, tidak mengunci tabel lama di Postgres modern.
--   * IF NOT EXISTS membuat script ini idempotent.
--   * Backfill hanya menyentuh KOLOM BARU dan hanya pada baris yang
--     nilainya masih NULL. Tidak satu pun kolom lama disentuh.
--   * Join backfill lewat source_id -> l0_raw.id, yang sudah
--     terverifikasi 0 orphan untuk kedua platform.
--
-- TIDAK menulis apa pun ke l0_raw. TIDAK membuat tabel baru.
-- TIDAK menyentuh l1_silver.
--
-- Procedure sinkronisasi diperbarui terpisah di migration 008, supaya
-- run berikutnya ikut mengisi kedua kolom ini untuk baris baru.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1) STRUKTUR — tambah kolom
--    Nama mengikuti konvensi profil yang sudah dipakai project:
--      profil   -> avatar_url  (tt_profile_apify, tiktok_profile,
--                               unified_profile)
--      follower -> profile_pic_url
--    Jadi 'avatar_url', BUKAN 'profile_pic_url', supaya simetris dengan
--    l0_harmonization.tiktok_profile.avatar_url dan langsung cocok
--    dengan l1_silver.unified_profile.avatar_url.
-- ---------------------------------------------------------------------
ALTER TABLE l0_harmonization.instagram_profile
  ADD COLUMN IF NOT EXISTS avatar_url text;

ALTER TABLE l0_harmonization.tiktok_profile
  ADD COLUMN IF NOT EXISTS website text;

COMMENT ON COLUMN l0_harmonization.instagram_profile.avatar_url IS
  'Foto profil. Sumber: l0_raw.ig_profile_apify.raw_payload -> COALESCE(profilePicUrlHD, profilePicUrl). '
  'Catatan: URL Instagram CDN bertanda tangan dan kedaluwarsa (oe=/oh=/_nc_ohc).';

COMMENT ON COLUMN l0_harmonization.tiktok_profile.website IS
  'Bio link. Sumber: l0_raw.tt_profile_apify.raw_payload -> authorMeta.bioLink, '
  'dinormalisasi dengan menambahkan https:// bila belum berskema.';

-- ---------------------------------------------------------------------
-- 2) BACKFILL INSTAGRAM avatar_url
--    COALESCE(profilePicUrlHD, profilePicUrl): 4 baris tidak punya versi
--    HD (abiejie, bekasi.terkini, infodepok24, infojkt24) dan tertutup
--    oleh fallback, sehingga cakupannya 931/931.
-- ---------------------------------------------------------------------
UPDATE l0_harmonization.instagram_profile h
SET avatar_url = NULLIF(btrim(COALESCE(r.raw_payload->>'profilePicUrlHD',
                                       r.raw_payload->>'profilePicUrl')), '')
FROM l0_raw.ig_profile_apify r
WHERE r.id = h.source_id
  AND h.source_table = 'l0_raw.ig_profile_apify'
  AND h.avatar_url IS NULL;

-- ---------------------------------------------------------------------
-- 3) BACKFILL TIKTOK website
--    authorMeta.bioLink dinormalisasi: 439 dari 492 sudah berawalan
--    http/https, 53 sisanya tanpa skema (mis. 'bit.ly/hyeiwns',
--    'instagram.com/cintaindraa') sehingga diberi prefix https://.
--    555 akun memang tidak mengisi bio link -> tetap NULL, itu benar.
-- ---------------------------------------------------------------------
UPDATE l0_harmonization.tiktok_profile h
SET website = CASE
      WHEN btrim(COALESCE(r.raw_payload->'authorMeta'->>'bioLink', '')) = ''
        THEN NULL
      WHEN btrim(r.raw_payload->'authorMeta'->>'bioLink') ~* '^https?://'
        THEN btrim(r.raw_payload->'authorMeta'->>'bioLink')
      ELSE 'https://' || btrim(r.raw_payload->'authorMeta'->>'bioLink')
    END
FROM l0_raw.tt_profile_apify r
WHERE r.id = h.source_id
  AND h.source_table = 'l0_raw.tt_profile_apify'
  AND h.website IS NULL;
