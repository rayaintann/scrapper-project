-- 053_drop_redundant_card_audience_classification.sql
--
-- Membatalkan bagian AUDIENCE dari migration 052: enam kolom
-- l2_gold.kol_profile_card.audience_{age_top,city_top,country_top,
-- interest_segment,classification_source,classification_evidence}.
--
-- KENAPA
--   Audit alur Audience Analysis (l1_silver.unified_follower -> asset
--   audience_feature -> feature.{ig,tt}_audience_analysis -> asset
--   audience_gold -> l2_gold.audience_{demographics,geo,interest}_daily)
--   membuktikan:
--     * sumber kebenaran audiens adalah feature.*_audience_analysis (dan
--       ekspansinya di L2), dihitung dari bukti per-follower;
--     * untuk 29/29 akun yang punya follower, isi feature identik dengan
--       hitung ulang logika audience_feature atas unified_follower -- tidak
--       ada celah yang perlu diisi;
--     * keenam kolom kartu di bawah hanyalah ringkasan ULANG dari tabel yang
--       sama, tidak dibaca pembaca mana pun (Feature, L2, Discovery,
--       Brand Match), dan `audience_interest_segment` memperkenalkan definisi
--       interest kedua.
--   Dua sumber kebenaran untuk audiens tidak dipertahankan. Hasil Audience
--   Classification sekarang dibaca langsung dari feature/L2
--   (audience_classification.load), tidak ditulis ke tempat lain.
--
-- Yang TIDAK disentuh: female_pct, male_pct, gender_known_pct,
-- gender_reliability, audience_interest_top/_source, audience_quality_*
-- (kolom kartu existing dari asset kol_profile_card), semua tabel feature/L2
-- audiens, dan seluruh bagian creator dari 052 (kol_directory.inferred_*,
-- kol_attribute_map.source/confidence/evidence).
--
-- Data yang hilang: hanya isi keenam kolom itu (29 baris ringkasan turunan
-- yang bisa dihitung ulang kapan pun dari feature/L2).
--
-- AMAN DIJALANKAN BERULANG: DROP COLUMN IF EXISTS.
--
-- ROLLBACK: jalankan ulang bagian 3 migration 052.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '10s';

-- Sidik jari kartu atas kolom yang TETAP ADA, sebelum DROP.
CREATE TEMP TABLE _sebelum_053 ON COMMIT DROP AS
SELECT count(*) AS kartu_total,
       md5(string_agg(row(
           t.id, t.social_account_id, t.platform, t.username, t.female_pct, t.male_pct,
           t.gender_known_pct, t.gender_reliability, t.audience_interest_top,
           t.audience_interest_source, t.audience_quality_score, t.authenticity_score,
           t.audience_quality_tier, t.creator_gender, t.creator_gender_source,
           t.creator_gender_confidence, t.creator_age, t.creator_age_band,
           t.creator_age_source, t.creator_age_confidence, t.updated_at)::text,
           '|' ORDER BY t.id)) AS kartu_md5
  FROM l2_gold.kol_profile_card t;

ALTER TABLE l2_gold.kol_profile_card
    DROP COLUMN IF EXISTS audience_age_top,
    DROP COLUMN IF EXISTS audience_city_top,
    DROP COLUMN IF EXISTS audience_country_top,
    DROP COLUMN IF EXISTS audience_interest_segment,
    DROP COLUMN IF EXISTS audience_classification_source,
    DROP COLUMN IF EXISTS audience_classification_evidence;

DO $verifikasi$
DECLARE
    n bigint;
    s record;
BEGIN
    SELECT * INTO s FROM _sebelum_053;

    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('audience_age_top', 'audience_city_top', 'audience_country_top',
                           'audience_interest_segment', 'audience_classification_source',
                           'audience_classification_evidence');
    IF n <> 0 THEN
        RAISE EXCEPTION 'Masih ada % kolom audience classification di kartu', n;
    END IF;

    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = 'l2_gold.kol_profile_card'::regclass
       AND conname IN ('ck_kpc_audience_age_top', 'ck_kpc_audience_country_top',
                       'ck_kpc_audience_interest_segment',
                       'ck_kpc_audience_classification_source',
                       'ck_kpc_audience_classification_lengkap');
    IF n <> 0 THEN
        RAISE EXCEPTION 'Masih ada % CHECK audience classification', n;
    END IF;

    -- Kolom existing kartu (audiens production + creator) tetap utuh.
    IF (SELECT count(*) FROM l2_gold.kol_profile_card) <> s.kartu_total
       OR (SELECT md5(string_agg(row(
               t.id, t.social_account_id, t.platform, t.username, t.female_pct, t.male_pct,
               t.gender_known_pct, t.gender_reliability, t.audience_interest_top,
               t.audience_interest_source, t.audience_quality_score, t.authenticity_score,
               t.audience_quality_tier, t.creator_gender, t.creator_gender_source,
               t.creator_gender_confidence, t.creator_age, t.creator_age_band,
               t.creator_age_source, t.creator_age_confidence, t.updated_at)::text,
               '|' ORDER BY t.id))
             FROM l2_gold.kol_profile_card t) IS DISTINCT FROM s.kartu_md5 THEN
        RAISE EXCEPTION 'Kolom existing kol_profile_card berubah';
    END IF;

    -- Bagian creator dari 052 tetap terpasang.
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE (table_schema, table_name, column_name) IN (
        ('public', 'kol_directory', 'inferred_category_id'),
        ('public', 'kol_directory', 'inferred_subcategory_id'),
        ('public', 'kol_attribute_map', 'source'));
    IF n <> 3 THEN
        RAISE EXCEPTION 'Kolom creator classification 052 hilang (% dari 3)', n;
    END IF;
END
$verifikasi$;

COMMIT;
