-- 001_fix_ig_profile_apify_fk.sql
--
-- Masalah:
--   Kolom l0_raw.ig_profile_apify.social_account_id punya DUA foreign key yang
--   menunjuk tabel berbeda:
--     fk_ig_profile_apify_social_account     -> public.social_account(id)   (benar)
--     fk_ig_profile_apify_social_account_id  -> public.kol_directory(id)    (keliru)
--   Kedua tabel itu tidak berbagi satu id pun, sehingga nilai non-NULL apa pun
--   pasti melanggar salah satu constraint. Akibatnya kolom tersebut hanya bisa
--   NULL dan seluruh raw layer tidak pernah bisa ditautkan.
--
-- Dasar penentuan mana yang keliru:
--   - Nama kolomnya social_account_id.
--   - l0_harmonization.instagram_profile memakai fk_instagram_profile_social_account
--     -> social_account(id), hanya satu FK.
--   - l1_silver.unified_profile memakai fk_upr_social -> social_account(id).
--
-- Cakupan: HANYA tabel l0_raw.ig_profile_apify. 18 tabel l0_raw lain punya pola
-- yang sama tapi masih kosong dan tidak diubah di sini.
--
-- Jalankan seluruh file dalam satu transaksi:
--   psql -f migrations/001_fix_ig_profile_apify_fk.sql
--   atau: python apply_migration.py migrations/001_fix_ig_profile_apify_fk.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Prasyarat: FK yang benar harus ada sebelum yang keliru dihapus.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_ig_profile_apify_social_account'
          AND conrelid = 'l0_raw.ig_profile_apify'::regclass
          AND confrelid = 'public.social_account'::regclass
    ) THEN
        RAISE EXCEPTION
            'FK ke public.social_account tidak ditemukan; migrasi dibatalkan agar kolom tidak kehilangan semua constraint';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Hapus FK yang keliru (menunjuk kol_directory).
-- ---------------------------------------------------------------------------
ALTER TABLE l0_raw.ig_profile_apify
    DROP CONSTRAINT IF EXISTS fk_ig_profile_apify_social_account_id;

-- ---------------------------------------------------------------------------
-- 3. Backfill social_account_id berdasarkan username + platform Instagram.
--
--    Username dinormalisasi sama seperti di kode Python (transform.normalize_username):
--    buang query string, path, dan '@', lalu lowercase.
--
--    DISTINCT ON menjaga hasilnya deterministik kalau satu username punya lebih
--    dari satu baris social_account (saat ini: 'sitisarahadiyastuti'). Yang
--    username-nya sudah bersih dimenangkan, lalu id terkecil sebagai penentu akhir.
-- ---------------------------------------------------------------------------
WITH ig_accounts AS (
    SELECT DISTINCT ON (uname) uname, id
    FROM (
        SELECT ltrim(lower(btrim(split_part(s.username, '?', 1))), '@') AS uname,
               s.id,
               (s.username = ltrim(lower(btrim(split_part(s.username, '?', 1))), '@')) AS is_clean
        FROM public.social_account s
        JOIN public.platforms p ON p.id = s.platform_id
        WHERE p.key = 'instagram'
    ) t
    ORDER BY uname, is_clean DESC, id
)
UPDATE l0_raw.ig_profile_apify r
SET social_account_id = a.id
FROM ig_accounts a
WHERE a.uname = r.username
  AND r.social_account_id IS DISTINCT FROM a.id;

-- ---------------------------------------------------------------------------
-- 4. Verifikasi. Gagal di sini membatalkan seluruh transaksi.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    jumlah_fk    int;
    tujuan_fk    text;
    total_baris  int;
    belum_tertaut int;
BEGIN
    SELECT count(*), min(c.confrelid::regclass::text)
      INTO jumlah_fk, tujuan_fk
      FROM pg_constraint c
      JOIN unnest(c.conkey) AS k(attnum) ON true
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
     WHERE c.contype = 'f'
       AND c.conrelid = 'l0_raw.ig_profile_apify'::regclass
       AND a.attname = 'social_account_id';

    IF jumlah_fk <> 1 THEN
        RAISE EXCEPTION 'Diharapkan tepat 1 FK pada social_account_id, ditemukan %', jumlah_fk;
    END IF;

    IF tujuan_fk <> 'social_account' THEN
        RAISE EXCEPTION 'FK yang tersisa menunjuk ke %, seharusnya social_account', tujuan_fk;
    END IF;

    SELECT count(*), count(*) FILTER (WHERE social_account_id IS NULL)
      INTO total_baris, belum_tertaut
      FROM l0_raw.ig_profile_apify;

    RAISE NOTICE 'FK tersisa   : % (-> %)', jumlah_fk, tujuan_fk;
    RAISE NOTICE 'Total baris  : %', total_baris;
    RAISE NOTICE 'Tertaut      : %', total_baris - belum_tertaut;
    RAISE NOTICE 'Belum tertaut: %', belum_tertaut;

    IF belum_tertaut > 0 THEN
        RAISE WARNING '% baris tidak punya pasangan di social_account; kolomnya dibiarkan NULL', belum_tertaut;
    END IF;
END $$;

COMMIT;

-- ---------------------------------------------------------------------------
-- Cara mengembalikan (kalau ternyata FK ke kol_directory memang disengaja):
--
--   BEGIN;
--   UPDATE l0_raw.ig_profile_apify SET social_account_id = NULL;
--   ALTER TABLE l0_raw.ig_profile_apify
--       ADD CONSTRAINT fk_ig_profile_apify_social_account_id
--       FOREIGN KEY (social_account_id) REFERENCES public.kol_directory(id);
--   COMMIT;
-- ---------------------------------------------------------------------------
