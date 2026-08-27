-- 017_ig_post_engagement_rate_precision.sql
--
-- Memperlebar `feature.ig_post_analysis.engagement_rate` dari numeric(5,2)
-- menjadi numeric(9,4), supaya nilai engagement rate tidak lagi kehilangan
-- dua desimal terakhir saat ditulis asset `ig_post_analysis`.
--
-- ============================================================================
-- MASALAH YANG DIPERBAIKI (diverifikasi 2026-08-21)
-- ============================================================================
--
-- Sumbernya `l1_silver.unified_post.engagement_rate` bertipe `numeric` tanpa
-- batas, diisi `round(..., 4)` oleh migration 015 dan `sp_build_unified_post()`,
-- jadi selalu 4 desimal. Kolom targetnya hanya menampung 2.
--
-- Dampak pembulatan pada data sekarang:
--
--   platform    nilai berubah kalau dibulatkan ke 2 desimal   jadi 0 padahal bukan 0
--   instagram                                    114 / 115                        7
--   tiktok                                        90 /  90                        8
--
-- Dibulatkan ke 4 desimal: 0 nilai berubah, di kedua platform. Jadi 4 desimal
-- persis cukup -- bukan tebakan, melainkan presisi yang memang dipakai sumber.
--
-- Yang paling merusak bukan pergeseran kecilnya, melainkan 7 post Instagram
-- yang engagement rate-nya hancur menjadi 0,00. Nol berarti "tidak ada
-- engagement", padahal nilai sebenarnya 0,0012 sampai 0,0049 -- kecil, tapi
-- bukan nol.
--
-- ============================================================================
-- KENAPA numeric(9,4)
-- ============================================================================
--
-- SKALA 4 -- menyamai presisi sumber, dan menjadikannya fakta yang dijamin
--   skema, bukan sekadar konvensi yang dijaga dua procedure. Data saat ini
--   memakai paling banyak 4 desimal signifikan di kedua platform.
--
-- PRESISI 9 -- menyisakan 5 digit bulat (maksimum 99.999,9999%). Nilai
--   tertinggi sekarang 11,1440 (IG) dan 263,5992 (TT), jadi plafonnya sekitar
--   400x di atas data nyata. Engagement rate memang bisa besar untuk akun
--   berpengikut sedikit yang satu kontennya viral, dan plafon yang terlalu
--   rapat memaksa pilihan antara meng-clamp (memalsukan angka diam-diam) atau
--   gagal insert (mematikan pipeline). Dengan 9 digit, dua-duanya tidak
--   pernah perlu terjadi pada data yang masuk akal.
--
-- Alternatif `numeric` tanpa batas -- persis seperti sumbernya -- sengaja
-- tidak dipakai: skala yang tidak dideklarasikan berarti kolom ini menerima
-- berapa pun desimal yang kebetulan dikirim penulisnya, sehingga "kolom ini
-- 4 desimal" tidak lagi bisa dipastikan dari skema.
--
-- ============================================================================
-- NILAI LAMA TETAP 2 DESIMAL SAMPAI ASSET DIJALANKAN ULANG
-- ============================================================================
--
-- ALTER hanya melebarkan wadahnya. 130 baris yang sudah ada TIDAK ikut
-- diperbaiki -- 0,23 menjadi 0,2300, bukan kembali ke 0,2345 -- karena
-- presisi yang hilang tidak tersimpan di tabel ini.
--
-- Migrasi ini SENGAJA tidak menghitung ulang dari `unified_post`. Rumus
-- engagement rate sudah punya satu rumah (asset `ig_post_analysis`), dan
-- menyalinnya ke sini akan menciptakan tempat kedua yang harus ikut diubah
-- setiap kali rumusnya berubah -- persis sumber ketidakcocokan yang selama
-- ini dihindari.
--
-- Jadi setelah migrasi ini: JALANKAN ULANG asset `ig_post_analysis`.
-- UPSERT-nya menimpa `engagement_rate` dengan penugasan langsung, jadi
-- sekali materialize seluruh 82 nilai kembali ke presisi penuh.
-- Sampai itu dilakukan, nilai di tabel TERLIHAT 4 desimal (0,2300) padahal
-- masih hasil pembulatan 2 desimal.
--
-- ============================================================================
-- KEAMANAN
-- ============================================================================
--
--   * Tidak ada view, materialized view, rule, atau constraint yang bergantung
--     pada kolom ini (diverifikasi lewat pg_depend dan pg_get_viewdef) -- jadi
--     ALTER tidak akan ditolak.
--   * Tidak ada index yang menyentuh `engagement_rate`; 2 index yang ada
--     (pkey pada id, uq pada social_account_id+media_id) tidak terpengaruh.
--   * Perubahan skala memicu rewrite tabel, tapi tabelnya 130 baris / 88 kB.
--   * numeric(5,2) -> numeric(9,4) adalah pelebaran murni: setiap nilai lama
--     muat tanpa perlu dibulatkan, jadi ALTER tidak bisa gagal karena data.
--
-- CAKUPAN: satu kolom di satu tabel. `ig_engagement_analysis` dan
-- `tt_engagement_analysis` juga masih numeric(5,2) dan punya keterbatasan yang
-- sama, tapi keduanya DI LUAR cakupan yang diminta dan tidak disentuh.
--
-- Jalankan:
--   python apply_migration.py migrations/017_ig_post_engagement_rate_precision.sql --dry-run --yes
--   python apply_migration.py migrations/017_ig_post_engagement_rate_precision.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga. Batalkan kalau kondisi awal bukan yang diasumsikan.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    tipe_sekarang text;
    n_bergantung  int;
    n_baris       bigint;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipe_sekarang
    FROM pg_attribute a
    WHERE a.attrelid = 'feature.ig_post_analysis'::regclass
      AND a.attname = 'engagement_rate' AND a.attnum > 0 AND NOT a.attisdropped;

    IF tipe_sekarang IS NULL THEN
        RAISE EXCEPTION 'Kolom feature.ig_post_analysis.engagement_rate tidak ditemukan.';
    END IF;

    IF tipe_sekarang = 'numeric(9,4)' THEN
        RAISE EXCEPTION 'Kolom sudah numeric(9,4) -- migrasi ini sudah pernah dijalankan.';
    END IF;

    IF tipe_sekarang <> 'numeric(5,2)' THEN
        RAISE EXCEPTION 'Tipe awal % di luar dugaan (diharapkan numeric(5,2)) -- '
                        'periksa dulu sebelum melanjutkan.', tipe_sekarang;
    END IF;

    -- View/rule yang bergantung pada kolom ini akan membuat ALTER gagal.
    SELECT count(*) INTO n_bergantung
    FROM pg_depend d
    JOIN pg_rewrite r ON r.oid = d.objid
    WHERE d.refobjid = 'feature.ig_post_analysis'::regclass
      AND d.refobjsubid = (SELECT attnum FROM pg_attribute
                           WHERE attrelid = 'feature.ig_post_analysis'::regclass
                             AND attname = 'engagement_rate');

    IF n_bergantung > 0 THEN
        RAISE EXCEPTION 'Ada % view/rule yang bergantung pada kolom ini -- '
                        'ALTER akan ditolak. Periksa dulu.', n_bergantung;
    END IF;

    SELECT count(*) INTO n_baris FROM feature.ig_post_analysis;
    RAISE NOTICE 'Penjaga lolos: tipe % , % baris, 0 view bergantung.',
        tipe_sekarang, n_baris;
END $$;

-- ---------------------------------------------------------------------------
-- Langkah 1 -- pelebaran tipe.
-- ---------------------------------------------------------------------------
ALTER TABLE feature.ig_post_analysis
    ALTER COLUMN engagement_rate TYPE numeric(9,4);

-- ---------------------------------------------------------------------------
-- Langkah 2 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    tipe_baru   text;
    n_baris     bigint;
    n_terisi    bigint;
    n_kolom     int;
    n_idx       int;
    er_maks     numeric;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod) INTO tipe_baru
    FROM pg_attribute a
    WHERE a.attrelid = 'feature.ig_post_analysis'::regclass
      AND a.attname = 'engagement_rate';

    SELECT count(*), count(engagement_rate), max(engagement_rate)
      INTO n_baris, n_terisi, er_maks
    FROM feature.ig_post_analysis;

    SELECT count(*) INTO n_kolom FROM information_schema.columns
    WHERE table_schema = 'feature' AND table_name = 'ig_post_analysis';

    SELECT count(*) INTO n_idx FROM pg_indexes
    WHERE schemaname = 'feature' AND tablename = 'ig_post_analysis';

    IF tipe_baru <> 'numeric(9,4)' THEN
        RAISE EXCEPTION 'Tipe akhir %, seharusnya numeric(9,4)', tipe_baru;
    END IF;
    IF n_baris <> 130 THEN
        RAISE EXCEPTION 'Jumlah baris berubah menjadi % -- seharusnya tetap 130', n_baris;
    END IF;
    IF n_terisi <> 82 THEN
        RAISE EXCEPTION 'engagement_rate terisi % -- seharusnya tetap 82', n_terisi;
    END IF;
    IF n_kolom <> 18 THEN
        RAISE EXCEPTION 'Jumlah kolom %, seharusnya tetap 18', n_kolom;
    END IF;
    IF n_idx <> 2 THEN
        RAISE EXCEPTION 'Jumlah index %, seharusnya tetap 2', n_idx;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: tipe %, % baris, % nilai terisi, maks %, '
                 '% kolom, % index.', tipe_baru, n_baris, n_terisi, er_maks,
                 n_kolom, n_idx;
    RAISE NOTICE 'PERHATIAN: nilai lama masih hasil pembulatan 2 desimal. '
                 'Jalankan ulang asset ig_post_analysis untuk memulihkan presisinya.';
END $$;

COMMIT;
