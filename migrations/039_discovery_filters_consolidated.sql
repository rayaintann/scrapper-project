-- 039_discovery_filters_consolidated.sql
--
-- SATU migration untuk filter Discovery yang definisinya sudah disepakati:
--
--     Save Rate              saves / engagement x 100      (TikTok saja)
--     Viral Frequency        post >= 3x median views creator
--     Content Topic          klasifikasi caption + hashtag post
--     Content Format         normalisasi media_type
--     Audience Quality       label atas skor yang SUDAH ada
--     Audience Interest      minat teratas + penanda asalnya
--     Performance Stability  simpangan baku ER historis
--     Rising Creator         Growth >= 5%
--
-- Aditif dan nullable, pola yang sama dengan 036/037/038. Tidak ada tabel
-- baru, tidak ada schema baru, tidak ada DROP, tidak ada perubahan tipe,
-- dan tidak satu baris pun diubah atau dihapus.
--
-- ============================================================================
-- YANG SENGAJA TIDAK MENDAPAT KOLOM
-- ============================================================================
--
-- Audience Location TIDAK menambah satu kolom pun. Filternya dijawab
-- `EXISTS` terhadap `l2_gold.audience_geo_daily` yang sudah ada -- pola yang
-- sama dipakai filter Agency dan Connected. Yang diperbaiki di sana bukan
-- strukturnya melainkan ISINYA: `geo_level` selama ini menulis 'city' untuk
-- SEMUA tebakan, termasuk yang sebenarnya provinsi, sehingga "Bali" dan
-- "Lampung" berdiri sejajar dengan "Bandung". Perbaikannya ada di
-- `audience_inference.tingkat_geo()` dan asset audience, bukan di schema.
--
-- Share Rate juga tidak muncul di sini: kolomnya sudah dibuat migration 037
-- dan definisinya tidak berubah (shares / (likes+comments+shares) x 100).
--
-- ============================================================================
-- KENAPA TIAP METRIK MEMBAWA PENYEBUT ATAU ASALNYA
-- ============================================================================
--
-- Pola yang sama dengan 037/038, dan alasannya sama: angka tanpa penyebutnya
-- tidak bisa diaudit.
--
--   viral_threshold_views   ambang 3x median yang BENAR-BENAR dipakai akun itu
--   content_topic_source    'content' atau 'creator_category_fallback'
--   audience_interest_source 'audience' atau 'content_inferred'
--   er_periods              berapa periode yang menyusun simpangan bakunya
--   saves_total             pembilang save_rate
--
-- Dua kolom `*_source` itu yang menjaga janji "inferred tidak boleh
-- menyamar sebagai observed".
--
-- ============================================================================
-- SATUAN
-- ============================================================================
--
-- `er_stddev_pp` bersatuan POIN PERSEN, dan namanya menyebutkannya karena
-- pencampuran satuan di sini adalah kesalahan yang paling mudah terjadi:
-- `kol_metric_daily.er_followers_daily` disimpan sebagai FRAKSI (0,0000164
-- .. 0,1615) sementara `feature.*_engagement_analysis.engagement_rate`
-- disimpan sebagai PERSEN (0,00 .. 16,15). Simpangan baku atas fraksi lalu
-- dibandingkan dengan ambang "1%" akan menyatakan setiap akun stabil.
--
-- ROLLBACK
--   DROP COLUMN untuk tiap kolom di bawah.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. feature.*_engagement_analysis
-- ---------------------------------------------------------------------------
ALTER TABLE feature.ig_engagement_analysis
    ADD COLUMN IF NOT EXISTS save_rate             numeric,
    ADD COLUMN IF NOT EXISTS saves_total           bigint,
    ADD COLUMN IF NOT EXISTS viral_post_count      integer,
    ADD COLUMN IF NOT EXISTS viral_frequency       numeric,
    ADD COLUMN IF NOT EXISTS viral_threshold_views numeric,
    ADD COLUMN IF NOT EXISTS content_topic         varchar(32),
    ADD COLUMN IF NOT EXISTS content_topic_source  varchar(32),
    ADD COLUMN IF NOT EXISTS content_topic_posts   integer,
    ADD COLUMN IF NOT EXISTS format_dominant       varchar(16);

ALTER TABLE feature.tt_engagement_analysis
    ADD COLUMN IF NOT EXISTS save_rate             numeric,
    ADD COLUMN IF NOT EXISTS saves_total           bigint,
    ADD COLUMN IF NOT EXISTS viral_post_count      integer,
    ADD COLUMN IF NOT EXISTS viral_frequency       numeric,
    ADD COLUMN IF NOT EXISTS viral_threshold_views numeric,
    ADD COLUMN IF NOT EXISTS content_topic         varchar(32),
    ADD COLUMN IF NOT EXISTS content_topic_source  varchar(32),
    ADD COLUMN IF NOT EXISTS content_topic_posts   integer,
    ADD COLUMN IF NOT EXISTS format_dominant       varchar(16);

COMMENT ON COLUMN feature.ig_engagement_analysis.save_rate IS
    'saves_total / share_engagement_base * 100. Penyebutnya ENGAGEMENT '
    '(like+comment+share), sama dengan share_rate -- bukan views, dan saves '
    'sendiri TIDAK masuk penyebut. NULL bila platform tidak melaporkan saves; '
    'Instagram publik tidak, jadi seluruh baris IG NULL. NULL, bukan 0.';
COMMENT ON COLUMN feature.ig_engagement_analysis.viral_frequency IS
    'viral_post_count / post ber-views * 100. Sebuah post viral bila '
    'views >= 3x MEDIAN views creator itu sendiri -- pengali relatif, bukan '
    'ambang views absolut, supaya akun kecil tidak otomatis tidak pernah viral.';
COMMENT ON COLUMN feature.ig_engagement_analysis.viral_threshold_views IS
    'Ambang 3x median yang benar-benar dipakai akun ini. Tanpa kolom ini '
    'viral_frequency tidak bisa diperiksa ulang oleh siapa pun.';
COMMENT ON COLUMN feature.ig_engagement_analysis.content_topic IS
    'Topik dominan dari caption + hashtag post NYATA, memakai kosakata '
    '`audience_inference.INTEREST` yang sama dengan audience_interest_daily. '
    'BUKAN kategori creator, dan tidak pernah ditebak dari username.';
COMMENT ON COLUMN feature.ig_engagement_analysis.content_topic_source IS
    '''content'' bila dari post, ''creator_category_fallback'' bila dari '
    'kategori roster. Fallback WAJIB ditandai: kategori creator bukan hasil '
    'klasifikasi konten, dan menyamakan keduanya akan menyesatkan.';
COMMENT ON COLUMN feature.ig_engagement_analysis.format_dominant IS
    'Format terbanyak setelah normalisasi: Video / Carousel / Image. '
    'CAROUSEL dan carousel_container digabung; casing tidak lagi menghasilkan '
    'kategori kembar.';

COMMENT ON COLUMN feature.tt_engagement_analysis.save_rate IS
    'Lihat feature.ig_engagement_analysis.save_rate. Berbeda dengan Instagram, '
    'TikTok memang melaporkan saves (collect).';
COMMENT ON COLUMN feature.tt_engagement_analysis.viral_frequency IS
    'Lihat feature.ig_engagement_analysis.viral_frequency.';
COMMENT ON COLUMN feature.tt_engagement_analysis.content_topic IS
    'Lihat feature.ig_engagement_analysis.content_topic.';

-- ---------------------------------------------------------------------------
-- 2. feature.*_audience_analysis
-- ---------------------------------------------------------------------------
ALTER TABLE feature.ig_audience_analysis
    ADD COLUMN IF NOT EXISTS audience_quality_tier varchar(16),
    ADD COLUMN IF NOT EXISTS interest_top          varchar(32),
    ADD COLUMN IF NOT EXISTS interest_source       varchar(32);

ALTER TABLE feature.tt_audience_analysis
    ADD COLUMN IF NOT EXISTS audience_quality_tier varchar(16),
    ADD COLUMN IF NOT EXISTS interest_top          varchar(32),
    ADD COLUMN IF NOT EXISTS interest_source       varchar(32);

COMMENT ON COLUMN feature.ig_audience_analysis.audience_quality_tier IS
    'High/Medium/Low atas audience_quality_score yang SUDAH ada. Skornya '
    'tidak dihitung ulang; hanya dilabeli. Ambang di metrics_thresholds.py.';
COMMENT ON COLUMN feature.ig_audience_analysis.interest_top IS
    'Minat audiens teratas selain ''unknown''. Diambil dari top_interest yang '
    'sudah ada; bila seluruhnya unknown, diisi topik konten creator sebagai '
    'pengganti -- dan interest_source yang membedakan keduanya.';
COMMENT ON COLUMN feature.ig_audience_analysis.interest_source IS
    '''audience'' bila dari minat follower yang teramati, ''content_inferred'' '
    'bila diturunkan dari topik konten creator karena minat audiens seluruhnya '
    'unknown. NULL bila keduanya tidak tersedia -- tidak pernah ditebak.';

-- ---------------------------------------------------------------------------
-- 3. l2_gold.kol_profile_card
-- ---------------------------------------------------------------------------
ALTER TABLE l2_gold.kol_profile_card
    ADD COLUMN IF NOT EXISTS save_rate                numeric,
    ADD COLUMN IF NOT EXISTS viral_frequency          numeric,
    ADD COLUMN IF NOT EXISTS viral_post_count         integer,
    ADD COLUMN IF NOT EXISTS viral_threshold_views    numeric,
    ADD COLUMN IF NOT EXISTS content_topic            varchar(32),
    ADD COLUMN IF NOT EXISTS content_topic_source     varchar(32),
    ADD COLUMN IF NOT EXISTS format_dominant          varchar(16),
    ADD COLUMN IF NOT EXISTS audience_quality_score   numeric,
    ADD COLUMN IF NOT EXISTS authenticity_score       numeric,
    ADD COLUMN IF NOT EXISTS audience_quality_tier    varchar(16),
    ADD COLUMN IF NOT EXISTS audience_interest_top    varchar(32),
    ADD COLUMN IF NOT EXISTS audience_interest_source varchar(32),
    ADD COLUMN IF NOT EXISTS er_stddev_pp             numeric,
    ADD COLUMN IF NOT EXISTS er_periods               integer,
    ADD COLUMN IF NOT EXISTS performance_stability    varchar(24),
    ADD COLUMN IF NOT EXISTS rising_creator           boolean;

COMMENT ON COLUMN l2_gold.kol_profile_card.er_stddev_pp IS
    'Simpangan baku ER historis dalam POIN PERSEN. Sumbernya '
    'l2_gold.kol_metric_daily.er_followers_daily yang bersatuan FRAKSI, jadi '
    'dikali 100 lebih dulu. Nama kolom menyebut satuannya dengan sengaja.';
COMMENT ON COLUMN l2_gold.kol_profile_card.er_periods IS
    'Jumlah periode ER yang menyusun er_stddev_pp. Kurang dari 3 -> '
    'performance_stability NULL: dua titik selalu tampak stabil, dan '
    'melabelinya High akan menjual kekurangan data sebagai konsistensi.';
COMMENT ON COLUMN l2_gold.kol_profile_card.performance_stability IS
    'High/Medium/Low Stability atas er_stddev_pp. NULL bila er_periods < 3.';
COMMENT ON COLUMN l2_gold.kol_profile_card.rising_creator IS
    'followers_growth >= 5% (batas Medium Growth). Ambang lama 5,5% dari '
    'prototype tidak dipakai lagi, dan tidak ada syarat ER tambahan. '
    'NULL bila Growth belum terukur -- NULL BUKAN false.';
COMMENT ON COLUMN l2_gold.kol_profile_card.save_rate IS
    'Dibawa apa adanya dari feature.*_engagement_analysis.save_rate.';
COMMENT ON COLUMN l2_gold.kol_profile_card.audience_interest_source IS
    '''audience'' atau ''content_inferred'' -- penanda supaya minat yang '
    'diturunkan dari konten tidak terbaca sebagai minat audiens teramati.';

DO $verifikasi$
DECLARE
    n int;
BEGIN
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE (table_schema = 'feature'
            AND table_name IN ('ig_engagement_analysis','tt_engagement_analysis')
            AND column_name IN ('save_rate','saves_total','viral_post_count',
                                'viral_frequency','viral_threshold_views',
                                'content_topic','content_topic_source',
                                'content_topic_posts','format_dominant'))
        OR (table_schema = 'feature'
            AND table_name IN ('ig_audience_analysis','tt_audience_analysis')
            AND column_name IN ('audience_quality_tier','interest_top','interest_source'))
        OR (table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
            AND column_name IN ('save_rate','viral_frequency','viral_post_count',
                                'viral_threshold_views','content_topic',
                                'content_topic_source','format_dominant',
                                'audience_quality_score','authenticity_score',
                                'audience_quality_tier','audience_interest_top',
                                'audience_interest_source','er_stddev_pp',
                                'er_periods','performance_stability','rising_creator'));
    -- 9*2 + 3*2 + 16 = 40
    IF n <> 40 THEN
        RAISE EXCEPTION 'Kolom terpasang % dari 40 yang diharapkan', n;
    END IF;

    -- Kolom 036/037/038 harus utuh: migration ini menambah, tidak mengganti.
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('avg_views','median_views','view_to_follower_ratio',
                           'like_to_view_ratio','followers_growth','daily_growth',
                           'projected_30d','paid_ratio','share_rate',
                           'post_frequency_monthly','female_pct','male_pct',
                           'gender_known_pct','growth_class','gender_reliability',
                           'post_frequency_reliability','monitoring_priority',
                           'post_frequency_daily','post_frequency_count',
                           'monitoring_er_pct');
    IF n <> 20 THEN
        RAISE EXCEPTION 'Kolom 036/037/038 tinggal % dari 20 -- ada yang hilang', n;
    END IF;

    RAISE NOTICE 'OK: 40 kolom aditif terpasang; 036/037/038 utuh.';
END $verifikasi$;

COMMIT;
