-- 023_create_l2_gold_remaining_tables.sql
--
-- Melengkapi schema `l2_gold` dengan 6 tabel sisa yang tercantum di backlog
-- "L2 Database" (SCRUM-490), sehingga seluruh 8 tabel L2 Gold yang required
-- punya rumah. Tabel dibuat KOSONG; tidak ada satu baris data pun yang ditulis.
--
-- SCRUM-513 (kol_metric_daily) dan SCRUM-516 (kol_metric_monthly) sudah dibuat
-- migration 021 dan 022 -- keduanya TIDAK disentuh migrasi ini.
--
-- ============================================================================
-- SUMBER REQUIREMENT
-- ============================================================================
--
-- Backlog Jira "L2 Database" (SCRUM-490), 10 subtask, 8 tabel distinct:
--
--   SCRUM-513  kol_metric_daily             <- unified_post + unified_profile   SUDAH ADA
--   SCRUM-516  kol_metric_monthly           <- gold.kol_metric_daily            SUDAH ADA
--   SCRUM-514  kol_profile_card             <- unified_profile + unified_rate_card
--   SCRUM-515  post_metric                  <- unified_post + feature post analysis
--   SCRUM-517  content_format_daily         <- silver.unified_post
--   SCRUM-518  content_format_daily         <- silver.unified_post   (teks & sumber
--                                              IDENTIK dengan 517 -- diperlakukan
--                                              sebagai SATU tabel; lihat CATATAN 1)
--   SCRUM-519  audience_demographics_daily  <- silver.unified_audience
--   SCRUM-520  audience_geo_daily           <- silver.unified_audience
--   SCRUM-521  audience_interest_daily      <- silver.unified_audience
--
-- SCRUM-491 ("hasil dari skema feature") bukan tabel, jadi tidak dibuatkan apa pun.
--
-- Tidak ada tabel di luar daftar ini yang dibuat. Kandidat dari database
-- referensi (`posting_time_heatmap`, `post_wordcloud`, `ugc_tagged_posts`,
-- `pillar_performance_daily`, `story_*`, `comment_*`, `competitor_*`) SENGAJA
-- tidak dibuat: tidak satu pun muncul di backlog project ini.
--
-- ============================================================================
-- KESIAPAN SUMBER -- diverifikasi 2026-08-21
-- ============================================================================
--
--   Tabel                        Sumber                          Baris sumber
--   post_metric                  l1_silver.unified_post               221
--                                feature.ig/tt_post_analysis      130 + 91
--   kol_profile_card             l1_silver.unified_profile          1.971
--                                l1_silver.unified_rate_card        9.210
--   content_format_daily         l1_silver.unified_post               221
--   audience_demographics_daily  l1_silver.unified_audience             0
--   audience_geo_daily           l1_silver.unified_audience             0
--   audience_interest_daily      l1_silver.unified_audience             0
--
-- Tiga tabel pertama sumbernya SIAP; tiga tabel audience sumbernya kosong.
-- Migrasi ini tetap hanya membuat SCHEMA untuk keenamnya -- belum ada satu pun
-- asset Dagster yang mengisinya, dan logic pengisian belum divalidasi.
-- Membuat tabel lebih dulu tidak berbahaya; menebak isinya berbahaya.
--
-- ============================================================================
-- CATATAN 1 -- SCRUM-517 dan SCRUM-518 diperlakukan sebagai SATU tabel
-- ============================================================================
--
-- Kedua tiket berbunyi persis sama: "bikin tabel content_format_daily di gold
-- dari silver.unified_post". Nama tabel, sumber, dan deskripsinya identik.
-- Membuat dua tabel dengan nama sama mustahil, dan membuat dua tabel dengan
-- nama berbeda berarti mengarang. Jadi dibuat SATU tabel `content_format_daily`.
--
-- Ini kemungkinan duplikat tiket, TAPI belum dikonfirmasi. Kalau ternyata salah
-- satunya dimaksudkan untuk hal lain, tabel keduanya bisa ditambahkan menyusul.
--
-- ============================================================================
-- CATATAN 2 -- audience_interest_daily TIDAK PUNYA SUMBER SAMA SEKALI
-- ============================================================================
--
-- Bukan sekadar "datanya masih kosong". Jalur audience di project ini:
--
--   l0_raw.ig_profile_official.demographics_{age,city,country,gender}  (4 kolom jsonb)
--        -> sp_sync_instagram_audience() memecahnya jadi audience_type:
--           'age', 'gender', 'country', 'city'   <- HANYA EMPAT NILAI INI
--        -> l0_harmonization.instagram_audience
--        -> l1_silver.unified_audience
--
-- Tidak ada `interest` di mana pun. Pencarian kolom ber-nama '%interest%' di
-- seluruh schema l0_raw + l0_harmonization + l1_silver mengembalikan NOL kolom.
--
-- Jadi `audience_interest_daily` tidak akan pernah terisi lewat pipeline yang
-- ada sekarang, berapa kali pun dijalankan. Yang dibutuhkan lebih dulu: sumber
-- data minat audiens (field baru dari Instagram Insights, atau penyedia lain).
-- Tabelnya tetap dibuat karena SCRUM-521 memintanya dan UI menyebut `interests`,
-- tapi statusnya harus dibaca sebagai "menunggu sumber", bukan "menunggu ETL".
--
-- ============================================================================
-- KONVENSI -- mengikuti kol_metric_daily / kol_metric_monthly
-- ============================================================================
--
--   * PRIMARY KEY (id uuid DEFAULT gen_random_uuid())
--   * UNIQUE pada grain, dinamai uq_<nama_tabel>
--   * FK social_account_id -> public.social_account(id), NO ACTION
--   * platform varchar(30)
--   * Kolom metrik NULLABLE TANPA DEFAULT 0 -- NULL berarti "tidak diketahui",
--     0 berarti "diketahui, nilainya nol". Hanya kolom hitungan (COUNT) yang
--     NOT NULL DEFAULT 0.
--   * created_at / updated_at timestamptz NOT NULL DEFAULT now()
--   * Index baca dinamai ix_<singkatan>_<kolom>
--   * Kolom BLOCKED dibuat tapi tidak akan diisi, konsisten dengan 021/022.
--
-- ============================================================================
-- KEAMANAN
-- ============================================================================
--
--   * Hanya CREATE TABLE + constraint + index. Tidak ada DROP, ALTER, atau
--     perubahan data. Tabel 021/022 tidak disentuh sama sekali.
--   * Keenam nama tabel dijaga belum terpakai di Langkah 0.
--   * kol_metric_daily (160 baris) dan kol_metric_monthly (53 baris) dijaga
--     tidak berubah di Langkah 2.
--
-- Jalankan:
--   python apply_migration.py migrations/023_create_l2_gold_remaining_tables.sql --dry-run --yes
--   python apply_migration.py migrations/023_create_l2_gold_remaining_tables.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga.
-- ---------------------------------------------------------------------------
DO $penjaga$
DECLARE
    n_ada       int;
    n_bentrok   int;
    n_daily     bigint;
    n_monthly   bigint;
BEGIN
    SELECT count(*) INTO n_ada FROM information_schema.tables
    WHERE table_schema = 'l2_gold' AND table_name IN
          ('kol_metric_daily', 'kol_metric_monthly');
    IF n_ada <> 2 THEN
        RAISE EXCEPTION 'Diharapkan kol_metric_daily + kol_metric_monthly sudah ada, '
                        'ditemukan %. Terapkan migration 021 dan 022 dulu.', n_ada;
    END IF;

    SELECT count(*) INTO n_bentrok FROM information_schema.tables
    WHERE table_name IN ('post_metric', 'kol_profile_card', 'content_format_daily',
                         'audience_demographics_daily', 'audience_geo_daily',
                         'audience_interest_daily');
    IF n_bentrok <> 0 THEN
        RAISE EXCEPTION '% dari 6 nama tabel target sudah terpakai di database ini -- '
                        'migrasi ini sudah pernah dijalankan sebagian.', n_bentrok;
    END IF;

    SELECT count(*) INTO n_daily   FROM l2_gold.kol_metric_daily;
    SELECT count(*) INTO n_monthly FROM l2_gold.kol_metric_monthly;

    RAISE NOTICE 'Penjaga lolos: 2 tabel L2 existing (% + % baris), '
                 '6 nama target belum terpakai.', n_daily, n_monthly;
END $penjaga$;

-- ===========================================================================
-- TABEL 1 -- l2_gold.post_metric            (SCRUM-515)
-- ===========================================================================
--
-- Grain: (social_account_id, platform, content_id) -- satu baris per konten.
-- Sumber: l1_silver.unified_post (fakta + metrik mentah)
--         feature.ig_post_analysis / tt_post_analysis (rank, top_hashtags)
--         l1_silver.unified_profile (followers carry-forward untuk ER)
--
-- Bedanya dengan feature.*_post_analysis yang sudah ada: yang di `feature`
-- terpisah per platform dan berorientasi analisis konten; `post_metric` adalah
-- proyeksi lintas-platform berorientasi metrik, sejajar dengan pola
-- l2_gold.post_metric di database referensi.
--
-- `likes_hidden` dan `is_collaboration` ikut disimpan supaya konsumen bisa
-- menyaring sendiri dengan aturan yang sama seperti kol_metric_daily, tanpa
-- harus kembali ke L1.
-- ===========================================================================
CREATE TABLE l2_gold.post_metric (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- grain ---------------------------------------------------------------
    social_account_id       uuid        NOT NULL,
    platform                varchar(30) NOT NULL,
    content_id              varchar(255) NOT NULL,

    -- fakta konten (unified_post) -------------------------------------------
    posted_at               timestamptz,
    post_date               date,           -- posted_at di WIB, untuk filter harian
    media_type              varchar(255),
    is_sponsored            boolean,
    permalink               text,

    -- penanda aturan sampel (unified_post) ----------------------------------
    likes_hidden            boolean,
    is_collaboration        boolean,

    -- metrik mentah per konten ----------------------------------------------
    likes                   bigint,
    comments                bigint,
    shares                  bigint,     -- TikTok saja pada data sekarang
    saves                   bigint,     -- TikTok saja pada data sekarang
    views                   bigint,

    -- turunan ---------------------------------------------------------------
    engagement_owned        bigint,     -- likes+comments+shares+saves
    engagement_public       bigint,     -- likes+comments
    followers_at_post_date  bigint,     -- carry-forward snapshot <= post_date
    er_followers            numeric(12,8),  -- FRAKSI 0..1

    -- dari layer feature ----------------------------------------------------
    rank_in_account         integer,    -- feature.*_post_analysis.rank
    top_hashtags            jsonb,      -- feature.*_post_analysis.top_hashtags

    -- BLOCKED: dibuat, tidak diisi ------------------------------------------
    reach                   bigint,
    er_reach                numeric(12,8),
    reposts                 bigint,
    avg_watch_time_seconds  numeric(12,4),
    completion_rate         numeric(12,8),

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_post_metric UNIQUE (social_account_id, platform, content_id),
    CONSTRAINT fk_post_metric_social_account
        FOREIGN KEY (social_account_id) REFERENCES public.social_account(id)
);

CREATE INDEX ix_pm_account_date    ON l2_gold.post_metric (social_account_id, post_date);
CREATE INDEX ix_pm_platform_date   ON l2_gold.post_metric (platform, post_date);

COMMENT ON TABLE l2_gold.post_metric IS
    'SCRUM-515. Metrik per konten lintas platform. Grain (social_account_id, '
    'platform, content_id). Sumber l1_silver.unified_post + feature.*_post_analysis. '
    'BELUM DIISI -- belum ada asset Dagster.';

-- ===========================================================================
-- TABEL 2 -- l2_gold.kol_profile_card       (SCRUM-514)
-- ===========================================================================
--
-- Grain: (social_account_id, platform) -- SATU kartu per akun, bukan per hari.
-- Sumber: l1_silver.unified_profile (snapshot TERBARU per akun)
--         l1_silver.unified_rate_card (agregat harga per akun)
--
-- Ini tabel kartu profil untuk daftar/pencarian KOL, jadi grain-nya per akun
-- tanpa dimensi tanggal. `profile_snapshot_date` mencatat snapshot mana yang
-- dipakai, supaya kartu yang basi masih bisa dikenali.
--
-- Kolom rate card sengaja RINGKASAN, bukan salinan 9.210 baris: `rate_card`
-- jsonb menyimpan peta post_type -> fee, plus min/maks untuk penyaringan cepat.
-- Empat kolom unified_rate_card lain (location, segmentasi, quantity,
-- duration_days, is_owning, link_file) SEMUANYA 0 terisi, jadi tidak dibawa.
-- ===========================================================================
CREATE TABLE l2_gold.kol_profile_card (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- grain ---------------------------------------------------------------
    social_account_id       uuid        NOT NULL,
    platform                varchar(30) NOT NULL,

    -- identitas (unified_profile, snapshot terbaru) -------------------------
    username                varchar(255),
    display_name            varchar(255),
    avatar_url              text,
    profile_url             text,
    bio                     text,
    website                 text,
    is_verified             boolean,
    is_private              boolean,

    -- ukuran akun ----------------------------------------------------------
    followers_count         bigint,
    following_count         bigint,
    media_count             bigint,
    tier                    varchar(50),
    profile_snapshot_date   date,       -- tanggal snapshot yang dipakai

    -- ringkasan rate card (unified_rate_card) --------------------------------
    rate_card               jsonb,      -- {post_type: fee, ...}
    rate_card_currency      varchar(10),
    rate_card_min_fee       numeric(18,2),
    rate_card_max_fee       numeric(18,2),
    rate_card_post_types    integer,    -- berapa jenis paket yang punya harga

    -- BLOCKED: dibuat, tidak diisi ------------------------------------------
    followers_growth        bigint,

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_kol_profile_card UNIQUE (social_account_id, platform),
    CONSTRAINT fk_kol_profile_card_social_account
        FOREIGN KEY (social_account_id) REFERENCES public.social_account(id)
);

CREATE INDEX ix_kpc_platform_followers ON l2_gold.kol_profile_card (platform, followers_count DESC);
CREATE INDEX ix_kpc_username           ON l2_gold.kol_profile_card (username);

COMMENT ON TABLE l2_gold.kol_profile_card IS
    'SCRUM-514. Kartu profil KOL, satu baris per (akun, platform). Sumber '
    'l1_silver.unified_profile (snapshot terbaru) + l1_silver.unified_rate_card '
    '(ringkasan harga). BELUM DIISI -- belum ada asset Dagster.';

-- ===========================================================================
-- TABEL 3 -- l2_gold.content_format_daily   (SCRUM-517 / SCRUM-518)
-- ===========================================================================
--
-- Grain: (social_account_id, platform, metric_date, media_type)
-- Sumber: l1_silver.unified_post
--
-- Bentuknya mengikuti l2_gold.content_attribute_daily di database referensi
-- (grain akun x platform x hari x tag, isi post_count + engagement_sum +
-- penyebut ER), diperluas dengan komponen additive yang sama seperti
-- kol_metric_daily supaya ER per format bisa dihitung dengan cara yang sama
-- dan hasilnya bisa direkonsiliasi terhadap kol_metric_daily.
--
-- `media_type` dipakai apa adanya dari unified_post -- Instagram
-- 'carousel_container'/'clips'/'feed', TikTok 'VIDEO'/'CAROUSEL'. Sengaja TIDAK
-- dinormalisasi jadi label bersama: pemetaannya keputusan produk, belum ada.
-- ===========================================================================
CREATE TABLE l2_gold.content_format_daily (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- grain ---------------------------------------------------------------
    social_account_id       uuid        NOT NULL,
    platform                varchar(30) NOT NULL,
    metric_date             date        NOT NULL,   -- posted_at di WIB
    media_type              varchar(255) NOT NULL,

    -- hitungan --------------------------------------------------------------
    post_count              bigint      NOT NULL DEFAULT 0,
    posts_in_sample         bigint      NOT NULL DEFAULT 0,

    -- komponen additive ------------------------------------------------------
    likes_sum               bigint,
    comments_sum            bigint,
    shares_sum              bigint,
    saves_sum               bigint,
    views_sum               bigint,
    engagement_sum          bigint,
    engagement_public_sum   bigint,

    -- ER --------------------------------------------------------------------
    followers_denom_sum     bigint,
    er_followers_daily      numeric(12,8),  -- FRAKSI 0..1

    -- BLOCKED ----------------------------------------------------------------
    reach_sum               bigint,
    er_reach_daily          numeric(12,8),

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_content_format_daily
        UNIQUE (social_account_id, platform, metric_date, media_type),
    CONSTRAINT fk_content_format_daily_social_account
        FOREIGN KEY (social_account_id) REFERENCES public.social_account(id)
);

CREATE INDEX ix_cfd_account_date  ON l2_gold.content_format_daily (social_account_id, metric_date);
CREATE INDEX ix_cfd_format_date   ON l2_gold.content_format_daily (platform, media_type, metric_date);

COMMENT ON TABLE l2_gold.content_format_daily IS
    'SCRUM-517/518 (dua tiket identik, satu tabel). Performa per format konten '
    'per hari. Grain (social_account_id, platform, metric_date, media_type). '
    'Sumber l1_silver.unified_post. BELUM DIISI -- belum ada asset Dagster.';

-- ===========================================================================
-- TABEL 4 -- l2_gold.audience_demographics_daily   (SCRUM-519)
-- ===========================================================================
--
-- Grain: (social_account_id, platform, audience_date, audience_type, dimension_key)
-- Sumber: l1_silver.unified_audience, disaring audience_type IN ('age','gender')
--
-- Bentuknya EAV, MENGIKUTI SUMBER, bukan pivot 15 kolom seperti database
-- referensi. Alasannya: sumber kita sudah ternormalisasi
-- (audience_type/dimension_key/value), sementara referensi mem-pivot karena
-- sumbernya jsonb dengan kunci tetap. Pivot di sini akan mengunci nama bucket
-- ('18-24', 'F', ...) di DDL padahal bucket-nya ditentukan Instagram, bukan kita.
-- ===========================================================================
CREATE TABLE l2_gold.audience_demographics_daily (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    social_account_id       uuid        NOT NULL,
    platform                varchar(30) NOT NULL,
    audience_date           date        NOT NULL,
    audience_type           varchar(30) NOT NULL,   -- 'age' | 'gender'
    dimension_key           varchar(100) NOT NULL,  -- '18-24', 'F', ...

    audience_count          numeric,                -- unified_audience.value
    confidence              varchar(30),            -- 'measured' | 'estimated'

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_audience_demographics_daily
        UNIQUE (social_account_id, platform, audience_date, audience_type, dimension_key),
    CONSTRAINT fk_audience_demographics_daily_social_account
        FOREIGN KEY (social_account_id) REFERENCES public.social_account(id)
);

CREATE INDEX ix_add_account_date ON l2_gold.audience_demographics_daily (social_account_id, audience_date);
CREATE INDEX ix_add_type_key     ON l2_gold.audience_demographics_daily (audience_type, dimension_key);

COMMENT ON TABLE l2_gold.audience_demographics_daily IS
    'SCRUM-519. Demografi audiens (umur & gender) per akun per hari. Sumber '
    'l1_silver.unified_audience WHERE audience_type IN (''age'',''gender''). '
    'KOSONG: sumbernya 0 baris karena l0_raw.ig_profile_official belum terisi '
    '(butuh Instagram Insights API).';

-- ===========================================================================
-- TABEL 5 -- l2_gold.audience_geo_daily     (SCRUM-520)
-- ===========================================================================
--
-- Grain: (social_account_id, platform, audience_date, geo_level, geo_key)
-- Sumber: l1_silver.unified_audience, disaring audience_type IN ('country','city')
--
-- `geo_level` mengambil nilai audience_type ('country'/'city') dan `geo_key`
-- mengambil dimension_key. Penamaan ini mengikuti l2_gold.audience_geo_daily di
-- database referensi, yang memakai geo_level/geo_key/audience_count persis.
-- ===========================================================================
CREATE TABLE l2_gold.audience_geo_daily (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    social_account_id       uuid        NOT NULL,
    platform                varchar(30) NOT NULL,
    audience_date           date        NOT NULL,
    geo_level               varchar(30) NOT NULL,   -- 'country' | 'city'
    geo_key                 varchar(255) NOT NULL,  -- 'ID', 'Jakarta', ...

    audience_count          numeric,
    confidence              varchar(30),

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_audience_geo_daily
        UNIQUE (social_account_id, platform, audience_date, geo_level, geo_key),
    CONSTRAINT fk_audience_geo_daily_social_account
        FOREIGN KEY (social_account_id) REFERENCES public.social_account(id)
);

CREATE INDEX ix_agd_account_date ON l2_gold.audience_geo_daily (social_account_id, audience_date);
CREATE INDEX ix_agd_level_key    ON l2_gold.audience_geo_daily (geo_level, geo_key);

COMMENT ON TABLE l2_gold.audience_geo_daily IS
    'SCRUM-520. Lokasi audiens per akun per hari. Sumber l1_silver.unified_audience '
    'WHERE audience_type IN (''country'',''city''). KOSONG: sumbernya 0 baris '
    '(butuh Instagram Insights API).';

-- ===========================================================================
-- TABEL 6 -- l2_gold.audience_interest_daily   (SCRUM-521)
-- ===========================================================================
--
-- Grain: (social_account_id, platform, audience_date, interest_key)
--
-- ⚠ TIDAK PUNYA SUMBER SAMA SEKALI -- lihat CATATAN 2 di kepala file.
-- `sp_sync_instagram_audience()` hanya menghasilkan audience_type 'age',
-- 'gender', 'country', 'city'. Tidak ada satu pun kolom bernama '%interest%'
-- di seluruh l0_raw, l0_harmonization, maupun l1_silver.
--
-- Tabel ini dibuat karena SCRUM-521 memintanya dan UI menyebut `interests`,
-- tapi ia menunggu SUMBER DATA BARU, bukan menunggu ETL. Bentuknya sengaja
-- dibuat sejajar dengan dua tabel audience di atas supaya kalau sumbernya
-- suatu saat ada, pengisiannya mengikuti pola yang sama.
-- ===========================================================================
CREATE TABLE l2_gold.audience_interest_daily (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),

    social_account_id       uuid        NOT NULL,
    platform                varchar(30) NOT NULL,
    audience_date           date        NOT NULL,
    interest_key            varchar(255) NOT NULL,

    audience_count          numeric,
    confidence              varchar(30),

    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_audience_interest_daily
        UNIQUE (social_account_id, platform, audience_date, interest_key),
    CONSTRAINT fk_audience_interest_daily_social_account
        FOREIGN KEY (social_account_id) REFERENCES public.social_account(id)
);

CREATE INDEX ix_aid_account_date ON l2_gold.audience_interest_daily (social_account_id, audience_date);
CREATE INDEX ix_aid_interest     ON l2_gold.audience_interest_daily (interest_key);

COMMENT ON TABLE l2_gold.audience_interest_daily IS
    'SCRUM-521. Minat audiens per akun per hari. TIDAK ADA SUMBER: pipeline '
    'audience hanya menghasilkan age/gender/country/city, dan tidak ada kolom '
    'bernama interest di L0/L1 mana pun. Menunggu sumber data baru, bukan ETL.';

-- ---------------------------------------------------------------------------
-- Langkah 2 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $verif$
DECLARE
    n_tabel     int;
    n_baru      int;
    n_baris     bigint;
    n_uq        int;
    n_fk        int;
    n_idx       int;
    n_daily     bigint;
    n_monthly   bigint;
    r           record;
BEGIN
    SELECT count(*) INTO n_tabel FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'l2_gold' AND c.relkind = 'r';

    SELECT count(*) INTO n_baru FROM information_schema.tables
    WHERE table_schema = 'l2_gold' AND table_name IN
          ('post_metric', 'kol_profile_card', 'content_format_daily',
           'audience_demographics_daily', 'audience_geo_daily',
           'audience_interest_daily');

    -- Keenam tabel baru WAJIB kosong.
    SELECT (SELECT count(*) FROM l2_gold.post_metric)
         + (SELECT count(*) FROM l2_gold.kol_profile_card)
         + (SELECT count(*) FROM l2_gold.content_format_daily)
         + (SELECT count(*) FROM l2_gold.audience_demographics_daily)
         + (SELECT count(*) FROM l2_gold.audience_geo_daily)
         + (SELECT count(*) FROM l2_gold.audience_interest_daily)
      INTO n_baris;

    -- Tiap tabel baru harus punya tepat 1 UNIQUE dan 1 FK ke social_account.
    SELECT count(*) INTO n_uq FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'l2_gold' AND c.contype = 'u' AND t.relname IN
          ('post_metric', 'kol_profile_card', 'content_format_daily',
           'audience_demographics_daily', 'audience_geo_daily',
           'audience_interest_daily');

    SELECT count(*) INTO n_fk FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'l2_gold' AND c.contype = 'f'
      AND pg_get_constraintdef(c.oid) LIKE '%REFERENCES social_account(id)%'
      AND t.relname IN ('post_metric', 'kol_profile_card', 'content_format_daily',
                        'audience_demographics_daily', 'audience_geo_daily',
                        'audience_interest_daily');

    SELECT count(*) INTO n_idx FROM pg_indexes
    WHERE schemaname = 'l2_gold' AND tablename IN
          ('post_metric', 'kol_profile_card', 'content_format_daily',
           'audience_demographics_daily', 'audience_geo_daily',
           'audience_interest_daily');

    SELECT count(*) INTO n_daily   FROM l2_gold.kol_metric_daily;
    SELECT count(*) INTO n_monthly FROM l2_gold.kol_metric_monthly;

    IF n_tabel <> 8 THEN
        RAISE EXCEPTION 'l2_gold berisi % tabel, seharusnya 8 (2 lama + 6 baru)', n_tabel;
    END IF;
    IF n_baru <> 6 THEN
        RAISE EXCEPTION 'Tabel baru terbentuk %, seharusnya 6', n_baru;
    END IF;
    IF n_baris <> 0 THEN
        RAISE EXCEPTION 'Tabel baru berisi % baris -- seharusnya KOSONG semua. '
                        'Migrasi ini tidak boleh menulis data.', n_baris;
    END IF;
    IF n_uq <> 6 THEN
        RAISE EXCEPTION 'UNIQUE constraint pada tabel baru berjumlah %, seharusnya 6', n_uq;
    END IF;
    IF n_fk <> 6 THEN
        RAISE EXCEPTION 'FK ke social_account pada tabel baru berjumlah %, seharusnya 6', n_fk;
    END IF;
    -- 6 pkey + 6 uq + 12 index baca = 24
    IF n_idx <> 24 THEN
        RAISE EXCEPTION 'Index pada tabel baru berjumlah %, seharusnya 24', n_idx;
    END IF;
    IF n_daily <> 160 THEN
        RAISE EXCEPTION 'kol_metric_daily berubah jadi % baris -- seharusnya tetap 160', n_daily;
    END IF;
    IF n_monthly <> 53 THEN
        RAISE EXCEPTION 'kol_metric_monthly berubah jadi % baris -- seharusnya tetap 53', n_monthly;
    END IF;

    -- Tidak boleh ada kolom metrik yang NOT NULL kecuali grain/hitungan/timestamp.
    FOR r IN
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema = 'l2_gold' AND is_nullable = 'NO'
          AND table_name IN ('post_metric', 'kol_profile_card', 'content_format_daily',
                             'audience_demographics_daily', 'audience_geo_daily',
                             'audience_interest_daily')
          AND column_name NOT IN ('id', 'social_account_id', 'platform', 'content_id',
                                  'metric_date', 'media_type', 'audience_date',
                                  'audience_type', 'dimension_key', 'geo_level',
                                  'geo_key', 'interest_key', 'post_count',
                                  'posts_in_sample', 'created_at', 'updated_at')
    LOOP
        RAISE EXCEPTION 'Kolom %.% NOT NULL padahal bukan grain/hitungan/timestamp -- '
                        'kolom metrik harus nullable supaya NULL bisa berarti '
                        '"tidak diketahui".', r.table_name, r.column_name;
    END LOOP;

    RAISE NOTICE 'Verifikasi lolos: l2_gold kini % tabel, 6 baru dan KOSONG, '
                 '% UNIQUE, % FK, % index. kol_metric_daily % baris, '
                 'kol_metric_monthly % baris -- keduanya utuh.',
                 n_tabel, n_uq, n_fk, n_idx, n_daily, n_monthly;
    RAISE NOTICE 'Tidak ada asset Dagster untuk keenam tabel baru; semuanya '
                 'sengaja dibiarkan kosong sampai logic pengisiannya dirancang '
                 'dan divalidasi tersendiri.';
END $verif$;

COMMIT;
