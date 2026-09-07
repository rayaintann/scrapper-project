-- =====================================================================
-- 033_fix_kol_tiers_boundaries.sql
-- Memperbaiki ambang tier di public.kol_tiers agar sesuai kesepakatan
-- produk (KOL Discovery).
--
-- MASALAH
--   Ambang Mid-tier dan Macro di database sudah kedaluwarsa:
--
--     tier      DI DATABASE (salah)      KESEPAKATAN (benar)
--     Nano       1.000 -     9.999        1K   - 9.999        (sama)
--     Micro     10.000 -    49.999        10K  - 49.999       (sama)
--     Mid-tier  50.000 -    99.999        50K  - 499.999      <- BERUBAH
--     Macro    100.000 -   999.999        500K - 999.999      <- BERUBAH
--     Mega   1.000.000 -      NULL        >= 1M               (sama)
--
--   Akibatnya 1.103 KOL ber-followers 100.000-499.999 tampil sebagai
--   "Macro" padahal seharusnya "Mid-Tier". Audit 2026-09-07 mengukur
--   angka itu langsung ke database.
--
-- SIAPA YANG IKUT BERUBAH
--   public.kol_tiers dibaca DUA pihak, jadi satu perbaikan memperbaiki
--   keduanya:
--     1. UI Discovery  -> LEFT JOIN kol_tiers di kolDirectory.ts
--                         (langsung berubah, dibaca live tiap request)
--     2. l1_silver.sp_build_unified_profile()
--                      -> tier tersimpan di L1 dan diturunkan ke L2.
--                         BARU berubah setelah transform_chain_job
--                         dijalankan lagi.
--   Jadi akan ada jeda di mana UI sudah benar dan L1/L2 belum. Itu
--   disengaja dan hilang setelah pipeline jalan.
--
-- KENAPA UPDATE, BUKAN DELETE + INSERT
--   public.agency_kol_accounts.tier_id punya FOREIGN KEY ke
--   kol_tiers.id. Mengganti baris akan memutus relasi itu. UPDATE
--   min_followers/max_followers tidak menyentuh id, jadi FK aman.
--
-- NAMA TIER SENGAJA TIDAK DIUBAH
--   Database menyimpan 'Mid-tier', dokumen produk menulis 'Mid-Tier'.
--   Penggantian nama TIDAK dilakukan di sini karena nilai itu sudah
--   tersimpan sebagai teks di l1_silver.unified_profile.tier dan
--   l2_gold.kol_profile_card.tier, dan dipakai Saved List di UI.
--   Mengubahnya adalah perubahan tersendiri dengan dampak sendiri.
--   Migration ini hanya memperbaiki ANGKA.
--
-- TIDAK ADA PERUBAHAN SCHEMA
--   Hanya UPDATE dua baris data. Tidak ada kolom/tabel baru.
--
-- ROLLBACK
--   Jalankan kembali nilai lama:
--     UPDATE public.kol_tiers SET min_followers=50000,  max_followers=99999
--      WHERE id='e1220e96-0584-41de-817a-1d8f75bf425d';   -- Mid-tier
--     UPDATE public.kol_tiers SET min_followers=100000, max_followers=999999
--      WHERE id='26e8c7fb-e458-42c3-b44b-4aa7c0fd2cda';   -- Macro
-- =====================================================================

BEGIN;

DO $perbaikan$
DECLARE
  n int;
BEGIN
  -- Mid-tier: batas atas 99.999 -> 499.999
  UPDATE public.kol_tiers
     SET max_followers = 499999
   WHERE name = 'Mid-tier' AND min_followers = 50000;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'Mid-tier: % baris terpengaruh, seharusnya 1', n;
  END IF;

  -- Macro: batas bawah 100.000 -> 500.000
  UPDATE public.kol_tiers
     SET min_followers = 500000
   WHERE name = 'Macro' AND max_followers = 999999;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'Macro: % baris terpengaruh, seharusnya 1', n;
  END IF;

  RAISE NOTICE 'OK: ambang Mid-tier dan Macro diperbarui.';
END $perbaikan$;

-- ---------------------------------------------------------------------
-- Verifikasi 1: kelima ambang persis seperti kesepakatan
-- ---------------------------------------------------------------------
DO $verifikasi_nilai$
DECLARE
  n_benar int;
BEGIN
  SELECT count(*) INTO n_benar
  FROM public.kol_tiers
  WHERE (name, min_followers, max_followers) IN (
          ('Nano',      1000,     9999),
          ('Micro',    10000,    49999),
          ('Mid-tier', 50000,   499999),
          ('Macro',   500000,   999999),
          ('Mega',   1000000,     NULL))
     OR (name = 'Mega' AND min_followers = 1000000 AND max_followers IS NULL);

  IF n_benar <> 5 THEN
    RAISE EXCEPTION 'Ambang tier benar hanya % dari 5', n_benar;
  END IF;

  RAISE NOTICE 'OK: 5 ambang tier sesuai kesepakatan.';
END $verifikasi_nilai$;

-- ---------------------------------------------------------------------
-- Verifikasi 2: tidak ada celah maupun tumpang tindih antar-band.
--   Band harus bersambung: max baris ke-n + 1 = min baris ke-n+1.
-- ---------------------------------------------------------------------
DO $verifikasi_band$
DECLARE
  n_masalah int;
BEGIN
  SELECT count(*) INTO n_masalah
  FROM (
    SELECT max_followers,
           LEAD(min_followers) OVER (ORDER BY min_followers) AS min_berikutnya
    FROM public.kol_tiers
  ) x
  WHERE min_berikutnya IS NOT NULL
    AND (max_followers IS NULL OR max_followers + 1 <> min_berikutnya);

  IF n_masalah <> 0 THEN
    RAISE EXCEPTION 'Ada % batas band yang bercelah atau tumpang tindih', n_masalah;
  END IF;

  RAISE NOTICE 'OK: band tier bersambung tanpa celah/tumpang tindih.';
END $verifikasi_band$;

-- ---------------------------------------------------------------------
-- Verifikasi 3: satu followers_count tidak boleh cocok >1 tier.
--   Diuji pada nilai batas, bukan asumsi.
-- ---------------------------------------------------------------------
DO $verifikasi_batas$
DECLARE
  r        record;
  n_cocok  int;
  harapan  text;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      (999,        NULL),
      (1000,       'Nano'),
      (9999,       'Nano'),
      (10000,      'Micro'),
      (49999,      'Micro'),
      (50000,      'Mid-tier'),
      (499999,     'Mid-tier'),
      (500000,     'Macro'),
      (999999,     'Macro'),
      (1000000,    'Mega'),
      (685896635,  'Mega')
    ) AS v(followers, tier_diharapkan)
  LOOP
    SELECT count(*) INTO n_cocok
    FROM public.kol_tiers t
    WHERE r.followers >= t.min_followers
      AND (t.max_followers IS NULL OR r.followers <= t.max_followers);

    IF n_cocok > 1 THEN
      RAISE EXCEPTION 'followers % cocok dengan % tier sekaligus', r.followers, n_cocok;
    END IF;

    SELECT t.name INTO harapan
    FROM public.kol_tiers t
    WHERE r.followers >= t.min_followers
      AND (t.max_followers IS NULL OR r.followers <= t.max_followers)
    ORDER BY t.min_followers DESC LIMIT 1;

    IF harapan IS DISTINCT FROM r.tier_diharapkan THEN
      RAISE EXCEPTION 'followers % -> tier %, seharusnya %',
        r.followers, COALESCE(harapan, '(null)'), COALESCE(r.tier_diharapkan, '(null)');
    END IF;
  END LOOP;

  RAISE NOTICE 'OK: 11 nilai batas terpetakan ke tier yang benar.';
END $verifikasi_batas$;

COMMIT;
