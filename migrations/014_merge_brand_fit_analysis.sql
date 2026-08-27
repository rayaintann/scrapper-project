-- 014_merge_brand_fit_analysis.sql
--
-- Menggabungkan feature.ig_brand_fit_analysis + feature.tt_brand_fit_analysis
-- menjadi satu tabel feature.brand_fit_analysis.
--
-- Grain: 1 baris = 1 kombinasi KOL x Brand.
--   - 1 KOL boleh punya banyak brand
--   - 1 brand boleh punya banyak KOL
--   - kombinasi yang sama hanya boleh 1 baris
--       -> UNIQUE (agency_kol_account_id, brand_id)
--
-- Dasar keputusan (diverifikasi langsung ke database 2026-08-21):
--   1. Kedua tabel identik 100%: 11 kolom, nama/tipe/nullability/urutan sama.
--   2. Platform ditentukan public.agency_kol_accounts.platform_id (FK ke
--      public.platforms; 7.494 dari 7.718 terisi -- TikTok 4.087,
--      Instagram 3.407). Prefix ig_/tt_ hanya mengulang informasi yang sudah
--      ada, tanpa constraint apa pun yang menegakkannya: tidak ada yang
--      mencegah baris TikTok masuk ke tabel ig_.
--   3. UI tidak punya konsep brand fit per platform. Tab Brand Fit
--      (app/Autometric-KOL-Module.html:1235-1247) tidak punya platform
--      selector, dan k.match adalah skalar tunggal per KOL sementara k.plat
--      bisa berisi 2-3 platform sekaligus.
--   4. Nol dependensi: tidak ada view, procedure, function, trigger, FK masuk,
--      RLS policy, comment, grant non-owner, maupun kode aplikasi yang
--      mereferensi kedua tabel.
--   5. Kedua tabel 0 baris -- tidak ada data yang perlu dipindahkan.
--
-- Sekalian membereskan FK duplikat: masing-masing tabel lama punya DUA foreign
-- key identik ke agency_kol_accounts(id) dan DUA ke brand(id) -- delapan
-- constraint untuk empat relasi. Polanya berbeda dari yang diperbaiki migrasi
-- 001/002 (di sana dua FK menunjuk tabel BERBEDA pada kolom social_account_id
-- sehingga kolomnya mustahil diisi), jadi kriteria pencarian migrasi 002 tidak
-- menjangkaunya. Ini FK duplikat terakhir yang tersisa di schema feature.
--
-- Pilihan desain yang SENGAJA TIDAK diambil, beserta buktinya:
--   - ON DELETE CASCADE: 0 dari 72 FK di seluruh layer analitik memakainya
--     (feature 16, l0_raw 24, l0_harmonization 14, l1_silver 16, l0_extra 2 --
--     semuanya NO ACTION). 18 CASCADE yang ada di database semuanya di schema
--     public, untuk baris anak yang dimiliki penuh induknya (agency_members,
--     brand_members, campaign_activities, report_items, dst). Dipakai NO ACTION,
--     sesuai perilaku FK existing.
--   - CHECK rentang 0-100: 0 CHECK constraint di seluruh database, semua schema.
--     Validasi rentang jadi tanggung jawab procedure pengisi.
--   - INDEX (brand_id): ditunda. uq_brand_fit_analysis sudah melayani query dari
--     sisi KOL (leftmost prefix); schema feature punya 0 index sekunder; dan
--     belum ada satu pun procedure/kode yang query dari sisi brand.
--
-- Yang DIADOPSI dari pola l1_silver:
--   - created_at/updated_at NOT NULL DEFAULT now() -- l1_silver memakainya
--     16/16 tanpa kecuali. Schema feature belum pernah; ini yang pertama.
--   - Penamaan uq_<tabel> -- l1_silver memakainya 8/8.
--   Penamaan FK fk_<tabel>_<tabel_tujuan> mengikuti schema feature sendiri
--   (fk_ig_audience_analysis_social_account), bukan pola auto-generate terpotong
--   yang dipakai kedua tabel lama.
--
-- Jalankan:
--   python apply_migration.py migrations/014_merge_brand_fit_analysis.sql --dry-run --yes
--   python apply_migration.py migrations/014_merge_brand_fit_analysis.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga. Batalkan kalau asumsi dasar sudah tidak berlaku.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    n_ig bigint;
    n_tt bigint;
BEGIN
    IF to_regclass('feature.brand_fit_analysis') IS NOT NULL THEN
        RAISE EXCEPTION
            'feature.brand_fit_analysis sudah ada -- migrasi dibatalkan.';
    END IF;

    SELECT count(*) INTO n_ig FROM feature.ig_brand_fit_analysis;
    SELECT count(*) INTO n_tt FROM feature.tt_brand_fit_analysis;

    -- Migrasi ini TIDAK memindahkan data. Kalau tabelnya sudah terisi,
    -- rencananya harus disusun ulang, bukan dipaksa jalan.
    IF n_ig <> 0 OR n_tt <> 0 THEN
        RAISE EXCEPTION
            'Tabel brand fit tidak lagi kosong (ig=%, tt=%). Migrasi ini tidak '
            'memindahkan data -- susun ulang rencana sebelum melanjutkan.',
            n_ig, n_tt;
    END IF;

    RAISE NOTICE 'Penjaga lolos: ig=% baris, tt=% baris, nama tujuan bebas.',
        n_ig, n_tt;
END $$;

-- ---------------------------------------------------------------------------
-- Langkah 1 -- tabel gabungan.
-- Sebelas kolom, sama persis dengan kedua tabel lama. Yang berubah hanya
-- constraint: NOT NULL pada dua kolom grain, plus UNIQUE grain.
-- ---------------------------------------------------------------------------
CREATE TABLE feature.brand_fit_analysis (
    id                    uuid         NOT NULL DEFAULT gen_random_uuid(),
    agency_kol_account_id uuid         NOT NULL,
    brand_id              uuid         NOT NULL,
    partnership_score     numeric(5,2),
    sub_scores            jsonb,
    audience_overlap_pct  numeric(5,2),
    overlap_summary       text,
    category_fit_tags     jsonb,
    recommendations       jsonb,
    created_at            timestamptz  NOT NULL DEFAULT now(),
    updated_at            timestamptz  NOT NULL DEFAULT now(),

    CONSTRAINT brand_fit_analysis_pkey PRIMARY KEY (id),

    -- NO ACTION (default) -- sesuai 16/16 FK existing di schema feature.
    CONSTRAINT fk_brand_fit_analysis_agency_kol_account
        FOREIGN KEY (agency_kol_account_id)
        REFERENCES public.agency_kol_accounts (id),

    CONSTRAINT fk_brand_fit_analysis_brand
        FOREIGN KEY (brand_id)
        REFERENCES public.brand (id),

    -- Grain: 1 KOL x 1 brand = 1 baris.
    -- Butuh NOT NULL di kedua kolom, karena PostgreSQL memperlakukan NULL
    -- sebagai nilai yang selalu berbeda di dalam UNIQUE -- tanpa NOT NULL,
    -- banyak baris ber-brand_id NULL untuk KOL yang sama tetap lolos.
    CONSTRAINT uq_brand_fit_analysis
        UNIQUE (agency_kol_account_id, brand_id)
);

-- ---------------------------------------------------------------------------
-- Langkah 2 -- dokumentasi in-database.
-- Project memakai COMMENT di l0_harmonization (8) dan l1_silver (4).
-- Dicatat di sini supaya alasan penggabungan ikut hidup di database,
-- bukan hanya di file migrasi.
-- ---------------------------------------------------------------------------
COMMENT ON TABLE feature.brand_fit_analysis IS
    'Skor kecocokan KOL x brand. Grain: (agency_kol_account_id, brand_id). '
    'Platform ditentukan public.agency_kol_accounts.platform_id, bukan nama tabel. '
    'Menggantikan feature.ig_brand_fit_analysis + feature.tt_brand_fit_analysis '
    '(migrasi 014).';

COMMENT ON COLUMN feature.brand_fit_analysis.partnership_score IS
    'Skor kecocokan 0-100. UI: gauge Partnership Score, badge match, '
    'sort default KOL Directory, filter brandFitMin.';
COMMENT ON COLUMN feature.brand_fit_analysis.sub_scores IS
    'Rincian skor per aspek. UI merender 4 bar: Category matching, '
    'Audience overlap, Values alignment, Past performance. Jangan menyalin '
    'audience_overlap_pct ke sini -- turunkan dari kolomnya agar tidak ada '
    'dua sumber kebenaran.';
COMMENT ON COLUMN feature.brand_fit_analysis.audience_overlap_pct IS
    'Persen irisan audiens KOL dengan audiens brand, 0-100. '
    'UI: donut Audience Overlap.';
COMMENT ON COLUMN feature.brand_fit_analysis.overlap_summary IS
    'Naratif generatif (bukan metric) yang menyertai donut Audience Overlap.';
COMMENT ON COLUMN feature.brand_fit_analysis.category_fit_tags IS
    'Pasangan (tag, cocok/tidak). UI: chips Category Fit dengan status on/off.';
COMMENT ON COLUMN feature.brand_fit_analysis.recommendations IS
    'Naratif generatif. UI: kartu Collaboration Recommendations, '
    'tiap item (icon, judul, deskripsi).';

-- ---------------------------------------------------------------------------
-- Langkah 3 -- buang tabel lama.
-- Sengaja TANPA CASCADE: kalau ada dependensi tak terduga, biar perintahnya
-- gagal dan seluruh transaksi dibatalkan, bukan diam-diam ikut menghapus
-- objek lain. Delapan constraint FK (empat di antaranya duplikat) dan dua
-- index PK ikut terbuang bersama tabelnya.
-- ---------------------------------------------------------------------------
DROP TABLE feature.ig_brand_fit_analysis;
DROP TABLE feature.tt_brand_fit_analysis;

-- ---------------------------------------------------------------------------
-- Langkah 4 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    n_kolom    int;
    n_fk       int;
    n_uq       int;
    n_notnull  int;
    n_ts       int;
    n_sisa     int;
    n_fk_ganda int;
BEGIN
    SELECT count(*) INTO n_kolom
    FROM information_schema.columns
    WHERE table_schema = 'feature' AND table_name = 'brand_fit_analysis';

    SELECT count(*) INTO n_notnull
    FROM information_schema.columns
    WHERE table_schema = 'feature' AND table_name = 'brand_fit_analysis'
      AND column_name IN ('agency_kol_account_id', 'brand_id')
      AND is_nullable = 'NO';

    SELECT count(*) INTO n_ts
    FROM information_schema.columns
    WHERE table_schema = 'feature' AND table_name = 'brand_fit_analysis'
      AND column_name IN ('created_at', 'updated_at')
      AND is_nullable = 'NO'
      AND column_default = 'now()';

    SELECT count(*) INTO n_fk
    FROM pg_constraint
    WHERE conrelid = 'feature.brand_fit_analysis'::regclass AND contype = 'f';

    SELECT count(*) INTO n_uq
    FROM pg_constraint
    WHERE conrelid = 'feature.brand_fit_analysis'::regclass AND contype = 'u';

    SELECT count(*) INTO n_sisa
    FROM pg_class c
    JOIN pg_namespace n2 ON n2.oid = c.relnamespace
    WHERE n2.nspname = 'feature'
      AND c.relname IN ('ig_brand_fit_analysis', 'tt_brand_fit_analysis');

    -- Tidak boleh ada lagi FK duplikat di seluruh schema feature.
    SELECT count(*) INTO n_fk_ganda FROM (
        SELECT c.conrelid, pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n3 ON n3.oid = t.relnamespace
        WHERE n3.nspname = 'feature' AND c.contype = 'f'
        GROUP BY 1, 2
        HAVING count(*) > 1
    ) x;

    IF n_kolom <> 11 THEN
        RAISE EXCEPTION 'Jumlah kolom %, seharusnya 11', n_kolom;
    END IF;
    IF n_notnull <> 2 THEN
        RAISE EXCEPTION 'Kolom grain NOT NULL %, seharusnya 2', n_notnull;
    END IF;
    IF n_ts <> 2 THEN
        RAISE EXCEPTION 'created_at/updated_at NOT NULL DEFAULT now() %, seharusnya 2', n_ts;
    END IF;
    IF n_fk <> 2 THEN
        RAISE EXCEPTION 'Jumlah FK %, seharusnya 2', n_fk;
    END IF;
    IF n_uq <> 1 THEN
        RAISE EXCEPTION 'Constraint UNIQUE grain tidak terbentuk (%)', n_uq;
    END IF;
    IF n_sisa <> 0 THEN
        RAISE EXCEPTION 'Masih ada % tabel brand fit lama', n_sisa;
    END IF;
    IF n_fk_ganda <> 0 THEN
        RAISE EXCEPTION 'Masih ada % FK duplikat di schema feature', n_fk_ganda;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: 11 kolom, 2 kolom grain NOT NULL, '
                 '2 timestamp NOT NULL DEFAULT now(), 2 FK, 1 UNIQUE grain, '
                 '0 tabel lama tersisa, 0 FK duplikat di schema feature.';
END $$;

COMMIT;
