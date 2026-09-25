-- 054_curated_classification_storage.sql
--
-- Persistent storage for CURATED classification (human review / best-effort values approved
-- by the mentor) that has no semantically correct home yet. No new tables.
--
--   1. Creator Category + Subcategory  -> public.kol_directory.inferred_*
--      The source constraint is widened to 'creator_classification' OR 'curated'.
--      creator_classification_writer never touches 'curated' rows (same pattern as
--      kol_attribute_map since 052). No new columns.
--
--   2. Audience Gender / Age / Country / City  -> feature.{ig,tt}_audience_analysis.curated_*
--      Curated LABEL columns on the existing Analysis Audience row, following the
--      interest_top / interest_source pattern (039). They are separate from the
--      measurement columns (gender_breakdown, age_gender_breakdown, geo_distribution,
--      female_pct/male_pct): the audience_feature asset UPSERTs with an explicit SET
--      list that does not include curated_*, so these values persist across runs.
--      audience_classification uses them ONLY when the measured/inferred result is Unknown.
--
-- No existing row is changed or deleted. Measurement columns, updated_at, l0_raw,
-- l0_harmonization, l1_silver, and l2_gold are not touched.
--
-- SAFE TO RE-RUN: ADD COLUMN IF NOT EXISTS / DROP CONSTRAINT IF EXISTS.
--
-- ROLLBACK
--   ALTER TABLE feature.ig_audience_analysis DROP COLUMN IF EXISTS curated_gender, DROP COLUMN IF EXISTS curated_age,
--       DROP COLUMN IF EXISTS curated_country, DROP COLUMN IF EXISTS curated_city, DROP COLUMN IF EXISTS curated_evidence;
--   (same for feature.tt_audience_analysis)
--   Clear inferred_* rows whose source is 'curated' first, then restore
--   ck_kd_inferred_category_source to CHECK (inferred_category_source IS NULL
--       OR inferred_category_source = 'creator_classification').
-- ============================================================================

BEGIN;
SET LOCAL lock_timeout = '10s';

CREATE TEMP TABLE _sebelum_054 ON COMMIT DROP AS
SELECT (SELECT count(*) FROM public.kol_directory) AS kd_total,
       (SELECT md5(string_agg(to_jsonb(k)::text, '|' ORDER BY k.id::text)) FROM public.kol_directory k) AS kd_md5,
       (SELECT count(*) FROM feature.ig_audience_analysis) AS ig_total,
       (SELECT md5(string_agg(to_jsonb(t)::text, '|' ORDER BY t.id::text)) FROM feature.ig_audience_analysis t) AS ig_md5,
       (SELECT count(*) FROM feature.tt_audience_analysis) AS tt_total,
       (SELECT md5(string_agg(to_jsonb(t)::text, '|' ORDER BY t.id::text)) FROM feature.tt_audience_analysis t) AS tt_md5;

-- 1. CREATOR CATEGORY + SUBCATEGORY: allow source 'curated' ---------------------
ALTER TABLE public.kol_directory DROP CONSTRAINT IF EXISTS ck_kd_inferred_category_source;
ALTER TABLE public.kol_directory ADD CONSTRAINT ck_kd_inferred_category_source
    CHECK (inferred_category_source IS NULL
           OR inferred_category_source IN ('creator_classification', 'curated'));

COMMENT ON COLUMN public.kol_directory.inferred_category_source IS
    '''creator_classification'' (classifier output; rewritten by the writer on every run) or '
    '''curated'' (human review / approved best-effort; NEVER overwritten by the writer). '
    'NULL when empty. Per-field provenance lives in inferred_category_evidence.';

-- 2. CURATED AUDIENCE LABELS on the Analysis Audience row ---------------------
DO $$
DECLARE t text; p text;
BEGIN
    FOREACH t IN ARRAY ARRAY['ig_audience_analysis', 'tt_audience_analysis'] LOOP
        p := left(t, 2);
        EXECUTE format($f$
            ALTER TABLE feature.%1$I
                ADD COLUMN IF NOT EXISTS curated_gender   varchar(10),
                ADD COLUMN IF NOT EXISTS curated_age      varchar(10),
                ADD COLUMN IF NOT EXISTS curated_country  varchar(2),
                ADD COLUMN IF NOT EXISTS curated_city     varchar(100),
                ADD COLUMN IF NOT EXISTS curated_evidence jsonb;
            ALTER TABLE feature.%1$I
                DROP CONSTRAINT IF EXISTS ck_%2$s_aa_curated_gender,
                DROP CONSTRAINT IF EXISTS ck_%2$s_aa_curated_age,
                DROP CONSTRAINT IF EXISTS ck_%2$s_aa_curated_country,
                DROP CONSTRAINT IF EXISTS ck_%2$s_aa_curated_city;
            ALTER TABLE feature.%1$I
                ADD CONSTRAINT ck_%2$s_aa_curated_gender
                    CHECK (curated_gender IS NULL OR curated_gender IN ('female', 'male', 'balanced')),
                ADD CONSTRAINT ck_%2$s_aa_curated_age
                    CHECK (curated_age IS NULL OR curated_age IN ('13-17', '18-24', '25-34', '35-44', '45+')),
                ADD CONSTRAINT ck_%2$s_aa_curated_country
                    CHECK (curated_country IS NULL OR curated_country ~ '^[A-Z]{2}$'),
                ADD CONSTRAINT ck_%2$s_aa_curated_city
                    CHECK (curated_city IS NULL OR btrim(curated_city) <> '');
            COMMENT ON COLUMN feature.%1$I.curated_gender IS
                'Curated audience gender LABEL (female/male/balanced), not a count. Used only when the result '
                'from gender_breakdown/female_pct is Unknown. Not written by audience_feature.';
            COMMENT ON COLUMN feature.%1$I.curated_age IS
                'Curated audience age-bracket LABEL, not a count. Fallback for age_gender_breakdown.';
            COMMENT ON COLUMN feature.%1$I.curated_country IS
                'Curated audience country LABEL (ISO-2), not a count. Fallback for geo_distribution / audience_geo_daily.';
            COMMENT ON COLUMN feature.%1$I.curated_city IS
                'Curated audience city LABEL, not a count. Fallback for geo_distribution / audience_geo_daily.';
            COMMENT ON COLUMN feature.%1$I.curated_evidence IS
                'Per-field provenance of curated_*: {field: {method, confidence, evidence, source, reason}}.';
        $f$, t, p);
    END LOOP;
END $$;

-- 3. VERIFICATION -------------------------------------------------------------
DO $$
DECLARE s record;
BEGIN
    SELECT * INTO s FROM _sebelum_054;
    IF (SELECT count(*) FROM public.kol_directory) <> s.kd_total
       OR (SELECT md5(string_agg(to_jsonb(k)::text, '|' ORDER BY k.id::text)) FROM public.kol_directory k) <> s.kd_md5 THEN
        RAISE EXCEPTION '054: kol_directory changed';
    END IF;
    -- existing rows unchanged: every column except the new (still NULL) curated_* columns
    IF (SELECT count(*) FROM feature.ig_audience_analysis) <> s.ig_total
       OR (SELECT md5(string_agg((to_jsonb(t) - 'curated_gender' - 'curated_age' - 'curated_country'
               - 'curated_city' - 'curated_evidence')::text, '|' ORDER BY t.id::text))
             FROM feature.ig_audience_analysis t) <> s.ig_md5 THEN
        RAISE EXCEPTION '054: feature.ig_audience_analysis changed';
    END IF;
    IF (SELECT count(*) FROM feature.tt_audience_analysis) <> s.tt_total
       OR (SELECT md5(string_agg((to_jsonb(t) - 'curated_gender' - 'curated_age' - 'curated_country'
               - 'curated_city' - 'curated_evidence')::text, '|' ORDER BY t.id::text))
             FROM feature.tt_audience_analysis t) <> s.tt_md5 THEN
        RAISE EXCEPTION '054: feature.tt_audience_analysis changed';
    END IF;
    IF (SELECT count(*) FROM feature.ig_audience_analysis WHERE curated_gender IS NOT NULL OR curated_age IS NOT NULL
           OR curated_country IS NOT NULL OR curated_city IS NOT NULL) > 0 THEN
        RAISE EXCEPTION '054: curated_* must still be empty';
    END IF;
END $$;

COMMIT;
