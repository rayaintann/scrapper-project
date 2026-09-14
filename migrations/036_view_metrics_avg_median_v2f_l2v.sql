-- 036_view_metrics_avg_median_v2f_l2v.sql
--
-- Empat metrik views yang sudah disetujui, dari layer feature sampai L2 Gold:
--
--     Avg Views      rata-rata views post yang views-nya diketahui
--     Median Views   median views post yang views-nya diketahui
--     V2F            views / followers x 100  (View-to-Follower Ratio)
--     L2V            avg likes / views x 100  (Like-to-View Ratio)
--
-- Migrasi ini HANYA menambah kolom. Tidak ada tabel baru, tidak ada schema
-- baru, tidak ada perubahan tipe, tidak ada DROP, dan tidak satu baris pun
-- diubah atau dihapus. Seluruh kolom NULLABLE tanpa DEFAULT, jadi baris yang
-- sudah ada tetap sah dan bernilai NULL sampai asset pengisinya jalan.
--
-- ============================================================================
-- KENAPA TIDAK ADA TABEL BARU
-- ============================================================================
--
-- Keempat metrik bergrain PER AKUN. Tabel dengan grain itu sudah ada, satu di
-- tiap layer, dan masing-masing sudah menampung metrik sejenis:
--
--   feature.ig_engagement_analysis   grain (social_account_id)
--   feature.tt_engagement_analysis   grain (social_account_id)
--       -- sudah menampung engagement_rate, total_likes, total_comments,
--          reel_plays (IG) dan total_views (TT). Rumahnya metrik engagement
--          per akun; keempat metrik ini metrik engagement per akun.
--
--   l2_gold.kol_profile_card         grain (social_account_id, platform)
--       -- sudah menampung followers_count, tier, followers_growth. Kartu
--          ringkas per akun yang dibaca KOL Directory dan KOL Detail.
--
-- `l2_gold.kol_metric_daily` SENGAJA TIDAK dipakai. Grainnya
-- (akun, platform, metric_date) dengan metric_date = tanggal TAYANG post.
-- Median tidak bisa hidup di sana: median harian dari satu-dua post per hari
-- bukan median akun, dan median rentang N hari TIDAK BISA diturunkan dari
-- median harian -- tidak seperti sum, median tidak additive. Alasan yang sama
-- dipakai gold_profile.py butir "followers_growth milik akun, bukan milik post".
--
-- ============================================================================
-- KENAPA `views_analyzed_count` PERLU, TERPISAH DARI YANG SUDAH ADA
-- ============================================================================
--
-- `posts_analyzed_count` (IG) / `videos_analyzed_count` (TT) menghitung post
-- yang lolos aturan sampel. Itu BUKAN penyebut Avg Views.
--
-- Views tidak selalu ada. Instagram hanya melaporkan `videoPlayCount` untuk
-- post video, sehingga foto dan carousel ber-`views = NULL` -- bukan 0.
-- Memakai `posts_analyzed_count` sebagai penyebut sama saja memasukkan NULL
-- sebagai nol, dan rata-ratanya akan tertarik ke bawah sebanyak proporsi post
-- non-video akun tersebut.
--
-- Kolom terpisah ini menyimpan berapa post yang benar-benar masuk hitungan,
-- sehingga:
--   * penyebutnya bisa diaudit, bukan diasumsikan;
--   * "belum pernah dianalisis" (kolom NULL) bisa dibedakan dari "dianalisis,
--     tidak ada satu pun post ber-views" (kolom 0, metrik NULL);
--   * UI bisa menulis basisnya ("dari 7 post ber-views") tanpa query kedua.
--
-- Pola yang sama sudah dipakai `posts_in_sample` di kol_metric_daily.
--
-- ============================================================================
-- KENAPA TIPENYA SEGINI
-- ============================================================================
--
-- avg_views / median_views  numeric(18,2)
--     Views bisa ratusan juta; 18 digit aman jauh ke depan. Dua desimal karena
--     median dari jumlah post GENAP adalah rata-rata dua nilai tengah dan bisa
--     berakhir .5 -- membulatkannya ke bigint akan membuang informasi yang
--     memang dihitung. Dua desimal juga mengikuti `avg_engagement` di
--     format_performance yang sudah memakai round(...,2).
--
-- view_to_follower_ratio / like_to_view_ratio  numeric(12,4)
--     BUKAN numeric(5,2) seperti `engagement_rate`. Dua alasan:
--
--     1. V2F rutin melewati 100%. Satu video viral di akun kecil bisa
--        menghasilkan views berkali-kali lipat followers -- 1.200% bukan
--        anomali, itu memang yang terjadi. numeric(5,2) (maks 999,99) akan
--        overflow, dan menambalnya butuh clamp LEAST().
--     2. Clamp LEAST() adalah sumber bug yang sudah tercatat dua kali di
--        project ini: `LEAST(NULL, 999.99)` = 999,99, sehingga akun tanpa
--        sampel tercatat bernilai maksimum. numeric(12,4) membuat clamp tidak
--        diperlukan sama sekali, jadi kelas bug itu tidak bisa muncul lagi.
--
--     Empat desimal karena L2V akun besar sering di bawah 1% (mis. 0,8412%);
--     dua desimal akan memampatkan seluruh papan atas ke angka yang sama.
--
-- ============================================================================
-- TABEL & KOLOM YANG DITAMBAH -- 5 kolom x 3 tabel = 15
-- ============================================================================
--
--   feature.ig_engagement_analysis   + 5
--   feature.tt_engagement_analysis   + 5
--   l2_gold.kol_profile_card         + 5
--
-- Nama kolom identik di ketiga tabel supaya nilainya bisa ditelusuri
-- Feature -> L2 tanpa tabel pemetaan nama.
--
-- ============================================================================
-- YANG SENGAJA TIDAK DISENTUH
-- ============================================================================
--
--   * `public.kol_directory.followers_count` -- source of truth followers,
--     tidak dibaca maupun ditulis migrasi ini.
--   * `engagement_rate`, `followers_growth`, `tier` dan seluruh kolom lama:
--     tidak diubah tipe, tidak diubah isi, tidak di-rename.
--   * `l2_gold.kol_metric_daily`, `kol_metric_monthly`, `post_metric`: tidak
--     disentuh sama sekali.
--   * Tidak ada procedure/function yang dibuat atau diubah. Pengisian adalah
--     tugas asset Dagster, sama seperti kolom feature lain.
--
-- Jalankan:
--   python apply_migration.py migrations/036_view_metrics_avg_median_v2f_l2v.sql --dry-run --yes
--   python apply_migration.py migrations/036_view_metrics_avg_median_v2f_l2v.sql --yes

BEGIN;

-- ---------------------------------------------------------------------------
-- Langkah 0 -- penjaga.
--
-- Ketiga tabel tujuan harus sudah ada, dan tidak satu pun dari 5 nama kolom
-- baru boleh sudah terpakai di tabel-tabel itu. Kalau sudah terpakai, berarti
-- ada migrasi/percobaan lain yang memberi arti berbeda pada nama yang sama --
-- berhenti dan periksa, jangan menimpa.
-- ---------------------------------------------------------------------------
DO $penjaga$
DECLARE
    n_tabel  int;
    n_bentur int;
    daftar   text;
BEGIN
    SELECT count(*) INTO n_tabel
    FROM information_schema.tables
    WHERE (table_schema, table_name) IN (
        ('feature',  'ig_engagement_analysis'),
        ('feature',  'tt_engagement_analysis'),
        ('l2_gold',  'kol_profile_card')
    );
    IF n_tabel <> 3 THEN
        RAISE EXCEPTION 'Diharapkan 3 tabel tujuan, ditemukan %. '
                        'Migrasi 016/023 belum dijalankan?', n_tabel;
    END IF;

    SELECT count(*), string_agg(table_schema || '.' || table_name || '.' || column_name, ', ')
      INTO n_bentur, daftar
    FROM information_schema.columns
    WHERE (table_schema, table_name) IN (
        ('feature',  'ig_engagement_analysis'),
        ('feature',  'tt_engagement_analysis'),
        ('l2_gold',  'kol_profile_card')
    )
      AND column_name IN ('views_analyzed_count', 'avg_views', 'median_views',
                          'view_to_follower_ratio', 'like_to_view_ratio');
    IF n_bentur <> 0 THEN
        RAISE EXCEPTION 'Nama kolom sudah terpakai: %. Periksa dulu artinya '
                        'sebelum migrasi ini menimpanya.', daftar;
    END IF;

    RAISE NOTICE 'Penjaga lolos: 3 tabel tujuan ada, 0 benturan nama kolom.';
END $penjaga$;

-- ---------------------------------------------------------------------------
-- Langkah 1 -- feature.ig_engagement_analysis.
-- ---------------------------------------------------------------------------
ALTER TABLE feature.ig_engagement_analysis
    ADD COLUMN views_analyzed_count   integer,
    ADD COLUMN avg_views              numeric(18,2),
    ADD COLUMN median_views           numeric(18,2),
    ADD COLUMN view_to_follower_ratio numeric(12,4),
    ADD COLUMN like_to_view_ratio     numeric(12,4);

-- ---------------------------------------------------------------------------
-- Langkah 2 -- feature.tt_engagement_analysis.
-- ---------------------------------------------------------------------------
ALTER TABLE feature.tt_engagement_analysis
    ADD COLUMN views_analyzed_count   integer,
    ADD COLUMN avg_views              numeric(18,2),
    ADD COLUMN median_views           numeric(18,2),
    ADD COLUMN view_to_follower_ratio numeric(12,4),
    ADD COLUMN like_to_view_ratio     numeric(12,4);

-- ---------------------------------------------------------------------------
-- Langkah 3 -- l2_gold.kol_profile_card.
--
-- Kolom yang sama, dibawa apa adanya dari feature tanpa dihitung ulang --
-- pola yang sama dipakai `followers_growth` (dihitung di L1, disalin ke L2).
-- ---------------------------------------------------------------------------
ALTER TABLE l2_gold.kol_profile_card
    ADD COLUMN views_analyzed_count   integer,
    ADD COLUMN avg_views              numeric(18,2),
    ADD COLUMN median_views           numeric(18,2),
    ADD COLUMN view_to_follower_ratio numeric(12,4),
    ADD COLUMN like_to_view_ratio     numeric(12,4);

-- ---------------------------------------------------------------------------
-- Langkah 4 -- komentar kolom.
--
-- Rumusnya ditulis di database, bukan hanya di kode, supaya siapa pun yang
-- membaca tabel lewat psql/DBeaver tahu penyebutnya apa tanpa membuka repo.
-- ---------------------------------------------------------------------------
DO $komentar$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['feature.ig_engagement_analysis',
                             'feature.tt_engagement_analysis',
                             'l2_gold.kol_profile_card']
    LOOP
        EXECUTE format($f$
            COMMENT ON COLUMN %s.views_analyzed_count IS
                'Jumlah post yang LOLOS aturan sampel DAN ber-views > 0. '
                'Ini penyebut avg_views/median_views -- BUKAN posts_analyzed_count, '
                'yang menghitung post lolos sampel termasuk yang views-nya tidak '
                'diketahui (Instagram hanya melaporkan views untuk post video). '
                'Syaratnya > 0 dan bukan sekadar NOT NULL: di Instagram, views = 0 '
                'hanya muncul pada tipe media yang TIDAK PERNAH punya views positif '
                '(carousel & feed), jadi nol di situ berarti "tidak dilaporkan", '
                'bukan "tidak ada yang menonton". '
                '0 berarti "dianalisis, tidak ada post ber-views"; NULL berarti '
                '"belum pernah dianalisis".';
            COMMENT ON COLUMN %s.avg_views IS
                'AVG(views) atas post lolos sampel yang views-nya > 0. '
                'Post tanpa views tidak ikut sebagai 0 -- tidak ikut sama sekali. '
                'NULL bila views_analyzed_count = 0.';
            COMMENT ON COLUMN %s.median_views IS
                'percentile_cont(0.5) atas himpunan post yang SAMA PERSIS dengan '
                'avg_views. Jumlah post genap menghasilkan rata-rata dua nilai '
                'tengah, karena itu kolomnya berdesimal. NULL bila '
                'views_analyzed_count = 0.';
            COMMENT ON COLUMN %s.view_to_follower_ratio IS
                'V2F, PERSEN: SUM(views) / SUM(followers_pada_tanggal_post) * 100. '
                'Penyebut ADITIF memakai followers pada tanggal tayang tiap post, '
                'bukan followers terbaru -- pola yang sama dipakai engagement_rate. '
                'Hanya post ber-views > 0 yang followers-nya diketahui dan > 0 yang '
                'ikut, di kedua sisi pecahan. NULL bila tidak ada post seperti itu. '
                'Bisa melebihi 100%% dan itu sah.';
            COMMENT ON COLUMN %s.like_to_view_ratio IS
                'L2V, PERSEN: SUM(likes) / SUM(views) * 100 atas post lolos sampel '
                'yang likes-nya NOT NULL dan views-nya > 0. Setara avg_likes/avg_views '
                'karena keduanya dibagi jumlah post yang sama -- himpunan post-nya '
                'sama persis dengan avg_views, ditambah syarat likes diketahui. '
                'NULL bila tidak ada post yang memenuhi.';
        $f$, t, t, t, t, t);
    END LOOP;
END $komentar$;

-- ---------------------------------------------------------------------------
-- Langkah 5 -- verifikasi sebelum transaksi ditutup.
-- Gagal di sini membatalkan seluruh migrasi.
-- ---------------------------------------------------------------------------
DO $verif$
DECLARE
    n_kolom     int;
    n_nullable  int;
    n_default   int;
    n_komentar  int;
    tipe_avg    text;
    tipe_v2f    text;
    n_ig_lama   bigint;
    n_tt_lama   bigint;
    n_card_lama bigint;
BEGIN
    -- 15 kolom baru terbentuk (5 x 3 tabel).
    SELECT count(*) INTO n_kolom
    FROM information_schema.columns
    WHERE (table_schema, table_name) IN (
        ('feature',  'ig_engagement_analysis'),
        ('feature',  'tt_engagement_analysis'),
        ('l2_gold',  'kol_profile_card')
    )
      AND column_name IN ('views_analyzed_count', 'avg_views', 'median_views',
                          'view_to_follower_ratio', 'like_to_view_ratio');
    IF n_kolom <> 15 THEN
        RAISE EXCEPTION 'Kolom baru berjumlah %, seharusnya 15', n_kolom;
    END IF;

    -- Semuanya HARUS nullable: NULL adalah jawaban yang sah ("tidak cukup
    -- data"), dan NOT NULL akan memaksa 0 palsu.
    SELECT count(*) INTO n_nullable
    FROM information_schema.columns
    WHERE (table_schema, table_name) IN (
        ('feature',  'ig_engagement_analysis'),
        ('feature',  'tt_engagement_analysis'),
        ('l2_gold',  'kol_profile_card')
    )
      AND column_name IN ('views_analyzed_count', 'avg_views', 'median_views',
                          'view_to_follower_ratio', 'like_to_view_ratio')
      AND is_nullable = 'YES';
    IF n_nullable <> 15 THEN
        RAISE EXCEPTION 'Hanya % dari 15 kolom baru yang nullable. '
                        'Semuanya harus nullable supaya NULL bisa berarti '
                        '"data tidak cukup", bukan 0 palsu.', n_nullable;
    END IF;

    -- Tidak boleh ada DEFAULT. DEFAULT 0 akan membuat baris lama tampak
    -- seolah sudah diukur dan hasilnya nol.
    SELECT count(*) INTO n_default
    FROM information_schema.columns
    WHERE (table_schema, table_name) IN (
        ('feature',  'ig_engagement_analysis'),
        ('feature',  'tt_engagement_analysis'),
        ('l2_gold',  'kol_profile_card')
    )
      AND column_name IN ('views_analyzed_count', 'avg_views', 'median_views',
                          'view_to_follower_ratio', 'like_to_view_ratio')
      AND column_default IS NOT NULL;
    IF n_default <> 0 THEN
        RAISE EXCEPTION '% kolom baru punya DEFAULT; seharusnya tidak ada '
                        'satu pun.', n_default;
    END IF;

    -- Tipe presisi harus persis seperti yang dirancang.
    SELECT format_type(atttypid, atttypmod) INTO tipe_avg
    FROM pg_attribute
    WHERE attrelid = 'feature.ig_engagement_analysis'::regclass
      AND attname = 'avg_views';
    IF tipe_avg <> 'numeric(18,2)' THEN
        RAISE EXCEPTION 'avg_views bertipe %, seharusnya numeric(18,2)', tipe_avg;
    END IF;

    SELECT format_type(atttypid, atttypmod) INTO tipe_v2f
    FROM pg_attribute
    WHERE attrelid = 'l2_gold.kol_profile_card'::regclass
      AND attname = 'view_to_follower_ratio';
    IF tipe_v2f <> 'numeric(12,4)' THEN
        RAISE EXCEPTION 'view_to_follower_ratio bertipe %, seharusnya '
                        'numeric(12,4) -- numeric(5,2) akan overflow pada V2F '
                        'di atas 999,99%% yang memang terjadi.', tipe_v2f;
    END IF;

    -- Semua kolom baru harus punya komentar rumus.
    SELECT count(*) INTO n_komentar
    FROM information_schema.columns c
    JOIN pg_class t   ON t.relname = c.table_name
    JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = c.table_schema
    WHERE (c.table_schema, c.table_name) IN (
        ('feature',  'ig_engagement_analysis'),
        ('feature',  'tt_engagement_analysis'),
        ('l2_gold',  'kol_profile_card')
    )
      AND c.column_name IN ('views_analyzed_count', 'avg_views', 'median_views',
                            'view_to_follower_ratio', 'like_to_view_ratio')
      AND col_description(t.oid, c.ordinal_position::int) IS NOT NULL;
    IF n_komentar <> 15 THEN
        RAISE EXCEPTION 'Hanya % dari 15 kolom baru yang berkomentar', n_komentar;
    END IF;

    -- Data lama utuh: ketiga tabel masih bisa dibaca dan tidak dikosongkan.
    SELECT count(*) INTO n_ig_lama   FROM feature.ig_engagement_analysis;
    SELECT count(*) INTO n_tt_lama   FROM feature.tt_engagement_analysis;
    SELECT count(*) INTO n_card_lama FROM l2_gold.kol_profile_card;

    RAISE NOTICE 'OK: 15 kolom aditif, semua nullable, tanpa DEFAULT, '
                 'semua berkomentar.';
    RAISE NOTICE 'Baris existing tidak disentuh: ig_engagement_analysis=%, '
                 'tt_engagement_analysis=%, kol_profile_card=%',
                 n_ig_lama, n_tt_lama, n_card_lama;
END $verif$;

COMMIT;
