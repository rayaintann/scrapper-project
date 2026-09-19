-- 051_creator_gender_columns.sql
--
-- Tiga kolom untuk GENDER KREATOR di KOL Discovery, pola yang sama dengan
-- creator_age (042/044):
--
--     creator_gender             'female' | 'male' | NULL (tidak diketahui)
--     creator_gender_source      dari mana nilainya datang
--     creator_gender_confidence  seberapa kuat buktinya
--
-- Aditif dan nullable. Tidak ada tabel baru, tidak ada schema baru, tidak ada
-- DROP, tidak ada perubahan tipe, dan tidak satu baris pun diubah atau dihapus.
-- Pengisinya asset `creator_gender` (orchestration/kol_orchestration/assets/
-- creator_gender.py), yang ikut `transform_chain_job` setelah kol_profile_card.
--
-- ============================================================================
-- INI BUKAN GENDER AUDIENCE. JANGAN DIGABUNG.
-- ============================================================================
--
--     Gender Kreator    jenis kelamin ORANG KOL-nya     -> kolom di migration INI
--     Gender Audience   sebaran jenis kelamin PENGIKUT  -> female_pct, male_pct,
--                                                          gender_known_pct,
--                                                          gender_reliability,
--                                                          audience_demographics_daily
--
-- Brand Profile `gender_majority` = Female/Male menyaring Discovery dengan kolom
-- INI, bukan dengan female_pct/male_pct.
--
-- ============================================================================
-- SUMBER DAN URUTAN PRIORITAS (ditegakkan asset, bukan DDL)
-- ============================================================================
--
--     manual           diisi manusia; TIDAK PERNAH ditimpa pipeline
--     roster           l0_raw.kol_roster_import.influencer_gender
--                      (1 = female, 0 = male). Arti kode ini BUKTI DATA --
--                      cocok dengan digit jenis kelamin NIK 15/15 dan 49/51 --
--                      belum kontrak resmi pemilik data.
--     name_inference   creator_gender_inference.py dari username + display
--                      name, aturan konservatif (precision Female ~98%, Male
--                      ~76% terhadap roster). Tidak pernah menimpa roster.
--     NULL             sisanya, dan itu mayoritas.
--
-- NULL berarti "tidak diketahui" dan adalah keadaan normal: platform tidak
-- mengekspos gender kreator. Filter Female/Male di Discovery TIDAK
-- meloloskan baris NULL.
--
-- AMAN DIJALANKAN BERULANG: ADD COLUMN IF NOT EXISTS, DROP CONSTRAINT IF EXISTS.
--
-- ROLLBACK
--   DROP INDEX IF EXISTS l2_gold.ix_kpc_creator_gender;
--   ALTER TABLE l2_gold.kol_profile_card
--       DROP COLUMN creator_gender, DROP COLUMN creator_gender_source,
--       DROP COLUMN creator_gender_confidence;
--   (CHECK ikut terhapus bersama kolomnya.)
-- ============================================================================

BEGIN;

CREATE TEMP TABLE _sebelum_051 ON COMMIT DROP AS
SELECT count(*) AS kartu_total FROM l2_gold.kol_profile_card;

ALTER TABLE l2_gold.kol_profile_card
    ADD COLUMN IF NOT EXISTS creator_gender            varchar(10),
    ADD COLUMN IF NOT EXISTS creator_gender_source     varchar(30),
    ADD COLUMN IF NOT EXISTS creator_gender_confidence varchar(10);

ALTER TABLE l2_gold.kol_profile_card
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_gender,
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_gender_source,
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_gender_confidence,
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_gender_lengkap;

ALTER TABLE l2_gold.kol_profile_card
    ADD CONSTRAINT ck_kpc_creator_gender
        CHECK (creator_gender IS NULL OR creator_gender IN ('female', 'male')),
    ADD CONSTRAINT ck_kpc_creator_gender_source
        CHECK (creator_gender_source IS NULL OR creator_gender_source IN
               ('manual', 'roster', 'name_inference')),
    ADD CONSTRAINT ck_kpc_creator_gender_confidence
        CHECK (creator_gender_confidence IS NULL OR creator_gender_confidence IN
               ('high', 'medium', 'low')),
    -- Nilai tanpa asal tidak boleh ada: gender yang tidak bisa ditelusuri ke
    -- sumbernya tidak boleh ikut menyaring Discovery.
    ADD CONSTRAINT ck_kpc_creator_gender_lengkap
        CHECK (creator_gender IS NULL OR creator_gender_source IS NOT NULL);

-- Filter Discovery memilih gender, jadi itu yang diindeks. Partial: mayoritas
-- baris NULL.
CREATE INDEX IF NOT EXISTS ix_kpc_creator_gender
    ON l2_gold.kol_profile_card (creator_gender)
    WHERE creator_gender IS NOT NULL;

COMMENT ON COLUMN l2_gold.kol_profile_card.creator_gender IS
    'Gender KREATOR: ''female'' / ''male'' / NULL (tidak diketahui). BUKAN gender '
    'audiens -- itu female_pct/male_pct/audience_demographics_daily. Dipakai '
    'filter Discovery dari Brand Profile gender_majority. Diisi asset '
    'creator_gender (migration 051).';
COMMENT ON COLUMN l2_gold.kol_profile_card.creator_gender_source IS
    'Asal gender kreator, berurut menurut prioritas: ''manual'' (diisi manusia, '
    'TIDAK PERNAH ditimpa pipeline), ''roster'' (l0_raw.kol_roster_import.'
    'influencer_gender, 1=female 0=male -- bukti data, belum kontrak resmi), '
    '''name_inference'' (creator_gender_inference.py dari username + display '
    'name; tidak pernah menimpa roster).';
COMMENT ON COLUMN l2_gold.kol_profile_card.creator_gender_confidence IS
    'high/medium/low. roster = medium (arti kode 0/1 belum resmi). '
    'name_inference: high = simbol/partikel eksplisit, medium = nama depan, '
    'awalan, sufiks, atau sapaan wanita, low = token nama wanita. Tidak ada '
    'nilai untuk tebakan yang ragu -- itu NULL.';

DO $verifikasi$
DECLARE
    n bigint;
BEGIN
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('creator_gender', 'creator_gender_source',
                           'creator_gender_confidence')
       AND is_nullable = 'YES';
    IF n <> 3 THEN
        RAISE EXCEPTION 'Kolom nullable terpasang % dari 3 yang diharapkan', n;
    END IF;

    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = 'l2_gold.kol_profile_card'::regclass
       AND conname IN ('ck_kpc_creator_gender', 'ck_kpc_creator_gender_source',
                       'ck_kpc_creator_gender_confidence',
                       'ck_kpc_creator_gender_lengkap');
    IF n <> 4 THEN
        RAISE EXCEPTION 'CHECK terpasang % dari 4 yang diharapkan', n;
    END IF;

    -- Migration ini menambah kolom, tidak menyentuh baris.
    SELECT count(*) INTO n FROM l2_gold.kol_profile_card;
    IF n <> (SELECT kartu_total FROM _sebelum_051) THEN
        RAISE EXCEPTION 'Jumlah kartu berubah: % -> %',
            (SELECT kartu_total FROM _sebelum_051), n;
    END IF;

    -- Kolom creator_age tetap utuh.
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('creator_age', 'creator_age_source',
                           'female_pct', 'male_pct');
    IF n <> 4 THEN
        RAISE EXCEPTION 'Kolom lama hilang: % dari 4', n;
    END IF;
END
$verifikasi$;

COMMIT;
