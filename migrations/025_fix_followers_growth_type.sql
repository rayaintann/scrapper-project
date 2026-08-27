-- 025_fix_followers_growth_type.sql
--
-- Membetulkan TIPE kolom `followers_growth` di l2_gold.kol_profile_card:
-- `bigint` -> `numeric`, supaya nilai persen dari L1 bisa dibawa apa adanya.
--
-- Hanya SATU kolom di SATU tabel yang disentuh. l1_silver, feature,
-- l0_harmonization, kol_metric_daily, dan kol_metric_monthly tidak berubah.
--
-- ============================================================================
-- KENAPA -- BUKAN SEKADAR KERAPIAN TIPE
-- ============================================================================
--
-- `l1_silver.unified_profile.followers_growth` bertipe `numeric` dan berisi
-- PERSEN, dihitung oleh `l1_silver.sp_build_unified_profile()`:
--
--     (followers_kini - followers_sebelumnya) / followers_sebelumnya * 100
--
-- Sedangkan kolom tujuan di l2_gold bertipe `bigint`, yang menyiratkan JUMLAH
-- ORANG. Menyalin persen ke bigint bukan sekadar kehilangan desimal -- untuk
-- data yang ada sekarang metriknya HILANG SAMA SEKALI.
--
-- Diukur pada 22 baris L1 yang sudah terisi (snapshot kedua 2026-08-24):
--
--     rentang nilai     : -0,0510% s.d. +0,9174%
--     seluruh 22 nilai  : ada di antara -1% dan +1%
--     kalau di-cast     : 20 dari 22 jadi 0, sisanya jadi 1
--
--     pojoksatu.id  tiktok      +0,9174%  ->  1
--     hesfinatia    tiktok      +0,6711%  ->  1
--     ibnuwardani   tiktok      +0,2865%  ->  0
--     cristiano     instagram   +0,0637%  ->  0
--     isyanasarasvati instagram -0,0510%  ->  0
--
-- Jadi `bigint` akan melaporkan "tidak ada pertumbuhan" untuk 20 akun yang
-- followers-nya benar-benar bergerak, dan menghapus tanda minus pada akun yang
-- justru turun. Perubahan tipe ini syarat supaya angkanya bermakna.
--
-- Perilaku ini sudah diantisipasi di migrations/FEATURE_METRICS_BACKLOG.md §10:
--     "kolom L1 bertipe numeric dan berisi persen, sedangkan kolom
--      followers_growth di tiga tabel l2_gold bertipe bigint yang menyiratkan
--      jumlah orang. Menyalin apa adanya akan memotong 5,2% jadi 5."
--
-- ============================================================================
-- KENAPA `numeric` TANPA PRESISI
-- ============================================================================
--
-- Mengikuti kolom sumbernya di l1_silver.unified_profile yang juga `numeric`
-- polos. Membatasi jadi `numeric(9,4)` di L2 akan membuat L2 memotong nilai
-- yang L1 simpan utuh -- L2 tidak boleh lebih sempit dari sumbernya.
--
-- ============================================================================
-- KENAPA HANYA kol_profile_card
-- ============================================================================
--
-- `kol_metric_daily` dan `kol_metric_monthly` juga punya `followers_growth
-- bigint`, tapi grain keduanya digerakkan POST (metric_date dari posted_at),
-- bukan profil. Growth adalah milik akun/profil, bukan milik post, jadi
-- kolomnya di dua tabel itu tetap tidak diisi dan tipenya sengaja TIDAK
-- diubah -- mengubahnya akan menyiratkan rencana mengisi yang tidak ada.
--
-- Keduanya juga sudah berisi data (160 + 53 baris); ALTER TYPE di sana berarti
-- rewrite tabel tanpa alasan. `kol_profile_card` masih 0 baris, jadi perubahan
-- ini gratis dan tidak mungkin merusak data.
--
-- ============================================================================
-- AMAN DIULANG
-- ============================================================================
--
-- Penjaga di bawah keluar diam-diam kalau tipenya sudah `numeric`, jadi
-- migrasi ini boleh dijalankan berkali-kali.

BEGIN;

DO $penjaga$
DECLARE
    tipe_kini text;
    n_baris   bigint;
BEGIN
    SELECT data_type INTO tipe_kini
    FROM information_schema.columns
    WHERE table_schema = 'l2_gold'
      AND table_name   = 'kol_profile_card'
      AND column_name  = 'followers_growth';

    IF tipe_kini IS NULL THEN
        RAISE EXCEPTION 'l2_gold.kol_profile_card.followers_growth tidak ditemukan -- '
                        'terapkan migration 023 dulu.';
    END IF;

    IF tipe_kini = 'numeric' THEN
        RAISE NOTICE 'Tipe sudah numeric -- tidak ada yang perlu diubah.';
        RETURN;
    END IF;

    -- Menolak mengubah tipe kalau tabelnya ternyata sudah berisi: nilai bigint
    -- yang terlanjur masuk sudah kehilangan desimalnya dan tidak bisa
    -- dipulihkan oleh cast. Lebih baik gagal keras daripada mengawetkan angka
    -- yang sudah rusak.
    SELECT count(*) INTO n_baris FROM l2_gold.kol_profile_card;
    IF n_baris <> 0 THEN
        RAISE EXCEPTION 'kol_profile_card sudah berisi % baris. Nilai bigint yang '
                        'sudah tersimpan tidak bisa dipulihkan dengan cast -- '
                        'kosongkan tabel lebih dulu, lalu jalankan ulang.', n_baris;
    END IF;

    ALTER TABLE l2_gold.kol_profile_card
        ALTER COLUMN followers_growth TYPE numeric;

    RAISE NOTICE 'followers_growth: % -> numeric.', tipe_kini;
END $penjaga$;

COMMENT ON COLUMN l2_gold.kol_profile_card.followers_growth IS
    'Pertumbuhan followers dalam PERSEN, dibawa apa adanya dari '
    'l1_silver.unified_profile.followers_growth pada snapshot yang sama dengan '
    'profile_snapshot_date. Perbandingannya snapshot-ke-snapshot (bukan jendela '
    'waktu tetap): (followers_kini - followers_sebelumnya) / followers_sebelumnya '
    '* 100. NULL kalau akun baru punya satu snapshot. Satuannya PERSEN, bukan '
    'jumlah orang -- karena itu numeric, bukan bigint.';

-- Verifikasi akhir: kalau ALTER di atas tidak berlaku, transaksi dibatalkan.
DO $verifikasi$
DECLARE
    tipe_akhir text;
BEGIN
    SELECT data_type INTO tipe_akhir
    FROM information_schema.columns
    WHERE table_schema = 'l2_gold'
      AND table_name   = 'kol_profile_card'
      AND column_name  = 'followers_growth';

    IF tipe_akhir <> 'numeric' THEN
        RAISE EXCEPTION 'Verifikasi gagal: tipe akhir % -- diharapkan numeric.', tipe_akhir;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: followers_growth bertipe numeric.';
END $verifikasi$;

COMMIT;
