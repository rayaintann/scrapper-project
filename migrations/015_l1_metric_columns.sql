-- 015_l1_metric_columns.sql
--
-- Menambahkan tiga kolom metrik row-level ke layer L1, lalu mengisi yang
-- sumbernya sudah tersedia.
--
-- CAKUPAN: HANYA schema l1_silver. Tidak menyentuh `feature`, tidak menyentuh
-- L2, tidak membuat tabel, tidak membuat procedure/function.
--
-- ============================================================================
-- KOLOM YANG DITAMBAHKAN
-- ============================================================================
--
-- 1. l1_silver.unified_post.likes_hidden      boolean   -> DIISI
-- 2. l1_silver.unified_post.is_collaboration  boolean   -> DIISI
-- 3. l1_silver.unified_profile.followers_growth numeric -> SENGAJA TETAP NULL
--
-- Plus mengisi kolom yang SUDAH ADA:
-- 4. l1_silver.unified_post.engagement_rate    numeric  -> DIISI (0/221 sebelumnya)
--
-- ============================================================================
-- RUMUS
-- ============================================================================
--
-- likes_hidden
--     (likes = -1)
--   Instagram memakai -1 sebagai sentinel "jumlah like disembunyikan", bukan
--   angka nol. NULL kalau `likes` sendiri NULL - tidak diketahui, bukan false.
--   Terdampak: 15 dari 130 post Instagram, 0 dari 91 TikTok.
--
-- is_collaboration
--     username_post <> username_akun   (dinormalisasi)
--   `unified_post.username` menyimpan pemilik ASLI post. Untuk post kolaborasi
--   nilainya berbeda dari akun yang di-scrape. Normalisasi memakai ekspresi yang
--   sama dengan db.py:_SQL_NORMALIZED_USERNAME.
--   NULL kalau salah satu sisi NULL - pemilik tak diketahui BUKAN bukti
--   kolaborasi. `IS DISTINCT FROM` sendirian akan salah di sini karena ia
--   mengembalikan TRUE saat satu sisi NULL, jadi dibungkus CASE.
--   Terdampak: 41 dari 130 post Instagram, 0 dari 91 TikTok.
--
-- engagement_rate (per post)
--     CASE WHEN likes = -1 OR followers IS NULL OR followers = 0 THEN NULL
--          ELSE round((likes + comments) / followers * 100, 4) END
--   Dibulatkan 4 desimal, mengikuti transform.py:compute_engagement_rate().
--   Kolomnya `numeric` tanpa presisi, jadi tidak ada risiko overflow.
--   Akan terisi: 115 dari 130 Instagram, 90 dari 91 TikTok.
--
-- followers_growth
--     TIDAK DIISI. Butuh minimal dua snapshot per akun; saat ini 0 akun punya
--     lebih dari satu. Rumus jendelanya juga belum disepakati. Kolomnya dibuat
--     supaya strukturnya siap, nilainya menunggu.
--
-- ============================================================================
-- CATATAN PENTING
-- ============================================================================
--
-- * `followers` dan `username_akun` diambil dari baris `unified_profile`
--   TERBARU untuk akun tersebut, dengan `public.social_account.username`
--   sebagai cadangan untuk akun yang belum punya baris profil sama sekali
--   (kasus `inul.d` TikTok - satu-satunya akun dengan video tanpa profil).
--
-- * Perbandingan NULL memakai `IS NULL` eksplisit, bukan operator biasa.
--   Simulasi pra-migrasi memakai `NOT (likes <> -1 AND followers > 0)` dan satu
--   baris TikTok hilang dari kedua bucket karena `NOT (TRUE AND NULL)` = NULL.
--   Migrasi ini tidak mengulangi kesalahan itu.
--
-- * `updated_at` SENGAJA tidak disentuh. Kolom itu mencatat kapan baris berubah
--   dari sisi pipeline harmonisasi; menimpanya di sini akan mengaburkan
--   freshness data sumber dengan waktu pengisian metrik.
--
-- * Kedua procedure L1 (`sp_build_unified_post`, `sp_build_unified_profile`)
--   memakai daftar kolom eksplisit - diverifikasi tidak ada `SELECT *` - jadi
--   penambahan kolom ini aman untuk keduanya.
--   >> Konsekuensi yang perlu diketahui: karena procedure itu belum tahu kolom
--   >> baru ini, baris yang masuk lewat `sp_build_unified_post()` di kemudian
--   >> hari akan ber-`likes_hidden`/`is_collaboration`/`engagement_rate` NULL
--   >> sampai ada prosedur pengisi tersendiri (di luar cakupan migrasi ini).
--
-- Jalankan:
--   python apply_migration.py migrations/015_l1_metric_columns.sql --dry-run --yes
--   python apply_migration.py migrations/015_l1_metric_columns.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    n_sudah_ada int;
    n_er        int;
    n_post      bigint;
    n_profile   bigint;
BEGIN
    SELECT count(*) INTO n_sudah_ada FROM information_schema.columns
     WHERE table_schema = 'l1_silver'
       AND (   (table_name = 'unified_post'    AND column_name IN ('likes_hidden','is_collaboration'))
            OR (table_name = 'unified_profile' AND column_name = 'followers_growth'));
    IF n_sudah_ada <> 0 THEN
        RAISE EXCEPTION 'Sebagian kolom baru sudah ada (%) -- migrasi dibatalkan.', n_sudah_ada;
    END IF;

    SELECT count(*) INTO n_er FROM information_schema.columns
     WHERE table_schema = 'l1_silver' AND table_name = 'unified_post'
       AND column_name = 'engagement_rate';
    IF n_er <> 1 THEN
        RAISE EXCEPTION 'unified_post.engagement_rate tidak ditemukan -- migrasi dibatalkan.';
    END IF;

    SELECT count(*) INTO n_post    FROM l1_silver.unified_post;
    SELECT count(*) INTO n_profile FROM l1_silver.unified_profile;
    RAISE NOTICE 'Penjaga lolos: unified_post % baris, unified_profile % baris.',
        n_post, n_profile;
END $$;

-- ---------------------------------------------------------------------------
-- Langkah 1 -- tambahkan kolom. Nullable, tanpa default.
-- ---------------------------------------------------------------------------
ALTER TABLE l1_silver.unified_post    ADD COLUMN likes_hidden     boolean;
ALTER TABLE l1_silver.unified_post    ADD COLUMN is_collaboration boolean;
ALTER TABLE l1_silver.unified_profile ADD COLUMN followers_growth numeric;

COMMENT ON COLUMN l1_silver.unified_post.likes_hidden IS
    'TRUE bila likes = -1, sentinel Instagram untuk jumlah like yang '
    'disembunyikan. Post bertanda ini harus DIKELUARKAN dari perhitungan '
    'engagement, bukan dihitung nol.';
COMMENT ON COLUMN l1_silver.unified_post.is_collaboration IS
    'TRUE bila username pemilik post berbeda dari username akun yang di-scrape '
    '(post kolaborasi). Post bertanda ini harus DIKELUARKAN dari engagement '
    'rate akun, karena engagement-nya sebagian milik akun lain. '
    'NULL bila kepemilikan tidak bisa ditentukan.';
COMMENT ON COLUMN l1_silver.unified_post.engagement_rate IS
    'Engagement rate satu post, persen: (likes + comments) / followers * 100. '
    'NULL bila likes_hidden, atau followers akun tidak diketahui / nol.';
COMMENT ON COLUMN l1_silver.unified_profile.followers_growth IS
    'Pertumbuhan followers antar snapshot, persen. BELUM DIISI: butuh minimal '
    'dua snapshot per akun (saat ini 0 akun) dan rumus jendela yang disepakati.';

-- ---------------------------------------------------------------------------
-- Langkah 2 -- isi ketiga metrik post dalam satu UPDATE.
-- Hanya kolom baru + engagement_rate yang disentuh; kolom lain tidak diubah.
-- ---------------------------------------------------------------------------
UPDATE l1_silver.unified_post u
   SET likes_hidden = CASE WHEN u.likes IS NULL THEN NULL
                           ELSE (u.likes = -1) END,

       is_collaboration = CASE
           WHEN u.username IS NULL OR p.username_akun IS NULL THEN NULL
           ELSE (ltrim(lower(btrim(u.username)), '@')
                 IS DISTINCT FROM p.username_akun)
       END,

       engagement_rate = CASE
           WHEN u.likes IS NULL OR u.likes = -1
             OR p.followers_count IS NULL OR p.followers_count = 0 THEN NULL
           ELSE round((u.likes + COALESCE(u.comments, 0))::numeric
                      / p.followers_count * 100, 4)
       END
  FROM (
        SELECT sa.id AS social_account_id,
               ltrim(lower(btrim(split_part(split_part(
                   COALESCE(up.username, sa.username), '?', 1), '/', 1))), '@') AS username_akun,
               up.followers_count
        FROM public.social_account sa
        LEFT JOIN LATERAL (
            SELECT username, followers_count
            FROM l1_silver.unified_profile pr
            WHERE pr.social_account_id = sa.id
            ORDER BY date DESC
            LIMIT 1
        ) up ON true
       ) p
 WHERE p.social_account_id = u.social_account_id;

-- Langkah 3 -- followers_growth SENGAJA tidak di-UPDATE. Tidak ada statement
-- di sini, dan itu memang yang diinginkan.

-- ---------------------------------------------------------------------------
-- Langkah 4 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    n_post        bigint;
    n_profile     bigint;
    n_kol_post    int;
    n_kol_profile int;
    n_lh_null     bigint;
    n_ic_null     bigint;
    n_lh_salah    bigint;
    n_ic_salah    bigint;
    n_er_isi      bigint;
    n_er_salah    bigint;
    n_fg_isi      bigint;
BEGIN
    SELECT count(*) INTO n_post    FROM l1_silver.unified_post;
    SELECT count(*) INTO n_profile FROM l1_silver.unified_profile;

    SELECT count(*) INTO n_kol_post FROM information_schema.columns
     WHERE table_schema='l1_silver' AND table_name='unified_post';
    SELECT count(*) INTO n_kol_profile FROM information_schema.columns
     WHERE table_schema='l1_silver' AND table_name='unified_profile';

    -- likes_hidden harus konsisten dengan sumbernya di setiap baris.
    SELECT count(*) INTO n_lh_null  FROM l1_silver.unified_post WHERE likes_hidden IS NULL;
    SELECT count(*) INTO n_lh_salah FROM l1_silver.unified_post
     WHERE likes IS NOT NULL AND likes_hidden IS DISTINCT FROM (likes = -1);

    SELECT count(*) INTO n_ic_null FROM l1_silver.unified_post WHERE is_collaboration IS NULL;
    SELECT count(*) INTO n_ic_salah FROM l1_silver.unified_post u
     WHERE u.username IS NOT NULL
       AND u.is_collaboration IS NULL;

    SELECT count(*) INTO n_er_isi FROM l1_silver.unified_post WHERE engagement_rate IS NOT NULL;
    -- Tidak boleh ada ER terisi untuk post yang like-nya disembunyikan.
    SELECT count(*) INTO n_er_salah FROM l1_silver.unified_post
     WHERE likes_hidden IS TRUE AND engagement_rate IS NOT NULL;

    SELECT count(*) INTO n_fg_isi FROM l1_silver.unified_profile
     WHERE followers_growth IS NOT NULL;

    IF n_post <> 221 OR n_profile <> 1971 THEN
        RAISE EXCEPTION 'Jumlah baris berubah: post=%, profile=% (seharusnya 221 dan 1971)',
            n_post, n_profile;
    END IF;
    IF n_kol_post <> 41 THEN
        RAISE EXCEPTION 'unified_post punya % kolom, seharusnya 41 (39 + 2)', n_kol_post;
    END IF;
    IF n_kol_profile <> 38 THEN
        RAISE EXCEPTION 'unified_profile punya % kolom, seharusnya 38 (37 + 1)', n_kol_profile;
    END IF;
    IF n_lh_salah <> 0 THEN
        RAISE EXCEPTION '% baris likes_hidden tidak cocok dengan likes', n_lh_salah;
    END IF;
    IF n_ic_salah <> 0 THEN
        RAISE EXCEPTION '% baris punya username tapi is_collaboration NULL', n_ic_salah;
    END IF;
    IF n_er_salah <> 0 THEN
        RAISE EXCEPTION '% baris likes_hidden=TRUE tapi engagement_rate terisi', n_er_salah;
    END IF;
    IF n_fg_isi <> 0 THEN
        RAISE EXCEPTION 'followers_growth terisi di % baris, seharusnya seluruhnya NULL', n_fg_isi;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: post % baris / % kolom, profile % baris / % kolom.',
        n_post, n_kol_post, n_profile, n_kol_profile;
    RAISE NOTICE '  likes_hidden     : % NULL, 0 tidak cocok', n_lh_null;
    RAISE NOTICE '  is_collaboration : % NULL', n_ic_null;
    RAISE NOTICE '  engagement_rate  : % terisi, 0 melanggar aturan likes_hidden', n_er_isi;
    RAISE NOTICE '  followers_growth : 0 terisi (sesuai rencana)';
END $$;

COMMIT;
