-- 022_create_kol_metric_monthly.sql
--
-- Tabel L2 Gold kedua: rekap BULANAN per KOL per platform (SCRUM-516).
-- Sumbernya HANYA `l2_gold.kol_metric_daily` -- tidak mengagregasi ulang dari
-- l1_silver, sesuai backlog ("bikin tabel kol_metric_monthly di gold dari
-- gold.kol_metric_daily").
--
-- Tidak ada tabel, kolom, atau data lain yang disentuh. l1_silver, feature,
-- l0_harmonization, dan kol_metric_daily sendiri tidak berubah sama sekali.
--
-- ============================================================================
-- GRAIN
-- ============================================================================
--
--     UNIQUE (social_account_id, platform, month_start)
--
-- `month_start` = date_trunc('month', metric_date)::date, yaitu tanggal 1 tiap
-- bulan. Dengan data sekarang: 53 baris dari 160 baris harian, 23 akun,
-- rentang 2021-02 s.d. 2026-08.
--
-- Pola kolom dan constraint menyalin `kol_metric_daily`: PRIMARY KEY (id),
-- UNIQUE pada grain, FK ke public.social_account, dua timestamp, dan metrik
-- NULLABLE TANPA DEFAULT 0 supaya NULL bisa berarti "tidak diketahui".
--
-- Dimensi kalender (year, month, month_year, quarter, year_quarter) mengikuti
-- kedua referensi monthly di socmed_report -- keduanya menyimpan lima kolom itu
-- supaya dashboard tidak perlu menurunkan ulang dari month_start.
--
-- ============================================================================
-- engagement_for_er_sum -- KOLOM YANG MEMPERBAIKI CACAT NYATA
-- ============================================================================
--
-- `SUM(engagement_sum) / SUM(followers_denom_sum)` yang naif SALAH, karena
-- pembilang dan penyebut mencakup himpunan hari yang berbeda: engagement ada
-- untuk semua hari yang punya sampel, tapi denominator hanya ada untuk hari
-- yang follower-nya diketahui (carry-forward).
--
-- Terbukti pada data sekarang -- cristiano, Agustus 2026:
--
--     tanggal      posts_in_sample  engagement_sum   followers_denom_sum
--     2026-08-05         1             24.368.955          NULL
--     2026-08-12         1             31.144.645          NULL
--     2026-08-14         1             12.267.307      679.264.838
--     2026-08-16         0                  NULL           NULL
--
--     naif    : 67.780.907 / 679.264.838 = 0,0998  (pembilang 3 hari, penyebut 1)
--     selaras : 12.267.307 / 679.264.838 = 0,0181
--
-- Salah 5,5 kali lipat, dan 11 dari 18 bulan ber-ER terdampak. Karena itu
-- pembilangnya disimpan terpisah:
--
--     engagement_for_er_sum = SUM(engagement_sum)
--                             FILTER (WHERE followers_denom_sum IS NOT NULL)
--     er_followers_monthly  = engagement_for_er_sum / followers_denom_sum
--
-- `engagement_sum` tetap melaporkan total sebenarnya; `engagement_for_er_sum`
-- adalah bagian yang sebanding dengan penyebutnya. Keduanya perlu ada.
--
-- ============================================================================
-- KOLOM YANG SENGAJA DIBUAT TAPI AKAN NULL
-- ============================================================================
--
--   reach_sum, er_reach_monthly, reposts_sum, followers_growth
--
-- Keempatnya 100% NULL di `kol_metric_daily`, jadi apa pun agregatnya tetap
-- NULL. Dibuat sekarang supaya skema tidak perlu di-ALTER saat Insights API
-- menyala. Pengisinya tidak menulis keempatnya sama sekali.
--
-- TIDAK dibuat, dan itu disengaja:
--   kolom month-over-month (*_inc / LAG)  Data kita rata-rata hanya 2,9-3,3
--       hari aktif per bulan dan bulannya TIDAK berurutan, jadi LAG() akan
--       membandingkan Agustus dengan bulan tersedia sebelumnya yang bisa saja
--       beberapa bulan lebih awal, lalu menyebutnya "perubahan bulan lalu".
--   channel_reach   Referensi socmed_report sendiri mengisinya NULL::bigint
--                   hard-coded.
--   profile_visit_month, brand_name_display, main_brand_id
--
-- ============================================================================
-- KEAMANAN
-- ============================================================================
--
--   * Hanya CREATE TABLE + 1 UNIQUE + 1 FK + 2 index. Tidak ada DROP/ALTER.
--   * `l2_gold` saat ini berisi tepat 1 tabel (kol_metric_daily) dan nama
--     `kol_metric_monthly` belum terpakai -- dijaga di Langkah 0.
--   * Tabel dibuat KOSONG; pengisian adalah tugas asset Dagster.
--   * kol_metric_daily dijaga tetap 160 baris di Langkah 2.
--
-- Jalankan:
--   python apply_migration.py migrations/022_create_kol_metric_monthly.sql --dry-run --yes
--   python apply_migration.py migrations/022_create_kol_metric_monthly.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga.
-- ---------------------------------------------------------------------------
DO $penjaga$
DECLARE
    n_daily  int;
    n_nama   int;
    n_baris  bigint;
BEGIN
    SELECT count(*) INTO n_daily FROM information_schema.tables
    WHERE table_schema = 'l2_gold' AND table_name = 'kol_metric_daily';
    IF n_daily <> 1 THEN
        RAISE EXCEPTION 'l2_gold.kol_metric_daily tidak ditemukan -- ia sumber '
                        'satu-satunya tabel ini. Terapkan migration 021 dulu.';
    END IF;

    SELECT count(*) INTO n_nama FROM information_schema.tables
    WHERE table_name = 'kol_metric_monthly';
    IF n_nama <> 0 THEN
        RAISE EXCEPTION 'Nama kol_metric_monthly sudah dipakai di % tempat.', n_nama;
    END IF;

    SELECT count(*) INTO n_baris FROM l2_gold.kol_metric_daily;
    IF n_baris = 0 THEN
        RAISE EXCEPTION 'kol_metric_daily kosong -- tidak ada yang bisa diagregasi.';
    END IF;

    RAISE NOTICE 'Penjaga lolos: sumber kol_metric_daily ada (% baris), '
                 'nama belum terpakai.', n_baris;
END $penjaga$;

-- ---------------------------------------------------------------------------
-- Langkah 1 -- tabel.
-- ---------------------------------------------------------------------------
CREATE TABLE l2_gold.kol_metric_monthly (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- grain -------------------------------------------------------------
    social_account_id       uuid        NOT NULL,
    platform                varchar(30) NOT NULL,
    month_start             date        NOT NULL,   -- tanggal 1 bulan tsb

    -- dimensi kalender: turunan deterministik dari month_start ------------
    year                    integer     NOT NULL,
    month                   integer     NOT NULL,
    month_year              varchar(7)  NOT NULL,   -- 'YYYY-MM'
    quarter                 integer     NOT NULL,
    year_quarter            varchar(6)  NOT NULL,   -- 'YYYYQn'

    -- hitungan: selalu punya jawaban --------------------------------------
    active_days             bigint      NOT NULL DEFAULT 0,  -- hari ber-post
    post_count              bigint      NOT NULL DEFAULT 0,
    posts_in_sample         bigint      NOT NULL DEFAULT 0,

    -- komponen additive: NULL = tidak diketahui, BUKAN nol -----------------
    likes_sum               bigint,
    comments_sum            bigint,
    shares_sum              bigint,     -- TikTok saja; IG NULL
    saves_sum               bigint,     -- TikTok saja; IG NULL
    views_sum               bigint,
    engagement_sum          bigint,     -- total sebenarnya sebulan
    engagement_public_sum   bigint,

    -- follower & engagement rate -------------------------------------------
    followers_eom           bigint,     -- snapshot HARI TERAKHIR yang ada di bulan itu
    followers_denom_sum     bigint,
    engagement_for_er_sum   bigint,     -- pembilang ER, selaras dengan penyebut
    er_followers_monthly    numeric(12,8),  -- FRAKSI 0..1, bukan persen

    -- sengaja dibiarkan NULL sampai sumbernya ada ---------------------------
    reach_sum               bigint,
    er_reach_monthly        numeric(12,8),
    reposts_sum             bigint,
    followers_growth        bigint,

    -- jejak -----------------------------------------------------------------
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_kol_metric_monthly
        UNIQUE (social_account_id, platform, month_start),
    CONSTRAINT fk_kol_metric_monthly_social_account
        FOREIGN KEY (social_account_id) REFERENCES public.social_account(id)
);

-- Meniru ix_kmd_* di kol_metric_daily: pola query dashboard adalah
-- "satu KOL, rentang bulan" dan "satu KOL, satu platform, rentang bulan".
CREATE INDEX ix_kmm_account_month
    ON l2_gold.kol_metric_monthly (social_account_id, month_start);
CREATE INDEX ix_kmm_account_platform_month
    ON l2_gold.kol_metric_monthly (social_account_id, platform, month_start);

COMMENT ON TABLE l2_gold.kol_metric_monthly IS
    'Rekap bulanan per KOL per platform. Grain (social_account_id, platform, '
    'month_start). Diagregasi HANYA dari l2_gold.kol_metric_daily, bukan dari '
    'l1_silver. NULL berarti sumbernya tidak tersedia, bukan nol. '
    'er_followers_monthly adalah FRAKSI 0..1 dan dihitung dari '
    'engagement_for_er_sum / followers_denom_sum -- BUKAN rata-rata ER harian.';

COMMENT ON COLUMN l2_gold.kol_metric_monthly.engagement_for_er_sum IS
    'SUM(engagement_sum) FILTER (WHERE followers_denom_sum IS NOT NULL). '
    'Pembilang ER yang selaras dengan penyebutnya: hanya hari yang follower-nya '
    'diketahui. Berbeda dari engagement_sum yang melaporkan total sebenarnya.';

COMMENT ON COLUMN l2_gold.kol_metric_monthly.followers_eom IS
    'followers_at_post_date dari baris harian TERAKHIR dalam bulan itu '
    '(DISTINCT ON ... ORDER BY metric_date DESC). Bukan rata-rata.';

-- ---------------------------------------------------------------------------
-- Langkah 2 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $verif$
DECLARE
    n_kolom    int;
    n_baris    bigint;
    n_uq       int;
    n_fk       int;
    n_idx      int;
    n_notnull  int;
    tipe_er    text;
    n_daily    bigint;
    n_tabel    int;
BEGIN
    SELECT count(*) INTO n_kolom FROM information_schema.columns
    WHERE table_schema = 'l2_gold' AND table_name = 'kol_metric_monthly';

    SELECT count(*) INTO n_baris FROM l2_gold.kol_metric_monthly;

    SELECT count(*) INTO n_uq FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'l2_gold' AND t.relname = 'kol_metric_monthly' AND c.contype = 'u'
      AND pg_get_constraintdef(c.oid) = 'UNIQUE (social_account_id, platform, month_start)';

    SELECT count(*) INTO n_fk FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'l2_gold' AND t.relname = 'kol_metric_monthly' AND c.contype = 'f'
      AND pg_get_constraintdef(c.oid) LIKE '%REFERENCES social_account(id)%';

    SELECT count(*) INTO n_idx FROM pg_indexes
    WHERE schemaname = 'l2_gold' AND tablename = 'kol_metric_monthly';

    SELECT count(*) INTO n_notnull FROM information_schema.columns
    WHERE table_schema = 'l2_gold' AND table_name = 'kol_metric_monthly'
      AND is_nullable = 'NO';

    SELECT format_type(atttypid, atttypmod) INTO tipe_er FROM pg_attribute
    WHERE attrelid = 'l2_gold.kol_metric_monthly'::regclass
      AND attname = 'er_followers_monthly';

    SELECT count(*) INTO n_daily FROM l2_gold.kol_metric_daily;

    SELECT count(*) INTO n_tabel FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'l2_gold' AND c.relkind = 'r';

    IF n_kolom <> 29 THEN
        RAISE EXCEPTION 'Jumlah kolom %, seharusnya 29', n_kolom;
    END IF;
    IF n_baris <> 0 THEN
        RAISE EXCEPTION 'Tabel harus dibuat KOSONG, ditemukan % baris', n_baris;
    END IF;
    IF n_uq <> 1 THEN
        RAISE EXCEPTION 'UNIQUE (social_account_id, platform, month_start) tidak terbentuk';
    END IF;
    IF n_fk <> 1 THEN
        RAISE EXCEPTION 'FK ke social_account(id) berjumlah %, seharusnya 1', n_fk;
    END IF;
    IF n_idx <> 4 THEN
        RAISE EXCEPTION 'Index berjumlah %, seharusnya 4 (pkey + uq + 2 index baca)', n_idx;
    END IF;
    -- 14 = id + 3 grain + 5 kalender + 3 hitungan + 2 timestamp
    IF n_notnull <> 14 THEN
        RAISE EXCEPTION 'Kolom NOT NULL berjumlah %, seharusnya 14. Seluruh kolom '
                        'metrik harus nullable supaya NULL bisa berarti '
                        '"tidak diketahui".', n_notnull;
    END IF;
    IF tipe_er <> 'numeric(12,8)' THEN
        RAISE EXCEPTION 'er_followers_monthly bertipe %, seharusnya numeric(12,8) '
                        '(sama dengan er_followers_daily)', tipe_er;
    END IF;
    IF n_daily <> 160 THEN
        RAISE EXCEPTION 'kol_metric_daily berubah jadi % baris -- seharusnya tetap 160. '
                        'Migrasi ini tidak boleh menyentuh sumbernya.', n_daily;
    END IF;
    IF n_tabel <> 2 THEN
        RAISE EXCEPTION 'l2_gold berisi % tabel, seharusnya 2 '
                        '(kol_metric_daily + kol_metric_monthly)', n_tabel;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: % kolom, 0 baris, UNIQUE grain + FK + % index, '
                 '% kolom NOT NULL, er %. Sumber kol_metric_daily utuh % baris.',
                 n_kolom, n_idx, n_notnull, tipe_er, n_daily;
    RAISE NOTICE 'Tabel siap diisi asset Dagster kol_metric_monthly. '
                 'Migrasi ini tidak mengisi data.';
END $verif$;

COMMIT;
