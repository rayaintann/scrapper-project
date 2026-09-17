-- 050_cleanup_roster_rate_card.sql
--
-- Membersihkan Rate Card yang sudah terlanjur masuk DB KOL dari roster.
--
-- !! JANGAN DITERAPKAN TANPA PERSETUJUAN. Jalankan --dry-run dulu. !!
--
-- ============================================================================
-- CAKUPAN (audit read-only 17 Sep 2026)
-- ============================================================================
--
--   l0_harmonization.instagram_rate_card   3.878 baris  source='uploader'
--   l0_harmonization.tiktok_rate_card      4.978 baris  source='uploader'
--   l1_silver.unified_rate_card            8.856 baris  source='harmonization',
--                                                       source_table = dua tabel di atas
--
--   Seluruh isi ketiga tabel berasal dari l0_raw.kol_roster_import. Tidak ada
--   FK, view, atau trigger lain yang bergantung pada ketiganya. Sumber sah
--   lain (l0_extra.*_rate_card) 0 baris.
--
--   l0_raw.kol_roster_import TIDAK disentuh: itu data mentah upload, dan kolom
--   harganya tetap ada sebagai arsip. Yang dihentikan adalah alirannya
--   (migrasi 048).
--
-- ============================================================================
-- PEMBACA YANG TERDAMPAK SETELAH L1 KOSONG
-- ============================================================================
--
--   autometric kolMeasured.ts:179-184     Rate Card header + Add to Campaign
--   autometric kolDirectory.ts:688, :784  rateFrom / rateCount / filter maxRate
--   L2 kol_profile_card.rate_card_*       sudah NULL, tidak berubah
--
-- Hanya baris ber-source roster yang dihapus, dan migrasi dibatalkan kalau
-- ada baris dari sumber lain atau kalau jumlahnya tidak sesuai audit. Kalau
-- data berubah sejak audit, perbarui angka di penjaga setelah diperiksa ulang.
--
-- Menjalankan (SETELAH 048 dan setelah disetujui):
--   python apply_migration.py migrations/050_cleanup_roster_rate_card.sql --dry-run --yes
--   python apply_migration.py migrations/050_cleanup_roster_rate_card.sql --yes

BEGIN;

DO $penjaga$
DECLARE
    v_src      text;
    n_ig       bigint;
    n_tt       bigint;
    n_l1       bigint;
    n_ig_lain  bigint;
    n_tt_lain  bigint;
    n_l1_lain  bigint;
BEGIN
    -- 048 harus sudah terpasang, supaya data tidak masuk lagi setelah dibersihkan
    SELECT p.prosrc INTO v_src
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization' AND p.proname = 'sp_sync_roster_rate_card';
    IF v_src IS NULL OR v_src NOT LIKE '%dinonaktifkan%' THEN
        RAISE EXCEPTION 'Migrasi 048 belum diterapkan: sp_sync_roster_rate_card masih aktif.';
    END IF;

    SELECT count(*) FILTER (WHERE source = 'uploader'
                              AND source_table = 'l0_raw.kol_roster_import'),
           count(*) FILTER (WHERE source IS DISTINCT FROM 'uploader'
                               OR source_table IS DISTINCT FROM 'l0_raw.kol_roster_import')
      INTO n_ig, n_ig_lain
    FROM l0_harmonization.instagram_rate_card;

    SELECT count(*) FILTER (WHERE source = 'uploader'
                              AND source_table = 'l0_raw.kol_roster_import'),
           count(*) FILTER (WHERE source IS DISTINCT FROM 'uploader'
                               OR source_table IS DISTINCT FROM 'l0_raw.kol_roster_import')
      INTO n_tt, n_tt_lain
    FROM l0_harmonization.tiktok_rate_card;

    SELECT count(*) FILTER (WHERE source = 'harmonization'
                              AND source_table IN ('l0_harmonization.instagram_rate_card',
                                                   'l0_harmonization.tiktok_rate_card')),
           count(*) FILTER (WHERE source IS DISTINCT FROM 'harmonization'
                               OR source_table NOT IN ('l0_harmonization.instagram_rate_card',
                                                       'l0_harmonization.tiktok_rate_card')
                               OR source_table IS NULL)
      INTO n_l1, n_l1_lain
    FROM l1_silver.unified_rate_card;

    RAISE NOTICE 'Akan dihapus: harmonization IG %, TT %, L1 %. Baris sumber lain: %, %, %.',
                 n_ig, n_tt, n_l1, n_ig_lain, n_tt_lain, n_l1_lain;

    IF n_ig_lain + n_tt_lain + n_l1_lain > 0 THEN
        RAISE EXCEPTION 'Ada baris rate card dari sumber selain roster; periksa dulu sebelum membersihkan.';
    END IF;
    IF (n_ig, n_tt, n_l1) IS DISTINCT FROM (3878::bigint, 4978::bigint, 8856::bigint) THEN
        RAISE EXCEPTION 'Jumlah baris berbeda dari audit (3.878 / 4.978 / 8.856); audit ulang dulu.';
    END IF;
END $penjaga$;

-- L1 dulu: isinya turunan harmonization.
DELETE FROM l1_silver.unified_rate_card
 WHERE source = 'harmonization'
   AND source_table IN ('l0_harmonization.instagram_rate_card',
                        'l0_harmonization.tiktok_rate_card');

DELETE FROM l0_harmonization.instagram_rate_card
 WHERE source = 'uploader' AND source_table = 'l0_raw.kol_roster_import';

DELETE FROM l0_harmonization.tiktok_rate_card
 WHERE source = 'uploader' AND source_table = 'l0_raw.kol_roster_import';

DO $verif$
DECLARE
    n_l1   bigint;
    n_harm bigint;
    n_l2   bigint;
BEGIN
    SELECT count(*) INTO n_l1 FROM l1_silver.unified_rate_card;
    SELECT (SELECT count(*) FROM l0_harmonization.instagram_rate_card)
         + (SELECT count(*) FROM l0_harmonization.tiktok_rate_card) INTO n_harm;
    SELECT count(*) INTO n_l2 FROM l2_gold.kol_profile_card
     WHERE rate_card IS NOT NULL OR rate_card_min_fee IS NOT NULL
        OR rate_card_max_fee IS NOT NULL OR rate_card_post_types IS NOT NULL
        OR rate_card_currency IS NOT NULL;

    IF n_l1 <> 0 OR n_harm <> 0 THEN
        RAISE EXCEPTION 'Pembersihan tidak tuntas: L1 %, harmonization %.', n_l1, n_harm;
    END IF;
    IF n_l2 <> 0 THEN
        RAISE EXCEPTION 'L2 kol_profile_card.rate_card_* tidak NULL di % baris.', n_l2;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: harmonization dan L1 rate card kosong, L2 rate_card_* NULL.';
END $verif$;

COMMIT;
