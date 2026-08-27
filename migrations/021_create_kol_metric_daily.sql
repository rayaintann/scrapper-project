-- 021_create_kol_metric_daily.sql
--
-- Tabel L2 Gold pertama di database `kol`: rekap harian per KOL per platform.
-- Sesuai backlog SCRUM-513 ("bikin tabel kol_metric_daily di gold dari
-- unified_post dan unified_profile di silver").
--
-- Schema `l2_gold` sudah ada sejak awal tapi masih 0 tabel dan 0 routine;
-- migrasi ini mengisinya untuk pertama kali. Tidak ada tabel, kolom, atau data
-- lain yang disentuh -- termasuk seluruh l1_silver dan feature.
--
-- ============================================================================
-- GRAIN
-- ============================================================================
--
--     UNIQUE (social_account_id, platform, metric_date)
--
-- Satu baris = satu KOL, satu platform, satu HARI TAYANG. Volume dengan data
-- sekarang: 160 baris (Instagram 100, TikTok 60), rentang 2021-02-18 s.d.
-- 2026-08-20.
--
-- `metric_date` diturunkan dari `unified_post.posted_at`, BUKAN dari
-- `unified_post.date`. `date` adalah tanggal SCRAPE -- seluruh 221 baris
-- bernilai 2026-08-20, jadi memakainya akan menghasilkan tabel harian dengan
-- satu tanggal saja. `posted_at` punya 68 tanggal berbeda.
--
-- Konversi ke WIB (`AT TIME ZONE 'Asia/Jakarta'`) mengikuti konvensi referensi
-- ("semua tanggal/jam sudah WIB") dan bukan formalitas: konversi itu memindah
-- 2 baris Instagram ke tanggal yang berbeda (98 -> 100 pasangan akun-tanggal).
--
-- ============================================================================
-- POLA KOLOM -- mengikuti l2_gold.brand_metric_daily di autometric_v2
-- ============================================================================
--
-- Referensi diaudit langsung lewat pg_get_functiondef, bukan dari nama tabel:
-- komponen additive `*_sum`, penyebut ER yang disimpan terpisah supaya rentang
-- N hari bisa dihitung `SUM(pembilang)/SUM(penyebut)`, dan jejak waktu build.
--
-- Tiga penyimpangan sadar dari referensi:
--
--   1. PRIMARY KEY (id) + UNIQUE (grain), bukan composite PK.
--      Mengikuti pola 9 tabel `feature` di database ini supaya konsisten ke
--      dalam, bukan konsisten ke database produk lain.
--
--   2. Metrik yang sumbernya tidak tersedia dibiarkan NULL, bukan 0.
--      Referensi membungkus semuanya `COALESCE(...,0)` -- aman di sana karena
--      L1-nya memang terisi. Di sini `shares_sum = 0` untuk Instagram akan
--      berbunyi "tidak ada yang membagikan", padahal artinya "tidak
--      diketahui". Karena itu kolom metrik NULLABLE tanpa DEFAULT 0.
--      Hanya `post_count` dan `posts_in_sample` yang NOT NULL DEFAULT 0 --
--      keduanya hasil COUNT, yang memang selalu punya jawaban.
--
--   3. Tidak ada kolom brand/account dua tingkat.
--      Referensi memakai (brand_id, account_id) lewat brand_social_accounts;
--      di jalur KOL tidak ada konsep brand payung.
--
-- ============================================================================
-- KOLOM YANG SENGAJA DIBUAT TAPI AKAN NULL
-- ============================================================================
--
--   reach_sum, er_reach_daily   `unified_post.reach` terisi 0/221 -- actor
--                               tidak menyediakannya, hanya Insights API.
--   reposts_sum                 `unified_post.reposts` 0/221 (IG-only).
--   followers_growth            `unified_profile.followers_growth` 0/1.971 --
--                               tiap akun baru punya SATU snapshot sehingga
--                               LAG() tidak punya baris sebelumnya.
--
-- Dibuat sekarang supaya skema tidak perlu di-ALTER saat sumbernya menyala.
-- Pengisinya TIDAK menulis keempatnya sama sekali. Pola yang sama dipakai
-- kolom BLOCKED di layer feature.
--
-- TIDAK dibuat, dan itu disengaja:
--   impressions_sum / er_impressions_daily  Facebook-only; tidak ada FB di sini
--   video_views_sum                         glosarium referensi menyebutnya
--                                           duplikat views_sum
--   new_/lost_followers_sum, net_growth_sum tidak ada kolom sumbernya sama
--                                           sekali di unified_profile kita
--   profile_visit_sum, accounts_engaged_sum 0/1.971
--
-- ============================================================================
-- KEAMANAN
-- ============================================================================
--
--   * Hanya CREATE TABLE + 1 UNIQUE + 1 FK + 2 index. Tidak ada DROP, ALTER,
--     atau perubahan data.
--   * `l2_gold` saat ini 0 tabel / 0 routine dan nama `kol_metric_daily` belum
--     terpakai di database mana pun -- dijaga di Langkah 0.
--   * FK ke public.social_account(id) NO ACTION, mengikuti 8 tabel feature.
--   * Tabel dibuat KOSONG. Migrasi ini tidak mengisi satu baris pun;
--     pengisian adalah tugas asset Dagster `kol_metric_daily`.
--
-- Jalankan:
--   python apply_migration.py migrations/021_create_kol_metric_daily.sql --dry-run --yes
--   python apply_migration.py migrations/021_create_kol_metric_daily.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga.
-- ---------------------------------------------------------------------------
DO $penjaga$
DECLARE
    n_schema  int;
    n_tabel   int;
    n_nama    int;
BEGIN
    SELECT count(*) INTO n_schema FROM pg_namespace WHERE nspname = 'l2_gold';
    IF n_schema <> 1 THEN
        RAISE EXCEPTION 'Schema l2_gold tidak ditemukan.';
    END IF;

    SELECT count(*) INTO n_tabel
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'l2_gold' AND c.relkind = 'r';
    IF n_tabel <> 0 THEN
        RAISE EXCEPTION 'l2_gold sudah berisi % tabel -- diharapkan 0. '
                        'Periksa dulu sebelum menambah yang pertama.', n_tabel;
    END IF;

    SELECT count(*) INTO n_nama FROM information_schema.tables
    WHERE table_name = 'kol_metric_daily';
    IF n_nama <> 0 THEN
        RAISE EXCEPTION 'Nama kol_metric_daily sudah dipakai di % tempat.', n_nama;
    END IF;

    RAISE NOTICE 'Penjaga lolos: schema l2_gold ada, 0 tabel, nama belum terpakai.';
END $penjaga$;

-- ---------------------------------------------------------------------------
-- Langkah 1 -- tabel.
-- ---------------------------------------------------------------------------
CREATE TABLE l2_gold.kol_metric_daily (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- grain -------------------------------------------------------------
    social_account_id       uuid        NOT NULL,
    platform                varchar(30) NOT NULL,
    metric_date             date        NOT NULL,

    -- hitungan konten: selalu punya jawaban, jadi NOT NULL DEFAULT 0 ------
    post_count              bigint      NOT NULL DEFAULT 0,   -- semua post hari itu
    posts_in_sample         bigint      NOT NULL DEFAULT 0,   -- yang lolos aturan sampel

    -- komponen additive: NULL berarti "tidak diketahui", bukan nol --------
    likes_sum               bigint,
    comments_sum            bigint,
    shares_sum              bigint,     -- TikTok saja; IG NULL (0/130 di sumber)
    saves_sum               bigint,     -- TikTok saja; IG NULL (0/130 di sumber)
    views_sum               bigint,
    engagement_sum          bigint,
    engagement_public_sum   bigint,

    -- follower & engagement rate -----------------------------------------
    followers_at_post_date  bigint,     -- carry-forward snapshot <= metric_date
    followers_denom_sum     bigint,     -- followers_at_post_date * posts_in_sample
    er_followers_daily      numeric(12,8),  -- FRAKSI 0..1, bukan persen

    -- sengaja dibiarkan NULL sampai sumbernya ada -------------------------
    reach_sum               bigint,
    er_reach_daily          numeric(12,8),
    reposts_sum             bigint,
    followers_growth        bigint,

    -- jejak ---------------------------------------------------------------
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_kol_metric_daily
        UNIQUE (social_account_id, platform, metric_date),
    CONSTRAINT fk_kol_metric_daily_social_account
        FOREIGN KEY (social_account_id) REFERENCES public.social_account(id)
);

-- Dua index baca, meniru ix_bmd_* di brand_metric_daily: pola query dashboard
-- adalah "satu KOL, rentang tanggal" dan "satu KOL, satu platform, rentang".
CREATE INDEX ix_kmd_account_date
    ON l2_gold.kol_metric_daily (social_account_id, metric_date);
CREATE INDEX ix_kmd_account_platform_date
    ON l2_gold.kol_metric_daily (social_account_id, platform, metric_date);

COMMENT ON TABLE l2_gold.kol_metric_daily IS
    'Rekap harian per KOL per platform. Grain (social_account_id, platform, '
    'metric_date). metric_date = tanggal TAYANG (posted_at, WIB), bukan tanggal '
    'scrape. Metrik diagregasi hanya dari post yang lolos aturan sampel '
    '(likes_hidden IS NOT TRUE AND is_collaboration IS NOT TRUE); post_count '
    'menghitung semua post, posts_in_sample menghitung yang layak. NULL berarti '
    'sumbernya tidak tersedia, bukan nol. er_followers_daily adalah FRAKSI 0..1.';

COMMENT ON COLUMN l2_gold.kol_metric_daily.followers_at_post_date IS
    'Carry-forward: followers_count dari snapshot unified_profile TERAKHIR '
    'dengan date <= metric_date. NULL bila post lebih tua dari snapshot pertama.';

COMMENT ON COLUMN l2_gold.kol_metric_daily.followers_denom_sum IS
    'Penyebut additive untuk ER rentang N hari: SUM(engagement_sum) / '
    'SUM(followers_denom_sum). JANGAN merata-rata er_followers_daily.';

-- ---------------------------------------------------------------------------
-- Langkah 2 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $verif$
DECLARE
    n_kolom     int;
    n_baris     bigint;
    n_uq        int;
    n_fk        int;
    n_idx       int;
    n_notnull   int;
    tipe_er     text;
    n_l1        bigint;
BEGIN
    SELECT count(*) INTO n_kolom FROM information_schema.columns
    WHERE table_schema = 'l2_gold' AND table_name = 'kol_metric_daily';

    SELECT count(*) INTO n_baris FROM l2_gold.kol_metric_daily;

    SELECT count(*) INTO n_uq FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'l2_gold' AND t.relname = 'kol_metric_daily' AND c.contype = 'u'
      AND pg_get_constraintdef(c.oid) = 'UNIQUE (social_account_id, platform, metric_date)';

    SELECT count(*) INTO n_fk FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'l2_gold' AND t.relname = 'kol_metric_daily' AND c.contype = 'f';

    SELECT count(*) INTO n_idx FROM pg_indexes
    WHERE schemaname = 'l2_gold' AND tablename = 'kol_metric_daily';

    -- Hanya 5 kolom yang boleh NOT NULL: id, grain (3), + 2 count + 2 timestamp.
    SELECT count(*) INTO n_notnull FROM information_schema.columns
    WHERE table_schema = 'l2_gold' AND table_name = 'kol_metric_daily'
      AND is_nullable = 'NO';

    SELECT format_type(atttypid, atttypmod) INTO tipe_er FROM pg_attribute
    WHERE attrelid = 'l2_gold.kol_metric_daily'::regclass AND attname = 'er_followers_daily';

    SELECT (SELECT count(*) FROM l1_silver.unified_post)
         + (SELECT count(*) FROM l1_silver.unified_profile) INTO n_l1;

    -- 22 = id + 3 grain + 2 count + 7 metrik additive + 3 follower/ER
    --      + 4 kolom BLOCKED + 2 timestamp
    IF n_kolom <> 22 THEN
        RAISE EXCEPTION 'Jumlah kolom %, seharusnya 22', n_kolom;
    END IF;
    IF n_baris <> 0 THEN
        RAISE EXCEPTION 'Tabel harus dibuat KOSONG, ditemukan % baris', n_baris;
    END IF;
    IF n_uq <> 1 THEN
        RAISE EXCEPTION 'UNIQUE grain tidak terbentuk dengan definisi yang benar';
    END IF;
    IF n_fk <> 1 THEN
        RAISE EXCEPTION 'FK ke social_account berjumlah %, seharusnya 1', n_fk;
    END IF;
    IF n_idx <> 4 THEN
        RAISE EXCEPTION 'Index berjumlah %, seharusnya 4 (pkey + uq + 2 index baca)', n_idx;
    END IF;
    IF n_notnull <> 8 THEN
        RAISE EXCEPTION 'Kolom NOT NULL berjumlah %, seharusnya 8 '
                        '(id, 3 grain, 2 count, 2 timestamp). Metrik harus nullable '
                        'supaya NULL bisa berarti "tidak diketahui".', n_notnull;
    END IF;
    IF tipe_er <> 'numeric(12,8)' THEN
        RAISE EXCEPTION 'er_followers_daily bertipe %, seharusnya numeric(12,8)', tipe_er;
    END IF;
    IF n_l1 <> 2192 THEN
        RAISE EXCEPTION 'Baris L1 berubah jadi % -- seharusnya tetap 2192 (221 + 1971). '
                        'Migrasi ini tidak boleh menyentuh L1.', n_l1;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: % kolom, 0 baris, UNIQUE grain + FK + % index, '
                 '% kolom NOT NULL, er %.', n_kolom, n_idx, n_notnull, tipe_er;
    RAISE NOTICE 'Tabel siap diisi asset Dagster kol_metric_daily. '
                 'Migrasi ini tidak mengisi data.';
END $verif$;

COMMIT;
