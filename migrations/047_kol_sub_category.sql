-- 047_kol_sub_category.sql
--
-- 42 Sub Category resmi disimpan di public.kol_categories sebagai CHILD dari
-- Parent Category. Tidak ada source production baru.
--
--     public.kol_categories  + kolom code, level, parent_id
--                            + 6 baris Parent Category baru
--                            + 42 baris Sub Category
--
-- ============================================================================
-- KEPUTUSAN (Mba Yunita, 16 Sep 2026)
-- ============================================================================
--
--   * Sub Category boleh dibuat, di tabel kategori yang SUDAH ADA.
--   * Source of record: docs/brand_match_master.xlsx, 42 Sub Category.
--   * Category existing tidak diubah atau dihapus.
--   * Mapping KOL -> Sub Category tidak dikarang.
--
-- Versi sebelumnya dari file ini membuat dua tabel baru
-- (public.kol_sub_category + public.kol_sub_category_map) dan sempat
-- diterapkan 16 Sep 2026 05:48 UTC. Keputusan di atas menggantikannya, jadi
-- migrasi ini juga MEMBERSIHKAN kedua tabel itu (bagian 6) — dengan guard:
-- dibatalkan kalau map berisi, kalau ada objek yang bergantung, atau kalau
-- isi tabel lama tidak identik dengan 42 baris yang baru ditulis.
--
-- ============================================================================
-- SUMBER: docs/brand_match_master.xlsx
-- ============================================================================
--
--   sheet `Taxonomy` bagian C, baris 21-163     42 baris "L2 Sub Category"
--   sheet `Lookup_Lists` bagian 2, baris 51-92  42 pasang label -> induk
--
-- Keduanya identik. Literal VALUES di bawah TIDAK diketik ulang — digenerate
-- oleh `kol_sub_category_taxonomy.baris_parent_sql()` dan `baris_seed_sql()`,
-- dan `tests/test_kol_sub_category_taxonomy.py` membandingkannya balik ke
-- KEDUA sheet.
--
-- ============================================================================
-- PERUBAHAN SKEMA — SEMINIMAL MUNGKIN, SEMUANYA ADITIF
-- ============================================================================
--
--   code       varchar(20) NULL   kode node Excel (BEA, BEA.SKN). Unik bila
--                                 terisi. NULL untuk kategori existing yang
--                                 tidak punya padanan persis di Excel.
--   level      varchar(20) NOT NULL DEFAULT 'category'
--                                 'category' | 'sub_category'. Default membuat
--                                 ke-28 baris existing otomatis 'category'.
--   parent_id  uuid NULL -> kol_categories(id)
--                                 wajib untuk sub_category, wajib NULL untuk
--                                 category (ck_kol_categories_level_parent).
--
-- Tidak ada kolom existing yang diubah tipe/nullability-nya, tidak ada
-- constraint existing yang disentuh, tidak ada DROP COLUMN.
--
-- ============================================================================
-- PARENT CATEGORY
-- ============================================================================
--
-- Nama PERSIS sama dengan baris existing -> baris existing jadi induk; hanya
-- kolom baru `code`-nya yang diisi (8: Beauty, Fashion, Food, Fitness,
-- Lifestyle, Travel, Entertainment, Gaming).
-- Tidak ada yang sama persis -> baris Category baru dengan label Excel
-- (6: Tech, Finance, Education, Parenting, Automotive, Home & Living).
--
-- Tidak ada alias nama-mirip (mis. Tech -> "Technology and gadgets"): Excel
-- bagian F tidak menyatakannya. Baris baru ber-taxonomy_key NULL, jadi
-- filter Discovery Category (migration 029, db.py, feature_engagement) tidak
-- berubah hasilnya.
--
-- ============================================================================
-- MAPPING KOL -> SUB CATEGORY: TIDAK DITULIS
-- ============================================================================
--
-- Field mapping KOL -> Sub Category BELUM DITETAPKAN, dan datanya belum ada.
--
-- kol_directory.category_ids BUKAN field itu. Array tersebut (tanpa FK)
-- adalah daftar CATEGORY: seluruh 5.172 id-nya menunjuk baris level
-- 'category', category_id selalu termasuk di dalamnya, dan endpoint
-- Discovery di app mengagregasi setiap elemennya sebagai chip Category tanpa
-- saringan level. Excel pun menulis "category_ids -> kol_categories (L1
-- only)" dan meminta field L2 tersendiri.
--
-- Migrasi ini tidak menulis ke kol_directory maupun agency_kol_accounts.
-- Verifikasi 7g menjadi PENJAGA: gagal kalau ada KOL yang lewat category_id
-- atau category_ids menunjuk baris Sub Category.
--
-- ============================================================================
-- DAMPAK KE KONSUMEN
-- ============================================================================
--
-- Konsumen yang membaca SELURUH kol_categories tanpa saringan (mis. dropdown
-- kategori di aplikasi) akan melihat 48 baris tambahan. Konsumen yang hanya
-- mau Category wajib menambah `WHERE level = 'category'`.
--
-- Konsumen yang membaca kategori lewat `c.id = ANY(k.category_ids)` (db.py,
-- feature_engagement, endpoint Discovery di app) tidak terdampak SELAMA
-- tidak ada id Sub Category di array itu — dan 7g menjaganya. db.py dan
-- feature_engagement juga menyaring `taxonomy_key IS NOT NULL`, yang NULL
-- untuk seluruh 48 baris baru; endpoint app tidak menyaring level.
--
-- ============================================================================
-- IDEMPOTEN
-- ============================================================================
--
-- ADD COLUMN IF NOT EXISTS, constraint/index dibuat hanya bila belum ada,
-- UPDATE code hanya bila masih NULL, INSERT hanya bila code belum ada,
-- DROP TABLE IF EXISTS. Dijalankan dua kali -> keadaan sama persis.
--
-- ============================================================================
-- REVERSIBLE (bagian 1-5)
-- ============================================================================
--
--     DELETE FROM public.kol_categories WHERE level = 'sub_category';
--     DELETE FROM public.kol_categories
--      WHERE code IN ('TEC','FIN','EDU','PAR','AUT','HNL');
--     ALTER TABLE public.kol_categories
--         DROP COLUMN parent_id, DROP COLUMN level, DROP COLUMN code;
--
-- Tabel lama bagian 6 bisa dibuat ulang dari git history bila perlu; isinya
-- 42 baris yang sama dan map kosong.
--
-- Untuk menjalankan tanpa menyimpan perubahan (COMMIT ditukar ROLLBACK):
--     python apply_migration.py migrations/047_kol_sub_category.sql --dry-run

BEGIN;

-- Tabel kecil, tapi dipakai jalur baca produksi: jangan antre lama di lock.
SET LOCAL lock_timeout = '5s';

-- ============================================================================
-- 1. KOLOM BARU
-- ============================================================================
-- Ditambahkan SEBELUM baseline supaya baseline bisa memakai `level`/`code`
-- pada run pertama maupun run ulang. Menambah kolom tidak mengubah nilai
-- kolom mana pun yang sudah ada.

ALTER TABLE public.kol_categories
    ADD COLUMN IF NOT EXISTS code      varchar(20),
    ADD COLUMN IF NOT EXISTS level     varchar(20) NOT NULL DEFAULT 'category',
    ADD COLUMN IF NOT EXISTS parent_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_kol_categories_parent'
                      AND conrelid = 'public.kol_categories'::regclass) THEN
        ALTER TABLE public.kol_categories
            ADD CONSTRAINT fk_kol_categories_parent
            FOREIGN KEY (parent_id) REFERENCES public.kol_categories(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_kol_categories_level'
                      AND conrelid = 'public.kol_categories'::regclass) THEN
        ALTER TABLE public.kol_categories
            ADD CONSTRAINT ck_kol_categories_level
            CHECK (level IN ('category', 'sub_category'));
    END IF;

    -- Category tidak punya induk; Sub Category wajib punya.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_kol_categories_level_parent'
                      AND conrelid = 'public.kol_categories'::regclass) THEN
        ALTER TABLE public.kol_categories
            ADD CONSTRAINT ck_kol_categories_level_parent
            CHECK ((level = 'category'     AND parent_id IS NULL)
                OR (level = 'sub_category' AND parent_id IS NOT NULL));
    END IF;
END $$;

-- Kode unik bila terisi. Partial, jadi baris existing ber-code NULL bebas.
CREATE UNIQUE INDEX IF NOT EXISTS uq_kol_categories_code
    ON public.kol_categories (code)
 WHERE code IS NOT NULL;

-- Nama Sub Category unik. Hanya berlaku untuk baris sub_category, jadi tidak
-- membatasi cara aplikasi menambah Category.
CREATE UNIQUE INDEX IF NOT EXISTS uq_kol_categories_sub_category_name
    ON public.kol_categories (name)
 WHERE level = 'sub_category';

CREATE INDEX IF NOT EXISTS ix_kol_categories_parent
    ON public.kol_categories (parent_id)
 WHERE parent_id IS NOT NULL;

COMMENT ON COLUMN public.kol_categories.code IS
    'Kode node taxonomy dari docs/brand_match_master.xlsx sheet Taxonomy '
    '(mis. BEA untuk Category, BEA.SKN untuk Sub Category). Unik bila terisi. '
    'NULL = kategori existing tanpa padanan nama persis di Excel.';

COMMENT ON COLUMN public.kol_categories.level IS
    'category = Parent Category, sub_category = Sub Category (child). '
    'Konsumen yang hanya mau Category wajib menyaring level = ''category''.';

COMMENT ON COLUMN public.kol_categories.parent_id IS
    'Parent Category dari sebuah Sub Category. NULL untuk level category. '
    'Parent mapping mengikuti Excel Lookup_Lists bagian 2.';

-- ============================================================================
-- 2. BASELINE  -- bukti bahwa data existing tidak tersentuh
-- ============================================================================
-- "Baris existing" = semua baris category KECUALI 6 induk baru. Pada run
-- pertama itu 28 baris; pada run ulang tetap 28 baris yang sama.

CREATE TEMP TABLE _047_existing ON COMMIT DROP AS
SELECT c.id, c.name, c.taxonomy_key, c.created_at, c.updated_at
  FROM public.kol_categories c
 WHERE c.level = 'category'
   AND (c.code IS NULL OR c.code NOT IN ('TEC','FIN','EDU','PAR','AUT','HNL'));

CREATE TEMP TABLE _047_baseline ON COMMIT DROP AS
SELECT
    (SELECT count(*) FROM _047_existing)                              AS jumlah_existing,
    (SELECT md5(string_agg(e.id::text || '|' || COALESCE(e.name, '-') || '|' ||
                           COALESCE(e.taxonomy_key, '-') || '|' ||
                           COALESCE(e.created_at::text, '-') || '|' ||
                           COALESCE(e.updated_at::text, '-'), E'\n' ORDER BY e.id))
       FROM _047_existing e)                                          AS checksum_existing,
    (SELECT md5(string_agg(k.id::text || '|' ||
                           COALESCE(k.category_id::text, '-') || '|' ||
                           COALESCE(k.category_ids::text, '-'), E'\n'
                           ORDER BY k.id))
       FROM public.kol_directory k)                                   AS checksum_kategori_kol,
    (SELECT md5(string_agg(a.id::text || '|' ||
                           COALESCE(a.category_id::text, '-'), E'\n' ORDER BY a.id))
       FROM public.agency_kol_accounts a)                             AS checksum_kategori_agency;

-- ============================================================================
-- 3. 14 PARENT CATEGORY
-- ============================================================================
-- Digenerate oleh kol_sub_category_taxonomy.baris_parent_sql().

CREATE TEMP TABLE _047_parent (code varchar(20), name varchar(80)) ON COMMIT DROP;
INSERT INTO _047_parent (code, name)
VALUES
    ('BEA', 'Beauty'),
    ('FAS', 'Fashion'),
    ('FOD', 'Food'),
    ('FIT', 'Fitness'),
    ('TEC', 'Tech'),
    ('FIN', 'Finance'),
    ('EDU', 'Education'),
    ('LIF', 'Lifestyle'),
    ('TRV', 'Travel'),
    ('PAR', 'Parenting'),
    ('ENT', 'Entertainment'),
    ('GAM', 'Gaming'),
    ('AUT', 'Automotive'),
    ('HNL', 'Home & Living');

-- 3a. Baris existing bernama persis sama -> isi `code` saja. -----------------
-- Hanya bila code masih NULL: nilai yang sudah ada tidak pernah ditimpa, dan
-- kalau ternyata berbeda, verifikasi 7c yang menolak.
UPDATE public.kol_categories AS c
   SET code = p.code
  FROM _047_parent p
 WHERE c.name = p.name
   AND c.level = 'category'
   AND c.code IS NULL
   AND NOT EXISTS (SELECT 1 FROM public.kol_categories x WHERE x.code = p.code);

-- 3b. Sisanya -> baris Category baru. ----------------------------------------
INSERT INTO public.kol_categories (name, code, level, created_at, updated_at)
SELECT p.name, p.code, 'category', now(), now()
  FROM _047_parent p
 WHERE NOT EXISTS (SELECT 1 FROM public.kol_categories x WHERE x.code = p.code)
   AND NOT EXISTS (SELECT 1 FROM public.kol_categories x WHERE x.name = p.name);

-- ============================================================================
-- 4. 42 SUB CATEGORY
-- ============================================================================
-- Digenerate oleh kol_sub_category_taxonomy.baris_seed_sql().

CREATE TEMP TABLE _047_sub (code varchar(20), parent_code varchar(20), name varchar(80))
    ON COMMIT DROP;
INSERT INTO _047_sub (code, parent_code, name)
VALUES
    ('BEA.SKN', 'BEA', 'Skincare'),
    ('BEA.MKP', 'BEA', 'Makeup'),
    ('BEA.HAR', 'BEA', 'Haircare'),
    ('FAS.STR', 'FAS', 'Streetwear'),
    ('FAS.HJB', 'FAS', 'Hijab Fashion'),
    ('FAS.LOC', 'FAS', 'Local Brand'),
    ('FOD.CUL', 'FOD', 'Culinary Review'),
    ('FOD.HCK', 'FOD', 'Home Cooking'),
    ('FOD.BEV', 'FOD', 'Coffee & Beverage'),
    ('FIT.HOM', 'FIT', 'Home Workout'),
    ('FIT.GYM', 'FIT', 'Gym & Strength'),
    ('FIT.RUN', 'FIT', 'Running'),
    ('TEC.GDG', 'TEC', 'Gadget Review'),
    ('TEC.SAAS', 'TEC', 'Software & SaaS'),
    ('TEC.AIP', 'TEC', 'AI & Productivity'),
    ('FIN.PFN', 'FIN', 'Personal Finance'),
    ('FIN.INV', 'FIN', 'Investing'),
    ('FIN.BIZ', 'FIN', 'Business'),
    ('EDU.STU', 'EDU', 'Study Tips'),
    ('EDU.LNG', 'EDU', 'Language'),
    ('EDU.CAR', 'EDU', 'Career'),
    ('LIF.VLG', 'LIF', 'Daily Vlog'),
    ('LIF.SLF', 'LIF', 'Self Improvement'),
    ('LIF.MIN', 'LIF', 'Minimalism'),
    ('TRV.DOM', 'TRV', 'Domestic Travel'),
    ('TRV.BGT', 'TRV', 'Budget Travel'),
    ('TRV.STY', 'TRV', 'Staycation & Hotel'),
    ('PAR.MOM', 'PAR', 'Momlife'),
    ('PAR.KID', 'PAR', 'Kids & Family'),
    ('PAR.PRG', 'PAR', 'Pregnancy & Newborn'),
    ('ENT.COM', 'ENT', 'Comedy'),
    ('ENT.MUS', 'ENT', 'Music'),
    ('ENT.FLM', 'ENT', 'Film & Series'),
    ('GAM.MOB', 'GAM', 'Mobile Gaming'),
    ('GAM.PCC', 'GAM', 'PC & Console'),
    ('GAM.ESP', 'GAM', 'Esports'),
    ('AUT.MTR', 'AUT', 'Motorcycle'),
    ('AUT.CAR', 'AUT', 'Car Review'),
    ('AUT.MOD', 'AUT', 'Modification & Aftermarket'),
    ('HNL.INT', 'HNL', 'Interior'),
    ('HNL.ORG', 'HNL', 'Home Organization'),
    ('HNL.IMP', 'HNL', 'Home Improvement');

INSERT INTO public.kol_categories (name, code, level, parent_id, created_at, updated_at)
SELECT s.name, s.code, 'sub_category', p.id, now(), now()
  FROM _047_sub s
  JOIN public.kol_categories p
    ON p.code = s.parent_code
   AND p.level = 'category'
 WHERE NOT EXISTS (SELECT 1 FROM public.kol_categories x WHERE x.code = s.code);

-- ============================================================================
-- 5. (tidak ada)  -- migrasi ini tidak menulis ke kol_directory atau
--    agency_kol_accounts. Mapping KOL -> Sub Category tidak dikarang.
-- ============================================================================

-- ============================================================================
-- 6. BERSIHKAN TABEL DARI VERSI SEBELUMNYA FILE INI
-- ============================================================================

DO $$
DECLARE
    v_map     bigint;
    v_beda    text;
    v_dep     text;
BEGIN
    IF to_regclass('public.kol_sub_category_map') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM public.kol_sub_category_map' INTO v_map;
        IF v_map <> 0 THEN
            RAISE EXCEPTION 'public.kol_sub_category_map berisi % baris -- '
                            'tidak di-DROP, periksa dulu asal datanya', v_map;
        END IF;
    END IF;

    IF to_regclass('public.kol_sub_category') IS NOT NULL THEN
        -- Isi tabel lama harus identik dengan yang baru ditulis, supaya DROP
        -- tidak menghilangkan informasi apa pun.
        EXECUTE $q$
            SELECT string_agg(COALESCE(o.code, n.code), ', ')
              FROM (SELECT code, parent_code, label FROM public.kol_sub_category) o
              FULL JOIN (SELECT c.code, p.code AS parent_code, c.name AS label
                           FROM public.kol_categories c
                           JOIN public.kol_categories p ON p.id = c.parent_id
                          WHERE c.level = 'sub_category') n
                ON n.code = o.code
             WHERE o.code IS NULL OR n.code IS NULL
                OR o.parent_code IS DISTINCT FROM n.parent_code
                OR o.label       IS DISTINCT FROM n.label
        $q$ INTO v_beda;
        IF v_beda IS NOT NULL THEN
            RAISE EXCEPTION 'public.kol_sub_category tidak identik dengan Sub '
                            'Category baru di kol_categories: %', v_beda;
        END IF;
    END IF;

    -- Tidak boleh ada view/FK dari luar kedua tabel yang bergantung padanya.
    SELECT string_agg(DISTINCT d.classid::regclass::text || ':' || d.objid, ', ')
      INTO v_dep
      FROM pg_depend d
      LEFT JOIN pg_constraint k ON d.classid = 'pg_constraint'::regclass
                               AND k.oid = d.objid
      LEFT JOIN pg_rewrite r    ON d.classid = 'pg_rewrite'::regclass
                               AND r.oid = d.objid
     WHERE d.refobjid IN (SELECT oid FROM pg_class
                           WHERE relnamespace = 'public'::regnamespace
                             AND relname IN ('kol_sub_category', 'kol_sub_category_map'))
       AND d.deptype = 'n'
       AND (   (r.oid IS NOT NULL)
            OR (k.oid IS NOT NULL
                AND k.conrelid NOT IN (SELECT oid FROM pg_class
                                        WHERE relnamespace = 'public'::regnamespace
                                          AND relname IN ('kol_sub_category',
                                                          'kol_sub_category_map'))));
    IF v_dep IS NOT NULL THEN
        RAISE EXCEPTION 'Ada objek yang bergantung pada tabel lama: %', v_dep;
    END IF;
END $$;

DROP TABLE IF EXISTS public.kol_sub_category_map;
DROP TABLE IF EXISTS public.kol_sub_category;

-- ============================================================================
-- 7. VERIFIKASI  -- gagal di sini membatalkan seluruh migrasi
-- ============================================================================

DO $$
DECLARE
    b            _047_baseline%ROWTYPE;
    v_n          bigint;
    v_n2         bigint;
    v_teks       text;
BEGIN
    SELECT * INTO b FROM _047_baseline;

    -- 7a. Tepat 42 Sub Category, 0 duplicate. ---------------------------------
    SELECT count(*), count(DISTINCT code) INTO v_n, v_n2
      FROM public.kol_categories WHERE level = 'sub_category';
    IF v_n <> 42 OR v_n2 <> 42 THEN
        RAISE EXCEPTION 'Sub Category: % baris / % code unik, harusnya 42/42', v_n, v_n2;
    END IF;

    -- 7b. Isi dan parent mapping PERSIS sesuai Excel, baris per baris. --------
    SELECT string_agg(COALESCE(s.code, c.code), ', ') INTO v_teks
      FROM _047_sub s
      FULL JOIN (SELECT c.code, c.name, p.code AS parent_code, p.level AS parent_level
                   FROM public.kol_categories c
                   LEFT JOIN public.kol_categories p ON p.id = c.parent_id
                  WHERE c.level = 'sub_category') c
        ON c.code = s.code
     WHERE s.code IS NULL OR c.code IS NULL
        OR c.name         IS DISTINCT FROM s.name
        OR c.parent_code  IS DISTINCT FROM s.parent_code
        OR c.parent_level IS DISTINCT FROM 'category';
    IF v_teks IS NOT NULL THEN
        RAISE EXCEPTION 'Sub Category / parent mapping tidak sesuai Excel: %', v_teks;
    END IF;

    -- 7c. 14 Parent Category ada, bernama sesuai Excel, masing-masing 3 anak.
    SELECT string_agg(p.code, ', ') INTO v_teks
      FROM _047_parent p
      LEFT JOIN public.kol_categories c
        ON c.code = p.code AND c.level = 'category' AND c.parent_id IS NULL
     WHERE c.id IS NULL OR c.name IS DISTINCT FROM p.name
        OR (SELECT count(*) FROM public.kol_categories k
             WHERE k.parent_id = c.id AND k.level = 'sub_category') <> 3;
    IF v_teks IS NOT NULL THEN
        RAISE EXCEPTION 'Parent Category salah / tidak punya 3 anak: %', v_teks;
    END IF;

    -- 8 induk WAJIB baris existing, 6 WAJIB baris baru.
    SELECT string_agg(c.code, ', ') INTO v_teks
      FROM public.kol_categories c
     WHERE c.level = 'category' AND c.code IS NOT NULL
       AND (c.code IN ('BEA','FAS','FOD','FIT','LIF','TRV','ENT','GAM'))
           <> EXISTS (SELECT 1 FROM _047_existing e WHERE e.id = c.id);
    IF v_teks IS NOT NULL THEN
        RAISE EXCEPTION 'Induk existing/baru tertukar: %', v_teks;
    END IF;

    -- 7d. Hanya 56 code (14 + 42) yang boleh terisi; tidak ada kode karangan.
    SELECT count(*) INTO v_n FROM public.kol_categories WHERE code IS NOT NULL;
    IF v_n <> 56 THEN
        RAISE EXCEPTION 'Jumlah baris ber-code % , harusnya 56', v_n;
    END IF;

    -- 7e. Tidak ada nama duplikat di seluruh tabel (case-insensitive). --------
    SELECT string_agg(n, ', ') INTO v_teks
      FROM (SELECT lower(name) AS n FROM public.kol_categories
             GROUP BY lower(name) HAVING count(*) > 1) d;
    IF v_teks IS NOT NULL THEN
        RAISE EXCEPTION 'Nama kategori duplikat: %', v_teks;
    END IF;

    -- 7f. Data existing UTUH. -------------------------------------------------
    SELECT count(*) INTO v_n
      FROM public.kol_categories c JOIN _047_existing e ON e.id = c.id;
    IF v_n <> b.jumlah_existing THEN
        RAISE EXCEPTION 'Baris kategori existing hilang: % -> %', b.jumlah_existing, v_n;
    END IF;

    SELECT md5(string_agg(c.id::text || '|' || COALESCE(c.name, '-') || '|' ||
                          COALESCE(c.taxonomy_key, '-') || '|' ||
                          COALESCE(c.created_at::text, '-') || '|' ||
                          COALESCE(c.updated_at::text, '-'), E'\n' ORDER BY c.id))
      INTO v_teks
      FROM public.kol_categories c JOIN _047_existing e ON e.id = c.id;
    IF v_teks IS DISTINCT FROM b.checksum_existing THEN
        RAISE EXCEPTION 'id/name/taxonomy_key/created_at/updated_at kategori existing berubah';
    END IF;

    SELECT count(*) INTO v_n FROM public.kol_categories c
      JOIN _047_existing e ON e.id = c.id
     WHERE c.level <> 'category' OR c.parent_id IS NOT NULL;
    IF v_n <> 0 THEN
        RAISE EXCEPTION '% kategori existing berubah level/parent', v_n;
    END IF;

    SELECT count(*) INTO v_n FROM public.kol_categories
     WHERE taxonomy_key IS NOT NULL AND id NOT IN (SELECT id FROM _047_existing);
    IF v_n <> 0 THEN
        RAISE EXCEPTION '% baris baru ber-taxonomy_key -- filter Discovery akan berubah', v_n;
    END IF;

    SELECT count(*) INTO v_n FROM public.kol_categories;
    IF v_n <> b.jumlah_existing + 6 + 42 THEN
        RAISE EXCEPTION 'Total kol_categories % , harusnya % + 6 + 42', v_n, b.jumlah_existing;
    END IF;

    -- 7g. Relasi KOL tidak tersentuh, dan belum ada KOL yang menunjuk Sub
    --     Category (mapping tidak dikarang).
    SELECT md5(string_agg(k.id::text || '|' ||
                          COALESCE(k.category_id::text, '-') || '|' ||
                          COALESCE(k.category_ids::text, '-'), E'\n'
                          ORDER BY k.id))
      INTO v_teks FROM public.kol_directory k;
    IF v_teks IS DISTINCT FROM b.checksum_kategori_kol THEN
        RAISE EXCEPTION 'kol_directory.category_id/category_ids berubah -- dilarang';
    END IF;

    SELECT md5(string_agg(a.id::text || '|' ||
                          COALESCE(a.category_id::text, '-'), E'\n' ORDER BY a.id))
      INTO v_teks FROM public.agency_kol_accounts a;
    IF v_teks IS DISTINCT FROM b.checksum_kategori_agency THEN
        RAISE EXCEPTION 'agency_kol_accounts.category_id berubah -- dilarang';
    END IF;

    SELECT count(*) INTO v_n
      FROM public.kol_directory k
     WHERE EXISTS (SELECT 1 FROM public.kol_categories c
                    WHERE c.level = 'sub_category'
                      AND (c.id = ANY(k.category_ids) OR c.id = k.category_id));
    IF v_n <> 0 THEN
        RAISE EXCEPTION '% KOL menunjuk Sub Category -- mapping belum ditetapkan', v_n;
    END IF;

    -- 7h. Tabel lama sudah tidak ada. -----------------------------------------
    IF to_regclass('public.kol_sub_category') IS NOT NULL
       OR to_regclass('public.kol_sub_category_map') IS NOT NULL THEN
        RAISE EXCEPTION 'Tabel lama kol_sub_category(_map) masih ada';
    END IF;

    RAISE NOTICE 'OK: 42 Sub Category di kol_categories (level=sub_category) '
                 'di bawah 14 Parent Category (8 existing + 6 baru, 3 anak per induk), '
                 '0 duplicate, parent mapping sesuai Excel. % kategori existing utuh. '
                 'kol_directory/agency_kol_accounts tidak berubah; 0 KOL menunjuk Sub Category. '
                 'Tabel lama kol_sub_category(_map) sudah dihapus.', b.jumlah_existing;
END $$;

COMMIT;
