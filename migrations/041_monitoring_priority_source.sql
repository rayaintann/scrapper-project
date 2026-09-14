-- 041_monitoring_priority_source.sql
--
-- HANYA KOMENTAR KOLOM. Tidak ada kolom baru, tidak ada tabel, tidak ada
-- perubahan tipe, tidak ada DROP, dan tidak satu baris data pun disentuh.
--
-- ============================================================================
-- KENAPA MIGRATION UNTUK KOMENTAR SAJA
-- ============================================================================
--
-- Sumber Monitoring Priority berpindah dari
-- `feature.*_engagement_analysis.engagement_rate` ke
-- `public.kol_directory.engagement_rate`. Kolomnya tidak berubah, nilainya
-- dihitung ulang asset seperti biasa -- tapi komentar kolom yang dipasang
-- migration 038 masih berbunyi "dibawa apa adanya dari
-- feature.*_engagement_analysis.engagement_rate".
--
-- Komentar yang membantah kodenya lebih berbahaya daripada tidak ada komentar
-- sama sekali, karena ia dipercaya: seseorang yang mengaudit angka priority
-- akan mencari penyebabnya di tabel yang salah. `COMMENT ON` adalah DDL, jadi
-- perbaikannya harus lewat migration meski tidak ada schema yang bergerak.
--
-- ============================================================================
-- KENAPA SUMBERNYA BERPINDAH
-- ============================================================================
--
-- Cakupan. `feature.*_engagement_analysis.engagement_rate` hanya terisi untuk
-- 38 akun; `kol_directory.engagement_rate` terisi untuk 1.736 dari 7.432 KOL
-- (23,4%), dan 1.012 di antaranya punya kartu. Priority yang hanya bisa
-- menjawab 38 akun tidak bisa dipakai memprioritaskan apa pun.
--
-- SATUANNYA SUDAH DIPERIKSA, bukan diasumsikan. Terhadap 28 akun yang punya
-- kedua nilai: 6,94 vs 16,15 · 2,75 vs 3,78 · 2,21 vs 1,81 · 2,10 vs 2,10.
-- Nilainya berbeda -- sampel dan metodenya memang berbeda -- tetapi skalanya
-- sama, keduanya persen. Tidak ada faktor 100 tersembunyi seperti yang ada
-- pada `kol_metric_daily.er_followers_daily` (fraksi) dan yang harus
-- dikonversi untuk Performance Stability.
--
-- AMBANGNYA TIDAK BERUBAH: >= 5% High, >= 2% Medium, sisanya Low, NULL tetap
-- NULL. Ketiganya sudah disetujui dan hidup di `metrics_thresholds.py`.
--
-- ROLLBACK
--   Kembalikan komentar lama, dan kembalikan sumber `monitoring_er_pct` di
--   gold_profile.py ke `v.engagement_rate`.
-- ============================================================================

BEGIN;

COMMENT ON COLUMN l2_gold.kol_profile_card.monitoring_er_pct IS
    'Engagement rate yang dipakai menentukan monitoring_priority, dibawa apa '
    'adanya dari public.kol_directory.engagement_rate (persen). Dipetakan ke '
    'grain kartu lewat kol_social_account. BUKAN sumber kebenaran ER yang '
    'bersaing dengan feature.*_engagement_analysis.engagement_rate -- hanya '
    'penyebut yang membuat label di sebelahnya bisa diaudit. Sumbernya '
    'DIPINDAHKAN migration 041; sebelumnya dari layer feature, yang hanya '
    'terisi untuk 38 akun.';

COMMENT ON COLUMN l2_gold.kol_profile_card.monitoring_priority IS
    'High/Medium/Low atas monitoring_er_pct: >= 5% High, >= 2% Medium, '
    'sisanya Low. Ambang final dan sudah disetujui; angkanya hidup di '
    'metrics_thresholds.py dan CASE-nya digenerate dari sana. NULL bila ER '
    'tidak diketahui -- NULL BUKAN Low.';

COMMENT ON COLUMN l2_gold.kol_profile_card.audience_quality_tier IS
    'High/Medium/Low atas audience_quality_score: >= 75 High, >= 50 Medium, '
    'sisanya Low. Ambang final dan sudah disetujui. Menilai KUALITAS AUDIENS, '
    'dan skornya tidak dihitung ulang di sini -- ia berasal dari '
    'feature.*_audience_analysis.audience_quality_score.';

COMMENT ON COLUMN l2_gold.kol_profile_card.performance_stability IS
    'High/Medium/Low Stability atas er_stddev_pp: <= 1 poin persen High, '
    '<= 3 Medium, sisanya Low. Ambang final dan sudah disetujui. Mengukur '
    'KONSISTENSI ER, bukan tingginya: ER yang rendah tapi rata tetap High '
    'Stability. NULL bila er_periods < 3 -- dua titik selalu tampak stabil.';

DO $verifikasi$
DECLARE
    n int;
BEGIN
    -- Tidak ada kolom yang boleh hilang atau bertambah oleh migration ini.
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('monitoring_er_pct', 'monitoring_priority',
                           'audience_quality_tier', 'audience_quality_score',
                           'performance_stability', 'er_stddev_pp', 'er_periods');
    IF n <> 7 THEN
        RAISE EXCEPTION 'Kolom terkait tinggal % dari 7 -- ada yang hilang', n;
    END IF;

    -- Sumber barunya harus benar-benar ada dan bertipe numerik.
    PERFORM 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'kol_directory'
        AND column_name = 'engagement_rate' AND data_type = 'numeric';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'public.kol_directory.engagement_rate tidak ada / bukan numeric';
    END IF;

    RAISE NOTICE 'OK: komentar diperbarui, tidak ada schema yang berubah.';
END $verifikasi$;

COMMIT;
