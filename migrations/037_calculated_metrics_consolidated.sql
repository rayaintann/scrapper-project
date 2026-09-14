-- 037_calculated_metrics_consolidated.sql
--
-- SATU migration untuk SELURUH metric yang sumber dan definisinya sudah siap.
-- Sengaja tidak dipecah per metric: keenamnya menumpang tabel yang sama,
-- dan enam migration terpisah berarti enam kali ALTER pada tabel yang sama
-- tanpa satu pun manfaat tambahan.
--
--     Daily Growth + Proyeksi 30 hari  turunan followers_growth yang sudah ada
--     Paid Ratio                       unified_post.is_sponsored
--     Share Rate                       unified_post.shares / engagement
--     Post Frequency                   unified_post.posted_at
--     Female % / Male %                gender_breakdown (unknown DIKELUARKAN)
--
-- Migrasi ini HANYA menambah kolom. Tidak ada tabel baru, tidak ada schema
-- baru, tidak ada perubahan tipe, tidak ada DROP, dan tidak satu baris pun
-- diubah atau dihapus. Seluruh kolom NULLABLE tanpa DEFAULT, jadi baris yang
-- sudah ada tetap sah dan bernilai NULL sampai asset pengisinya jalan.
-- Polanya mengikuti migration 036 persis.
--
-- ============================================================================
-- KENAPA TIDAK ADA TABEL BARU
-- ============================================================================
--
-- Keenam metrik bergrain PER AKUN, dan tabel dengan grain itu sudah ada di
-- tiap layer:
--
--   feature.ig/tt_engagement_analysis  grain (social_account_id)
--       -- sudah menampung engagement_rate, avg_views, median_views, V2F, L2V.
--          Paid Ratio, Share Rate, dan Post Frequency adalah metrik per akun
--          yang lahir dari tabel post yang sama. Rumahnya di sini.
--
--   feature.ig/tt_audience_analysis    grain (social_account_id)
--       -- sudah menampung gender_breakdown (male/female/unknown, persen).
--          Female %/Male % adalah turunan LANGSUNG kolom itu; menaruhnya di
--          tabel lain akan memisahkan angka dari bahannya.
--
--   l2_gold.kol_profile_card           grain (social_account_id, platform)
--       -- kartu ringkas yang dibaca KOL Directory dan KOL Detail. Ia sudah
--          membawa followers_growth; kolom Growth turunan menyusul ke sini
--          supaya UI tidak perlu menghitung apa pun sendiri.
--
-- ============================================================================
-- KENAPA GROWTH TURUNAN PERLU KOLOM (DAN GROWTH % TIDAK)
-- ============================================================================
--
-- `followers_growth` sudah punya kolom sejak migration 015. Yang belum punya
-- rumah adalah `daily_growth` dan `projected_30d`: keduanya sempat dihitung
-- saat-baca di db.py, dan itu bekerja untuk konsumen Python -- tapi UI
-- (Next.js) query Postgres LANGSUNG dan tidak bisa memanggil db.py. Tanpa
-- kolom, satu-satunya cara UI mendapat angkanya adalah menyalin rumusnya ke
-- repo lain: dua definisi yang cepat atau lambat berbeda. Kolom ini yang
-- mencegah duplikasi itu.
--
-- `previous_followers`, `previous_snapshot_date`, dan `days_between` ikut
-- disimpan BUKAN sebagai hiasan: tanpa ketiganya, `daily_growth` adalah angka
-- yang tidak bisa diaudit siapa pun -- tidak ada cara tahu ia dibagi berapa
-- hari, atau dibandingkan terhadap snapshot yang mana.
--
-- ============================================================================
-- KENAPA TIAP METRIK MEMBAWA PENYEBUTNYA
-- ============================================================================
--
-- Paid Ratio 0% bisa berarti "tidak ada satu pun post berbayar" atau "tidak
-- ada satu pun post yang sinyal berbayarnya diketahui". Keduanya jawaban yang
-- sama sekali berbeda, dan angka persennya sendiri tidak bisa membedakannya.
-- Karena itu `paid_signal_count` ikut disimpan; hal yang sama berlaku untuk
-- `share_engagement_base`, `observation_days`, dan `gender_known_pct`.
--
-- ============================================================================
-- YANG SENGAJA TIDAK ADA DI SINI
-- ============================================================================
--
--   Growth Classification   ambang exploding/rising/stable/declining masih
--                           placeholder prototype -- belum keputusan bisnis.
--   Post Freq Reliability   ambang Low/Medium/High belum ada.
--   Brand Fit               feature.brand_fit_analysis 0 baris.
--   EMV / CPE / CPV         l1_silver.unified_rate_card 0 baris, konstanta CPM
--                           tidak ada di database, dan rate card belum approved.
--   Monitoring Priority     6 sinyal yang dibutuhkan, 0 yang bisa dipakai.
--
-- Kolom untuk kelimanya TIDAK dibuat. Kolom kosong yang menunggu keputusan
-- bisnis hanya mengundang seseorang mengisinya dengan tebakan.
--
-- ROLLBACK
--   ALTER TABLE ... DROP COLUMN untuk tiap kolom di bawah. Karena seluruhnya
--   aditif dan nullable, DROP mengembalikan keadaan semula tanpa kehilangan
--   data lain.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. feature.*_engagement_analysis -- Paid Ratio, Share Rate, Post Frequency
-- ---------------------------------------------------------------------------
ALTER TABLE feature.ig_engagement_analysis
    ADD COLUMN IF NOT EXISTS paid_ratio             numeric,
    ADD COLUMN IF NOT EXISTS paid_posts_count       integer,
    ADD COLUMN IF NOT EXISTS paid_signal_count      integer,
    ADD COLUMN IF NOT EXISTS share_rate             numeric,
    ADD COLUMN IF NOT EXISTS share_engagement_base  bigint,
    ADD COLUMN IF NOT EXISTS shares_total           bigint,
    ADD COLUMN IF NOT EXISTS post_frequency_monthly numeric,
    ADD COLUMN IF NOT EXISTS post_frequency_count   integer,
    ADD COLUMN IF NOT EXISTS observation_days       integer;

ALTER TABLE feature.tt_engagement_analysis
    ADD COLUMN IF NOT EXISTS paid_ratio             numeric,
    ADD COLUMN IF NOT EXISTS paid_posts_count       integer,
    ADD COLUMN IF NOT EXISTS paid_signal_count      integer,
    ADD COLUMN IF NOT EXISTS share_rate             numeric,
    ADD COLUMN IF NOT EXISTS share_engagement_base  bigint,
    ADD COLUMN IF NOT EXISTS shares_total           bigint,
    ADD COLUMN IF NOT EXISTS post_frequency_monthly numeric,
    ADD COLUMN IF NOT EXISTS post_frequency_count   integer,
    ADD COLUMN IF NOT EXISTS observation_days       integer;

COMMENT ON COLUMN feature.ig_engagement_analysis.paid_ratio IS
    'Persen post berbayar: paid_posts_count / paid_signal_count * 100. '
    'Penyebutnya post lolos sampel yang is_sponsored-nya TIDAK NULL -- post '
    'yang sinyalnya tidak diketahui dikeluarkan, bukan dianggap organik. '
    'NULL bila tidak ada satu pun post dengan sinyal diketahui.';
COMMENT ON COLUMN feature.ig_engagement_analysis.paid_signal_count IS
    'Penyebut paid_ratio. Dibawa terpisah supaya 0% "tidak ada yang berbayar" '
    'bisa dibedakan dari 0% "tidak ada yang diketahui".';
COMMENT ON COLUMN feature.ig_engagement_analysis.share_rate IS
    'Persen share terhadap engagement: shares_total / share_engagement_base '
    '* 100. Engagement memakai definisi bisnis yang sama dengan ER '
    '(Like + Comment + Share), bukan views. NULL bila shares tidak pernah '
    'dilaporkan platform -- Instagram publik memang tidak melaporkannya.';
COMMENT ON COLUMN feature.ig_engagement_analysis.post_frequency_monthly IS
    'Post per 30 hari: post_frequency_count / observation_days * 30. '
    'observation_days = rentang post pertama sampai terakhir. NULL bila '
    'rentangnya nol hari (satu post, atau semua post di hari yang sama) -- '
    'satu titik tidak menentukan frekuensi.';
COMMENT ON COLUMN feature.ig_engagement_analysis.observation_days IS
    'Penyebut post_frequency_monthly, dalam hari. Bukan periode tetap: '
    'dihitung dari data post yang benar-benar ada.';

COMMENT ON COLUMN feature.tt_engagement_analysis.paid_ratio IS
    'Lihat feature.ig_engagement_analysis.paid_ratio -- definisi identik.';
COMMENT ON COLUMN feature.tt_engagement_analysis.share_rate IS
    'Lihat feature.ig_engagement_analysis.share_rate -- definisi identik. '
    'Berbeda dengan Instagram, TikTok memang melaporkan shareCount.';
COMMENT ON COLUMN feature.tt_engagement_analysis.post_frequency_monthly IS
    'Lihat feature.ig_engagement_analysis.post_frequency_monthly.';

-- ---------------------------------------------------------------------------
-- 2. feature.*_audience_analysis -- Female % / Male %
-- ---------------------------------------------------------------------------
ALTER TABLE feature.ig_audience_analysis
    ADD COLUMN IF NOT EXISTS female_pct       numeric,
    ADD COLUMN IF NOT EXISTS male_pct         numeric,
    ADD COLUMN IF NOT EXISTS gender_known_pct numeric;

ALTER TABLE feature.tt_audience_analysis
    ADD COLUMN IF NOT EXISTS female_pct       numeric,
    ADD COLUMN IF NOT EXISTS male_pct         numeric,
    ADD COLUMN IF NOT EXISTS gender_known_pct numeric;

COMMENT ON COLUMN feature.ig_audience_analysis.female_pct IS
    'female / (female + male) * 100. UNKNOWN DIKELUARKAN DARI PENYEBUT, '
    'sesuai kesepakatan: 40 male + 60 female -> 60%, berapa pun unknown-nya. '
    'NULL bila female + male = 0.';
COMMENT ON COLUMN feature.ig_audience_analysis.male_pct IS
    'male / (female + male) * 100. Penyebut sama dengan female_pct, jadi '
    'keduanya selalu berjumlah 100 kalau tidak NULL.';
COMMENT ON COLUMN feature.ig_audience_analysis.gender_known_pct IS
    'Porsi audiens yang gendernya diketahui: (female + male) dibagi seluruh '
    'audiens. BUKAN bagian dari rumus Female %/Male % -- ini yang memberi '
    'tahu seberapa jauh angka itu boleh dipercaya. Pada data sekarang '
    'unknown mendominasi (1.828 dari 2.568), jadi kolom ini penting.';
COMMENT ON COLUMN feature.tt_audience_analysis.female_pct IS
    'Lihat feature.ig_audience_analysis.female_pct -- definisi identik.';
COMMENT ON COLUMN feature.tt_audience_analysis.male_pct IS
    'Lihat feature.ig_audience_analysis.male_pct -- definisi identik.';
COMMENT ON COLUMN feature.tt_audience_analysis.gender_known_pct IS
    'Lihat feature.ig_audience_analysis.gender_known_pct.';

-- ---------------------------------------------------------------------------
-- 3. l2_gold.kol_profile_card -- kartu yang dibaca UI
-- ---------------------------------------------------------------------------
ALTER TABLE l2_gold.kol_profile_card
    ADD COLUMN IF NOT EXISTS previous_snapshot_date date,
    ADD COLUMN IF NOT EXISTS previous_followers     bigint,
    ADD COLUMN IF NOT EXISTS days_between           integer,
    ADD COLUMN IF NOT EXISTS daily_growth           numeric,
    ADD COLUMN IF NOT EXISTS projected_30d          bigint,
    ADD COLUMN IF NOT EXISTS paid_ratio             numeric,
    ADD COLUMN IF NOT EXISTS paid_signal_count      integer,
    ADD COLUMN IF NOT EXISTS share_rate             numeric,
    ADD COLUMN IF NOT EXISTS post_frequency_monthly numeric,
    ADD COLUMN IF NOT EXISTS observation_days       integer,
    ADD COLUMN IF NOT EXISTS female_pct             numeric,
    ADD COLUMN IF NOT EXISTS male_pct               numeric,
    ADD COLUMN IF NOT EXISTS gender_known_pct       numeric;

COMMENT ON COLUMN l2_gold.kol_profile_card.daily_growth IS
    'Follower per hari antar dua snapshot: (followers - previous_followers) '
    '/ days_between. Bukan persen. NULL bila belum ada snapshot pembanding, '
    'previous_followers = 0, atau days_between <= 0.';
COMMENT ON COLUMN l2_gold.kol_profile_card.projected_30d IS
    'previous_followers + daily_growth * 30. BASELINE-nya previous_followers, '
    'bukan followers sekarang: "30 hari setelah snapshot SEBELUMNYA". '
    'Acuan yang disepakati: 100 -> 125 dalam 25 hari menghasilkan 130, '
    'bukan 155.';
COMMENT ON COLUMN l2_gold.kol_profile_card.previous_followers IS
    'Followers pada snapshot valid TERAKHIR sebelum snapshot kartu ini. '
    'Snapshot yang di-NULL-kan sanity guard 035 dilewati, bukan dipakai.';
COMMENT ON COLUMN l2_gold.kol_profile_card.days_between IS
    'previous_snapshot_date sampai profile_snapshot_date, dalam hari. '
    'Penyebut daily_growth; tanpa kolom ini angka itu tidak bisa diaudit.';
COMMENT ON COLUMN l2_gold.kol_profile_card.paid_ratio IS
    'Dibawa apa adanya dari feature.*_engagement_analysis.paid_ratio. '
    'TIDAK dihitung ulang di L2.';
COMMENT ON COLUMN l2_gold.kol_profile_card.share_rate IS
    'Dibawa apa adanya dari feature.*_engagement_analysis.share_rate.';
COMMENT ON COLUMN l2_gold.kol_profile_card.post_frequency_monthly IS
    'Dibawa apa adanya dari feature.*_engagement_analysis.';
COMMENT ON COLUMN l2_gold.kol_profile_card.female_pct IS
    'Dibawa apa adanya dari feature.*_audience_analysis.female_pct. '
    'Unknown sudah dikeluarkan dari penyebut di layer feature.';

-- ---------------------------------------------------------------------------
-- Verifikasi: seluruh kolom ada, seluruhnya nullable, dan tidak ada satu pun
-- baris yang hilang dari empat tabel yang disentuh.
-- ---------------------------------------------------------------------------
DO $verifikasi$
DECLARE
    n_kolom int;
BEGIN
    SELECT count(*) INTO n_kolom
      FROM information_schema.columns
     WHERE (table_schema = 'feature'
            AND table_name IN ('ig_engagement_analysis', 'tt_engagement_analysis')
            AND column_name IN ('paid_ratio','paid_posts_count','paid_signal_count',
                                'share_rate','share_engagement_base','shares_total',
                                'post_frequency_monthly','post_frequency_count',
                                'observation_days'))
        OR (table_schema = 'feature'
            AND table_name IN ('ig_audience_analysis', 'tt_audience_analysis')
            AND column_name IN ('female_pct','male_pct','gender_known_pct'))
        OR (table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
            AND column_name IN ('previous_snapshot_date','previous_followers',
                                'days_between','daily_growth','projected_30d',
                                'paid_ratio','paid_signal_count','share_rate',
                                'post_frequency_monthly','observation_days',
                                'female_pct','male_pct','gender_known_pct'));

    -- 9*2 engagement + 3*2 audience + 13 kartu = 37
    IF n_kolom <> 37 THEN
        RAISE EXCEPTION 'Kolom terpasang % dari 37 yang diharapkan', n_kolom;
    END IF;

    SELECT count(*) INTO n_kolom
      FROM information_schema.columns
     WHERE table_schema IN ('feature', 'l2_gold')
       AND table_name IN ('ig_engagement_analysis','tt_engagement_analysis',
                          'ig_audience_analysis','tt_audience_analysis',
                          'kol_profile_card')
       AND column_name IN ('paid_ratio','share_rate','post_frequency_monthly',
                           'female_pct','male_pct','daily_growth','projected_30d')
       AND is_nullable = 'NO';

    IF n_kolom <> 0 THEN
        RAISE EXCEPTION '% kolom baru bertanda NOT NULL; seharusnya nullable', n_kolom;
    END IF;

    RAISE NOTICE 'OK: 37 kolom aditif terpasang, seluruhnya nullable.';
END $verifikasi$;

COMMIT;
