-- 002_fix_remaining_double_fk.sql
--
-- Lanjutan dari 001, untuk 25 tabel sisanya yang polanya sama persis:
-- kolom social_account_id punya DUA foreign key, satu ke public.social_account
-- (benar) dan satu ke public.kol_directory (keliru), sehingga kolom itu tidak
-- pernah bisa diisi nilai apa pun selain NULL.
--
-- Sebaran: 18 tabel di l0_raw + 8 tabel di feature (dikurangi ig_profile_apify
-- yang sudah dibereskan migrasi 001).
--
-- Migrasi ini TIDAK memakai daftar nama tabel. Ia mencari constraint berdasarkan
-- tanda pengenal yang presisi:
--     1. foreign key ke public.kol_directory
--     2. kolomnya bernama social_account_id
--     3. kolom yang sama juga punya foreign key ke public.social_account
-- Syarat ke-3 memastikan tidak ada kolom yang berakhir tanpa constraint sama
-- sekali, dan membuat migrasi ini aman dijalankan ulang (idempoten).
--
-- FK ke kol_directory yang MEMANG benar tidak tersentuh karena nama kolomnya
-- berbeda:
--     l0_extra.ig_rate_card.kol_id
--     l0_extra.tt_rate_card.kol_id
--     l0_raw.kol_roster_import.kol_directory_id
--     public.kol_social_account.kol_id
-- Jumlahnya tidak ditulis sebagai angka tetap; migrasi menghitungnya sebelum dan
-- sesudah, lalu menuntut angkanya tidak berubah.
--
-- Backfill tidak diperlukan: semua tabel yang terdampak masih 0 baris.
--
-- Jalankan:
--   python apply_migration.py migrations/002_fix_remaining_double_fk.sql --dry-run --yes
--   python apply_migration.py migrations/002_fix_remaining_double_fk.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Seluruh langkah berada dalam satu blok agar jumlah FK sah bisa dibandingkan
-- sebelum dan sesudah penghapusan, tanpa mengandalkan angka hardcode.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r            record;
    n_baris      bigint;
    total        int := 0;
    berisi       int := 0;
    dihapus      int := 0;
    fk_sah_awal  int;
    fk_sah_akhir int;
    sisa_ganda   int;
BEGIN
    -- FK "sah" = menunjuk kol_directory lewat kolom yang BUKAN social_account_id.
    SELECT count(*) INTO fk_sah_awal
    FROM pg_constraint c
    JOIN unnest(c.conkey) AS k(attnum) ON true
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
    WHERE c.contype = 'f'
      AND c.confrelid = 'public.kol_directory'::regclass
      AND a.attname <> 'social_account_id';

    RAISE NOTICE 'FK sah ke kol_directory sebelum migrasi: %', fk_sah_awal;

    FOR r IN
        SELECT c.conname, c.conrelid::regclass::text AS tabel
        FROM pg_constraint c
        JOIN unnest(c.conkey) AS k(attnum) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype = 'f'
          AND c.confrelid = 'public.kol_directory'::regclass
          AND a.attname = 'social_account_id'
          AND array_length(c.conkey, 1) = 1
          AND EXISTS (
              SELECT 1
              FROM pg_constraint c2
              JOIN unnest(c2.conkey) AS k2(attnum) ON true
              JOIN pg_attribute a2 ON a2.attrelid = c2.conrelid AND a2.attnum = k2.attnum
              WHERE c2.contype = 'f'
                AND c2.conrelid = c.conrelid
                AND a2.attname = 'social_account_id'
                AND c2.confrelid = 'public.social_account'::regclass
          )
        ORDER BY 2, 1
    LOOP
        EXECUTE format('SELECT count(*) FROM %s', r.tabel) INTO n_baris;
        total := total + 1;
        IF n_baris > 0 THEN
            berisi := berisi + 1;
            RAISE NOTICE 'akan dihapus: % pada % (% baris - PERIKSA)', r.conname, r.tabel, n_baris;
        ELSE
            RAISE NOTICE 'akan dihapus: % pada % (kosong)', r.conname, r.tabel;
        END IF;
    END LOOP;

    RAISE NOTICE '--- kandidat: % constraint, % di antaranya pada tabel berisi data ---', total, berisi;

    FOR r IN
        SELECT c.conname, c.conrelid::regclass::text AS tabel
        FROM pg_constraint c
        JOIN unnest(c.conkey) AS k(attnum) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype = 'f'
          AND c.confrelid = 'public.kol_directory'::regclass
          AND a.attname = 'social_account_id'
          AND array_length(c.conkey, 1) = 1
          AND EXISTS (
              SELECT 1
              FROM pg_constraint c2
              JOIN unnest(c2.conkey) AS k2(attnum) ON true
              JOIN pg_attribute a2 ON a2.attrelid = c2.conrelid AND a2.attnum = k2.attnum
              WHERE c2.contype = 'f'
                AND c2.conrelid = c.conrelid
                AND a2.attname = 'social_account_id'
                AND c2.confrelid = 'public.social_account'::regclass
          )
        ORDER BY 2, 1
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', r.tabel, r.conname);
        dihapus := dihapus + 1;
    END LOOP;

    RAISE NOTICE 'Constraint dihapus: %', dihapus;

    -- ----------------------------------------------------------------------
    -- Verifikasi. Gagal di sini membatalkan seluruh transaksi.
    -- ----------------------------------------------------------------------
    -- Tidak boleh ada lagi kolom social_account_id dengan lebih dari satu FK.
    SELECT count(*) INTO sisa_ganda
    FROM (
        SELECT c.conrelid
        FROM pg_constraint c
        JOIN unnest(c.conkey) AS k(attnum) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype = 'f' AND a.attname = 'social_account_id'
        GROUP BY c.conrelid
        HAVING count(*) > 1
    ) t;

    IF sisa_ganda > 0 THEN
        RAISE EXCEPTION 'Masih ada % tabel dengan FK ganda pada social_account_id', sisa_ganda;
    END IF;

    -- FK sah ke kol_directory tidak boleh ikut terhapus.
    SELECT count(*) INTO fk_sah_akhir
    FROM pg_constraint c
    JOIN unnest(c.conkey) AS k(attnum) ON true
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
    WHERE c.contype = 'f'
      AND c.confrelid = 'public.kol_directory'::regclass
      AND a.attname <> 'social_account_id';

    IF fk_sah_akhir <> fk_sah_awal THEN
        RAISE EXCEPTION 'FK sah ke kol_directory berubah dari % menjadi %', fk_sah_awal, fk_sah_akhir;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: 0 FK ganda tersisa, % FK sah ke kol_directory utuh', fk_sah_akhir;
END $$;

COMMIT;

-- ---------------------------------------------------------------------------
-- Cara mengembalikan: tambahkan lagi constraint per tabel, misalnya
--   ALTER TABLE l0_raw.tt_profile_apify
--       ADD CONSTRAINT fk_tt_profile_apify_social_account_id
--       FOREIGN KEY (social_account_id) REFERENCES public.kol_directory(id);
-- Daftar lengkap nama constraint yang dihapus tercetak di NOTICE saat migrasi
-- dijalankan; simpan keluarannya sebelum menerapkan.
-- ---------------------------------------------------------------------------
