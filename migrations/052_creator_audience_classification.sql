-- 052_creator_audience_classification.sql
--
-- Storage MINIMAL untuk hasil Creator + Audience Classification
-- (creator_classification.py, audience_classification.py; penulisnya
-- creator_classification_writer.py). Semua perubahan adalah ADD COLUMN /
-- CHECK / FK / index / trigger validasi pada tabel EXISTING. Tidak ada tabel
-- baru, tidak ada tabel taxonomy/classification baru, dan tidak satu baris
-- pun diubah atau dihapus.
--
-- ============================================================================
-- KENAPA PERLU, PER OUTPUT
-- ============================================================================
--
-- Creator Category + Subcategory  -> public.kol_directory.inferred_*
--   `kol_directory.category_id/category_ids` dan `agency_kol_accounts.
--   category_id` adalah mapping roster KURASI (excel_import) dan tidak boleh
--   ditimpa hasil inferensi. Mapping KOL -> Sub Category belum punya field
--   sama sekali (kol_sub_category_taxonomy.py). Dua kolom FK ke
--   public.kol_categories -- satu-satunya sumber taxonomy -- dengan source,
--   confidence, dan evidence, di tabel yang sama dengan mapping kurasinya
--   supaya keduanya bisa dibandingkan tanpa join tambahan. Relasi induk-anak
--   (subcategory.parent_id = category.id) tidak bisa diungkapkan dengan FK
--   biasa tanpa mengubah kol_categories, jadi ditegakkan trigger validasi.
--
-- Creator Style + Personality  -> public.kol_attribute_map + source/confidence/evidence
--   Satu-satunya storage per-KOL untuk kedua output ini (migration 045), tapi
--   045 mendefinisikannya sebagai kurasi manual. Tanpa penanda, hasil
--   classifier akan terbaca sebagai kurasi. `source` DEFAULT 'curated' membuat
--   setiap baris lama/manual tetap kurasi; baris classifier WAJIB membawa
--   source 'creator_classification' + confidence.
--
-- Audience Age / City / Country / Interest  -> l2_gold.kol_profile_card.audience_*
--   Sebaran audiens sudah ada (feature.{ig,tt}_audience_analysis,
--   l2_gold.audience_{demographics,geo,interest}_daily), dan kartu sudah
--   memegang ringkasan gender (female_pct/male_pct/gender_known_pct) serta
--   audience_interest_top. Yang belum ada: ringkasan umur, kota, negara, dan
--   segmen interest (kosakata Autometric_research `interest_segment`).
--   Ditambahkan ke kartu, sejajar dengan audience_interest_top.
--
-- Creator Gender/Age dan Audience Gender TIDAK butuh kolom baru: sudah ada
-- di kartu (041/042/051 dan female_pct/male_pct) dan diisi asset production.
--
-- AMAN DIJALANKAN BERULANG: IF NOT EXISTS / DROP ... IF EXISTS / OR REPLACE.
--
-- ROLLBACK
--   DROP TRIGGER IF EXISTS trg_kd_inferred_category ON public.kol_directory;
--   DROP FUNCTION IF EXISTS public.fn_kd_inferred_category_check();
--   ALTER TABLE public.kol_directory
--       DROP COLUMN inferred_category_id, DROP COLUMN inferred_subcategory_id,
--       DROP COLUMN inferred_category_source, DROP COLUMN inferred_category_confidence,
--       DROP COLUMN inferred_subcategory_confidence, DROP COLUMN inferred_category_evidence,
--       DROP COLUMN inferred_category_at;
--   ALTER TABLE public.kol_attribute_map
--       DROP COLUMN source, DROP COLUMN confidence, DROP COLUMN evidence;
--   ALTER TABLE l2_gold.kol_profile_card
--       DROP COLUMN audience_age_top, DROP COLUMN audience_city_top,
--       DROP COLUMN audience_country_top, DROP COLUMN audience_interest_segment,
--       DROP COLUMN audience_classification_source,
--       DROP COLUMN audience_classification_evidence;
--   (CHECK/FK/index ikut terhapus bersama kolomnya.)
-- ============================================================================

BEGIN;

-- ALTER TABLE butuh ACCESS EXCLUSIVE. Kalau ada transaksi lain yang memegang
-- kol_directory/kol_profile_card, gagal cepat -- jangan mengantre dan membuat
-- semua pembaca lain ikut tertahan di belakang ALTER ini.
SET LOCAL lock_timeout = '10s';

CREATE TEMP TABLE _sebelum_052 ON COMMIT DROP AS
SELECT (SELECT count(*) FROM public.kol_directory)     AS kd_total,
       (SELECT count(*) FROM public.kol_attribute_map) AS map_total,
       (SELECT count(*) FROM l2_gold.kol_profile_card) AS kartu_total,
       (SELECT count(*) FROM public.kol_categories)    AS taxonomy_total,
       (SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) FROM public.kol_categories t) AS taxonomy_md5;

-- ============================================================================
-- 1. CREATOR CATEGORY + SUBCATEGORY  (public.kol_directory)
-- ============================================================================
ALTER TABLE public.kol_directory
    ADD COLUMN IF NOT EXISTS inferred_category_id            uuid,
    ADD COLUMN IF NOT EXISTS inferred_subcategory_id         uuid,
    ADD COLUMN IF NOT EXISTS inferred_category_source        varchar(32),
    ADD COLUMN IF NOT EXISTS inferred_category_confidence    varchar(10),
    ADD COLUMN IF NOT EXISTS inferred_subcategory_confidence varchar(10),
    ADD COLUMN IF NOT EXISTS inferred_category_evidence      jsonb,
    ADD COLUMN IF NOT EXISTS inferred_category_at            timestamptz;

ALTER TABLE public.kol_directory
    DROP CONSTRAINT IF EXISTS fk_kd_inferred_category,
    DROP CONSTRAINT IF EXISTS fk_kd_inferred_subcategory,
    DROP CONSTRAINT IF EXISTS ck_kd_inferred_category_source,
    DROP CONSTRAINT IF EXISTS ck_kd_inferred_confidence,
    DROP CONSTRAINT IF EXISTS ck_kd_inferred_category_lengkap,
    DROP CONSTRAINT IF EXISTS ck_kd_inferred_subcategory_lengkap;

ALTER TABLE public.kol_directory
    ADD CONSTRAINT fk_kd_inferred_category
        FOREIGN KEY (inferred_category_id) REFERENCES public.kol_categories(id),
    ADD CONSTRAINT fk_kd_inferred_subcategory
        FOREIGN KEY (inferred_subcategory_id) REFERENCES public.kol_categories(id),
    ADD CONSTRAINT ck_kd_inferred_category_source
        CHECK (inferred_category_source IS NULL
               OR inferred_category_source = 'creator_classification'),
    ADD CONSTRAINT ck_kd_inferred_confidence
        CHECK ((inferred_category_confidence IS NULL
                OR inferred_category_confidence IN ('high', 'medium', 'low'))
           AND (inferred_subcategory_confidence IS NULL
                OR inferred_subcategory_confidence IN ('high', 'medium', 'low'))),
    -- Kategori hasil inferensi tanpa asal/confidence tidak boleh ada.
    ADD CONSTRAINT ck_kd_inferred_category_lengkap
        CHECK ((inferred_category_id IS NULL AND inferred_category_source IS NULL
                AND inferred_category_confidence IS NULL)
            OR (inferred_category_id IS NOT NULL AND inferred_category_source IS NOT NULL
                AND inferred_category_confidence IS NOT NULL)),
    -- Subcategory selalu bersama kategorinya.
    ADD CONSTRAINT ck_kd_inferred_subcategory_lengkap
        CHECK ((inferred_subcategory_id IS NULL AND inferred_subcategory_confidence IS NULL)
            OR (inferred_subcategory_id IS NOT NULL AND inferred_category_id IS NOT NULL
                AND inferred_subcategory_confidence IS NOT NULL));

-- Level dan relasi induk-anak dari kol_categories: category = baris canonical
-- (level 'category', tanpa parent, punya code); subcategory = baris
-- 'sub_category' dengan parent_id = inferred_category_id. Hanya membaca
-- kol_categories; hanya aktif kalau salah satu kolom inferred diisi.
CREATE OR REPLACE FUNCTION public.fn_kd_inferred_category_check() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.inferred_category_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.kol_categories c
         WHERE c.id = NEW.inferred_category_id AND c.level = 'category'
           AND c.parent_id IS NULL AND c.code IS NOT NULL) THEN
        RAISE EXCEPTION 'inferred_category_id % bukan kategori canonical', NEW.inferred_category_id;
    END IF;
    IF NEW.inferred_subcategory_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.kol_categories s
         WHERE s.id = NEW.inferred_subcategory_id AND s.level = 'sub_category'
           AND s.parent_id = NEW.inferred_category_id) THEN
        RAISE EXCEPTION 'inferred_subcategory_id % bukan anak (parent_id) dari %',
            NEW.inferred_subcategory_id, NEW.inferred_category_id;
    END IF;
    RETURN NEW;
END
$fn$;

DROP TRIGGER IF EXISTS trg_kd_inferred_category ON public.kol_directory;
CREATE TRIGGER trg_kd_inferred_category
    BEFORE INSERT OR UPDATE OF inferred_category_id, inferred_subcategory_id
    ON public.kol_directory
    FOR EACH ROW
    WHEN (NEW.inferred_category_id IS NOT NULL OR NEW.inferred_subcategory_id IS NOT NULL)
    EXECUTE FUNCTION public.fn_kd_inferred_category_check();

CREATE INDEX IF NOT EXISTS ix_kd_inferred_category
    ON public.kol_directory (inferred_category_id) WHERE inferred_category_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_kd_inferred_subcategory
    ON public.kol_directory (inferred_subcategory_id) WHERE inferred_subcategory_id IS NOT NULL;

COMMENT ON COLUMN public.kol_directory.inferred_category_id IS
    'Category KREATOR hasil creator_classification (FK kol_categories, level '
    '''category'', canonical). TERPISAH dari category_id/category_ids (mapping '
    'roster kurasi) dan tidak pernah menimpanya. Nama tampilan = kol_categories.name.';
COMMENT ON COLUMN public.kol_directory.inferred_subcategory_id IS
    'Subcategory KREATOR hasil creator_classification (FK kol_categories, level '
    '''sub_category'', parent_id = inferred_category_id -- ditegakkan '
    'trg_kd_inferred_category). NULL = tidak cukup bukti.';
COMMENT ON COLUMN public.kol_directory.inferred_category_source IS
    '''creator_classification'' untuk setiap nilai inferred_*; NULL kalau kosong.';
COMMENT ON COLUMN public.kol_directory.inferred_category_evidence IS
    'Bukti + alasan (dasar roster/inferensi, istilah yang cocok, bobot). Tanpa PII/NIK.';

-- ============================================================================
-- 2. CREATOR STYLE + PERSONALITY  (public.kol_attribute_map)
-- ============================================================================
ALTER TABLE public.kol_attribute_map
    ADD COLUMN IF NOT EXISTS source     varchar(32) NOT NULL DEFAULT 'curated',
    ADD COLUMN IF NOT EXISTS confidence varchar(10),
    ADD COLUMN IF NOT EXISTS evidence   jsonb;

ALTER TABLE public.kol_attribute_map
    DROP CONSTRAINT IF EXISTS ck_kol_attribute_map_source,
    DROP CONSTRAINT IF EXISTS ck_kol_attribute_map_confidence,
    DROP CONSTRAINT IF EXISTS ck_kol_attribute_map_classifier_lengkap;

ALTER TABLE public.kol_attribute_map
    ADD CONSTRAINT ck_kol_attribute_map_source
        CHECK (source IN ('curated', 'creator_classification')),
    ADD CONSTRAINT ck_kol_attribute_map_confidence
        CHECK (confidence IS NULL OR confidence IN ('high', 'medium', 'low')),
    ADD CONSTRAINT ck_kol_attribute_map_classifier_lengkap
        CHECK (source = 'curated' OR confidence IS NOT NULL);

COMMENT ON COLUMN public.kol_attribute_map.source IS
    '''curated'' (default; kurasi manual, 045) atau ''creator_classification'' '
    '(hasil classifier; tidak pernah menimpa/menyaingi baris curated di kind yang sama).';
COMMENT ON COLUMN public.kol_attribute_map.confidence IS
    'high/medium/low untuk baris creator_classification; NULL untuk curated.';
COMMENT ON COLUMN public.kol_attribute_map.evidence IS
    'Bukti + alasan baris creator_classification. Tanpa PII.';

-- ============================================================================
-- 3. AUDIENCE AGE / CITY / COUNTRY / INTEREST  (l2_gold.kol_profile_card)
-- ============================================================================
ALTER TABLE l2_gold.kol_profile_card
    ADD COLUMN IF NOT EXISTS audience_age_top                 varchar(8),
    ADD COLUMN IF NOT EXISTS audience_city_top                varchar(64),
    ADD COLUMN IF NOT EXISTS audience_country_top             varchar(2),
    ADD COLUMN IF NOT EXISTS audience_interest_segment        varchar(40),
    ADD COLUMN IF NOT EXISTS audience_classification_source   varchar(32),
    ADD COLUMN IF NOT EXISTS audience_classification_evidence jsonb;

ALTER TABLE l2_gold.kol_profile_card
    DROP CONSTRAINT IF EXISTS ck_kpc_audience_age_top,
    DROP CONSTRAINT IF EXISTS ck_kpc_audience_country_top,
    DROP CONSTRAINT IF EXISTS ck_kpc_audience_interest_segment,
    DROP CONSTRAINT IF EXISTS ck_kpc_audience_classification_source,
    DROP CONSTRAINT IF EXISTS ck_kpc_audience_classification_lengkap;

ALTER TABLE l2_gold.kol_profile_card
    ADD CONSTRAINT ck_kpc_audience_age_top
        CHECK (audience_age_top IS NULL
               OR audience_age_top IN ('13-17', '18-24', '25-34', '35-44', '45+')),
    ADD CONSTRAINT ck_kpc_audience_country_top
        CHECK (audience_country_top IS NULL OR audience_country_top ~ '^[A-Z]{2}$'),
    -- Kosakata `interest_segment` Autometric_research, tanpa 'General/Unclear'
    -- (itu NULL di sini).
    ADD CONSTRAINT ck_kpc_audience_interest_segment
        CHECK (audience_interest_segment IS NULL OR audience_interest_segment IN (
               'Islamic/Religious & Civic', 'Fashion & Lifestyle',
               'Business & Entrepreneurship', 'Entertainment & Pop Culture',
               'Tech & Digital', 'Sports & Fitness', 'Family & Parenting',
               'Food & Culinary', 'Travel', 'Education', 'Politics & Government')),
    ADD CONSTRAINT ck_kpc_audience_classification_source
        CHECK (audience_classification_source IS NULL
               OR audience_classification_source = 'audience_classification'),
    ADD CONSTRAINT ck_kpc_audience_classification_lengkap
        CHECK ((audience_age_top IS NULL AND audience_city_top IS NULL
                AND audience_country_top IS NULL AND audience_interest_segment IS NULL)
            OR audience_classification_source IS NOT NULL);

COMMENT ON COLUMN l2_gold.kol_profile_card.audience_age_top IS
    'Bucket umur AUDIENS dominan (bio follower, creator_age_inference). Bukan umur kreator.';
COMMENT ON COLUMN l2_gold.kol_profile_card.audience_city_top IS
    'Kota AUDIENS dominan dari l2_gold.audience_geo_daily (geo_level city). '
    'Bukan kota kreator (kol_directory.creator_city).';
COMMENT ON COLUMN l2_gold.kol_profile_card.audience_country_top IS
    'Negara AUDIENS dominan (ISO-2) dari l2_gold.audience_geo_daily (geo_level country).';
COMMENT ON COLUMN l2_gold.kol_profile_card.audience_interest_segment IS
    'Segmen interest AUDIENS (kosakata Autometric_research interest_segment) dari '
    'sebaran interest follower. Bukan category kreator.';
COMMENT ON COLUMN l2_gold.kol_profile_card.audience_classification_evidence IS
    'Per field: sumber tabel, jumlah follower diketahui, share, confidence, alasan.';

-- ============================================================================
-- VERIFIKASI
-- ============================================================================
DO $verifikasi$
DECLARE
    n bigint;
    s record;
BEGIN
    SELECT * INTO s FROM _sebelum_052;

    SELECT count(*) INTO n FROM information_schema.columns
     WHERE (table_schema, table_name, column_name) IN (
        ('public', 'kol_directory', 'inferred_category_id'),
        ('public', 'kol_directory', 'inferred_subcategory_id'),
        ('public', 'kol_directory', 'inferred_category_source'),
        ('public', 'kol_directory', 'inferred_category_confidence'),
        ('public', 'kol_directory', 'inferred_subcategory_confidence'),
        ('public', 'kol_directory', 'inferred_category_evidence'),
        ('public', 'kol_directory', 'inferred_category_at'),
        ('public', 'kol_attribute_map', 'source'),
        ('public', 'kol_attribute_map', 'confidence'),
        ('public', 'kol_attribute_map', 'evidence'),
        ('l2_gold', 'kol_profile_card', 'audience_age_top'),
        ('l2_gold', 'kol_profile_card', 'audience_city_top'),
        ('l2_gold', 'kol_profile_card', 'audience_country_top'),
        ('l2_gold', 'kol_profile_card', 'audience_interest_segment'),
        ('l2_gold', 'kol_profile_card', 'audience_classification_source'),
        ('l2_gold', 'kol_profile_card', 'audience_classification_evidence'));
    IF n <> 16 THEN
        RAISE EXCEPTION 'Kolom terpasang % dari 16', n;
    END IF;

    SELECT count(*) INTO n FROM pg_trigger
     WHERE tgname = 'trg_kd_inferred_category' AND NOT tgisinternal;
    IF n <> 1 THEN
        RAISE EXCEPTION 'Trigger trg_kd_inferred_category tidak terpasang';
    END IF;

    -- Tidak ada baris yang berubah / bertambah / hilang.
    IF (SELECT count(*) FROM public.kol_directory) <> s.kd_total
       OR (SELECT count(*) FROM public.kol_attribute_map) <> s.map_total
       OR (SELECT count(*) FROM l2_gold.kol_profile_card) <> s.kartu_total THEN
        RAISE EXCEPTION 'Jumlah baris berubah';
    END IF;
    IF (SELECT count(*) FROM public.kol_categories) <> s.taxonomy_total
       OR (SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) FROM public.kol_categories t)
          IS DISTINCT FROM s.taxonomy_md5 THEN
        RAISE EXCEPTION 'kol_categories berubah';
    END IF;

    -- Baris classifier selalu lengkap (CHECK sudah memaksa; ini jaring kedua
    -- untuk run ulang setelah writer jalan).
    SELECT count(*) INTO n FROM public.kol_attribute_map
     WHERE source = 'creator_classification' AND confidence IS NULL;
    IF n <> 0 THEN
        RAISE EXCEPTION '% baris classifier tanpa confidence', n;
    END IF;
END
$verifikasi$;

COMMIT;
