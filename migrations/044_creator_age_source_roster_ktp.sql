-- 044_creator_age_source_roster_ktp.sql
--
-- Daftarkan `roster_ktp` sebagai nilai sah `kol_profile_card.creator_age_source`.
--
--     sebelum   'bio_self_declared' | 'manual'
--     sesudah   'bio_self_declared' | 'manual' | 'roster_ktp'
--
-- Ini SATU-SATUNYA perubahan struktural yang dibutuhkan jalur NIK. Tidak ada
-- kolom baru, tidak ada tabel baru, tidak ada tipe yang berubah, dan tidak
-- satu baris data pun disentuh.
--
-- ============================================================================
-- KENAPA CHECK-NYA DULU SENGAJA MENOLAK NILAI INI
-- ============================================================================
--
-- `creator_age_nik.py` sudah ada sejak sebelum migration ini, lengkap dengan
-- decoder-nya, dan sengaja dibiarkan MATI: memakai NIK adalah keputusan
-- kebijakan, bukan keputusan teknis. Salah satu dari tiga lapis penjagaannya
-- adalah CHECK ini -- selama `roster_ktp` tidak terdaftar, penulisan ke
-- production GAGAL DENGAN ERROR, bukan lolos diam-diam.
--
-- Migration ini adalah pelepasan lapis terakhir itu, dan ia hanya boleh
-- dijalankan bersamaan dengan dua lainnya (import di asset + default
-- `nik_aktif()`). Menjalankannya sendirian tidak berbahaya -- ia cuma
-- memperluas daftar nilai yang diizinkan -- tapi juga tidak berguna.
--
-- Persetujuan: 12 September 2026, pemilik data menyetujui `influencer_no_ktp`
-- dipakai sebagai sumber TAMBAHAN Creator Age.
--
-- ============================================================================
-- NOMOR KTP TIDAK MASUK KE TABEL INI
-- ============================================================================
--
-- Yang ditulis jalur `roster_ktp` hanya HASIL penguraian: umur, tahun lahir,
-- band, source, confidence. Nomornya berhenti di `creator_age_nik.py`, yang
-- melakukan SELECT-nya sendiri dan hanya mengembalikan hasil terurai.
--
-- Tidak ada kolom untuk nomor KTP di `kol_profile_card`, dan migration ini
-- TIDAK membuatnya. Kalau suatu saat ada yang mengusulkannya: kartu profil
-- adalah tabel yang dibaca Discovery, dan Discovery adalah etalase.
--
-- ============================================================================
-- KENAPA `roster_ktp`, BUKAN `ktp_nik`
-- ============================================================================
--
-- Yang menjadi sumber adalah KOLOM di roster. `nik` adalah mekanisme
-- penguraiannya. Kolom `creator_age_source` menjawab pertanyaan "datanya dari
-- mana", bukan "dihitungnya bagaimana" -- sama seperti `bio_self_declared`
-- menyebut bio, bukan menyebut regex.
--
-- ============================================================================
-- URUTAN PRIORITAS YANG DIJAGA ASSET (bukan oleh DDL ini)
-- ============================================================================
--
--     manual              diisi manusia; TIDAK PERNAH ditimpa siapa pun
--     bio_self_declared   kreator menyatakannya sendiri di bio
--     roster_ktp          diturunkan dari NIK di roster        <- baru
--     NULL                tidak diketahui
--
-- CHECK tidak bisa menegakkan urutan itu; `assets/creator_age.py` yang
-- menegakkannya, dan `tests/test_creator_age_nik.py` yang mengujinya.
--
-- AMAN DIJALANKAN BERULANG: DROP CONSTRAINT IF EXISTS sebelum ADD.
--
-- ROLLBACK
--   Kembalikan CHECK ke dua nilai, SESUDAH mengosongkan baris yang memakai
--   nilai baru:
--     UPDATE l2_gold.kol_profile_card
--        SET creator_age = NULL, creator_birth_year = NULL,
--            creator_age_band = NULL, creator_age_source = NULL,
--            creator_age_confidence = NULL
--      WHERE creator_age_source = 'roster_ktp';
--   Membalik CHECK lebih dulu akan gagal selama masih ada baris tersebut.
-- ============================================================================

BEGIN;

CREATE TEMP TABLE _sebelum_044 ON COMMIT DROP AS
SELECT
    (SELECT count(*) FROM l2_gold.kol_profile_card)          AS kartu_total,
    (SELECT count(*) FROM l2_gold.kol_profile_card
      WHERE creator_age IS NOT NULL)                         AS umur_terisi,
    (SELECT count(*) FROM l2_gold.kol_profile_card
      WHERE creator_age_source = 'bio_self_declared')        AS dari_bio,
    (SELECT count(*) FROM l2_gold.kol_profile_card
      WHERE creator_age_source = 'manual')                   AS dari_manual;

ALTER TABLE l2_gold.kol_profile_card
    DROP CONSTRAINT IF EXISTS ck_kpc_creator_age_source;

ALTER TABLE l2_gold.kol_profile_card
    ADD CONSTRAINT ck_kpc_creator_age_source
        CHECK (creator_age_source IS NULL OR creator_age_source IN
               ('bio_self_declared', 'manual', 'roster_ktp'));

COMMENT ON COLUMN l2_gold.kol_profile_card.creator_age_source IS
    'Asal umur kreator, berurut menurut prioritas: ''manual'' (diisi manusia, '
    'TIDAK PERNAH ditimpa pipeline), ''bio_self_declared'' (diekstrak dari bio '
    'oleh creator_age_inference.py), ''roster_ktp'' (diturunkan dari '
    'l0_raw.kol_roster_import.influencer_no_ktp oleh creator_age_nik.py, '
    'migration 044). NIK hanya CADANGAN: bio selalu menang bila tersedia. '
    'Nomor KTP-nya sendiri TIDAK disimpan di tabel ini dan tidak boleh '
    'ditambahkan -- yang tersimpan hanya umur, tahun lahir, band, source, dan '
    'confidence.';

DO $verifikasi$
DECLARE
    s _sebelum_044%ROWTYPE;
    n bigint;
BEGIN
    SELECT * INTO s FROM _sebelum_044;

    -- (a) CHECK-nya terpasang dan menerima tepat tiga nilai.
    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = 'l2_gold.kol_profile_card'::regclass
       AND conname = 'ck_kpc_creator_age_source';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ck_kpc_creator_age_source tidak terpasang kembali';
    END IF;

    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = 'l2_gold.kol_profile_card'::regclass
       AND conname = 'ck_kpc_creator_age_source'
       AND pg_get_constraintdef(oid) LIKE '%roster_ktp%'
       AND pg_get_constraintdef(oid) LIKE '%bio_self_declared%'
       AND pg_get_constraintdef(oid) LIKE '%manual%';
    IF n <> 1 THEN
        RAISE EXCEPTION 'CHECK tidak memuat ketiga nilai yang diharapkan';
    END IF;

    -- (b) TIDAK ADA data yang berubah. Migration ini hanya menyentuh DDL.
    SELECT count(*) INTO n FROM l2_gold.kol_profile_card;
    IF n <> s.kartu_total THEN
        RAISE EXCEPTION 'Baris kartu berubah % -> %', s.kartu_total, n;
    END IF;

    SELECT count(*) INTO n FROM l2_gold.kol_profile_card
     WHERE creator_age IS NOT NULL;
    IF n <> s.umur_terisi THEN
        RAISE EXCEPTION 'Umur terisi berubah % -> % -- migration ini tidak '
                        'boleh menulis data', s.umur_terisi, n;
    END IF;

    SELECT count(*) INTO n FROM l2_gold.kol_profile_card
     WHERE creator_age_source = 'bio_self_declared';
    IF n <> s.dari_bio THEN
        RAISE EXCEPTION 'Baris bio berubah % -> %', s.dari_bio, n;
    END IF;

    SELECT count(*) INTO n FROM l2_gold.kol_profile_card
     WHERE creator_age_source = 'manual';
    IF n <> s.dari_manual THEN
        RAISE EXCEPTION 'Baris manual berubah % -> %', s.dari_manual, n;
    END IF;

    -- (c) TIDAK ADA kolom yang memuat nomor KTP di kartu profil.
    SELECT count(*) INTO n FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND (column_name ILIKE '%ktp%' OR column_name ILIKE '%nik%');
    IF n <> 0 THEN
        RAISE EXCEPTION 'Ada % kolom bernuansa KTP/NIK di kol_profile_card -- '
                        'nomor identitas tidak boleh masuk tabel etalase', n;
    END IF;

    -- (d) Bucket LIMA dari migration 043 masih utuh.
    SELECT count(*) INTO n FROM pg_constraint
     WHERE conrelid = 'l2_gold.kol_profile_card'::regclass
       AND conname = 'ck_kpc_creator_age_band'
       AND pg_get_constraintdef(oid) LIKE '%45+%'
       AND pg_get_constraintdef(oid) NOT LIKE '%45-54%';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ck_kpc_creator_age_band tidak lagi berisi lima bucket '
                        '-- migration 043 tersentuh';
    END IF;

    RAISE NOTICE 'OK: creator_age_source kini menerima roster_ktp. Kartu % '
                 'baris, umur terisi % (bio %, manual %) — tidak satu pun '
                 'berubah. Tidak ada kolom KTP/NIK di kartu profil.',
                 s.kartu_total, s.umur_terisi, s.dari_bio, s.dari_manual;
END $verifikasi$;

COMMIT;
