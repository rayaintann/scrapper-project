"""Asset L2 Gold — kartu profil per KOL (SCRUM-514).

    kol_profile_card -> l2_gold.kol_profile_card

Grain `(social_account_id, platform)`: SATU kartu per akun, tanpa dimensi
tanggal. Sumbernya `l1_silver.unified_profile` — snapshot TERBARU per akun.

Dipisah dari `gold.py` dengan sengaja. `gold.py` berisi dua asset yang
digerakkan POST (`metric_date` diturunkan dari `posted_at`); yang ini
digerakkan PROFIL. Menaruhnya di file yang sama akan mengaburkan perbedaan
grain yang justru jadi alasan tabel ini ada.

============================================================================
KENAPA KARTU INI ADA — followers_growth MILIK AKUN, BUKAN MILIK POST
============================================================================

`l2_gold.kol_metric_daily` punya kolom `followers_growth` yang tidak pernah
diisi, dan memang TIDAK BISA diisi dengan benar di sana. Grainnya
`(akun, platform, metric_date)` dengan `metric_date` dari `posted_at` —
tanggal TAYANG POST. Growth tidak punya tanggal tayang; ia melekat pada
pasangan snapshot profil.

Dibuktikan pada data nyata sebelum tabel ini dibangun:

    followers_growth L1 terisi di tanggal : 2026-08-24 saja (22 baris)
    metric_date L2 tertinggi              : 2026-08-20
    aturan carry-forward (date <= metric_date):
    pasangan akun-hari yang memenuhi      : 0

Akunnya beririsan (22 dari 23), tanggalnya tidak. Jadi bahkan kalau logic
`kol_metric_daily` diubah untuk mengambil growth, hasilnya tetap 0 baris
terisi — bukan karena bug, tapi karena metriknya bukan milik grain itu.

`kol_profile_card` grainnya per AKUN, dan `profile_snapshot_date` mencatat
snapshot mana yang dipakai. Growth masuk apa adanya dari snapshot itu.

============================================================================
KEPUTUSAN DESAIN
============================================================================

1. SNAPSHOT TERBARU PER AKUN, LEWAT `DISTINCT ON`.
   `ORDER BY social_account_id, platform, date DESC` — pola yang sama dipakai
   `_CTE_BULANAN` di gold.py untuk `followers_eom`.

   Tie-break `updated_at DESC, id DESC` ditambahkan meski pada data sekarang
   TIDAK ADA pasangan (akun, platform, date) yang muncul dua kali (diperiksa:
   0 kasus). Tanpa tie-break, dua baris bertanggal sama akan membuat pilihan
   bergantung pada urutan fisik baris — hasilnya bisa berubah antar-run tanpa
   datanya berubah. Murah, dan membuat asset ini deterministik.

2. `followers_growth` DIBAWA APA ADANYA — TIDAK DIHITUNG ULANG.
   Rumusnya sudah dijalankan `l1_silver.sp_build_unified_profile()`. Menghitung
   ulang di sini berarti rumus yang sama hidup di dua tempat, dan cepat atau
   lambat keduanya berbeda. Ini alasan yang sama kenapa `kol_metric_monthly`
   membaca `kol_metric_daily` dan tidak pernah kembali ke L1.

   SATUANNYA PERSEN, bukan jumlah orang. Kolom tujuan diubah `bigint` ->
   `numeric` oleh migration 025; tanpa itu 20 dari 22 nilai jadi 0 karena
   semuanya ada di antara -1% dan +1%.

3. GROWTH DIAMBIL DARI SNAPSHOT YANG SAMA DENGAN `profile_snapshot_date`.
   Bukan dari snapshot mana pun yang kebetulan punya nilai. Kalau snapshot
   terbaru sebuah akun belum punya pendahulu, growth-nya NULL — dan NULL itu
   jawaban yang benar, bukan kekosongan yang perlu ditambal dengan nilai lama.

   Konsekuensinya pada data sekarang: 22 dari 1.972 kartu dapat growth. Sisanya
   snapshot terbarunya masih 2026-08-14/17/18, tanggal scrape pertama, jadi
   belum punya pembanding. Angka ini akan naik sendiri tiap scraping profil
   berikutnya — tanpa perubahan kode.

4. KOLOM RATE CARD TIDAK DITULIS SAMA SEKALI.
   `rate_card`, `rate_card_currency`, `rate_card_min_fee`, `rate_card_max_fee`,
   `rate_card_post_types` tidak disebut di daftar INSERT, jadi tetap NULL.
   Sumbernya (`l1_silver.unified_rate_card`, 9.210 baris / 7.230 akun) SIAP,
   tapi meringkasnya butuh keputusan yang belum diambil: bagaimana kalau satu
   akun punya beberapa mata uang, dan bagaimana `post_type` dipetakan. Menebak
   di sini akan menghasilkan angka harga yang salah — lebih buruk daripada NULL.
   Menyusul di tiket terpisah.

   Pola "kolom yang belum bisa diisi tidak disebut di INSERT" sama persis
   dengan keputusan #8 di gold.py.

5. UPSERT DENGAN PENJAGA `IS DISTINCT FROM`.
   Menyalin pola `kol_metric_daily`: baris yang isinya tidak berubah TIDAK
   ditulis ulang, sehingga `updated_at` menandai perubahan sungguhan dan rerun
   benar-benar idempoten.

   Kolom rate card TIDAK ikut di `DO UPDATE SET`. Kalau nanti diisi asset lain,
   asset ini tidak boleh menimpanya kembali jadi NULL.

6. TIDAK ADA DELETE.
   Akun yang hilang dari `unified_profile` kartunya dibiarkan berdiri. Tabel
   ini dipakai untuk daftar/pencarian KOL; menghapus kartu karena satu batch
   scraping kebetulan tidak menyertakan akunnya akan membuat daftar berkedip.

7. `is_verified` = BADGE PLATFORM, BUKAN Connected.
   Verified dan Connected adalah dua hal berbeda dan tidak boleh saling
   menggantikan:

       verified  = centang biru dari platform (Instagram/TikTok)
       connected = KOL benar-benar menautkan akunnya lewat OAuth, yaitu
                   social_account.platform_user_id DAN oauth_token terisi

   `l1_silver.unified_profile.is_verified` TIDAK memuat badge. Sejak
   migration 031 kolom itu diisi ekspresi Connected:

       (sa.platform_user_id IS NOT NULL AND sa.oauth_token IS NOT NULL)

   Akibatnya badge platform hilang tepat di L1. Terukur 2026-09-08: seluruh
   2.010 baris L1 bernilai false (karena 0 akun Connected), padahal sumbernya
   masih utuh -- 457 akun Instagram dan 115 akun TikTok ber-badge true, total
   572 akun. Kartu L2 mewarisi kesalahan itu: 1.979 kartu, 0 true.

   Asset ini karena itu TIDAK LAGI membaca `p.is_verified`, melainkan
   mengambil badge dari sumbernya langsung (lihat CTE `badge`). Setelah
   perubahan ini tidak ada satu pun pembaca `unified_profile.is_verified`
   yang tersisa, jadi kolom L1 itu menjadi tidak terpakai -- diperiksa:
   satu-satunya pembaca lain, audience.py, memakai `unified_follower`, tabel
   yang berbeda.

   YANG SENGAJA TIDAK DIKERJAKAN DI SINI:
   memperbaiki `l1_silver.unified_profile.is_verified` itu sendiri butuh
   ALTER TABLE pada l0_harmonization.instagram_profile (kolomnya belum ada)
   ditambah dua prosedur ditulis ulang. Itu perubahan schema, sementara
   perbaikan di layer ini sudah cukup untuk mengembalikan badge ke UI tanpa
   menyentuh schema sama sekali. Definisi Connected TIDAK diubah: endpoint
   menghitungnya sendiri dari social_account dan tidak pernah membaca kolom
   ini.

8. EMPAT METRIK VIEWS DIBAWA APA ADANYA DARI LAYER FEATURE.
   `views_analyzed_count`, `avg_views`, `median_views`,
   `view_to_follower_ratio` dan `like_to_view_ratio` (migration 036) disalin
   dari `feature.{ig,tt}_engagement_analysis` lewat CTE `metrik_views` —
   TIDAK dihitung ulang di sini. Alasannya sama persis dengan keputusan #2:
   satu rumus, satu tempat.

   Kedua tabel feature bergrain `(social_account_id)` saja; platformnya
   ditentukan oleh tabel mana yang dipakai, jadi UNION-nya menambahkan
   platform sebagai literal supaya join ke kartu tepat satu lawan satu.

   Konsekuensi yang disengaja: L2 tidak akan pernah punya angka yang tidak
   ada di feature, dan angka L2 selalu bisa diverifikasi dengan membandingkan
   kartu terhadap baris feature akun yang sama — nilainya harus IDENTIK,
   tanpa transformasi apa pun. Itulah yang diuji
   `tests/test_view_metrics.py::TestL2GoldCarryThrough`.

   Kolom-kolom ini IKUT penjaga `IS DISTINCT FROM` (keputusan #5). Kalau
   tidak, kartu yang hanya berubah Avg Views-nya akan dianggap tidak berubah
   dan angka barunya tidak pernah ditulis.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

# db.py ada di root project. Ditambahkan ke sys.path dengan pola yang sama
# seperti audience.py, supaya rumus Growth turunan (daily growth + proyeksi
# 30 hari) dipakai APA ADANYA dari sana dan tidak ditulis dua kali.
# Kalau rumusnya berubah, ia berubah di satu file.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from db import SQL_GROWTH_CTE  # noqa: E402
from metrics_thresholds import (  # noqa: E402
    RINGKASAN_AMBANG,
    sql_audience_quality_tier,
    sql_rising_creator,
    sql_stability,
    sql_gender_reliability,
    sql_growth_class,
    sql_monitoring_priority,
    sql_post_frequency_reliability,
)

GROUP = "l2_gold"
_PROFILE = AssetKey("unified_profile")
# Kartu ini sekarang membawa empat metrik views dari layer feature, jadi kedua
# asset itu harus sudah selesai sebelum kartu dibangun. Tanpa dep ini Dagster
# boleh menjalankan kartu lebih dulu, dan kartu akan menyalin nilai feature dari
# run SEBELUMNYA -- angka basi yang tidak terlihat salah.
_IG_ENGAGEMENT = AssetKey("ig_engagement_analysis")
_TT_ENGAGEMENT = AssetKey("tt_engagement_analysis")


# ---------------------------------------------------------------------------
# CTE bersama untuk statistik dan upsert
# ---------------------------------------------------------------------------
_CTE = """
    WITH """ + SQL_GROWTH_CTE + """,
    er_roster AS (
        -- ER ROSTER -- sumber yang disepakati untuk Monitoring Priority.
        --
        -- Sebelumnya priority dihitung dari
        -- `feature.*_engagement_analysis.engagement_rate`, yang hanya terisi
        -- untuk 38 akun. `public.kol_directory.engagement_rate` terisi untuk
        -- 1.736 dari 7.432 KOL (23,4%), jadi perpindahan ini menaikkan cakupan
        -- 45x tanpa menghitung ER baru satu pun.
        --
        -- SATUANNYA SAMA-SAMA PERSEN, sudah diperiksa terhadap 28 akun yang
        -- punya keduanya: 6,94 vs 16,15 · 2,75 vs 3,78 · 2,21 vs 1,81. Nilainya
        -- berbeda karena sampel dan metodenya berbeda, tapi skalanya sama --
        -- tidak ada faktor 100 yang tersembunyi seperti pada `er_followers_daily`.
        --
        -- `kol_directory` bergrain per KOL sementara kartu ini bergrain
        -- (social_account_id, platform), jadi dipetakan lewat
        -- `kol_social_account`. `max()` dipakai sebagai penjaga: pada data
        -- sekarang pemetaannya satu-lawan-satu (0 akun bercabang), dan agregat
        -- memastikan CTE ini tetap satu baris per akun kalau itu berubah.
        SELECT ksa.social_account_id,
               max(kd.engagement_rate) AS er_pct
          FROM public.kol_directory kd
          JOIN public.kol_social_account ksa ON ksa.kol_id = kd.id
         WHERE kd.engagement_rate IS NOT NULL
         GROUP BY 1
    ),
    badge AS (
        -- BADGE PLATFORM (centang biru), bukan Connected. Lihat keputusan #7.
        --
        -- TikTok diambil dari harmonization, lapisan bersih tertinggi yang
        -- memang membawa kolomnya. Instagram diambil dari l0_raw karena
        -- l0_harmonization.instagram_profile TIDAK punya kolom is_verified --
        -- satu-satunya tempat badge Instagram tersimpan adalah
        -- raw_payload->>'verified' (terukur: ada di 959 dari 959 baris).
        -- Menambah kolom itu ke harmonization adalah perubahan schema, dan
        -- sengaja TIDAK dilakukan di sini; lihat keputusan #7.
        -- Tiap cabang dibungkus subquery: ORDER BY milik DISTINCT ON tidak
        -- boleh berdiri tepat sebelum UNION.
        SELECT * FROM (
            SELECT DISTINCT ON (r.social_account_id)
                   r.social_account_id,
                   'instagram'::text                     AS platform,
                   (r.raw_payload->>'verified')::boolean  AS is_verified
              FROM l0_raw.ig_profile_apify r
             WHERE r.social_account_id IS NOT NULL
             ORDER BY r.social_account_id, r.scraped_at DESC
        ) ig
        UNION ALL
        SELECT * FROM (
            SELECT DISTINCT ON (h.social_account_id)
                   h.social_account_id,
                   'tiktok'::text                        AS platform,
                   h.is_verified
              FROM l0_harmonization.tiktok_profile h
             WHERE h.social_account_id IS NOT NULL
             ORDER BY h.social_account_id, h.date DESC
        ) tt
    ),
    metrik_views AS (
        -- Avg Views, Median Views, V2F, L2V -- DIBAWA APA ADANYA dari layer
        -- feature, tidak dihitung ulang di sini. Alasan yang sama dengan
        -- keputusan #2 untuk followers_growth: rumusnya sudah dijalankan
        -- feature_engagement.py, dan menuliskannya kedua kali berarti dua
        -- definisi yang cepat atau lambat berbeda.
        --
        -- Grain kedua tabel feature adalah (social_account_id) TANPA platform,
        -- karena platformnya sudah ditentukan oleh tabel mana yang dipakai.
        -- Kartu ini bergrain (social_account_id, platform), jadi platformnya
        -- ditambahkan sebagai literal supaya join-nya tepat satu lawan satu --
        -- akun yang punya Instagram DAN TikTok mendapat angkanya masing-masing,
        -- bukan angka salah satu platform yang bocor ke kartu satunya.
        SELECT social_account_id, 'instagram'::text AS platform,
               views_analyzed_count, avg_views, median_views,
               view_to_follower_ratio, like_to_view_ratio,
               -- Paid Ratio, Share Rate, Post Frequency (migration 037).
               -- DIBAWA APA ADANYA, alasan yang sama dengan keempat metrik
               -- views di atas: rumusnya sudah dijalankan feature_engagement.py.
               paid_ratio, paid_signal_count, share_rate,
               post_frequency_monthly, observation_days,
               -- Dibutuhkan migration 038: pembilang post_frequency_daily &
               -- syarat reliability, dan ER yang jadi dasar priority.
               post_frequency_count, engagement_rate,
               save_rate, viral_frequency, viral_post_count,
               viral_threshold_views, content_topic,
               content_topic_source, format_dominant
          FROM feature.ig_engagement_analysis
        UNION ALL
        SELECT social_account_id, 'tiktok'::text AS platform,
               views_analyzed_count, avg_views, median_views,
               view_to_follower_ratio, like_to_view_ratio,
               paid_ratio, paid_signal_count, share_rate,
               post_frequency_monthly, observation_days,
               post_frequency_count, engagement_rate,
               save_rate, viral_frequency, viral_post_count,
               viral_threshold_views, content_topic,
               content_topic_source, format_dominant
          FROM feature.tt_engagement_analysis
    ),
    -- Female %/Male % dari layer audience. Tabel terpisah dari engagement,
    -- jadi join-nya sendiri -- grainnya sama, (social_account_id) + platform
    -- ditentukan tabel asalnya.
    metrik_audiens AS (
        SELECT social_account_id, 'instagram'::text AS platform,
               female_pct, male_pct, gender_known_pct,
               audience_quality_score, authenticity_score,
               interest_top, interest_source
          FROM feature.ig_audience_analysis
        UNION ALL
        SELECT social_account_id, 'tiktok'::text AS platform,
               female_pct, male_pct, gender_known_pct,
               audience_quality_score, authenticity_score,
               interest_top, interest_source
          FROM feature.tt_audience_analysis
    ),
    -- PERFORMANCE STABILITY: simpangan baku ER historis, dalam POIN PERSEN.
    --
    -- `er_followers_daily` disimpan sebagai FRAKSI (0,0000164 .. 0,1615),
    -- sementara ambang stabilitas dinyatakan dalam persen. Dikali 100 DI SINI,
    -- sekali, sebelum stddev dihitung -- kalau tidak, simpangan baku 0,004
    -- akan dibandingkan dengan ambang 1 dan setiap akun tercatat sangat stabil.
    --
    -- `stddev_samp`, bukan `stddev_pop`: periodenya adalah SAMPEL dari
    -- perilaku akun, bukan seluruh populasinya. Ia juga mengembalikan NULL
    -- untuk n < 2, yang kebetulan sejalan dengan syarat minimal tiga periode.
    stabilitas AS (
        SELECT social_account_id, platform,
               count(er_followers_daily)::int AS er_periods,
               round(stddev_samp(er_followers_daily * 100)::numeric, 4) AS er_stddev_pp
          FROM l2_gold.kol_metric_daily
         GROUP BY 1, 2
    ),

    terbaru AS (
        SELECT DISTINCT ON (p.social_account_id, pl.key)
               p.social_account_id,
               pl.key            AS platform,
               p.date            AS profile_snapshot_date,
               p.username, p.display_name, p.avatar_url, p.profile_url,
               p.bio, p.website,
               -- BADGE PLATFORM, bukan p.is_verified. Kolom L1 itu berisi
               -- status Connected (lihat keputusan #7) dan sejak asset ini
               -- berhenti membacanya, tidak ada lagi yang memakainya.
               b.is_verified,
               p.is_private,
               p.followers_count, p.following_count, p.media_count,
               p.tier,
               -- PERSEN, dari snapshot yang sama. Tidak dihitung ulang.
               p.followers_growth,
               -- Empat metrik views dari layer feature. LEFT JOIN, jadi akun
               -- yang belum pernah punya post tetap dapat kartu -- kolomnya
               -- NULL, dan NULL di sini berarti "belum ada post yang diukur",
               -- bukan "nol views".
               v.views_analyzed_count,
               v.avg_views,
               v.median_views,
               v.view_to_follower_ratio,
               v.like_to_view_ratio,
               -- Paid Ratio / Share Rate / Post Frequency dari feature.
               v.paid_ratio, v.paid_signal_count, v.share_rate,
               v.post_frequency_monthly, v.observation_days,
               v.post_frequency_count,
               -- Monitoring Priority memakai ER ROSTER, bukan ER feature.
               er.er_pct AS monitoring_er_pct,
               -- post per HARI. monthly = angka ini x 30; keduanya disimpan
               -- karena requirement memakai dua satuan yang berbeda.
               round(v.post_frequency_count::numeric
                     / NULLIF(v.observation_days, 0), 4) AS post_frequency_daily,
               -- Female %/Male % dari feature audience.
               au.female_pct, au.male_pct, au.gender_known_pct,
               au.audience_quality_score, au.authenticity_score,
               au.interest_top  AS audience_interest_top,
               au.interest_source AS audience_interest_source,
               v.save_rate, v.viral_frequency, v.viral_post_count,
               v.viral_threshold_views, v.content_topic,
               v.content_topic_source, v.format_dominant,
               st.er_periods, st.er_stddev_pp,
               -- Growth turunan. Diambil dari CTE `growth` yang rumusnya
               -- diimpor dari db.py, dan HANYA kalau pasangan snapshotnya
               -- memang snapshot kartu ini -- kalau kartunya menunjuk
               -- tanggal lain, growth-nya bukan milik kartu ini.
               CASE WHEN gr.current_snapshot_date = p.date
                    THEN gr.previous_snapshot_date END AS previous_snapshot_date,
               CASE WHEN gr.current_snapshot_date = p.date
                    THEN gr.previous_followers END     AS previous_followers,
               CASE WHEN gr.current_snapshot_date = p.date
                    THEN gr.days_between END           AS days_between,
               CASE WHEN gr.current_snapshot_date = p.date
                    THEN gr.daily_growth END           AS daily_growth,
               CASE WHEN gr.current_snapshot_date = p.date
                    THEN gr.projected_30d END          AS projected_30d,
               CASE WHEN gr.current_snapshot_date = p.date
                    THEN gr.projected_followers_30d END AS projected_followers_30d
        FROM l1_silver.unified_profile p
        JOIN public.platforms pl ON pl.id = p.platform_id
        LEFT JOIN badge b
               ON b.social_account_id = p.social_account_id
              AND b.platform = pl.key
        LEFT JOIN metrik_views v
               ON v.social_account_id = p.social_account_id
              AND v.platform = pl.key
        LEFT JOIN metrik_audiens au
               ON au.social_account_id = p.social_account_id
              AND au.platform = pl.key
        LEFT JOIN growth gr
               ON gr.social_account_id = p.social_account_id
        LEFT JOIN stabilitas st
               ON st.social_account_id = p.social_account_id
              AND st.platform = pl.key
        LEFT JOIN er_roster er
               ON er.social_account_id = p.social_account_id
        WHERE p.social_account_id IS NOT NULL
        -- tie-break eksplisit supaya hasilnya deterministik
        ORDER BY p.social_account_id, pl.key,
                 p.date DESC, p.updated_at DESC NULLS LAST, p.id DESC
    )"""

SQL_UPSERT = _CTE + """
    INSERT INTO l2_gold.kol_profile_card (
        social_account_id, platform,
        username, display_name, avatar_url, profile_url,
        bio, website, is_verified, is_private,
        followers_count, following_count, media_count, tier,
        profile_snapshot_date, followers_growth,
        views_analyzed_count, avg_views, median_views,
        view_to_follower_ratio, like_to_view_ratio,
        paid_ratio, paid_signal_count, share_rate,
        post_frequency_monthly, observation_days,
        female_pct, male_pct, gender_known_pct,
        previous_snapshot_date, previous_followers, days_between,
        daily_growth, projected_30d, projected_followers_30d,
        post_frequency_daily, post_frequency_count, monitoring_er_pct,
        growth_class, gender_reliability, post_frequency_reliability,
        monitoring_priority,
        save_rate, viral_frequency, viral_post_count, viral_threshold_views,
        content_topic, content_topic_source, format_dominant,
        audience_quality_score, authenticity_score, audience_quality_tier,
        audience_interest_top, audience_interest_source,
        er_stddev_pp, er_periods, performance_stability, rising_creator,
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): rate_card, rate_card_currency,
        -- rate_card_min_fee, rate_card_max_fee, rate_card_post_types
    )
    SELECT t.social_account_id, t.platform,
           t.username, t.display_name, t.avatar_url, t.profile_url,
           t.bio, t.website, t.is_verified, t.is_private,
           t.followers_count, t.following_count, t.media_count, t.tier,
           t.profile_snapshot_date, t.followers_growth,
           t.views_analyzed_count, t.avg_views, t.median_views,
           t.view_to_follower_ratio, t.like_to_view_ratio,
           t.paid_ratio, t.paid_signal_count, t.share_rate,
           t.post_frequency_monthly, t.observation_days,
           t.female_pct, t.male_pct, t.gender_known_pct,
           t.previous_snapshot_date, t.previous_followers, t.days_between,
           t.daily_growth, t.projected_30d, t.projected_followers_30d,
           t.post_frequency_daily, t.post_frequency_count, t.monitoring_er_pct,
           -- Keempat label di bawah TIDAK ditulis tangan: CASE-nya digenerate
           -- metrics_thresholds.py dari konstanta yang sama yang dipakai fungsi
           -- Python-nya. Mengubah ambang = mengubah satu file, bukan file ini.
           """ + sql_growth_class("t.followers_growth") + """,
           """ + sql_gender_reliability("t.gender_known_pct") + """,
           """ + sql_post_frequency_reliability(
               "t.observation_days", "t.post_frequency_count") + """,
           """ + sql_monitoring_priority("t.monitoring_er_pct") + """,
           t.save_rate, t.viral_frequency, t.viral_post_count,
           t.viral_threshold_views, t.content_topic, t.content_topic_source,
           t.format_dominant,
           t.audience_quality_score, t.authenticity_score,
           """ + sql_audience_quality_tier("t.audience_quality_score") + """,
           t.audience_interest_top, t.audience_interest_source,
           t.er_stddev_pp, t.er_periods,
           """ + sql_stability("t.er_stddev_pp", "t.er_periods") + """,
           """ + sql_rising_creator("t.followers_growth") + """,
           now(), now()
    FROM terbaru t
    ON CONFLICT (social_account_id, platform) DO UPDATE SET
        username              = EXCLUDED.username,
        display_name          = EXCLUDED.display_name,
        avatar_url            = EXCLUDED.avatar_url,
        profile_url           = EXCLUDED.profile_url,
        bio                   = EXCLUDED.bio,
        website               = EXCLUDED.website,
        is_verified           = EXCLUDED.is_verified,
        is_private            = EXCLUDED.is_private,
        followers_count       = EXCLUDED.followers_count,
        following_count       = EXCLUDED.following_count,
        media_count           = EXCLUDED.media_count,
        tier                  = EXCLUDED.tier,
        profile_snapshot_date = EXCLUDED.profile_snapshot_date,
        followers_growth      = EXCLUDED.followers_growth,
        views_analyzed_count   = EXCLUDED.views_analyzed_count,
        avg_views              = EXCLUDED.avg_views,
        median_views           = EXCLUDED.median_views,
        view_to_follower_ratio = EXCLUDED.view_to_follower_ratio,
        like_to_view_ratio     = EXCLUDED.like_to_view_ratio,
        -- Penugasan LANGSUNG, bukan COALESCE: hasil NULL harus menimpa nilai
        -- lama. Akun yang kehilangan sampel post tidak boleh terus memajang
        -- Paid Ratio atau Share Rate basi.
        paid_ratio             = EXCLUDED.paid_ratio,
        paid_signal_count      = EXCLUDED.paid_signal_count,
        share_rate             = EXCLUDED.share_rate,
        post_frequency_monthly = EXCLUDED.post_frequency_monthly,
        observation_days       = EXCLUDED.observation_days,
        female_pct             = EXCLUDED.female_pct,
        male_pct               = EXCLUDED.male_pct,
        gender_known_pct       = EXCLUDED.gender_known_pct,
        previous_snapshot_date = EXCLUDED.previous_snapshot_date,
        previous_followers     = EXCLUDED.previous_followers,
        days_between           = EXCLUDED.days_between,
        daily_growth           = EXCLUDED.daily_growth,
        projected_30d          = EXCLUDED.projected_30d,
        projected_followers_30d = EXCLUDED.projected_followers_30d,
        post_frequency_daily   = EXCLUDED.post_frequency_daily,
        post_frequency_count   = EXCLUDED.post_frequency_count,
        monitoring_er_pct      = EXCLUDED.monitoring_er_pct,
        growth_class           = EXCLUDED.growth_class,
        gender_reliability     = EXCLUDED.gender_reliability,
        post_frequency_reliability = EXCLUDED.post_frequency_reliability,
        monitoring_priority    = EXCLUDED.monitoring_priority,
        save_rate              = EXCLUDED.save_rate,
        viral_frequency        = EXCLUDED.viral_frequency,
        viral_post_count       = EXCLUDED.viral_post_count,
        viral_threshold_views  = EXCLUDED.viral_threshold_views,
        content_topic          = EXCLUDED.content_topic,
        content_topic_source   = EXCLUDED.content_topic_source,
        format_dominant        = EXCLUDED.format_dominant,
        audience_quality_score = EXCLUDED.audience_quality_score,
        authenticity_score     = EXCLUDED.authenticity_score,
        audience_quality_tier  = EXCLUDED.audience_quality_tier,
        audience_interest_top  = EXCLUDED.audience_interest_top,
        audience_interest_source = EXCLUDED.audience_interest_source,
        er_stddev_pp           = EXCLUDED.er_stddev_pp,
        er_periods             = EXCLUDED.er_periods,
        performance_stability  = EXCLUDED.performance_stability,
        rising_creator         = EXCLUDED.rising_creator,
        updated_at            = now()
    -- Kolom rate_card_* SENGAJA tidak ada di atas: asset ini tidak mengisinya,
    -- jadi tidak boleh menimpanya balik jadi NULL kalau nanti diisi asset lain.
    --
    -- Penjaga: baris yang isinya tidak berubah tidak ditulis ulang, jadi
    -- updated_at menandai perubahan nyata dan rerun idempoten.
    WHERE kol_profile_card.username        IS DISTINCT FROM EXCLUDED.username
       OR kol_profile_card.display_name    IS DISTINCT FROM EXCLUDED.display_name
       OR kol_profile_card.avatar_url      IS DISTINCT FROM EXCLUDED.avatar_url
       OR kol_profile_card.profile_url     IS DISTINCT FROM EXCLUDED.profile_url
       OR kol_profile_card.bio             IS DISTINCT FROM EXCLUDED.bio
       OR kol_profile_card.website         IS DISTINCT FROM EXCLUDED.website
       OR kol_profile_card.is_verified     IS DISTINCT FROM EXCLUDED.is_verified
       -- Kolom migration 037. WAJIB ikut di penjaga ini: tanpa mereka, baris
       -- yang HANYA berubah di metrik baru dianggap tidak berubah dan upsert
       -- mengembalikan 0 -- kolomnya tetap NULL selamanya tanpa satu pun error.
       OR kol_profile_card.paid_ratio             IS DISTINCT FROM EXCLUDED.paid_ratio
       OR kol_profile_card.paid_signal_count      IS DISTINCT FROM EXCLUDED.paid_signal_count
       OR kol_profile_card.share_rate             IS DISTINCT FROM EXCLUDED.share_rate
       OR kol_profile_card.post_frequency_monthly IS DISTINCT FROM EXCLUDED.post_frequency_monthly
       OR kol_profile_card.observation_days       IS DISTINCT FROM EXCLUDED.observation_days
       OR kol_profile_card.female_pct             IS DISTINCT FROM EXCLUDED.female_pct
       OR kol_profile_card.male_pct               IS DISTINCT FROM EXCLUDED.male_pct
       OR kol_profile_card.gender_known_pct       IS DISTINCT FROM EXCLUDED.gender_known_pct
       OR kol_profile_card.daily_growth           IS DISTINCT FROM EXCLUDED.daily_growth
       OR kol_profile_card.projected_30d          IS DISTINCT FROM EXCLUDED.projected_30d
       OR kol_profile_card.projected_followers_30d
                                                  IS DISTINCT FROM EXCLUDED.projected_followers_30d
       OR kol_profile_card.previous_followers     IS DISTINCT FROM EXCLUDED.previous_followers
       OR kol_profile_card.previous_snapshot_date
                                                  IS DISTINCT FROM EXCLUDED.previous_snapshot_date
       OR kol_profile_card.days_between           IS DISTINCT FROM EXCLUDED.days_between
       -- Kolom migration 038. Wajib ikut, alasan yang sama dengan 037: tanpa
       -- ini baris yang hanya berubah di label dianggap tidak berubah.
       OR kol_profile_card.growth_class           IS DISTINCT FROM EXCLUDED.growth_class
       OR kol_profile_card.gender_reliability     IS DISTINCT FROM EXCLUDED.gender_reliability
       OR kol_profile_card.post_frequency_daily   IS DISTINCT FROM EXCLUDED.post_frequency_daily
       OR kol_profile_card.post_frequency_count   IS DISTINCT FROM EXCLUDED.post_frequency_count
       OR kol_profile_card.post_frequency_reliability
                                                  IS DISTINCT FROM EXCLUDED.post_frequency_reliability
       OR kol_profile_card.monitoring_er_pct      IS DISTINCT FROM EXCLUDED.monitoring_er_pct
       OR kol_profile_card.monitoring_priority    IS DISTINCT FROM EXCLUDED.monitoring_priority
       -- Kolom migration 039. Wajib ikut di penjaga, alasan yang sama:
       -- tanpa ini baris yang hanya berubah di metrik baru dianggap tidak
       -- berubah dan upsert mengembalikan 0 tanpa satu pun error.
       OR kol_profile_card.save_rate              IS DISTINCT FROM EXCLUDED.save_rate
       OR kol_profile_card.viral_frequency        IS DISTINCT FROM EXCLUDED.viral_frequency
       OR kol_profile_card.viral_post_count       IS DISTINCT FROM EXCLUDED.viral_post_count
       OR kol_profile_card.viral_threshold_views  IS DISTINCT FROM EXCLUDED.viral_threshold_views
       OR kol_profile_card.content_topic          IS DISTINCT FROM EXCLUDED.content_topic
       OR kol_profile_card.content_topic_source   IS DISTINCT FROM EXCLUDED.content_topic_source
       OR kol_profile_card.format_dominant        IS DISTINCT FROM EXCLUDED.format_dominant
       OR kol_profile_card.audience_quality_tier  IS DISTINCT FROM EXCLUDED.audience_quality_tier
       OR kol_profile_card.audience_interest_top  IS DISTINCT FROM EXCLUDED.audience_interest_top
       OR kol_profile_card.audience_interest_source
                                                  IS DISTINCT FROM EXCLUDED.audience_interest_source
       -- Kedua SKOR audiens ikut penjaga, bukan hanya TIER-nya. Keduanya ada
       -- di daftar SET tapi tidak pernah ada di sini, sehingga kartu yang
       -- HANYA berubah skornya dianggap tidak berubah dan angkanya tidak
       -- pernah ditulis -- persis kegagalan diam yang diperingatkan komentar
       -- migration 037/039 di atas. Terbukti 23 September: sesudah
       -- `kol_profile_card` dimaterialisasi ulang, 34 kartu IG masih memakai
       -- authenticity_score lama dan 27 audience_quality_score lama, satu di
       -- antaranya NULL padahal feature punya nilainya.
       OR kol_profile_card.audience_quality_score
                                                  IS DISTINCT FROM EXCLUDED.audience_quality_score
       OR kol_profile_card.authenticity_score     IS DISTINCT FROM EXCLUDED.authenticity_score
       OR kol_profile_card.performance_stability  IS DISTINCT FROM EXCLUDED.performance_stability
       OR kol_profile_card.er_stddev_pp           IS DISTINCT FROM EXCLUDED.er_stddev_pp
       -- `er_periods` ikut diperiksa terpisah: akun tanpa satu pun ER
       -- terukur punya er_periods 0 dan er_stddev_pp NULL, jadi memeriksa
       -- simpangan bakunya saja tidak pernah mendeteksi perubahan itu.
       OR kol_profile_card.er_periods             IS DISTINCT FROM EXCLUDED.er_periods
       OR kol_profile_card.rising_creator         IS DISTINCT FROM EXCLUDED.rising_creator
       OR kol_profile_card.is_private      IS DISTINCT FROM EXCLUDED.is_private
       OR kol_profile_card.followers_count IS DISTINCT FROM EXCLUDED.followers_count
       OR kol_profile_card.following_count IS DISTINCT FROM EXCLUDED.following_count
       OR kol_profile_card.media_count     IS DISTINCT FROM EXCLUDED.media_count
       OR kol_profile_card.tier            IS DISTINCT FROM EXCLUDED.tier
       OR kol_profile_card.profile_snapshot_date
                                           IS DISTINCT FROM EXCLUDED.profile_snapshot_date
       OR kol_profile_card.followers_growth
                                           IS DISTINCT FROM EXCLUDED.followers_growth
    -- Keempat metrik views ikut penjaga ini. Tanpa mereka, kartu yang HANYA
    -- berubah Avg Views-nya (mis. setelah post baru masuk) akan dianggap tidak
    -- berubah dan angka barunya tidak pernah ditulis.
       OR kol_profile_card.views_analyzed_count
                                           IS DISTINCT FROM EXCLUDED.views_analyzed_count
       OR kol_profile_card.avg_views       IS DISTINCT FROM EXCLUDED.avg_views
       OR kol_profile_card.median_views    IS DISTINCT FROM EXCLUDED.median_views
       OR kol_profile_card.view_to_follower_ratio
                                           IS DISTINCT FROM EXCLUDED.view_to_follower_ratio
       OR kol_profile_card.like_to_view_ratio
                                           IS DISTINCT FROM EXCLUDED.like_to_view_ratio
"""

SQL_STATS = _CTE + """
    -- `::bigint` pada sum() bukan kosmetik: SUM(bigint) mengembalikan numeric,
    -- yang sampai ke Python sebagai Decimal, dan Decimal ditolak Dagster
    -- sebagai nilai metadata. count() aman karena sudah bigint.
    SELECT count(*)                                              AS kartu,
           count(*) FILTER (WHERE platform = 'instagram')        AS kartu_ig,
           count(*) FILTER (WHERE platform = 'tiktok')           AS kartu_tt,
           count(followers_growth)                               AS growth_terisi,
           count(*) - count(followers_growth)                    AS growth_null,
           count(followers_growth) FILTER (WHERE platform = 'instagram')
                                                                 AS growth_ig,
           count(followers_growth) FILTER (WHERE platform = 'tiktok')
                                                                 AS growth_tt,
           count(followers_count)                                AS followers_terisi,
           count(tier)                                           AS tier_terisi,
           min(profile_snapshot_date)                            AS snapshot_tertua,
           max(profile_snapshot_date)                            AS snapshot_terbaru,
           -- Cakupan empat metrik views yang dibawa dari feature.
           count(avg_views)                                      AS avg_views_terisi,
           count(median_views)                                   AS median_views_terisi,
           count(view_to_follower_ratio)                         AS v2f_terisi,
           count(like_to_view_ratio)                             AS l2v_terisi
    FROM terbaru
    """


def _jalankan(postgres: PostgresResource) -> Output:
    """Hitung statistik, jalankan UPSERT, lalu laporkan metadata.

    SENGAJA tanpa try/except: kalau SQL-nya gagal, asset harus ikut gagal.
    Sumber kosong TIDAK dianggap gagal — selesai dengan 0 baris dan penjelasan.
    """
    tabel = "l2_gold.kol_profile_card"
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM l2_gold.kol_profile_card")
            sebelum = cur.fetchone()[0]

            cur.execute(SQL_STATS)
            (kartu, kartu_ig, kartu_tt, growth_terisi, growth_null,
             growth_ig, growth_tt, followers_terisi, tier_terisi,
             snapshot_tertua, snapshot_terbaru,
             avg_views_terisi, median_views_terisi,
             v2f_terisi, l2v_terisi) = cur.fetchone()

            if kartu == 0:
                conn.rollback()
                return Output(
                    0,
                    metadata={
                        "tabel": tabel,
                        "baris_ditulis": 0,
                        "catatan": MetadataValue.text(
                            "Tidak ada baris di l1_silver.unified_profile — tidak ada "
                            "kartu yang bisa dibangun. Bukan kegagalan."
                        ),
                    },
                )

            cur.execute(SQL_UPSERT)
            ditulis = cur.rowcount

            cur.execute("SELECT count(*) FROM l2_gold.kol_profile_card")
            sesudah = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return Output(
        sesudah,
        metadata={
            "tabel": tabel,
            "baris_sebelum": sebelum,
            "baris_sesudah": sesudah,
            "baris_disentuh_upsert": ditulis,
            "kartu_instagram": kartu_ig,
            "kartu_tiktok": kartu_tt,
            "followers_growth_terisi": growth_terisi,
            "followers_growth_null_belum_ada_snapshot_kedua": growth_null,
            "growth_instagram": growth_ig,
            "growth_tiktok": growth_tt,
            "followers_count_terisi": followers_terisi,
            "tier_terisi": tier_terisi,
            "rentang_snapshot": f"{snapshot_tertua} .. {snapshot_terbaru}",
            # Empat metrik views, dibawa dari feature (keputusan #8).
            "avg_views_terisi": avg_views_terisi,
            "median_views_terisi": median_views_terisi,
            "v2f_terisi": v2f_terisi,
            "l2v_terisi": l2v_terisi,
            "satuan_followers_growth": MetadataValue.text(
                "PERSEN (numeric), dibawa apa adanya dari "
                "l1_silver.unified_profile pada snapshot yang sama dengan "
                "profile_snapshot_date. Bukan jumlah orang."
            ),
            "kolom_sengaja_null": MetadataValue.text(
                "rate_card, rate_card_currency, rate_card_min_fee, "
                "rate_card_max_fee, rate_card_post_types — sumbernya siap "
                "(unified_rate_card 9.210 baris) tapi aturan ringkasannya "
                "belum diputuskan. Menyusul di tiket terpisah."
            ),
        },
    )


@asset(
    name="kol_profile_card",
    group_name=GROUP,
    deps=[_PROFILE, _IG_ENGAGEMENT, _TT_ENGAGEMENT],
    kinds={"postgres"},
    description=(
        "l2_gold.kol_profile_card — kartu profil KOL, grain "
        "(social_account_id, platform), satu kartu per akun tanpa dimensi "
        "tanggal. Sumber l1_silver.unified_profile snapshot TERBARU per akun; "
        "profile_snapshot_date mencatat snapshot mana yang dipakai. "
        "followers_growth dibawa apa adanya dari snapshot itu dan satuannya "
        "PERSEN, bukan jumlah orang — ini rumah account-grain untuk growth, "
        "yang tidak bisa diisi di kol_metric_daily karena grain-nya digerakkan "
        "posted_at. Membawa juga Avg Views, Median Views, V2F dan L2V apa "
        "adanya dari feature.{ig,tt}_engagement_analysis — tidak dihitung "
        "ulang di sini. Kolom rate_card_* sengaja dibiarkan NULL."
    ),
)
def kol_profile_card(postgres: PostgresResource) -> Output:
    return _jalankan(postgres)


gold_profile_assets = [kol_profile_card]
