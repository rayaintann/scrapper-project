-- 040_growth_30d_projection.sql
--
-- Dua hal, keduanya soal Growth 30D:
--
--   1. KOREKSI KOMENTAR `projected_30d`. Artinya berubah, kolomnya tidak.
--   2. Satu kolom baru: `projected_followers_30d`.
--
-- Tidak ada tabel baru, tidak ada schema baru, tidak ada DROP, tidak ada
-- perubahan tipe, dan tidak satu baris pun dihapus.
--
-- ============================================================================
-- 1. ARTI `projected_30d` BERUBAH -- KOLOMNYA DIPAKAI ULANG
-- ============================================================================
--
-- Sebelum:  projected_30d = previous_followers + daily_growth * 30
--           -> untuk 100 -> 125 dalam 25 hari, hasilnya 130
--           -> artinya "jumlah follower 30 hari setelah snapshot SEBELUMNYA"
--
-- Sekarang: projected_30d = daily_growth * 30
--           -> untuk contoh yang sama, hasilnya 30
--           -> artinya "SELISIH follower yang diproyeksikan selama 30 hari"
--
-- Kolomnya SENGAJA dipakai ulang, bukan ditambah yang baru: dua kolom bernama
-- mirip untuk gagasan yang sama adalah cara tercepat membuat konsumen memakai
-- yang salah. Yang berubah hanya nilainya, dan nilai lama tidak perlu
-- dipertahankan -- seluruhnya dihitung ulang tiap kali asset kartu jalan.
--
-- Tipe `bigint` tetap memadai: selisih bisa NEGATIF (akun yang followernya
-- turun), dan bigint menampung negatif.
--
-- KOMENTAR KOLOMNYA WAJIB IKUT BERUBAH. Komentar 037 masih berbunyi
-- "BASELINE-nya previous_followers ... 100 -> 125 dalam 25 hari menghasilkan
-- 130, bukan 155" -- persis kebalikan dari yang benar sekarang. Komentar yang
-- membantah kodenya lebih berbahaya daripada tidak ada komentar sama sekali,
-- karena ia dipercaya.
--
-- ============================================================================
-- 2. KENAPA `projected_followers_30d` MENDAPAT KOLOM
-- ============================================================================
--
-- Nilainya hanya `followers_count + projected_30d` -- penjumlahan dua kolom
-- yang sudah ada di baris yang sama. Menurunkannya saat dibaca memang mungkin,
-- dan itu pertimbangan pertama yang diambil.
--
-- Yang membalikkannya: UI (Next.js) query Postgres LANGSUNG. Kalau nilainya
-- hanya diturunkan di db.py, UI harus menuliskan penjumlahannya sendiri untuk
-- bisa menampilkan, mengurutkan, dan memfilternya -- dan begitu titik acuan
-- proyeksi berubah lagi (sudah sekali berubah, seperti tercatat di atas), ada
-- DUA tempat yang harus ikut berubah, di dua repo berbeda. Satu kolom aditif
-- lebih murah daripada risiko itu.
--
-- Kolom ini diisi `gold_profile.py` dari CTE yang SAMA (`db.SQL_GROWTH_CTE`)
-- yang menghitung `daily_growth` dan `projected_30d`, jadi ketiganya tidak
-- mungkin bercerita berbeda.
--
-- ============================================================================
-- INI PROYEKSI, BUKAN PERTUMBUHAN 30 HARI YANG TERAMATI
-- ============================================================================
--
-- Jarak snapshot nyata di data sekarang 10-15 hari. Angka ini mengekstrapolasi
-- laju harian yang terukur ke 30 hari; ia tidak pernah menuntut snapshotnya
-- berjarak tepat 30 hari, dan tidak boleh dibaca sebagai pertumbuhan yang
-- benar-benar terjadi selama 30 hari. Komentar kolomnya menyebutkan itu.
--
-- ROLLBACK
--   ALTER TABLE l2_gold.kol_profile_card DROP COLUMN projected_followers_30d;
--   lalu kembalikan rumus lama di db.SQL_GROWTH_CTE bila memang diinginkan.
-- ============================================================================

BEGIN;

ALTER TABLE l2_gold.kol_profile_card
    ADD COLUMN IF NOT EXISTS projected_followers_30d bigint;

COMMENT ON COLUMN l2_gold.kol_profile_card.projected_30d IS
    'SELISIH follower yang diproyeksikan selama 30 hari: daily_growth * 30. '
    'BUKAN jumlah follower absolut, dan BUKAN pertumbuhan 30 hari yang '
    'teramati -- jarak snapshot nyata 10-15 hari, dan angka ini '
    'mengekstrapolasi laju hariannya. Untuk 100 -> 125 dalam 25 hari: '
    'daily_growth 1, projected_30d 30. Boleh negatif. NULL bila daily_growth '
    'NULL. Arti kolom ini DIUBAH migration 040; sebelumnya ia berisi '
    'previous_followers + daily_growth * 30.';

COMMENT ON COLUMN l2_gold.kol_profile_card.projected_followers_30d IS
    'followers_count + projected_30d -- proyeksi jumlah follower 30 hari dari '
    'snapshot SEKARANG. Untuk 100 -> 125 dalam 25 hari: 125 + 30 = 155. '
    'NULL bila daily_growth atau followers_count NULL.';

COMMENT ON COLUMN l2_gold.kol_profile_card.daily_growth IS
    'Follower per hari antar dua snapshot: (followers_count - '
    'previous_followers) / days_between. Bukan persen. days_between memakai '
    'jarak NYATA antar snapshot, tidak pernah diasumsikan 30. NULL bila belum '
    'ada snapshot pembanding, previous_followers = 0, atau days_between <= 0.';

COMMENT ON COLUMN l2_gold.kol_profile_card.post_frequency_monthly IS
    'post_frequency_count / observation_days * 30 -- SATU-SATUNYA satuan Post '
    'Frequency yang ditampilkan, sesuai kesepakatan. Tidak ada varian mingguan '
    'maupun tahunan. NULL bila observation_days <= 0 atau tidak ada post valid.';

DO $verifikasi$
DECLARE
    n int;
BEGIN
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name = 'projected_followers_30d' AND is_nullable = 'YES';
    IF n <> 1 THEN
        RAISE EXCEPTION 'projected_followers_30d tidak terpasang sebagai nullable';
    END IF;

    -- Kolom Growth dan Post Frequency yang sudah ada harus utuh: migration ini
    -- mengubah ARTI satu kolom dan menambah satu, bukan mengganti apa pun.
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('followers_growth','daily_growth','projected_30d',
                           'previous_followers','days_between',
                           'post_frequency_monthly','post_frequency_count',
                           'post_frequency_daily','observation_days',
                           'post_frequency_reliability');
    IF n <> 10 THEN
        RAISE EXCEPTION 'Kolom Growth/Post Frequency tinggal % dari 10', n;
    END IF;

    RAISE NOTICE 'OK: projected_followers_30d terpasang; komentar diperbarui.';
END $verifikasi$;

COMMIT;
