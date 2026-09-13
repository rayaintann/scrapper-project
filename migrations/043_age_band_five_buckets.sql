-- 043_age_band_five_buckets.sql
--
-- Daftar bucket umur Discovery: ENAM -> LIMA.
--
--     sebelum   13-17 | 18-24 | 25-34 | 35-44 | 45-54 | 55+
--     sesudah   13-17 | 18-24 | 25-34 | 35-44 | 45+
--
-- Dua bucket teratas lama (`45-54`, `55+`) runtuh jadi satu bucket `45+`.
-- Empat bucket di bawahnya TIDAK BERUBAH sama sekali.
--
-- Berlaku untuk KEDUA fitur umur, karena keduanya memang berbagi satu daftar
-- chip di UI:
--
--     Age Kreator    l2_gold.kol_profile_card.creator_age_band     (migration 042)
--     Age Audience   l2_gold.audience_demographics_daily           (migration 023)
--                    WHERE audience_type = 'age', kolom dimension_key
--
-- Sumber kebenarannya tetap satu: `metrics_thresholds.BUCKET_AGE`. DDL tidak
-- bisa mengimpor Python, jadi daftarnya memang diulang di sini --
-- `tests/test_creator_age.py::TestParitasAmbang` yang menahan keduanya supaya
-- tidak bergeser sendiri-sendiri.
--
-- ============================================================================
-- KENAPA INI TIDAK KEHILANGAN DATA
-- ============================================================================
--
-- Penggabungan hanya terjadi ke ATAS dan hanya di bucket paling atas. Siapa
-- pun yang sebelumnya masuk `45-54` atau `55+` memang berumur 45 tahun ke
-- atas, jadi tidak ada satu baris pun yang berpindah ke kelompok umur yang
-- salah. Yang hilang hanya KEHALUSAN (tidak lagi bisa membedakan 47 dari 61)
-- -- dan itu memang yang diminta spesifikasi final.
--
-- Umur mentahnya tetap utuh: `kol_profile_card.creator_age` dan
-- `creator_birth_year` TIDAK disentuh migration ini. Kalau suatu hari
-- bucketnya dipecah lagi, band bisa dihitung ulang dari kolom itu tanpa
-- kehilangan apa pun.
--
-- ============================================================================
-- KENAPA BARIS AUDIENS DIJUMLAHKAN, BUKAN DI-UPDATE SATU PER SATU
-- ============================================================================
--
-- `uq_audience_demographics_daily` unik atas
-- (social_account_id, platform, audience_date, audience_type, dimension_key).
--
-- Satu akun bisa punya baris `45-54` DAN baris `55+` pada tanggal yang sama.
-- `UPDATE ... SET dimension_key='45+'` polos akan menabrak constraint itu pada
-- baris kedua, dan versi yang "memperbaikinya" dengan ON CONFLICT DO NOTHING
-- akan MEMBUANG audiens 55+ diam-diam -- persis bug yang dijaga
-- `agregasi_bucket_age` di sisi Python.
--
-- Karena itu baris lama dijumlahkan lebih dulu ke dalam satu baris `45+`, baru
-- baris sumbernya dihapus, semuanya di dalam satu transaksi. Blok verifikasi
-- di bawah membandingkan TOTAL audiens 45+ sebelum dan sesudah dan melempar
-- exception kalau tidak sama.
--
-- `confidence` baris gabungan mengambil yang paling LEMAH di antara baris yang
-- digabung: satu baris gabungan tidak boleh terbaca lebih pasti daripada bukti
-- terburuk yang menyusunnya. Aturan yang sama dipakai `_modus_confidence` di
-- assets/audience.py. Urutannya ditulis eksplisit, bukan diambil dari urutan
-- alfabet -- secara alfabet `measured` justru jatuh di tengah `inferred_*`.
--
-- ============================================================================
-- AMAN DIJALANKAN BERULANG
-- ============================================================================
--
-- Semuanya idempoten: DROP CONSTRAINT IF EXISTS sebelum ADD, dan
-- UPDATE/DELETE yang menyaring nilai lama yang pada run kedua sudah tidak ada
-- lagi. Run kedua menyentuh 0 baris.
--
-- ROLLBACK
--   Tidak ada rollback otomatis: `45-54` dan `55+` tidak bisa dipisahkan lagi
--   dari `45+` untuk baris AUDIENS. Untuk baris KREATOR, band bisa dihitung
--   ulang dari `creator_age` yang tidak disentuh:
--     UPDATE l2_gold.kol_profile_card
--        SET creator_age_band = CASE WHEN creator_age >= 55 THEN '55+'
--                                    WHEN creator_age >= 45 THEN '45-54' ... END;
--   Ambil dump sebelum menjalankan ini kalau baris audiens `age` sudah terisi.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Jumlah sebelum, dipakai blok verifikasi di bawah.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE _sebelum_043 ON COMMIT DROP AS
SELECT
    (SELECT count(*) FROM l2_gold.kol_profile_card
      WHERE creator_age_band IN ('45-54','55+'))               AS kreator_45plus_lama,
    (SELECT count(*) FROM l2_gold.kol_profile_card
      WHERE creator_age_band IS NOT NULL)                      AS kreator_band_terisi,
    (SELECT count(*) FROM l2_gold.kol_profile_card)            AS kreator_total_baris,
    (SELECT coalesce(sum(audience_count), 0)
       FROM l2_gold.audience_demographics_daily
      WHERE audience_type = 'age'
        AND dimension_key IN ('45-54','55+','45+'))            AS audiens_45plus_total,
    (SELECT count(*) FROM l2_gold.audience_demographics_daily) AS audiens_total_baris,
    (SELECT count(*) FROM l2_gold.audience_demographics_daily
      WHERE audience_type <> 'age')                            AS audiens_bukan_age;

-- ---------------------------------------------------------------------------
-- 1. CHECK Age Kreator: daftar lama dilepas dulu supaya UPDATE di bawah tidak
--    ditolak olehnya. Ditambahkan kembali dengan daftar LIMA bucket.
-- ---------------------------------------------------------------------------
ALTER TABLE l2_gold.kol_profile_card
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_age_band;

UPDATE l2_gold.kol_profile_card
   SET creator_age_band = '45+',
       updated_at       = now()
 WHERE creator_age_band IN ('45-54', '55+');

ALTER TABLE l2_gold.kol_profile_card
    ADD CONSTRAINT ck_kpc_creator_age_band
        CHECK (creator_age_band IS NULL OR creator_age_band IN
               ('13-17','18-24','25-34','35-44','45+'));

COMMENT ON COLUMN l2_gold.kol_profile_card.creator_age_band IS
    'Bucket Discovery: 13-17/18-24/25-34/35-44/45+ (LIMA bucket; migration 043 '
    'meruntuhkan 45-54 dan 55+ jadi 45+). Daftarnya sama dengan bucket Age '
    'Audience (metrics_thresholds.BUCKET_AGE) supaya chip yang sama berarti '
    'hal yang sama di kedua filter. Disimpan, bukan dihitung saat baca, karena '
    'UI query Postgres langsung. NULL = umur tidak diketahui, dan itu keadaan '
    'normal: platform tidak mengekspos umur kreator.';

-- ---------------------------------------------------------------------------
-- 2. Baris Age Audience: `45-54` + `55+` DIJUMLAHKAN jadi satu baris `45+`.
--    Hanya audience_type='age' yang disentuh -- baris gender di tabel yang
--    sama tidak boleh ikut bergerak.
--
--    HAVING menyaring keadaan yang sudah benar: akun yang cuma punya satu
--    baris dan baris itu sudah `45+` tidak perlu dihapus lalu ditulis ulang.
--    Itu yang membuat run kedua menyentuh 0 baris.
-- ---------------------------------------------------------------------------
WITH gabungan AS (
    SELECT social_account_id, platform, audience_date,
           sum(audience_count) AS total,
           min(CASE confidence
                 WHEN 'inferred_low'    THEN 1
                 WHEN 'inferred_medium' THEN 2
                 WHEN 'inferred_high'   THEN 3
                 WHEN 'measured'        THEN 4
                 ELSE 0
               END) AS peringkat_conf
      FROM l2_gold.audience_demographics_daily
     WHERE audience_type = 'age'
       AND dimension_key IN ('45-54', '55+', '45+')
     GROUP BY social_account_id, platform, audience_date
    HAVING count(*) > 1 OR bool_or(dimension_key <> '45+')
),
dibuang AS (
    DELETE FROM l2_gold.audience_demographics_daily ad
     USING gabungan g
     WHERE ad.social_account_id = g.social_account_id
       AND ad.platform          = g.platform
       AND ad.audience_date     = g.audience_date
       AND ad.audience_type     = 'age'
       AND ad.dimension_key IN ('45-54', '55+', '45+')
    RETURNING 1
)
INSERT INTO l2_gold.audience_demographics_daily (
    social_account_id, platform, audience_date,
    audience_type, dimension_key, audience_count, confidence,
    created_at, updated_at)
SELECT g.social_account_id, g.platform, g.audience_date,
       'age', '45+', g.total,
       CASE g.peringkat_conf
         WHEN 4 THEN 'measured'
         WHEN 3 THEN 'inferred_high'
         WHEN 2 THEN 'inferred_medium'
         WHEN 1 THEN 'inferred_low'
         ELSE NULL
       END,
       now(), now()
  FROM gabungan g;

COMMENT ON COLUMN l2_gold.audience_demographics_daily.dimension_key IS
    'Untuk audience_type=''age'': salah satu LIMA bucket Discovery '
    '13-17/18-24/25-34/35-44/45+ (metrics_thresholds.BUCKET_AGE). Bucket '
    'mentah Instagram Insights 45-54, 55-64 dan 65+ DIJUMLAHKAN jadi 45+, '
    'bukan diambil salah satu, supaya total per akun tetap sama dengan yang '
    'dilaporkan platform. Untuk audience_type=''gender'': male/female/unknown.';

-- ---------------------------------------------------------------------------
-- 3. Verifikasi -- exception di sini membatalkan seluruh transaksi.
-- ---------------------------------------------------------------------------
DO $verifikasi$
DECLARE
    s _sebelum_043%ROWTYPE;
    n bigint;
    x numeric;
BEGIN
    SELECT * INTO s FROM _sebelum_043;

    -- (a) Tidak ada band lama yang tersisa di KEDUA tabel.
    SELECT count(*) INTO n FROM l2_gold.kol_profile_card
     WHERE creator_age_band IN ('45-54','55+');
    IF n <> 0 THEN
        RAISE EXCEPTION 'Masih ada % baris creator_age_band bucket lama', n;
    END IF;

    SELECT count(*) INTO n FROM l2_gold.audience_demographics_daily
     WHERE audience_type = 'age' AND dimension_key IN ('45-54','55+');
    IF n <> 0 THEN
        RAISE EXCEPTION 'Masih ada % baris audiens age bucket lama', n;
    END IF;

    -- (b) Tidak ada band di luar LIMA bucket yang sah.
    SELECT count(*) INTO n FROM l2_gold.kol_profile_card
     WHERE creator_age_band IS NOT NULL
       AND creator_age_band NOT IN ('13-17','18-24','25-34','35-44','45+');
    IF n <> 0 THEN
        RAISE EXCEPTION '% baris creator_age_band di luar lima bucket', n;
    END IF;

    -- (c) Jumlah baris kartu profil TIDAK berubah: migration ini meng-UPDATE,
    --     tidak pernah INSERT maupun DELETE di tabel itu.
    SELECT count(*) INTO n FROM l2_gold.kol_profile_card;
    IF n <> s.kreator_total_baris THEN
        RAISE EXCEPTION 'Baris kol_profile_card berubah % -> %',
                        s.kreator_total_baris, n;
    END IF;

    -- (d) Jumlah kartu yang PUNYA band tidak berubah: menggabungkan bucket
    --     tidak boleh menghilangkan maupun menambah kreator ber-band.
    SELECT count(*) INTO n FROM l2_gold.kol_profile_card
     WHERE creator_age_band IS NOT NULL;
    IF n <> s.kreator_band_terisi THEN
        RAISE EXCEPTION 'Kartu ber-band berubah % -> %', s.kreator_band_terisi, n;
    END IF;

    -- (e) TOTAL audiens 45+ terjaga. Ini penjaga yang paling penting: kalau
    --     penggabungan menimpa alih-alih menjumlahkan, angkanya turun di sini.
    SELECT coalesce(sum(audience_count), 0) INTO x
      FROM l2_gold.audience_demographics_daily
     WHERE audience_type = 'age' AND dimension_key = '45+';
    IF x IS DISTINCT FROM s.audiens_45plus_total THEN
        RAISE EXCEPTION 'Total audiens 45+ berubah % -> % (penggabungan menimpa, '
                        'bukan menjumlahkan)', s.audiens_45plus_total, x;
    END IF;

    -- (f) Baris audiens NON-age tidak tersentuh sama sekali.
    SELECT count(*) INTO n FROM l2_gold.audience_demographics_daily
     WHERE audience_type <> 'age';
    IF n <> s.audiens_bukan_age THEN
        RAISE EXCEPTION 'Baris audiens non-age berubah % -> % -- migration ini '
                        'tidak boleh menyentuhnya', s.audiens_bukan_age, n;
    END IF;

    -- (g) Kolom Age Kreator dari 042 masih lengkap.
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema='l2_gold' AND table_name='kol_profile_card'
       AND column_name IN ('creator_age','creator_birth_year','creator_age_band',
                           'creator_age_source','creator_age_confidence');
    IF n <> 5 THEN
        RAISE EXCEPTION 'Kolom Age Kreator tinggal % dari 5', n;
    END IF;

    -- (h) CHECK-nya benar-benar terpasang kembali.
    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = 'l2_gold.kol_profile_card'::regclass
       AND conname = 'ck_kpc_creator_age_band';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ck_kpc_creator_age_band tidak terpasang kembali';
    END IF;

    RAISE NOTICE 'OK: bucket umur kini LIMA (13-17/18-24/25-34/35-44/45+). '
                 'Kartu % baris (band terisi %), total audiens 45+ % terjaga, '
                 'baris audiens non-age % tidak tersentuh.',
                 s.kreator_total_baris, s.kreator_band_terisi,
                 s.audiens_45plus_total, s.audiens_bukan_age;
END $verifikasi$;

COMMIT;
