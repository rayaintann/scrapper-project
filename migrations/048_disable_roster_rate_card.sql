-- 048_disable_roster_rate_card.sql
--
-- Rate Card TIDAK BOLEH masuk DB KOL dari roster. Procedure yang selama ini
-- memindahkan harga roster ke harmonization dinonaktifkan.
--
-- ============================================================================
-- KEPUTUSAN (17 Sep 2026)
-- ============================================================================
--
--   * Requirement final: harga di l0_raw.kol_roster_import bukan sumber Rate
--     Card. Alur roster -> l0_harmonization.{instagram,tiktok}_rate_card ->
--     l1_silver.unified_rate_card dihentikan.
--   * L2 kol_profile_card.rate_card_* tetap NULL (gold_profile.py tidak
--     menulisnya, dan migrasi ini tidak membuat writer baru).
--   * Tidak ada dummy Rate Card.
--
-- ============================================================================
-- WRITER YANG DITEMUKAN (audit read-only 17 Sep 2026)
-- ============================================================================
--
--   l0_harmonization.sp_sync_roster_rate_card()   roster -> harmonization
--       Tidak dipanggil oleh kode mana pun (Dagster, Python, autometric,
--       sp_sync_all). Dua kali dijalankan manual lewat CALL (sync_log
--       2026-08-13 dan 2026-09-13 10:17 UTC).
--   l1_silver.sp_sync_unified_rate_card()          harmonization -> L1
--   l1_silver.sp_build_unified_rate_card()         harmonization -> L1
--       Keduanya hanya menyalin isi harmonization. Setelah harmonization
--       dibersihkan, keduanya tidak menghasilkan apa pun, jadi dibiarkan.
--   l0_harmonization.sp_sync_{instagram,tiktok}_rate_card()
--       Sumbernya l0_extra.*_rate_card (bukan roster, 0 baris). Dibiarkan.
--
-- ============================================================================
-- YANG DILAKUKAN MIGRASI INI
-- ============================================================================
--
--   sp_sync_roster_rate_card() diganti tubuhnya menjadi RAISE EXCEPTION.
--   Signature dipertahankan (bukan DROP) supaya CALL lama gagal dengan pesan
--   yang jelas, bukan "procedure does not exist" yang bisa disalahartikan.
--
--   Migrasi ini TIDAK menghapus data. Baris yang sudah terlanjur masuk
--   (harmonization 3.878 + 4.978, L1 8.856) dibersihkan oleh migrasi 050,
--   yang dijalankan terpisah setelah disetujui.
--
-- Menjalankan:
--   python apply_migration.py migrations/048_disable_roster_rate_card.sql --dry-run --yes
--   python apply_migration.py migrations/048_disable_roster_rate_card.sql --yes

BEGIN;

DO $penjaga$
DECLARE
    n_proc int;
BEGIN
    SELECT count(*) INTO n_proc
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization' AND p.proname = 'sp_sync_roster_rate_card';
    IF n_proc <> 1 THEN
        RAISE EXCEPTION 'Diharapkan tepat 1 procedure sp_sync_roster_rate_card, ditemukan %.', n_proc;
    END IF;
END $penjaga$;

CREATE OR REPLACE PROCEDURE l0_harmonization.sp_sync_roster_rate_card()
LANGUAGE plpgsql
AS $procedure$
BEGIN
    RAISE EXCEPTION 'sp_sync_roster_rate_card dinonaktifkan (migrasi 048): '
                    'Rate Card tidak boleh masuk DB KOL dari l0_raw.kol_roster_import.';
END;
$procedure$;

COMMENT ON PROCEDURE l0_harmonization.sp_sync_roster_rate_card() IS
    'DINONAKTIFKAN (migrasi 048). Rate Card tidak boleh berasal dari roster; '
    'procedure ini selalu melempar exception.';

DO $verif$
DECLARE
    src text;
BEGIN
    SELECT p.prosrc INTO src
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'l0_harmonization' AND p.proname = 'sp_sync_roster_rate_card';

    IF src NOT LIKE '%RAISE EXCEPTION%' OR src LIKE '%kol_roster_import r%' THEN
        RAISE EXCEPTION 'sp_sync_roster_rate_card belum dinonaktifkan.';
    END IF;

    RAISE NOTICE 'Verifikasi lolos: sp_sync_roster_rate_card selalu melempar exception.';
END $verif$;

COMMIT;
