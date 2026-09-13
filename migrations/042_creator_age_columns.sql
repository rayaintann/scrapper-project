-- 042_creator_age_columns.sql
--
-- Lima kolom untuk fitur AGE KREATOR di KOL Discovery:
--
--     creator_age              umur kreator dalam tahun
--     creator_birth_year       tahun lahir, kalau yang dinyatakan itu
--     creator_age_band         bucket Discovery (13-17 .. 55+)
--     creator_age_source       dari mana umurnya datang
--     creator_age_confidence   seberapa kuat buktinya
--
-- Aditif dan nullable seperti 036/037/038. Tidak ada tabel baru, tidak ada
-- schema baru, tidak ada DROP, tidak ada perubahan tipe, dan tidak satu baris
-- pun diubah atau dihapus.
--
-- ============================================================================
-- INI BUKAN AGE AUDIENCE. JANGAN DIGABUNG.
-- ============================================================================
--
-- Discovery punya DUA filter umur, dan keduanya sengaja tidak berbagi apa pun
-- selain daftar bucket:
--
--     Age Kreator    umur ORANG KOL-nya      -> kolom di migration INI
--     Age Audience   umur PENGIKUTNYA        -> l2_gold.audience_demographics_daily
--                                               (audience_type='age'), schema
--                                               sudah ada sejak 023
--
-- Menaruh keduanya di satu tabel pernah dipertimbangkan dan ditolak: grainnya
-- berbeda (kartu per akun vs deret harian per bucket), sumbernya berbeda (teks
-- bio vs Insights API), dan pengisiannya berbeda. Satu-satunya yang dipakai
-- bersama adalah daftar bucket di `metrics_thresholds.BUCKET_AGE`, supaya chip
-- "55+" di kedua filter berarti hal yang sama.
--
-- ============================================================================
-- KENAPA UMUR DAN TAHUN LAHIR DISIMPAN TERPISAH
-- ============================================================================
--
-- `creator_age` BASI. Umur bertambah tiap tahun, jadi angka yang ditulis hari
-- ini salah 12 bulan lagi kalau asset-nya tidak dimaterialisasi ulang.
-- `creator_birth_year` tidak pernah basi.
--
-- Keduanya disimpan karena keduanya membawa informasi yang tidak dimiliki yang
-- lain:
--
--   * bio yang menulis "umur 24" TIDAK memberi tahun lahir yang pasti --
--     orangnya bisa sudah atau belum ulang tahun tahun ini. Untuk baris
--     seperti itu `creator_birth_year` NULL, dan menebaknya akan mengarang
--     presisi yang tidak ada di sumbernya.
--   * bio yang menulis "lahir 1998" memberi keduanya.
--
-- Jadi `creator_birth_year IS NULL AND creator_age IS NOT NULL` adalah keadaan
-- yang SAH, bukan data rusak.
--
-- ============================================================================
-- KENAPA ADA `creator_age_source`, DAN KENAPA `manual` TIDAK BOLEH DITIMPA
-- ============================================================================
--
-- Alasan yang sama dengan awalan `inferred_` pada audience: hasil turunan
-- tidak boleh menyamar jadi hasil terukur. Nilai yang dipakai:
--
--     'bio_self_declared'  kreator menyatakannya sendiri di bio
--     'manual'             diisi manusia (roster/CRM), bukan pipeline
--
-- Asset `creator_age` HANYA menulis baris yang sumbernya bukan 'manual'.
-- Tanpa penjagaan itu, umur yang sudah diverifikasi orang akan tertimpa hasil
-- ekstraksi tiap kali asset dijalankan -- dan karena ekstraksinya hampir selalu
-- mengembalikan NULL, efeknya adalah MENGHAPUS data bagus.
--
-- ============================================================================
-- YANG PERLU DIKETAHUI SEBELUM BERHARAP KOLOM INI TERISI
-- ============================================================================
--
-- Umur kreator TIDAK ADA di sumber mana pun yang dipakai pipeline ini.
-- Instagram dan TikTok tidak mengeksposnya, dan tidak ada actor Apify yang
-- mengembalikannya. Satu-satunya tempat umur bisa muncul adalah teks bio.
--
-- 902 bio asli hasil scrape sudah diuji terhadap extractor yang mengisi kolom
-- ini: HASILNYA NOL. Semuanya `unknown`. Itu bukan bug -- lihat docstring
-- `creator_age_inference.py`, yang mencatat bahwa "ada tahun di bio" hanya ~3%
-- benar sebagai tahun lahir (sisanya tahun penghargaan, tahun berdiri brand,
-- nomor telepon, dan tanggal lahir ANAK si kreator).
--
-- Jadi kolom ini dibuat dengan harapan yang jujur: pengisian nyata akan datang
-- dari jalur 'manual' (roster) atau dari sumber baru yang memang memuat
-- tanggal lahir. Extractor ada supaya bio yang MEMANG menyatakan umur tidak
-- terbuang, bukan supaya kolomnya terlihat penuh.
--
-- CHECK sengaja dipasang: kolom yang menunggu pengisian manual adalah kolom
-- yang paling mudah diisi nilai asal-asalan, dan batas 13..80 di DDL menolak
-- itu di tempat yang tidak bisa dilewati siapa pun.
--
-- ROLLBACK
--   ALTER TABLE l2_gold.kol_profile_card DROP COLUMN <nama> untuk kelimanya.
--   (CHECK ikut terhapus bersama kolomnya.)
-- ============================================================================

BEGIN;

ALTER TABLE l2_gold.kol_profile_card
    ADD COLUMN IF NOT EXISTS creator_age            smallint,
    ADD COLUMN IF NOT EXISTS creator_birth_year     smallint,
    ADD COLUMN IF NOT EXISTS creator_age_band       varchar(10),
    ADD COLUMN IF NOT EXISTS creator_age_source     varchar(30),
    ADD COLUMN IF NOT EXISTS creator_age_confidence varchar(10);

-- Batas yang sama dengan `metrics_thresholds.AGE_MIN/AGE_MAX`. Diulang di sini
-- karena DDL tidak bisa mengimpor Python; `tests/test_creator_age.py` menguji
-- bahwa keduanya tidak bergeser sendiri-sendiri.
ALTER TABLE l2_gold.kol_profile_card
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_age,
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_age_band,
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_age_source,
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_age_confidence;

ALTER TABLE l2_gold.kol_profile_card
    ADD CONSTRAINT ck_kpc_creator_age
        CHECK (creator_age IS NULL OR creator_age BETWEEN 13 AND 80),
    ADD CONSTRAINT ck_kpc_creator_age_band
        CHECK (creator_age_band IS NULL OR creator_age_band IN
               ('13-17','18-24','25-34','35-44','45-54','55+')),
    ADD CONSTRAINT ck_kpc_creator_age_source
        CHECK (creator_age_source IS NULL OR creator_age_source IN
               ('bio_self_declared','manual')),
    ADD CONSTRAINT ck_kpc_creator_age_confidence
        CHECK (creator_age_confidence IS NULL OR creator_age_confidence IN
               ('high','medium','low'));

-- Filter Discovery memilih band, jadi itu yang diindeks. Partial: mayoritas
-- baris NULL dan tidak ada gunanya ikut masuk indeks.
CREATE INDEX IF NOT EXISTS ix_kpc_creator_age_band
    ON l2_gold.kol_profile_card (creator_age_band)
    WHERE creator_age_band IS NOT NULL;

COMMENT ON COLUMN l2_gold.kol_profile_card.creator_age IS
    'Umur KREATOR dalam tahun (bukan umur audiens -- itu di '
    'l2_gold.audience_demographics_daily audience_type=''age''). BASI seiring '
    'waktu bila diturunkan dari creator_birth_year; nilai yang tidak basi ada '
    'di kolom itu. NULL = tidak diketahui, dan NULL adalah keadaan normal: '
    'platform tidak mengekspos umur kreator.';
COMMENT ON COLUMN l2_gold.kol_profile_card.creator_birth_year IS
    'Tahun lahir kreator bila yang dinyatakan memang tahun lahir. NULL saat '
    'bio hanya menyebut umur (mis. "umur 24") -- umur tidak menentukan tahun '
    'lahir secara pasti, dan menebaknya akan mengarang presisi. '
    'creator_birth_year NULL + creator_age terisi adalah keadaan SAH.';
COMMENT ON COLUMN l2_gold.kol_profile_card.creator_age_band IS
    'Bucket Discovery: 13-17/18-24/25-34/35-44/45-54/55+. Daftarnya sama '
    'dengan bucket Age Audience (metrics_thresholds.BUCKET_AGE) supaya chip '
    'yang sama berarti hal yang sama di kedua filter. Disimpan, bukan '
    'dihitung saat baca, karena UI query Postgres langsung.';
COMMENT ON COLUMN l2_gold.kol_profile_card.creator_age_source IS
    'Asal umur: ''bio_self_declared'' (diekstrak dari bio oleh '
    'creator_age_inference.py) atau ''manual'' (diisi manusia). Asset '
    'creator_age TIDAK PERNAH menimpa baris bersumber ''manual'' -- ekstraksi '
    'hampir selalu mengembalikan NULL, jadi menimpanya berarti menghapus data '
    'yang sudah diverifikasi.';
COMMENT ON COLUMN l2_gold.kol_profile_card.creator_age_confidence IS
    'high/medium/low. high = kata kunci umur atau lahir yang eksplisit '
    '("umur 24", "lahir 1998"); medium = satuan tahun yang lebih rawan salah '
    'baca ("21 tahun"). Tidak ada nilai untuk tebakan -- tebakan menghasilkan '
    'NULL, bukan confidence rendah.';

DO $verifikasi$
DECLARE
    n int;
BEGIN
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('creator_age','creator_birth_year',
                           'creator_age_band','creator_age_source',
                           'creator_age_confidence');
    IF n <> 5 THEN
        RAISE EXCEPTION 'Kolom terpasang % dari 5 yang diharapkan', n;
    END IF;

    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('creator_age','creator_birth_year',
                           'creator_age_band','creator_age_source',
                           'creator_age_confidence')
       AND is_nullable = 'NO';
    IF n <> 0 THEN
        RAISE EXCEPTION '% kolom baru bertanda NOT NULL; seharusnya nullable', n;
    END IF;

    SELECT count(*) INTO n
      FROM pg_constraint
     WHERE conrelid = 'l2_gold.kol_profile_card'::regclass
       AND conname IN ('ck_kpc_creator_age','ck_kpc_creator_age_band',
                       'ck_kpc_creator_age_source',
                       'ck_kpc_creator_age_confidence');
    IF n <> 4 THEN
        RAISE EXCEPTION 'CHECK terpasang % dari 4 yang diharapkan', n;
    END IF;

    -- Kolom 036/037/038 harus utuh: migration ini menambah, tidak mengganti.
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('avg_views','median_views','view_to_follower_ratio',
                           'like_to_view_ratio','followers_growth','daily_growth',
                           'projected_30d','paid_ratio','share_rate',
                           'post_frequency_monthly','female_pct','male_pct',
                           'gender_known_pct','growth_class','gender_reliability',
                           'post_frequency_daily','post_frequency_count',
                           'post_frequency_reliability','monitoring_er_pct',
                           'monitoring_priority');
    IF n <> 20 THEN
        RAISE EXCEPTION 'Kolom 036/037/038 tinggal % dari 20 -- ada yang hilang', n;
    END IF;

    -- Age Audience TIDAK disentuh migration ini; dipastikan tabelnya masih
    -- berdiri dengan bentuk yang sama supaya dua fitur ini tetap terpisah.
    IF to_regclass('l2_gold.audience_demographics_daily') IS NULL THEN
        RAISE EXCEPTION 'l2_gold.audience_demographics_daily hilang -- '
                        'Age Audience bergantung padanya';
    END IF;

    RAISE NOTICE 'OK: 5 kolom Age Kreator terpasang, nullable, CHECK aktif, '
                 'kolom lama utuh, dan tabel Age Audience tidak tersentuh.';
END $verifikasi$;

COMMIT;
