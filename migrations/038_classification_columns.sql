-- 038_classification_columns.sql
--
-- Tujuh kolom untuk lima metric PELABELAN yang ambangnya baru ditetapkan
-- sebagai *working threshold*:
--
--     growth_class                Growth % -> High/Medium/Low/Negative Growth
--     gender_reliability          gender_known_pct -> High/Medium/Low
--     post_frequency_daily        post per HARI (monthly sudah ada di 037)
--     post_frequency_count        jumlah post valid; penyebut reliability
--     post_frequency_reliability  observation_days + count -> High/Medium/Low
--     monitoring_er_pct           ER yang dipakai priority; penyebutnya
--     monitoring_priority         ER -> High/Medium/Low
--
-- Aditif dan nullable seperti 036 dan 037. Tidak ada tabel baru, tidak ada
-- schema baru, tidak ada DROP, tidak ada perubahan tipe, tidak satu baris pun
-- diubah atau dihapus.
--
-- ============================================================================
-- KENAPA MIGRATION LAGI, PADAHAL 037 BARU SAJA JALAN
-- ============================================================================
--
-- 037 SENGAJA tidak membuat kolom untuk kelima metric ini, dan alasannya
-- ditulis di headernya: ambangnya belum diputuskan, dan "kolom kosong yang
-- menunggu keputusan bisnis hanya mengundang seseorang mengisinya dengan
-- tebakan". Keputusan itu sekarang ada -- sebagai ambang kerja, tapi ada dan
-- eksplisit -- jadi kolomnya punya alasan yang tidak dimilikinya kemarin.
--
-- Dicek dulu sebelum menambah: tidak satu pun dari ketujuh nama ini sudah ada
-- di `l2_gold.kol_profile_card` (42 kolom saat migration ini ditulis), dan
-- tidak ada kolom lain yang bisa dipakai kembali untuk maksud yang sama.
--
-- ============================================================================
-- KENAPA `monitoring_er_pct` IKUT DISIMPAN
-- ============================================================================
--
-- Alasan yang sama dengan `paid_signal_count` di 037: label tanpa penyebutnya
-- adalah angka yang tidak bisa diaudit. "Medium" tidak memberi tahu siapa pun
-- ER berapa yang menghasilkannya, dan saat ambangnya nanti diubah, tidak ada
-- cara memeriksa baris mana yang berpindah kategori tanpa menjalankan ulang
-- seluruh pipeline.
--
-- NAMANYA SENGAJA BUKAN `engagement_rate`. Kartu ini tidak boleh terlihat
-- seperti sumber kebenaran ER yang bersaing dengan
-- `feature.*_engagement_analysis.engagement_rate` -- ia hanya menyimpan nilai
-- yang dipakai untuk satu keputusan, dan namanya harus mengatakan itu.
--
-- ============================================================================
-- AMBANGNYA TIDAK ADA DI FILE INI
-- ============================================================================
--
-- Tidak ada satu pun angka ambang di migration ini, dan itu disengaja. Angka-
-- angkanya hidup di `metrics_thresholds.py`, dan CASE yang mengisi kolom ini
-- digenerate dari sana oleh `gold_profile.py`. Menuliskannya juga di sini akan
-- membuat dua sumber yang harus diubah bersamaan -- persis yang dihindari.
--
-- ROLLBACK
--   ALTER TABLE l2_gold.kol_profile_card DROP COLUMN <nama> untuk ketujuhnya.
-- ============================================================================

BEGIN;

ALTER TABLE l2_gold.kol_profile_card
    ADD COLUMN IF NOT EXISTS growth_class               varchar(32),
    ADD COLUMN IF NOT EXISTS gender_reliability         varchar(16),
    ADD COLUMN IF NOT EXISTS post_frequency_daily       numeric,
    ADD COLUMN IF NOT EXISTS post_frequency_count       integer,
    ADD COLUMN IF NOT EXISTS post_frequency_reliability varchar(16),
    ADD COLUMN IF NOT EXISTS monitoring_er_pct          numeric,
    ADD COLUMN IF NOT EXISTS monitoring_priority        varchar(16);

COMMENT ON COLUMN l2_gold.kol_profile_card.growth_class IS
    'Label atas followers_growth: High/Medium/Low/Negative Growth. AMBANG '
    'KERJA, bukan kesepakatan final -- angkanya di metrics_thresholds.py, '
    'dan kolom ini diisi CASE yang digenerate dari sana. NULL bila '
    'followers_growth NULL; NULL BUKAN "Negative".';
COMMENT ON COLUMN l2_gold.kol_profile_card.gender_reliability IS
    'High/Medium/Low atas gender_known_pct. Menilai KEANDALAN DATA gender, '
    'bukan creator-nya. female_pct/male_pct tetap dihitung apa adanya.';
COMMENT ON COLUMN l2_gold.kol_profile_card.post_frequency_daily IS
    'post_frequency_count / observation_days. Penyebutnya rentang post NYATA, '
    'bukan 30 hari tetap. post_frequency_monthly = angka ini x 30.';
COMMENT ON COLUMN l2_gold.kol_profile_card.post_frequency_count IS
    'Jumlah post valid (lolos aturan sampel yang sama dengan ER). Pembilang '
    'post_frequency_daily dan salah satu dari dua syarat reliability.';
COMMENT ON COLUMN l2_gold.kol_profile_card.post_frequency_reliability IS
    'High/Medium/Low dari observation_days DAN post_frequency_count '
    'bersamaan. Dua syarat, bukan satu: 10 post dalam 2 hari menghasilkan '
    '150 post/bulan yang aritmetikanya benar tapi ekstrapolasinya tebakan. '
    'NULL bila tidak ada post valid -- NULL BUKAN "Low".';
COMMENT ON COLUMN l2_gold.kol_profile_card.monitoring_er_pct IS
    'ER yang dipakai menentukan monitoring_priority, dibawa apa adanya dari '
    'feature.*_engagement_analysis.engagement_rate. BUKAN sumber kebenaran ER '
    'yang bersaing -- hanya penyebut yang membuat label di sebelahnya bisa '
    'diaudit.';
COMMENT ON COLUMN l2_gold.kol_profile_card.monitoring_priority IS
    'High/Medium/Low atas monitoring_er_pct. SEMENTARA memakai ER sebagai '
    'satu-satunya sinyal: rule produk yang sebenarnya (campaign aktif, '
    'monitoring aktif, akses terakhir) diuji di '
    'docs/KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md dan nol dari enam '
    'sinyalnya punya data. NULL bila ER tidak diketahui.';

DO $verifikasi$
DECLARE
    n int;
BEGIN
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('growth_class','gender_reliability',
                           'post_frequency_daily','post_frequency_count',
                           'post_frequency_reliability','monitoring_er_pct',
                           'monitoring_priority');
    IF n <> 7 THEN
        RAISE EXCEPTION 'Kolom terpasang % dari 7 yang diharapkan', n;
    END IF;

    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('growth_class','gender_reliability',
                           'post_frequency_daily','post_frequency_count',
                           'post_frequency_reliability','monitoring_er_pct',
                           'monitoring_priority')
       AND is_nullable = 'NO';
    IF n <> 0 THEN
        RAISE EXCEPTION '% kolom baru bertanda NOT NULL; seharusnya nullable', n;
    END IF;

    -- Kolom 036 dan 037 harus utuh: migration ini menambah, tidak mengganti.
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
       AND column_name IN ('avg_views','median_views','view_to_follower_ratio',
                           'like_to_view_ratio','followers_growth','daily_growth',
                           'projected_30d','paid_ratio','share_rate',
                           'post_frequency_monthly','female_pct','male_pct',
                           'gender_known_pct');
    IF n <> 13 THEN
        RAISE EXCEPTION 'Kolom 036/037 tinggal % dari 13 -- ada yang hilang', n;
    END IF;

    RAISE NOTICE 'OK: 7 kolom aditif terpasang, nullable, dan 036/037 utuh.';
END $verifikasi$;

COMMIT;
