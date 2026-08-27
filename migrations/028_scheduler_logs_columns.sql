-- 028_scheduler_logs_columns.sql
--
-- Melengkapi `public.scheduler_logs` untuk kebutuhan Scheduler Engine.
--
-- SATU TABEL, TANPA SCHEMA BARU
-- =============================
-- `public.scheduler_logs` adalah SATU-SATUNYA tempat penyimpanan aktivitas
-- scheduler. Tidak ada tabel log baru, tidak ada schema baru, dan tidak ada
-- view. Kolom yang dibutuhkan scheduler tapi belum ada ditambahkan langsung ke
-- tabel itu sebagai kolom NULLABLE, jadi:
--
--   * baris lama tidak tersentuh dan tetap sah;
--   * penulis lama (`post_pipeline` lewat `scrape_log.ScrapeLogger`) tidak
--     perlu diubah — kolom yang tidak diisi bernilai NULL;
--   * riwayat post_pipeline dan riwayat scheduler tetap di satu tempat,
--     dibedakan lewat `job_name` ('post_scrape' vs 'scheduled_scrape').
--
-- `records_synced` yang sudah ada tetap dipakai dan artinya tidak berubah;
-- `posts_saved` diisi dengan nilai yang sama supaya baris scheduler bisa
-- dibaca tanpa harus tahu sejarah penamaan kolom.
--
-- Semua perubahan aditif. Tidak ada perubahan tipe kolom dan tidak ada baris
-- yang dihapus.

BEGIN;

-- 1. Bersihkan sisa percobaan sebelumnya -------------------------------------
-- Iterasi awal migrasi ini sempat memasang `schedule.logs` sebagai view di atas
-- tabel ini. Pendekatan itu dibatalkan: penyimpanan log harus satu, dan
-- `public.scheduler_logs` yang dipakai langsung. Blok ini membuat migrasi tetap
-- benar dijalankan di database yang terlanjur memasangnya, dan tidak melakukan
-- apa-apa di database yang bersih.

DROP VIEW IF EXISTS schedule.logs;
DROP SCHEMA IF EXISTS schedule RESTRICT;

-- 2. Kolom tambahan yang dibutuhkan log scheduler ----------------------------

ALTER TABLE public.scheduler_logs
    ADD COLUMN IF NOT EXISTS username           text,
    ADD COLUMN IF NOT EXISTS actor              text,
    ADD COLUMN IF NOT EXISTS profiles_processed integer,
    ADD COLUMN IF NOT EXISTS posts_fetched      integer,
    ADD COLUMN IF NOT EXISTS posts_saved        integer,
    ADD COLUMN IF NOT EXISTS duplicates_skipped integer,
    ADD COLUMN IF NOT EXISTS duration_seconds   numeric(12, 3);

COMMENT ON COLUMN public.scheduler_logs.username IS
    'Username yang diproses. Redundan dengan kol_account_id, tapi tetap terisi '
    'supaya baris log bisa dibaca tanpa join dan tidak hilang artinya kalau '
    'akun dihapus dari kol_directory.';
COMMENT ON COLUMN public.scheduler_logs.actor IS
    'Actor Apify yang dipakai: apify/instagram-scraper atau clockworks/tiktok-scraper.';
COMMENT ON COLUMN public.scheduler_logs.duplicates_skipped IS
    'Post yang dikembalikan actor tapi TIDAK disimpan karena content_id-nya '
    'sudah ada di l0_raw untuk akun yang sama.';
COMMENT ON COLUMN public.scheduler_logs.duration_seconds IS
    'Lama satu cycle dalam detik. Ditulis penulis log, bukan dihitung view.';

-- 3. Indeks pembacaan --------------------------------------------------------
-- Log scheduler hampir selalu dibaca sebagai "cycle terakhir untuk job ini".
-- Tanpa indeks, tabel yang tumbuh tiap 5 menit memaksa sequential scan.

CREATE INDEX IF NOT EXISTS idx_scheduler_logs_job_started
    ON public.scheduler_logs (job_name, started_at DESC);

-- 4. Verifikasi --------------------------------------------------------------
-- Gagal di sini membatalkan seluruh migrasi.

DO $$
DECLARE
    kolom_kurang text;
    ada_schema   boolean;
BEGIN
    SELECT string_agg(c, ', ')
      INTO kolom_kurang
      FROM unnest(ARRAY[
            'username', 'actor', 'profiles_processed', 'posts_fetched',
            'posts_saved', 'duplicates_skipped', 'duration_seconds']) AS c
     WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name   = 'scheduler_logs'
               AND column_name  = c);

    IF kolom_kurang IS NOT NULL THEN
        RAISE EXCEPTION 'Kolom belum terbentuk di public.scheduler_logs: %', kolom_kurang;
    END IF;

    -- Tidak boleh ada schema/view logging tambahan yang tersisa.
    SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'schedule')
      INTO ada_schema;

    IF ada_schema THEN
        RAISE EXCEPTION 'Schema `schedule` masih ada; log harus hanya di public.scheduler_logs';
    END IF;

    -- Tabel tujuan harus benar-benar bisa ditulis-baca.
    PERFORM 1 FROM public.scheduler_logs LIMIT 1;

    RAISE NOTICE 'OK: 7 kolom aditif di public.scheduler_logs, tanpa schema/view tambahan.';
END $$;

COMMIT;
