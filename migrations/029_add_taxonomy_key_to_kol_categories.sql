-- 029_add_taxonomy_key_to_kol_categories.sql
--
-- Menambahkan taxonomy Discovery di atas 28 kategori mentah yang sudah ada,
-- TANPA menyentuh satu pun kategori itu sendiri.
--
-- KENAPA KOLOM, BUKAN TABEL MAPPING ATAU KATEGORI BARU
-- ====================================================
-- Relasinya many-to-one: dari 28 kategori, tidak ada satu pun yang perlu masuk
-- ke lebih dari satu Discovery Category. Tabel mapping terpisah baru sepadan
-- kalau relasinya many-to-many.
--
-- `public.kol_categories` hanya 28 baris dan sudah menjadi titik rujukan resmi
-- (FK dari `kol_directory.category_id` dan `agency_kol_accounts.category_id`),
-- jadi taxonomy yang dipasang di sini otomatis berlaku untuk keduanya.
--
-- 9 Discovery Category TIDAK dibuat sebagai baris kategori baru. Membuatnya
-- sebagai baris akan mencampur "kategori kreator" dengan "grup taxonomy" di satu
-- tabel, dan membuka peluang id grup ikut tertulis ke `kol_directory.category_ids`.
-- Karena itu taxonomy disimpan sebagai NILAI TEKS, bukan sebagai baris ber-id.
--
-- YANG TIDAK DISENTUH MIGRASI INI
-- ===============================
--   * Tidak ada kategori mentah yang dihapus atau di-rename.
--   * `kol_directory.category_id` dan `kol_directory.category_ids` tidak diubah
--     sama sekali — dijaga oleh checksum before/after di blok verifikasi.
--   * Tidak ada tabel lain yang disentuh.
--   * Tidak ada baris kategori baru.
--
-- IDEMPOTEN
-- =========
-- `ADD COLUMN IF NOT EXISTS` membuat penambahan kolom aman diulang. Blok UPDATE
-- bersifat DEKLARATIF: seluruh 28 baris ditulis ulang setiap kali dijalankan,
-- termasuk 6 kategori unmapped yang dikembalikan ke NULL secara eksplisit.
-- Menjalankan file ini dua kali menghasilkan keadaan yang persis sama, dan
-- memperbaiki kembali nilai yang sempat diubah manual di luar migrasi.
--
-- REVERSIBLE
-- ==========
-- Perubahannya aditif dan bisa dibatalkan penuh dengan satu perintah:
--
--     ALTER TABLE public.kol_categories DROP COLUMN IF EXISTS taxonomy_key;
--
-- Tidak ada data lama yang hilang saat rollback, karena kolom ini tidak pernah
-- menjadi sumber data apa pun — ia hanya label turunan di atas `name`.
--
-- Untuk menjalankan tanpa menyimpan perubahan (COMMIT ditukar ROLLBACK):
--     python apply_migration.py migrations/029_add_taxonomy_key_to_kol_categories.sql --dry-run

BEGIN;

-- 1. Rekam keadaan awal untuk pembuktian di akhir ----------------------------
-- `category_ids` dan `category_id` harus terbukti TIDAK berubah oleh migrasi
-- ini. Checksum diambil sebelum perubahan apa pun, lalu dibandingkan di blok
-- verifikasi. Membandingkan terhadap nilai yang direkam di transaksi yang sama
-- (bukan terhadap angka yang di-hardcode) membuat pemeriksaan ini tetap sah
-- kapan pun migrasi dijalankan.

CREATE TEMP TABLE _029_baseline ON COMMIT DROP AS
SELECT
    (SELECT count(*) FROM public.kol_categories)                      AS jumlah_kategori,
    (SELECT md5(string_agg(k.id::text || '|' ||
                           COALESCE(k.category_id::text, '-') || '|' ||
                           COALESCE(k.category_ids::text, '-'), E'\n'
                           ORDER BY k.id))
       FROM public.kol_directory k)                                   AS checksum_kategori_kol,
    (SELECT md5(string_agg(c.id::text || '|' || c.name, E'\n' ORDER BY c.id))
       FROM public.kol_categories c)                                  AS checksum_kategori_mentah;

-- 2. Kolom taxonomy ----------------------------------------------------------
-- Nullable dengan sengaja: NULL adalah representasi resmi "Unmapped", sehingga
-- 6 kategori di luar 9 Discovery Category tidak butuh penanganan khusus.

ALTER TABLE public.kol_categories
    ADD COLUMN IF NOT EXISTS taxonomy_key text;

COMMENT ON COLUMN public.kol_categories.taxonomy_key IS
    'Discovery Category untuk KOL Discovery. Salah satu dari: Lifestyle, Beauty, '
    'Fashion, Food, Fitness, Entertainment, Moms, Gen Z, Tech. '
    'NULL = Unmapped (kategori mentah di luar 9 Discovery Category). '
    'Label turunan di atas `name`; bukan sumber data dan tidak pernah menjadi FK.';

-- 3. Isi taxonomy sesuai mapping final ---------------------------------------
-- Ditulis lengkap untuk ke-28 kategori supaya deklaratif dan idempoten:
-- 22 dipetakan, 6 dikembalikan ke NULL.

UPDATE public.kol_categories AS c
   SET taxonomy_key = m.taxonomy_key
  FROM (VALUES
        -- Lifestyle
        ('Lifestyle',                          'Lifestyle'),
        ('Home Decor',                         'Lifestyle'),
        ('Travel',                             'Lifestyle'),
        -- Beauty
        ('Beauty',                             'Beauty'),
        -- Fashion
        ('Fashion',                            'Fashion'),
        -- Food
        ('Foodies',                            'Food'),
        ('Food',                               'Food'),
        ('Cooking',                            'Food'),
        -- Fitness
        ('Fitness',                            'Fitness'),
        ('Sports',                             'Fitness'),
        ('Gym Enthusiast',                     'Fitness'),
        ('Cyclist',                            'Fitness'),
        -- Entertainment
        ('Entertainment',                      'Entertainment'),
        ('Humor',                              'Entertainment'),
        ('Musicians',                          'Entertainment'),
        ('Dance',                              'Entertainment'),
        ('Story Teller',                       'Entertainment'),
        -- Moms
        ('Moms',                               'Moms'),
        ('Parenting and family',               'Moms'),
        -- Gen Z
        ('Gen Z',                              'Gen Z'),
        -- Tech
        ('Technology and gadgets',             'Tech'),
        ('Gaming',                             'Tech'),
        -- Unmapped: NULL eksplisit, bukan dibiarkan
        ('Automotive and motorsports',         NULL),
        ('Medical',                            NULL),
        ('Spirituality and religion',          NULL),
        ('Animal Lovers',                      NULL),
        ('Business and entrepreneurship',      NULL),
        ('Environmentalism and sustainability', NULL)
       ) AS m(name, taxonomy_key)
 WHERE c.name = m.name
   AND c.taxonomy_key IS DISTINCT FROM m.taxonomy_key;

-- 4. Verifikasi --------------------------------------------------------------
-- Gagal di sini membatalkan seluruh migrasi.

DO $$
DECLARE
    b                 _029_baseline%ROWTYPE;
    v_checksum_kol    text;
    v_checksum_mentah text;
    v_jumlah          bigint;
    v_mapped          bigint;
    v_unmapped        bigint;
    v_taxonomy_asing  text;
    v_salah_petakan   text;
BEGIN
    SELECT * INTO b FROM _029_baseline;

    -- 4a. Kolom harus terbentuk.
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name   = 'kol_categories'
                      AND column_name  = 'taxonomy_key') THEN
        RAISE EXCEPTION 'Kolom taxonomy_key belum terbentuk di public.kol_categories';
    END IF;

    -- 4b. Tidak boleh ada kategori mentah yang hilang, bertambah, atau di-rename.
    SELECT count(*) INTO v_jumlah FROM public.kol_categories;
    IF v_jumlah <> b.jumlah_kategori THEN
        RAISE EXCEPTION 'Jumlah kategori berubah: % -> %', b.jumlah_kategori, v_jumlah;
    END IF;

    SELECT md5(string_agg(c.id::text || '|' || c.name, E'\n' ORDER BY c.id))
      INTO v_checksum_mentah FROM public.kol_categories c;
    IF v_checksum_mentah IS DISTINCT FROM b.checksum_kategori_mentah THEN
        RAISE EXCEPTION 'id/name kategori mentah berubah — migrasi ini tidak boleh menyentuhnya';
    END IF;

    -- 4c. category_id dan category_ids di kol_directory harus utuh.
    SELECT md5(string_agg(k.id::text || '|' ||
                          COALESCE(k.category_id::text, '-') || '|' ||
                          COALESCE(k.category_ids::text, '-'), E'\n'
                          ORDER BY k.id))
      INTO v_checksum_kol FROM public.kol_directory k;
    IF v_checksum_kol IS DISTINCT FROM b.checksum_kategori_kol THEN
        RAISE EXCEPTION 'kol_directory.category_id/category_ids berubah — dilarang oleh migrasi ini';
    END IF;

    -- 4d. Nilai taxonomy_key hanya boleh salah satu dari 9, atau NULL.
    SELECT string_agg(DISTINCT taxonomy_key, ', ')
      INTO v_taxonomy_asing
      FROM public.kol_categories
     WHERE taxonomy_key IS NOT NULL
       AND taxonomy_key NOT IN ('Lifestyle','Beauty','Fashion','Food','Fitness',
                                'Entertainment','Moms','Gen Z','Tech');
    IF v_taxonomy_asing IS NOT NULL THEN
        RAISE EXCEPTION 'taxonomy_key di luar 9 Discovery Category: %', v_taxonomy_asing;
    END IF;

    -- 4e. Komposisi harus tepat 22 mapped + 6 unmapped.
    SELECT count(*) FILTER (WHERE taxonomy_key IS NOT NULL),
           count(*) FILTER (WHERE taxonomy_key IS NULL)
      INTO v_mapped, v_unmapped
      FROM public.kol_categories;

    IF v_mapped <> 22 OR v_unmapped <> 6 THEN
        RAISE EXCEPTION 'Komposisi taxonomy salah: % mapped / % unmapped (harusnya 22/6)',
                        v_mapped, v_unmapped;
    END IF;

    -- 4f. Setiap pasangan name -> taxonomy_key harus persis sesuai mapping final.
    SELECT string_agg(c.name || ' => ' || COALESCE(c.taxonomy_key, 'NULL'), ', ')
      INTO v_salah_petakan
      FROM public.kol_categories c
      JOIN (VALUES
            ('Lifestyle','Lifestyle'),('Home Decor','Lifestyle'),('Travel','Lifestyle'),
            ('Beauty','Beauty'),('Fashion','Fashion'),
            ('Foodies','Food'),('Food','Food'),('Cooking','Food'),
            ('Fitness','Fitness'),('Sports','Fitness'),('Gym Enthusiast','Fitness'),('Cyclist','Fitness'),
            ('Entertainment','Entertainment'),('Humor','Entertainment'),('Musicians','Entertainment'),
            ('Dance','Entertainment'),('Story Teller','Entertainment'),
            ('Moms','Moms'),('Parenting and family','Moms'),
            ('Gen Z','Gen Z'),
            ('Technology and gadgets','Tech'),('Gaming','Tech')
           ) AS h(name, taxonomy_key) ON h.name = c.name
     WHERE c.taxonomy_key IS DISTINCT FROM h.taxonomy_key;

    IF v_salah_petakan IS NOT NULL THEN
        RAISE EXCEPTION 'Mapping tidak sesuai untuk: %', v_salah_petakan;
    END IF;

    -- 4g. Ke-9 Discovery Category harus benar-benar terpakai.
    IF (SELECT count(DISTINCT taxonomy_key) FROM public.kol_categories
         WHERE taxonomy_key IS NOT NULL) <> 9 THEN
        RAISE EXCEPTION 'Jumlah Discovery Category terpakai bukan 9';
    END IF;

    RAISE NOTICE 'OK: taxonomy_key terpasang. 28 kategori utuh, 22 mapped ke 9 Discovery Category, 6 unmapped (NULL). category_id/category_ids tidak berubah.';
END $$;

COMMIT;
