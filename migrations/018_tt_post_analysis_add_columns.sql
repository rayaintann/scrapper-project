-- 018_tt_post_analysis_add_columns.sql
--
-- Menambahkan tiga kolom ke `feature.tt_post_analysis` yang selama ini hanya
-- dimiliki padanan Instagram-nya, padahal datanya tersedia lengkap di
-- `l1_silver.unified_post` untuk seluruh 91 video TikTok:
--
--     posted_at        timestamptz
--     media_type       varchar(255)
--     engagement_rate  numeric(9,4)
--
-- ============================================================================
-- KENAPA
-- ============================================================================
--
-- Audit Fase 1c menemukan `tt_post_analysis` tidak punya keempat kolom yang
-- `ig_post_analysis` punya: `posted_at`, `media_type`, `engagement_rate`, dan
-- `reach`. Tiga yang pertama BUKAN keterbatasan data -- ketiganya terisi
-- 91/91 (posted_at, media_type) dan 90/91 (engagement_rate) di sumber, dan
-- asset `tt_post_analysis` terpaksa membuangnya karena tidak ada tempat.
--
-- `reach` SENGAJA tidak ikut ditambahkan: `unified_post.reach` terisi 0 dari
-- 221 baris karena actor TikTok maupun Instagram tidak menyediakannya, jadi
-- kolomnya hanya akan menjadi kolom kosong permanen. Menambah kolom yang tidak
-- bisa diisi membuat skema terlihat lebih mampu daripada kenyataannya.
--
-- Sesudah migrasi ini, kedua tabel post bergrain sama dan berisi himpunan
-- fakta dasar yang sama, sehingga perbandingan lintas platform di dashboard
-- tidak perlu lagi menangani TikTok sebagai kasus khusus.
--
-- ============================================================================
-- PILIHAN TIPE -- MENYAMAI SUMBER DAN PADANAN INSTAGRAM
-- ============================================================================
--
--   kolom            sumber (unified_post)   ig_post_analysis    dipakai di sini
--   posted_at        timestamptz             timestamptz         timestamptz
--   media_type       varchar                 varchar(255)        varchar(255)
--   engagement_rate  numeric                 numeric(5,2)*       numeric(9,4)
--
--   * numeric(5,2) adalah tipe LAMA Instagram; migration 017 mengubahnya
--     menjadi numeric(9,4). Kolom TikTok di sini langsung memakai tipe yang
--     benar supaya tidak perlu di-ALTER dua kali.
--
-- posted_at -- `timestamptz`, sama seperti sumber dan Instagram. Rentang data
--   TikTok sekarang 2021-02-18 sampai 2026-08-20. Zona waktu ikut tersimpan,
--   jadi konversi ke WIB tetap bisa dilakukan di sisi baca -- seperti yang
--   sudah dipakai heatmap di asset engagement.
--
-- media_type -- `varchar(255)`, menyamai `ig_post_analysis.media_type` supaya
--   kedua tabel bisa di-UNION tanpa cast. Nilai TikTok saat ini hanya 'VIDEO'
--   (89) dan 'CAROUSEL' (2), panjang maksimum 8 karakter -- jadi 255 sangat
--   lapang. Sengaja tidak dibuat enum: nilainya berasal dari actor pihak
--   ketiga yang bisa menambah jenis baru tanpa memberi tahu, dan enum akan
--   membuat post jenis baru GAGAL masuk, bukan sekadar tampil apa adanya.
--
-- engagement_rate -- `numeric(9,4)`, alasannya sama persis dengan migration
--   017: skala 4 menyamai presisi sumber, 5 digit bulat memberi plafon
--   99.999,9999%. Nilai TikTok tertinggi sekarang 263,5992 -- tiga digit bulat,
--   jadi numeric(5,2) yang dipakai `tt_engagement_analysis` bahkan tidak
--   sanggup menampungnya tanpa di-clamp. Untuk TikTok, pembulatan ke 2 desimal
--   mengubah 90 dari 90 nilai dan menghancurkan 8 di antaranya menjadi 0,00.
--
-- ============================================================================
-- KEAMANAN
-- ============================================================================
--
--   * Ketiganya NULLABLE dan TANPA DEFAULT. Sejak PostgreSQL 11, ADD COLUMN
--     semacam ini hanya mengubah katalog -- tidak ada rewrite tabel, tidak ada
--     baris yang disentuh, dan 91 baris yang sudah ada tetap utuh dengan
--     ketiga kolom baru bernilai NULL sampai asset dijalankan ulang.
--   * Tidak ada view, rule, index, atau constraint yang perlu diubah
--     (diverifikasi lewat pg_depend dan pg_get_viewdef -- keduanya kosong).
--   * Tidak ada kolom lama yang di-DROP, di-RENAME, atau diubah tipenya.
--     Migrasi ini murni penambahan.
--   * Nama ketiga kolom belum terpakai di tabel ini -- dijaga di Langkah 0.
--
-- SETELAH MIGRASI INI: jalankan ulang asset `tt_post_analysis`. Versi asset
-- yang sudah diperbarui mengisi ketiga kolom lewat UPSERT dengan penugasan
-- langsung. Sebelum dijalankan, ketiganya NULL di seluruh 91 baris -- yang
-- artinya "belum diisi", bukan "tidak tersedia".
--
-- CAKUPAN: satu tabel, tiga kolom baru. Tidak ada tabel, kolom, data,
-- procedure, atau constraint lain yang disentuh.
--
-- Jalankan:
--   python apply_migration.py migrations/018_tt_post_analysis_add_columns.sql --dry-run --yes
--   python apply_migration.py migrations/018_tt_post_analysis_add_columns.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga. Batalkan kalau kolomnya sudah ada.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    n_sudah_ada int;
    n_kolom     int;
    n_baris     bigint;
BEGIN
    SELECT count(*) INTO n_sudah_ada
    FROM information_schema.columns
    WHERE table_schema = 'feature' AND table_name = 'tt_post_analysis'
      AND column_name IN ('posted_at', 'media_type', 'engagement_rate');

    IF n_sudah_ada > 0 THEN
        RAISE EXCEPTION '% dari 3 kolom target sudah ada di feature.tt_post_analysis -- '
                        'migrasi ini sudah pernah dijalankan sebagian atau seluruhnya.',
                        n_sudah_ada;
    END IF;

    SELECT count(*) INTO n_kolom FROM information_schema.columns
    WHERE table_schema = 'feature' AND table_name = 'tt_post_analysis';

    IF n_kolom <> 15 THEN
        RAISE EXCEPTION 'feature.tt_post_analysis punya % kolom, diharapkan 15 -- '
                        'strukturnya berbeda dari yang diaudit; periksa dulu.', n_kolom;
    END IF;

    SELECT count(*) INTO n_baris FROM feature.tt_post_analysis;
    RAISE NOTICE 'Penjaga lolos: % kolom, % baris, 0 dari 3 nama kolom baru terpakai.',
        n_kolom, n_baris;
END $$;

-- ---------------------------------------------------------------------------
-- Langkah 1 -- penambahan kolom. Nullable tanpa default: katalog saja.
-- ---------------------------------------------------------------------------
ALTER TABLE feature.tt_post_analysis
    ADD COLUMN posted_at       timestamptz,
    ADD COLUMN media_type      varchar(255),
    ADD COLUMN engagement_rate numeric(9,4);

-- ---------------------------------------------------------------------------
-- Langkah 2 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    n_kolom       int;
    n_baru        int;
    n_baris       bigint;
    n_tidak_null  bigint;
    n_idx         int;
    tipe_er       text;
    tipe_posted   text;
    tipe_media    text;
BEGIN
    SELECT count(*) INTO n_kolom FROM information_schema.columns
    WHERE table_schema = 'feature' AND table_name = 'tt_post_analysis';

    SELECT count(*) INTO n_baru FROM information_schema.columns
    WHERE table_schema = 'feature' AND table_name = 'tt_post_analysis'
      AND column_name IN ('posted_at', 'media_type', 'engagement_rate')
      AND is_nullable = 'YES' AND column_default IS NULL;

    SELECT format_type(atttypid, atttypmod) INTO tipe_er FROM pg_attribute
    WHERE attrelid = 'feature.tt_post_analysis'::regclass AND attname = 'engagement_rate';
    SELECT format_type(atttypid, atttypmod) INTO tipe_posted FROM pg_attribute
    WHERE attrelid = 'feature.tt_post_analysis'::regclass AND attname = 'posted_at';
    SELECT format_type(atttypid, atttypmod) INTO tipe_media FROM pg_attribute
    WHERE attrelid = 'feature.tt_post_analysis'::regclass AND attname = 'media_type';

    SELECT count(*),
           count(posted_at) + count(media_type) + count(engagement_rate)
      INTO n_baris, n_tidak_null
    FROM feature.tt_post_analysis;

    SELECT count(*) INTO n_idx FROM pg_indexes
    WHERE schemaname = 'feature' AND tablename = 'tt_post_analysis';

    IF n_kolom <> 18 THEN
        RAISE EXCEPTION 'Jumlah kolom %, seharusnya 18 (15 + 3)', n_kolom;
    END IF;
    IF n_baru <> 3 THEN
        RAISE EXCEPTION 'Kolom baru yang nullable-tanpa-default berjumlah %, seharusnya 3', n_baru;
    END IF;
    IF tipe_er <> 'numeric(9,4)' THEN
        RAISE EXCEPTION 'engagement_rate bertipe %, seharusnya numeric(9,4)', tipe_er;
    END IF;
    IF tipe_posted <> 'timestamp with time zone' THEN
        RAISE EXCEPTION 'posted_at bertipe %, seharusnya timestamptz', tipe_posted;
    END IF;
    IF tipe_media <> 'character varying(255)' THEN
        RAISE EXCEPTION 'media_type bertipe %, seharusnya varchar(255)', tipe_media;
    END IF;
    IF n_baris <> 91 THEN
        RAISE EXCEPTION 'Jumlah baris berubah menjadi % -- seharusnya tetap 91', n_baris;
    END IF;
    IF n_tidak_null <> 0 THEN
        RAISE EXCEPTION 'Ada % nilai tidak-NULL di kolom baru -- seharusnya 0; '
                        'migrasi ini tidak boleh mengisi data.', n_tidak_null;
    END IF;
    IF n_idx <> 2 THEN
        RAISE EXCEPTION 'Jumlah index %, seharusnya tetap 2', n_idx;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: % kolom, 3 kolom baru (%, %, %), '
                 '% baris utuh, kolom baru 100%% NULL, % index.',
                 n_kolom, tipe_posted, tipe_media, tipe_er, n_baris, n_idx;
    RAISE NOTICE 'Langkah berikutnya: jalankan ulang asset tt_post_analysis '
                 'untuk mengisi ketiga kolom baru.';
END $$;

COMMIT;
