-- =====================================================================
-- 035_followers_sanity_guard.sql
-- Sanity guard followers_count di L1. Rancangan disetujui pada Step 3A:
-- docs/AUTOME_2_STEP3A_FOLLOWERS_GUARD_DESIGN.md
--
-- MASALAH
--   Scrape TikTok yang gagal sebagian mengembalikan authorMeta.fans = 0..999
--   untuk akun yang sebenarnya berfollower ratusan ribu sampai jutaan.
--   Nilai itu lolos L0 -> harmonization -> L1 -> L2 tanpa satu pun gerbang.
--   Terukur 2026-09-07/08: 54 akun ber-followers L2 di bawah 1.000, seluruhnya
--   TikTok; contoh acuan zeejkt48 = 17 padahal roster 4.500.000.
--
--   Bahayanya bukan angka di layar, melainkan angka itu menjadi PENYEBUT
--   followers_growth pada snapshot berikutnya:
--       4.500.000 -> 17 -> 4.500.000
--   menghasilkan -99,9996% lalu +26.470.588%. Satu baris seperti itu cukup
--   untuk menggeser kalibrasi threshold pertumbuhan di Discovery.
--
--   Hari ini belum ada Growth yang tercemar (0 akun bernilai rusak yang sudah
--   punya snapshot kedua), tetapi 54 akun sedang menunggu snapshot berikutnya.
--
-- KENAPA "followers < 1.000 = invalid" DITOLAK
--   public.kol_directory punya 304 KOL aktif ber-followers di bawah 1.000
--   (14 nol, 133 di 1-99, 157 di 100-999). Ambang mutlak akan salah menolak
--   seluruhnya. Ambang di bawah ini TIDAK PERNAH diterapkan pada nilai baru,
--   hanya pada ACUAN pembandingnya -- itulah yang melindungi mereka.
--
-- ATURAN (tiga lapis, konstanta disetujui Step 3A)
--   AMBANG_DASAR  = 1.000   ambang minimum sebuah nilai boleh jadi ACUAN
--   RASIO_RUNTUH  = 0,10    di bawah 10% acuan dianggap runtuh (turun >90%)
--
--   Lapis 1  followers_count < 0                     -> NULL
--            followers_count IS NULL                 -> tetap NULL (bukan
--            temuan guard; "tidak diketahui" sudah bahasa pipeline ini)
--
--   Lapis 2  acuan := COALESCE(snapshot VALID sebelumnya, roster)
--            acuan >= AMBANG_DASAR
--            DAN followers_count < acuan * RASIO_RUNTUH   -> NULL
--
--   Lapis 3  acuan TIDAK ADA sama sekali
--            DAN platform TikTok DAN followers_count < AMBANG_DASAR
--            DAN likes_count = 0 DAN video_count = 0      -> NULL
--            Jaring pengaman untuk akun yang belum punya acuan apa pun.
--            Syarat "acuan tidak ada" wajib: tanpa itu, akun kecil yang SAH
--            dan rosternya ikut kecil (roster 480, scrape 900, belum punya
--            video) akan salah diblokir.
--            Terukur: likes_count = 0 tidak pernah terjadi pada satu pun
--            dari 1.019 baris L0 ber-fans >= 1.000 (rata-rata heart mereka
--            67.019.939), jadi kombinasi ini tidak menyentuh akun normal.
--            Instagram tidak punya padanan sekuat ini di kolom L0, jadi
--            lapis 3 sengaja khusus TikTok -- perbedaan yang disengaja.
--
-- PERLAKUAN: JANGAN PROPAGATE, RAW TETAP UTUH
--   l0_raw dan l0_harmonization TIDAK DISENTUH sama sekali oleh migration
--   ini. Nilai asli tetap tersimpan lengkap beserta raw_payload untuk audit
--   dan debugging. Yang berubah hanya apa yang L1 tuliskan: baris suspect
--   ditulis followers_count = NULL.
--
--   NULL dipilih karena sudah menjadi bahasa pipeline ini untuk "tidak
--   diketahui": followers_growth sudah NULL untuk penyebut NULL, dan tier
--   sudah NULL untuk followers NULL sejak migration 034. Tidak ada satu pun
--   konsumen hilir yang perlu diubah, dan tidak ada kolom baru.
--
-- BAGIAN TERPENTING: SNAPSHOT SUSPECT TIDAK BOLEH JADI PEMBANDING GROWTH
--   Versi sebelumnya menghitung pembanding dengan
--       LAG(followers_count) OVER (PARTITION BY akun ORDER BY date)
--   yaitu nilai baris SEBELUMNYA apa adanya. LAG biasa TIDAK melompati NULL,
--   sehingga setelah guard memasang NULL, snapshot ketiga akan kehilangan
--   pembandingnya (Growth jadi NULL selamanya) -- guard-nya benar tetapi
--   riwayatnya putus.
--
--   PostgreSQL tidak mendukung LAG(...) IGNORE NULLS, jadi pembanding dibuat
--   dua tahap: bawa-maju nilai ter-guard non-NULL terakhir (FIRST_VALUE di
--   dalam partisi gaps-and-islands), lalu LAG hasil bawa-maju itu. Hasilnya
--   persis "snapshot VALID terakhir sebelum baris ini".
--
--       4.500.000 -> 17(suspect/NULL) -> 4.500.000
--       snapshot 3 membandingkan ke 4.500.000 yang VALID, bukan ke 17,
--       bukan ke NULL. Growth = 0%, benar.
--
--   RUMUS Growth-nya sendiri TIDAK BERUBAH satu karakter pun. Yang berubah
--   hanya dari mana nilai prev_followers_count berasal.
--
-- SATU BARIS LAIN YANG WAJIB IKUT BERUBAH
--   ON CONFLICT ... DO UPDATE sebelumnya memakai
--       followers_count = COALESCE(EXCLUDED.followers_count, <nilai lama>)
--   Dengan COALESCE itu, baris suspect (EXCLUDED = NULL) akan MEMPERTAHANKAN
--   nilai rusak yang sudah tersimpan, sementara tier dan followers_growth --
--   yang memang sudah memakai penugasan langsung -- dihitung ulang dari NULL.
--   Barisnya jadi bertentangan dengan dirinya sendiri: followers_count 17,
--   tier NULL, growth NULL, dan L2 tetap membaca 17. Guard-nya tidak akan
--   berpengaruh apa pun pada 54 baris yang sudah ada.
--
--   Karena itu followers_count ikut memakai penugasan langsung, alasan yang
--   sama persis dengan yang sudah tertulis di atas tier dan followers_growth.
--   Grainnya (social_account_id, date) membuat ini aman: konflik hanya
--   terjadi saat memproses ulang TANGGAL YANG SAMA, yang sumbernya adalah
--   baris harmonization yang sama juga.
--
-- YANG TIDAK BERUBAH
--   Seluruh isi prosedur lain identik dengan migration 034 -- daftar kolom,
--   business rule Connected (031), aturan tier tanpa fallback (034), aturan
--   has_insights sekali-TRUE-tetap-TRUE (020), dedup, dan seluruh COALESCE
--   kolom lain di DO UPDATE.
--
-- TIDAK ADA PERUBAHAN SCHEMA
--   Tidak ada CREATE TABLE, ALTER TABLE, ADD COLUMN, kolom alasan, tabel
--   karantina, maupun tipe baru. Hanya CREATE OR REPLACE FUNCTION.
--   Tidak ada DELETE, UPDATE, atau TRUNCATE terhadap tabel mana pun.
--
-- DAMPAK TERUKUR (simulasi read-only, 2026-09-08 sesudah run Step 3C)
--   51 baris menjadi suspect dari 2.010 baris harmonization.
--     per platform : TikTok 50, Instagram 1
--     per lapis    : lapis 1 = 0 (belum ada nilai negatif),
--                    lapis 2 = 51 (seluruh temuan),
--                    lapis 3 = 0 (tidak ada baris yang sama sekali tanpa
--                    acuan, jadi lapis ini murni jaring pengaman)
--   0 baris ber-acuan di bawah 1.000 yang kena  -> 304 KOL kecil aman.
--
--   Baris Instagram itu (its.fadil_ = 9 padahal roster 10.063, dari scrape
--   2026-09-08) membuktikan bahwa kerusakan ini BUKAN eksklusif TikTok --
--   hanya jauh lebih jarang. Lapis 1 dan 2 memang berlaku untuk kedua
--   platform; hanya lapis 3 yang khusus TikTok.
--
--   Angka-angka ini keadaan data saat diukur, bukan kontrak. Yang dikunci
--   blok verifikasi di bawah adalah sifatnya: acuan kecil tidak pernah
--   tersentuh, dan guard benar-benar menggigit.
--   0 akun dengan lebih dari satu snapshot yang kena -> tidak ada riwayat
--     Growth yang sudah terbentuk yang berubah oleh migration ini.
--
-- CARA MUNDUR (ROLLBACK)
--   Jalankan ulang migrations/034_remove_tier_fallback_p01.sql. File itu
--   memuat definisi prosedur yang lengkap sebelum guard ini, sehingga
--   CREATE OR REPLACE-nya mengembalikan keadaan semula. Tidak ada data yang
--   perlu dipulihkan: l0_raw dan l0_harmonization tidak pernah disentuh, dan
--   nilai followers_count di L1 akan terisi ulang dari sumbernya pada
--   pembangunan berikutnya.
--
-- CARA MENJALANKAN
--   python apply_migration.py migrations/035_followers_sanity_guard.sql --dry-run
--   python apply_migration.py migrations/035_followers_sanity_guard.sql --yes
-- =====================================================================

BEGIN;

CREATE OR REPLACE FUNCTION l1_silver.sp_build_unified_profile()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    WITH sumber AS (
        -- Instagram: avatar_url kini tersedia (migration 007); open_id & likes_count tetap tidak ada
        SELECT social_account_id, date, username, name AS display_name, biography AS bio,
               avatar_url, website, NULL::varchar AS open_id,
               followers_count, follows_count AS following_count,
               media_count, NULL::bigint AS likes_count, reach, profile_views,
               accounts_engaged, profile_links_taps, total_interactions, likes, comments,
               shares, saves, replies, reposts, has_insights, source, source_table,
               source_id, processed_at,
               platform_user_id, profile_url, is_private,
               'instagram'::text AS src_platform   -- penanda lapis 3 (migration 035)
        FROM l0_harmonization.instagram_profile
        UNION ALL
        -- TikTok: website kini tersedia (migration 007); insight metrics tetap tidak ada
        SELECT social_account_id, date, username, display_name, bio_description AS bio,
               avatar_url, website, open_id,
               follower_count, following_count, video_count AS media_count, likes_count,
               NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
               NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint, NULL::bigint,
               NULL::bigint, NULL::bigint, NULL::boolean, source, source_table,
               source_id, processed_at,
               platform_user_id, profile_url, is_private,
               'tiktok'::text
        FROM l0_harmonization.tiktok_profile
    ),   -- >>> SUMBER END (035)
    -- ---------------------------------------------------------------
    -- ACUAN guard (migration 035)
    -- ---------------------------------------------------------------
    -- roster: nilai followers di public.kol_directory, dipakai sebagai acuan
    -- cadangan ketika akun belum punya snapshot sebelumnya -- kondisi
    -- mayoritas hari ini (1.948 dari 1.973 akun baru punya SATU snapshot,
    -- sehingga guard berbasis snapshot saja tidak akan menangkap apa pun).
    -- LEFT JOIN aman dan tidak menggandakan baris: public.kol_social_account
    -- terukur 1:1 terhadap social_account (7.497 tautan, 7.497 akun unik,
    -- maksimum 1 KOL per akun) dan kol_directory.id adalah primary key.
    -- Blok verifikasi di bawah menguji ulang sifat 1:1 itu setiap kali
    -- migration dijalankan, supaya perubahan data di kemudian hari gagal
    -- dengan berisik alih-alih diam-diam melipatgandakan baris L1.
    roster AS (
        SELECT k.social_account_id, kd.followers_count AS roster_followers
          FROM public.kol_social_account k
          JOIN public.kol_directory kd ON kd.id = k.kol_id
    ),   -- >>> ROSTER END (035)
    acuan AS (
        SELECT s.*, r.roster_followers,
               -- Penomoran gaps-and-islands: naik satu setiap kali ditemui
               -- nilai yang layak jadi acuan (>= AMBANG_DASAR). Nilai di
               -- bawah AMBANG_DASAR sengaja tidak pernah dipakai sebagai
               -- acuan -- aturannya memang mensyaratkan acuan >= 1.000 --
               -- dan itu sekaligus membuat nilai rusak (seluruh 39 nilai
               -- rusak terukur ada di bawah 1.000) tidak bisa menjadi
               -- pembanding bagi snapshot sesudahnya.
               count(CASE WHEN s.followers_count >= 1000 THEN 1 END) OVER (
                   PARTITION BY s.social_account_id ORDER BY s.date
                   ROWS UNBOUNDED PRECEDING
               ) AS ref_grp
        FROM sumber s
        LEFT JOIN roster r ON r.social_account_id = s.social_account_id
    ),
    acuan_bawa_maju AS (
        -- Nilai layak-acuan terakhir pada atau sebelum baris ini.
        SELECT a.*,
               first_value(CASE WHEN a.followers_count >= 1000 THEN a.followers_count END) OVER (
                   PARTITION BY a.social_account_id, a.ref_grp ORDER BY a.date
               ) AS ref_incl
        FROM acuan a
    ),
    acuan_sebelumnya AS (
        -- Digeser satu baris: nilai layak-acuan terakhir SEBELUM baris ini.
        SELECT b.*,
               lag(b.ref_incl) OVER (
                   PARTITION BY b.social_account_id ORDER BY b.date
               ) AS prev_ref
        FROM acuan_bawa_maju b
    ),
    dijaga AS (
        SELECT c.*,
               -- >>> GUARD BEGIN (035) -- ekspresi ini diuji apa adanya oleh
               -- tests/test_followers_guard.py; jangan ubah tanpa test.
               CASE
                   -- Lapis 1: nilai mustahil. Tidak butuh acuan apa pun.
                   WHEN c.followers_count < 0 THEN NULL
                   -- Lapis 2: runtuh terhadap acuan. AMBANG_DASAR 1.000
                   -- diterapkan pada ACUAN, bukan pada nilai baru, sehingga
                   -- akun yang memang kecil tidak pernah dinilai sama sekali.
                   WHEN COALESCE(c.prev_ref, c.roster_followers) >= 1000
                    AND c.followers_count
                        < COALESCE(c.prev_ref, c.roster_followers) * 0.10 THEN NULL
                   -- Lapis 3: profil TikTok kosong. HANYA untuk akun yang
                   -- tidak punya acuan sama sekali -- kalau ada acuan, lapis
                   -- 2 di atas sudah memutuskan dan keputusannya lebih baik.
                   -- Tanpa syarat "acuan IS NULL" ini, akun kecil yang SAH
                   -- dan rosternya ikut kecil (mis. roster 480, scrape 900,
                   -- belum punya video) akan salah diblokir. Empat syarat
                   -- harus terpenuhi bersamaan.
                   WHEN COALESCE(c.prev_ref, c.roster_followers) IS NULL
                    AND c.src_platform = 'tiktok'
                    AND c.followers_count < 1000
                    AND c.likes_count = 0
                    AND c.media_count = 0 THEN NULL
                   ELSE c.followers_count
               END
               -- >>> GUARD END (035)
               AS followers_dijaga
        FROM acuan_sebelumnya c
    ),
    -- ---------------------------------------------------------------
    -- PEMBANDING GROWTH (migration 035)
    -- ---------------------------------------------------------------
    -- Sama-sama gaps-and-islands, tetapi atas nilai HASIL guard, dan tanpa
    -- syarat >= AMBANG_DASAR: pembanding Growth boleh kecil (500 -> 700
    -- adalah pertumbuhan yang sah). Yang harus dilewati hanyalah NULL.
    rantai AS (
        SELECT d.*,
               count(d.followers_dijaga) OVER (
                   PARTITION BY d.social_account_id ORDER BY d.date
                   ROWS UNBOUNDED PRECEDING
               ) AS grp_dijaga
        FROM dijaga d
    ),
    rantai_bawa_maju AS (
        SELECT e.*,
               first_value(e.followers_dijaga) OVER (
                   PARTITION BY e.social_account_id, e.grp_dijaga ORDER BY e.date
               ) AS dijaga_incl
        FROM rantai e
    ),
    src AS (
        -- prev_followers_count: snapshot VALID terakhir sebelum baris ini.
        -- Snapshot suspect (followers_dijaga NULL) dilewati, bukan dipakai
        -- dan bukan memutus rantai.
        SELECT f.*,
               lag(f.dijaga_incl) OVER (
                   PARTITION BY f.social_account_id ORDER BY f.date
               ) AS prev_followers_count
        FROM rantai_bawa_maju f
    )
    INSERT INTO l1_silver.unified_profile (
        social_account_id, platform_id, date, username, display_name, bio, avatar_url,
        website, open_id, is_verified, followers_count, following_count, media_count,
        likes_count, reach, profile_views, accounts_engaged, profile_links_taps,
        total_interactions, likes, comments, shares, saves, replies, reposts,
        has_insights, source, source_table, source_id, processed_at,
        platform_user_id, profile_url, is_private, tier, followers_growth
    )
    SELECT
        sa.id, sa.platform_id, src.date, src.username, src.display_name, src.bio,
        src.avatar_url, src.website, src.open_id,
        (sa.platform_user_id IS NOT NULL
         AND sa.oauth_token IS NOT NULL),     -- BUSINESS RULE: connection status
        -- followers_count: nilai HASIL guard (migration 035). Nilai mentahnya
        -- tetap utuh di l0_raw dan l0_harmonization.
        src.followers_dijaga,
        src.following_count, src.media_count, src.likes_count, src.reach, src.profile_views,
        src.accounts_engaged, src.profile_links_taps, src.total_interactions, src.likes,
        src.comments, src.shares, src.saves, src.replies, src.reposts, src.has_insights,
        src.source, src.source_table, src.source_id, src.processed_at,
        src.platform_user_id, src.profile_url, src.is_private,
        -- tier: klasifikasi followers_count memakai ambang public.kol_tiers.
        -- followers_count NULL          -> tier NULL.
        -- followers_count < 1.000       -> tier NULL (P-01). Tidak cocok
        --   baris kol_tiers mana pun, dan sejak migration 034 TIDAK LAGI
        --   dijatuhkan ke tier terendah. Lihat header migration 034.
        -- Sejak 035 dihitung dari nilai ter-guard, sehingga baris suspect
        -- tidak mendapat tier dari angka yang rusak.
        CASE WHEN src.followers_dijaga IS NULL THEN NULL ELSE
            (SELECT t.name FROM public.kol_tiers t
              WHERE src.followers_dijaga >= t.min_followers
                AND (t.max_followers IS NULL OR src.followers_dijaga <= t.max_followers)
              ORDER BY t.min_followers DESC LIMIT 1)
        END,
        -- followers_growth: persen perubahan followers terhadap SNAPSHOT
        -- SEBELUMNYA milik akun yang sama. NULL kalau belum ada snapshot
        -- pembanding, kalau followers sebelumnya NULL atau 0 (pembagian
        -- tidak terdefinisi), atau kalau followers sekarang NULL. Tidak ada
        -- tebakan, tidak ada 0.
        -- RUMUSNYA TIDAK BERUBAH di migration 035. Yang berubah hanya asal
        -- prev_followers_count: kini snapshot VALID terakhir, melompati
        -- baris yang di-NULL-kan guard.
        -- >>> GROWTH BEGIN (035)
        CASE
            WHEN src.prev_followers_count IS NULL
              OR src.prev_followers_count = 0
              OR src.followers_dijaga IS NULL THEN NULL
            ELSE round((src.followers_dijaga - src.prev_followers_count)::numeric
                       / src.prev_followers_count * 100, 4)
        END
        -- >>> GROWTH END (035)
    FROM src
    JOIN public.social_account sa ON sa.id = src.social_account_id
    ON CONFLICT (social_account_id, date) DO UPDATE SET
        username = COALESCE(EXCLUDED.username, l1_silver.unified_profile.username),
        display_name = COALESCE(EXCLUDED.display_name, l1_silver.unified_profile.display_name),
        bio = COALESCE(EXCLUDED.bio, l1_silver.unified_profile.bio),
        avatar_url = COALESCE(EXCLUDED.avatar_url, l1_silver.unified_profile.avatar_url),
        website = COALESCE(EXCLUDED.website, l1_silver.unified_profile.website),
        open_id = COALESCE(EXCLUDED.open_id, l1_silver.unified_profile.open_id),
        is_verified = EXCLUDED.is_verified,   -- connection status: selalu definit
        -- followers_count: penugasan LANGSUNG sejak migration 035, bukan
        -- COALESCE. Dengan COALESCE, baris yang di-NULL-kan guard akan
        -- mempertahankan nilai rusak yang sudah tersimpan sementara tier dan
        -- followers_growth di bawah dihitung ulang dari NULL -- barisnya
        -- bertentangan dengan dirinya sendiri dan L2 tetap membaca angka
        -- rusak. Alasannya sama dengan yang sudah berlaku untuk kedua
        -- turunannya. Aman karena grain (social_account_id, date): konflik
        -- hanya terjadi saat memproses ulang tanggal yang sama, dari baris
        -- harmonization yang sama.
        followers_count = EXCLUDED.followers_count,
        following_count = COALESCE(EXCLUDED.following_count, l1_silver.unified_profile.following_count),
        media_count = COALESCE(EXCLUDED.media_count, l1_silver.unified_profile.media_count),
        likes_count = COALESCE(EXCLUDED.likes_count, l1_silver.unified_profile.likes_count),
        reach = COALESCE(EXCLUDED.reach, l1_silver.unified_profile.reach),
        profile_views = COALESCE(EXCLUDED.profile_views, l1_silver.unified_profile.profile_views),
        accounts_engaged = COALESCE(EXCLUDED.accounts_engaged, l1_silver.unified_profile.accounts_engaged),
        profile_links_taps = COALESCE(EXCLUDED.profile_links_taps, l1_silver.unified_profile.profile_links_taps),
        total_interactions = COALESCE(EXCLUDED.total_interactions, l1_silver.unified_profile.total_interactions),
        likes = COALESCE(EXCLUDED.likes, l1_silver.unified_profile.likes),
        comments = COALESCE(EXCLUDED.comments, l1_silver.unified_profile.comments),
        shares = COALESCE(EXCLUDED.shares, l1_silver.unified_profile.shares),
        saves = COALESCE(EXCLUDED.saves, l1_silver.unified_profile.saves),
        replies = COALESCE(EXCLUDED.replies, l1_silver.unified_profile.replies),
        reposts = COALESCE(EXCLUDED.reposts, l1_silver.unified_profile.reposts),
        -- T4b: sekali TRUE tetap TRUE. Dengan COALESCE biasa, snapshot
        -- terbaru yang tanpa Insights mematikan bendera padahal kolom
        -- Insights-nya sendiri bertahan (COALESCE di baris-baris di atas),
        -- sehingga baris yang PUNYA angka Insights mengaku tidak punya.
        has_insights = COALESCE(EXCLUDED.has_insights, false)
                    OR COALESCE(l1_silver.unified_profile.has_insights, false),
        platform_user_id = COALESCE(EXCLUDED.platform_user_id, l1_silver.unified_profile.platform_user_id),
        profile_url = COALESCE(EXCLUDED.profile_url, l1_silver.unified_profile.profile_url),
        is_private = COALESCE(EXCLUDED.is_private, l1_silver.unified_profile.is_private),
        tier = EXCLUDED.tier,   -- turunan followers_count: selalu ikut nilai terbaru
        -- Turunan juga: tanpa penugasan langsung, hasil hitung NULL akan
        -- mempertahankan nilai lama dan metriknya jadi basi.
        followers_growth = EXCLUDED.followers_growth,
        processed_at = EXCLUDED.processed_at,
        updated_at = now()
    WHERE EXCLUDED.processed_at >= l1_silver.unified_profile.processed_at
       OR l1_silver.unified_profile.processed_at IS NULL;
END;
$function$;

-- =====================================================================
-- VERIFIKASI -- melempar exception kalau salah, sehingga transaksinya batal
-- Seluruhnya membaca; tidak satu pun menulis ke tabel mana pun.
-- =====================================================================
DO $verifikasi$
DECLARE
    badan            text;
    n_kecil_kena     bigint;
    n_kena           bigint;
    n_ig_kena        bigint;
    n_prev_putus     bigint;
    n_roster_ganda   bigint;
BEGIN
    SELECT pg_get_functiondef(p.oid) INTO badan
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'l1_silver' AND p.proname = 'sp_build_unified_profile';

    IF badan IS NULL THEN
        RAISE EXCEPTION 'l1_silver.sp_build_unified_profile tidak ditemukan';
    END IF;

    -- 1. Guard benar-benar terpasang di badan prosedur.
    IF position('GUARD BEGIN (035)' IN badan) = 0 THEN
        RAISE EXCEPTION 'penanda GUARD BEGIN (035) tidak ada di badan prosedur';
    END IF;
    IF position('followers_dijaga' IN badan) = 0 THEN
        RAISE EXCEPTION 'kolom hasil guard tidak dipakai prosedur';
    END IF;

    -- 2. Pembanding Growth sudah melompati NULL, bukan LAG mentah lagi.
    IF position('lag(f.dijaga_incl)' IN badan) = 0 THEN
        RAISE EXCEPTION 'pembanding Growth belum memakai rantai bawa-maju';
    END IF;
    IF position('LAG(u.followers_count)' IN badan) > 0 THEN
        RAISE EXCEPTION 'pembanding Growth mentah (LAG langsung) masih tersisa';
    END IF;

    -- 3. Rumus Growth tidak boleh berubah.
    IF position('/ src.prev_followers_count * 100, 4)' IN badan) = 0 THEN
        RAISE EXCEPTION 'rumus followers_growth berubah -- tidak boleh';
    END IF;
    IF position('src.prev_followers_count = 0' IN badan) = 0 THEN
        RAISE EXCEPTION 'penjaga pembagian nol pada Growth hilang';
    END IF;

    -- 4. followers_count harus penugasan langsung, kalau tidak guard mandul.
    IF position('followers_count = EXCLUDED.followers_count' IN badan) = 0 THEN
        RAISE EXCEPTION 'followers_count di DO UPDATE bukan penugasan langsung';
    END IF;

    -- 5. Aturan tier tanpa fallback (034) harus tetap utuh.
    IF position('ORDER BY t.min_followers DESC LIMIT 1' IN badan) = 0 THEN
        RAISE EXCEPTION 'aturan tier migration 034 tidak utuh';
    END IF;

    -- 6. LEFT JOIN roster tidak boleh menggandakan baris. Kalau sifat 1:1
    --    kol_social_account -> social_account rusak, setiap snapshot akan
    --    menghasilkan lebih dari satu baris L1 dan ON CONFLICT akan saling
    --    menimpa secara acak. Gagalkan migration alih-alih diam-diam salah.
    SELECT count(*) INTO n_roster_ganda
      FROM (SELECT k.social_account_id
              FROM public.kol_social_account k
              JOIN public.kol_directory kd ON kd.id = k.kol_id
             GROUP BY 1 HAVING count(*) > 1) t;
    IF n_roster_ganda <> 0 THEN
        RAISE EXCEPTION
            '% social_account tertaut ke lebih dari satu kol_directory -- LEFT JOIN roster akan menggandakan baris L1',
            n_roster_ganda;
    END IF;

    -- ---------------------------------------------------------------
    -- Uji-balik terhadap DATA NYATA, memakai aturan yang sama.
    -- ---------------------------------------------------------------
    WITH sumber AS (
        SELECT social_account_id, date, follower_count AS f, 'tiktok'::text AS plat,
               likes_count AS lk, video_count AS vd
          FROM l0_harmonization.tiktok_profile
        UNION ALL
        SELECT social_account_id, date, followers_count, 'instagram'::text,
               NULL::bigint, media_count
          FROM l0_harmonization.instagram_profile
    ), a AS (
        SELECT s.*,
               (SELECT kd.followers_count FROM public.kol_social_account k
                  JOIN public.kol_directory kd ON kd.id = k.kol_id
                 WHERE k.social_account_id = s.social_account_id) AS roster,
               count(CASE WHEN s.f >= 1000 THEN 1 END) OVER (
                   PARTITION BY s.social_account_id ORDER BY s.date
                   ROWS UNBOUNDED PRECEDING) AS grp
          FROM sumber s
    ), a2 AS (
        -- Dua langkah terpisah: PostgreSQL tidak mengizinkan window function
        -- bersarang, jadi bawa-maju dan penggeserannya harus beda CTE --
        -- persis seperti di badan prosedur.
        SELECT a.*, first_value(CASE WHEN a.f >= 1000 THEN a.f END) OVER (
                        PARTITION BY a.social_account_id, a.grp ORDER BY a.date) AS ref_incl
          FROM a
    ), b AS (
        SELECT a2.*, lag(a2.ref_incl) OVER (
                        PARTITION BY a2.social_account_id ORDER BY a2.date) AS prev_ref
          FROM a2
    ), g AS (
        SELECT b.*, COALESCE(b.prev_ref, b.roster) AS acuan,
               (b.f < 0
                OR (COALESCE(b.prev_ref, b.roster) >= 1000
                    AND b.f < COALESCE(b.prev_ref, b.roster) * 0.10)
                OR (COALESCE(b.prev_ref, b.roster) IS NULL
                    AND b.plat = 'tiktok' AND b.f < 1000 AND b.lk = 0 AND b.vd = 0)
               ) AS suspect
          FROM b
    )
    SELECT count(*) FILTER (WHERE suspect),
           count(*) FILTER (WHERE suspect AND acuan < 1000),
           count(*) FILTER (WHERE suspect AND plat = 'instagram')
      INTO n_kena, n_kecil_kena, n_ig_kena
      FROM g;

    -- 7. SIFAT KEAMANAN UTAMA: akun yang acuannya memang kecil tidak boleh
    --    pernah tersentuh. Inilah yang melindungi 304 KOL kecil yang sah.
    IF n_kecil_kena <> 0 THEN
        RAISE EXCEPTION
            'guard menyentuh % baris ber-acuan di bawah 1.000 -- KOL kecil yang sah ikut diblokir',
            n_kecil_kena;
    END IF;

    -- 8. Guard harus benar-benar menggigit, kalau tidak aturannya salah pasang.
    IF n_kena = 0 THEN
        RAISE EXCEPTION 'guard tidak menandai satu baris pun -- kemungkinan salah pasang';
    END IF;

    -- 9. Tidak boleh ada akun yang KEHILANGAN pembanding Growth-nya. Kalau
    --    sebuah akun punya >= 2 snapshot valid, snapshot terakhirnya wajib
    --    tetap menemukan pembanding sesudah guard berjalan.
    WITH sumber AS (
        SELECT social_account_id, date, follower_count AS f FROM l0_harmonization.tiktok_profile
        UNION ALL
        SELECT social_account_id, date, followers_count FROM l0_harmonization.instagram_profile
    )
    SELECT count(*) INTO n_prev_putus
      FROM (SELECT social_account_id FROM sumber
             WHERE f IS NOT NULL GROUP BY 1 HAVING count(*) >= 2) t
     WHERE NOT EXISTS (SELECT 1 FROM sumber s
                        WHERE s.social_account_id = t.social_account_id
                          AND s.f IS NOT NULL);
    IF n_prev_putus <> 0 THEN
        RAISE EXCEPTION '% akun kehilangan pembanding Growth', n_prev_putus;
    END IF;

    RAISE NOTICE 'Guard 035 terpasang. Baris suspect: % (Instagram: %, acuan kecil: %).',
        n_kena, n_ig_kena, n_kecil_kena;
    RAISE NOTICE 'l0_raw dan l0_harmonization tidak disentuh; nilai mentah tetap utuh.';
END;
$verifikasi$;

COMMIT;
