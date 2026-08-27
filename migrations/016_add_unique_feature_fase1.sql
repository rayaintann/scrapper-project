-- 016_add_unique_feature_fase1.sql
--
-- Prasyarat Fase 1 orkestrasi Dagster: menambahkan UNIQUE constraint sesuai
-- grain pada 4 tabel feature yang akan diisi, supaya asset bisa memakai
-- strategi UPSERT (INSERT ... ON CONFLICT ... DO UPDATE).
--
-- Tanpa UNIQUE, `ON CONFLICT` tidak punya arbiter dan idempotensi hanya bisa
-- dijaga kode lewat pola UPDATE-lalu-INSERT -- yang punya celah balapan: dua
-- proses yang jalan bersamaan bisa sama-sama lolos cek NOT EXISTS lalu
-- sama-sama INSERT. Constraint ini memindahkan jaminan grain dari kode ke
-- database.
--
-- ============================================================================
-- CONSTRAINT YANG DITAMBAHKAN
-- ============================================================================
--
--   feature.ig_engagement_analysis   UNIQUE (social_account_id)
--   feature.tt_engagement_analysis   UNIQUE (social_account_id)
--   feature.ig_post_analysis         UNIQUE (social_account_id, media_id)
--   feature.tt_post_analysis         UNIQUE (social_account_id, video_id)
--
-- Grain-nya berbeda dan itu disengaja:
--   *_engagement_analysis  bergrain PER AKUN   -> 1 baris per social_account_id
--   *_post_analysis        bergrain PER KONTEN -> 1 baris per (akun, konten)
--
-- Penamaan `uq_<tabel>` mengikuti pola l1_silver, yang memakainya di 8 dari 8
-- tabelnya (uq_unified_post, uq_unified_profile, dst).
--
-- ============================================================================
-- KONDISI SEBELUM MIGRASI (diverifikasi 2026-08-21)
-- ============================================================================
--
--   tabel                    baris  grain unik  duplikat  NULL
--   ig_engagement_analysis       0           0         0     0
--   tt_engagement_analysis       0           0         0     0
--   ig_post_analysis             0           0         0     0
--   tt_post_analysis             0           0         0     0
--
-- Keempatnya kosong, jadi tidak ada risiko constraint ditolak data lama.
-- Constraint existing hanya PRIMARY KEY (id) + satu FK ke social_account(id);
-- belum ada UNIQUE sama sekali. Nama `uq_*` yang dipakai di sini juga belum
-- terpakai di database.
--
-- ============================================================================
-- CATATAN: KOLOM GRAIN MASIH NULLABLE
-- ============================================================================
--
-- Keempat kolom grain (`social_account_id`, `media_id`, `video_id`) nullable,
-- dan migrasi ini SENGAJA tidak mengubahnya -- di luar cakupan yang diminta.
--
-- Konsekuensinya perlu diketahui: PostgreSQL memperlakukan NULL sebagai nilai
-- yang selalu berbeda di dalam UNIQUE, jadi banyak baris ber-`social_account_id`
-- NULL tetap lolos. Selama asset pengisi selalu menulis nilai (dan memang
-- begitu rancangannya -- sumbernya JOIN ke social_account), constraint ini
-- efektif penuh. Kalau nanti ingin ditutup rapat, `NOT NULL` bisa ditambahkan
-- lewat migrasi tersendiri.
--
-- ============================================================================
-- CAKUPAN
-- ============================================================================
--
-- HANYA menambah 4 constraint UNIQUE pada 4 tabel yang disebut. Tidak ada
-- kolom, data, index lain, procedure, maupun tabel lain yang disentuh --
-- termasuk 5 tabel feature sisanya (audience, comments, brand_fit).
--
-- Jalankan:
--   python apply_migration.py migrations/016_add_unique_feature_fase1.sql --dry-run --yes
--   python apply_migration.py migrations/016_add_unique_feature_fase1.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga. Batalkan kalau ada duplikat atau constraint sudah ada.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r          record;
    n_dup      bigint;
    n_baris    bigint;
    n_null     bigint;
    sudah_ada  int;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('ig_engagement_analysis', 'social_account_id'),
            ('tt_engagement_analysis', 'social_account_id'),
            ('ig_post_analysis',       'social_account_id, media_id'),
            ('tt_post_analysis',       'social_account_id, video_id')
        ) AS v(tabel, kolom)
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM (SELECT %s FROM feature.%I GROUP BY %s HAVING count(*) > 1) d',
            r.kolom, r.tabel, r.kolom) INTO n_dup;
        EXECUTE format('SELECT count(*) FROM feature.%I', r.tabel) INTO n_baris;

        SELECT count(*) INTO sudah_ada
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'feature' AND t.relname = r.tabel AND c.contype = 'u';

        IF n_dup > 0 THEN
            RAISE EXCEPTION
                'feature.% punya % kombinasi (%) duplikat -- bereskan datanya lebih '
                'dulu; migrasi ini sengaja tidak mengubah data.', r.tabel, n_dup, r.kolom;
        END IF;

        IF sudah_ada > 0 THEN
            RAISE EXCEPTION
                'feature.% sudah punya % constraint UNIQUE -- migrasi dibatalkan '
                'supaya tidak menambah yang kedua.', r.tabel, sudah_ada;
        END IF;

        RAISE NOTICE 'Penjaga lolos: feature.% -> % baris, % duplikat pada (%).',
            r.tabel, n_baris, n_dup, r.kolom;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Langkah 1 -- engagement: grain PER AKUN.
-- ---------------------------------------------------------------------------
ALTER TABLE feature.ig_engagement_analysis
    ADD CONSTRAINT uq_ig_engagement_analysis UNIQUE (social_account_id);

ALTER TABLE feature.tt_engagement_analysis
    ADD CONSTRAINT uq_tt_engagement_analysis UNIQUE (social_account_id);

-- ---------------------------------------------------------------------------
-- Langkah 2 -- post: grain PER KONTEN.
-- ---------------------------------------------------------------------------
ALTER TABLE feature.ig_post_analysis
    ADD CONSTRAINT uq_ig_post_analysis UNIQUE (social_account_id, media_id);

ALTER TABLE feature.tt_post_analysis
    ADD CONSTRAINT uq_tt_post_analysis UNIQUE (social_account_id, video_id);

-- ---------------------------------------------------------------------------
-- Langkah 3 -- verifikasi sebelum transaksi ditutup.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    n_uq       int;
    n_idx      int;
    n_uq_lain  int;
    n_baris    bigint;
BEGIN
    -- 4 constraint UNIQUE yang diharapkan, dengan definisi yang tepat.
    SELECT count(*) INTO n_uq
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'feature' AND c.contype = 'u'
      AND (t.relname, c.conname, pg_get_constraintdef(c.oid)) IN (
            ('ig_engagement_analysis', 'uq_ig_engagement_analysis', 'UNIQUE (social_account_id)'),
            ('tt_engagement_analysis', 'uq_tt_engagement_analysis', 'UNIQUE (social_account_id)'),
            ('ig_post_analysis',       'uq_ig_post_analysis',       'UNIQUE (social_account_id, media_id)'),
            ('tt_post_analysis',       'uq_tt_post_analysis',       'UNIQUE (social_account_id, video_id)')
          );

    -- Index unik pendukung harus ikut terbentuk.
    SELECT count(*) INTO n_idx
    FROM pg_indexes
    WHERE schemaname = 'feature'
      AND indexname IN ('uq_ig_engagement_analysis','uq_tt_engagement_analysis',
                        'uq_ig_post_analysis','uq_tt_post_analysis');

    -- 5 tabel feature LAIN tidak boleh ikut dapat UNIQUE dari migrasi ini.
    -- brand_fit_analysis memang sudah punya 1 dari migration 014.
    SELECT count(*) INTO n_uq_lain
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'feature' AND c.contype = 'u'
      AND t.relname NOT IN ('ig_engagement_analysis','tt_engagement_analysis',
                            'ig_post_analysis','tt_post_analysis');

    SELECT (SELECT count(*) FROM feature.ig_engagement_analysis)
         + (SELECT count(*) FROM feature.tt_engagement_analysis)
         + (SELECT count(*) FROM feature.ig_post_analysis)
         + (SELECT count(*) FROM feature.tt_post_analysis)
      INTO n_baris;

    IF n_uq <> 4 THEN
        RAISE EXCEPTION 'Constraint UNIQUE terbentuk %, seharusnya 4 (nama/definisi tidak cocok)', n_uq;
    END IF;
    IF n_idx <> 4 THEN
        RAISE EXCEPTION 'Index unik terbentuk %, seharusnya 4', n_idx;
    END IF;
    IF n_uq_lain <> 1 THEN
        RAISE EXCEPTION 'UNIQUE di tabel feature lain berjumlah %, seharusnya 1 '
                        '(hanya brand_fit_analysis dari migration 014)', n_uq_lain;
    END IF;
    IF n_baris <> 0 THEN
        RAISE EXCEPTION 'Baris di 4 tabel target berubah jadi % -- seharusnya tetap 0', n_baris;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: 4 constraint UNIQUE + 4 index unik terbentuk, '
                 'tabel feature lain tidak tersentuh, 4 tabel target tetap 0 baris.';
END $$;

COMMIT;
