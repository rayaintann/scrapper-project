-- 027_dedup_sync_instagram_follower.sql
--
-- Menambahkan DEDUP SUMBER pada l0_harmonization.sp_sync_instagram_follower().
--
-- Perubahan LOGIKA di dalam satu routine. Tidak ada tabel, kolom, index,
-- constraint, atau baris data yang disentuh. Nama, argumen, dan tipe kembalian
-- tidak berubah, jadi semua pemanggil yang ada tetap jalan.
--
-- ============================================================================
-- CACAT YANG DIPERBAIKI -- SUDAH DIRAMALKAN MIGRATION 019
-- ============================================================================
--
-- Migration 019 memperbaiki cacat yang persis sama pada procedure post, dan
-- mencatat di bagian penutupnya:
--
--     "BELUM diperbaiki, dan itu disengaja:
--        * 9 procedure sync lain juga tidak punya DISTINCT ON, tapi sumber
--          L0-nya semuanya 0 baris sehingga cacatnya tidak bisa aktif."
--
-- `sp_sync_instagram_follower` adalah salah satu dari sembilan itu. Sumber
-- L0-nya sekarang TIDAK lagi 0 baris, dan begitu satu follower punya DUA baris
-- L0 untuk (akun, follower, tanggal) yang sama -- satu dari actor follower-list,
-- satu dari actor profile -- satu statement mencoba menyentuh baris konflik yang
-- sama dua kali:
--
--     SQLSTATE 21000: ON CONFLICT DO UPDATE command cannot affect row a
--                     second time
--
-- Bukan hipotesis: error itu benar-benar muncul saat enrichment profil
-- dijalankan (1.300 baris follower-list + 1.263 baris profil di tabel yang sama).
--
-- ============================================================================
-- KENAPA MENGGABUNGKAN, BUKAN `DISTINCT ON` SEPERTI MIGRATION 019
-- ============================================================================
--
-- Migration 019 memakai `DISTINCT ON` -- ambil satu baris, buang sisanya. Itu
-- benar untuk post, karena `unified_post` memang tabel keadaan-terkini dan
-- snapshot terbaru sudah memuat semua yang dibutuhkan.
--
-- Di sini SALAH, karena kedua sumbernya saling melengkapi, bukan saling
-- menggantikan:
--
--     actor follower-list : username, full_name, is_private, is_verified,
--                           profile_pic_url    (bio & jumlah = NULL)
--     actor profile       : bio, followers_count, following_count, ...
--                           (sebagian full_name bisa NULL)
--
-- `DISTINCT ON` yang memilih baris profil akan MEMBUANG `full_name` untuk
-- follower yang profilnya tidak mengembalikan nama; yang memilih baris
-- follower-list akan membuang seluruh bio dan jumlah -- yaitu justru data yang
-- baru saja dibayar untuk diambil.
--
-- Jadi sumbernya digabung PER KOLOM: untuk tiap kolom diambil nilai TIDAK-NULL
-- pertama, diurutkan dari baris ber-`scraped_at` TERBARU. Efeknya:
--
--     * sumber terbaru menang kalau dua-duanya terisi
--     * sumber lama mengisi kalau yang terbaru NULL
--     * tidak ada kolom yang hilang dari sumber mana pun
--
-- Ini juga selaras dengan klausa `ON CONFLICT` procedure ini sendiri, yang
-- memang sudah bersemantik gabung (`COALESCE(EXCLUDED.x, existing.x)`).
-- Sebelum perbaikan ini, niat gabung itu hanya berlaku antar-RUN, tidak
-- antar-baris di dalam satu run.
--
-- Urutannya memakai `scraped_at DESC, id DESC` -- `id` sebagai pemecah seri
-- supaya hasilnya deterministik antar-run, pola yang sama dengan migration 019.
--
-- ============================================================================
-- CABANG `official` SENGAJA TIDAK DIUBAH
-- ============================================================================
--
-- `l0_raw.ig_followers_official` masih 0 baris, jadi cacat yang sama ada di
-- sana tapi tidak bisa aktif. Mengikuti cara migration 019 menimbang hal ini:
-- yang diperbaiki hanya yang sumbernya benar-benar berisi, supaya perubahan
-- tetap sekecil mungkin dan bisa diuji terhadap data nyata. Begitu jalur
-- official dipakai, cabang itu butuh perbaikan yang sama.
--
-- ============================================================================
-- AMAN DIULANG
-- ============================================================================
--
-- CREATE OR REPLACE; tidak ada state yang ditinggalkan. Menjalankan procedure
-- ini berkali-kali tetap idempoten karena ON CONFLICT-nya tidak berubah.

BEGIN;

CREATE OR REPLACE PROCEDURE l0_harmonization.sp_sync_instagram_follower()
 LANGUAGE plpgsql
AS $procedure$
DECLARE
  v_log_id uuid; v_baca bigint := 0; v_masuk bigint := 0; v_sebelum bigint := 0;
BEGIN
  SELECT count(*) INTO v_sebelum FROM l0_harmonization.instagram_follower;

  INSERT INTO l0_harmonization.sync_log
    (target_table, source_table, source, sync_date, status, started_at)
  VALUES ('instagram_follower','l0_raw.ig_followers_apify + l0_raw.ig_followers_official','apify+official', current_date, 'running', now())
  RETURNING id INTO v_log_id;

  -- dari apify -- sumber DIGABUNG per grain lebih dulu (lihat header migration 027)
  WITH sumber AS (
    SELECT
      s.social_account_id,
      COALESCE(s.scraped_at, s.insert_at, now())::date AS tgl,
      s.followers_ig_id,
      s.username, s.full_name, s.bio, s.profile_pic_url,
      s.is_private, s.is_verified, s.is_bussiness_account,
      s.followers_count, s.following_count, s.email, s.phones,
      CASE WHEN s.social_links IS NULL OR btrim(s.social_links)='' THEN NULL
           WHEN s.social_links ~ '^\s*[\[{]' THEN s.social_links::jsonb
           ELSE to_jsonb(s.social_links) END                       AS social_links_j,
      s.id                                                          AS src_id,
      COALESCE(s.scraped_at, s.insert_at, now())                    AS proc_at,
      -- prioritas: sumber terbaru lebih dulu; id sebagai pemecah seri
      row_number() OVER (
        PARTITION BY s.social_account_id, s.followers_ig_id,
                     COALESCE(s.scraped_at, s.insert_at, now())::date
        ORDER BY COALESCE(s.scraped_at, s.insert_at, now()) DESC, s.id DESC
      ) AS prio
    FROM l0_raw.ig_followers_apify s
    WHERE s.social_account_id IS NOT NULL AND s.followers_ig_id IS NOT NULL
  ),
  gabung AS (
    -- Untuk tiap kolom: nilai TIDAK-NULL pertama menurut `prio`.
    SELECT
      social_account_id, tgl, followers_ig_id,
      (array_agg(username        ORDER BY prio) FILTER (WHERE username        IS NOT NULL))[1] AS username,
      (array_agg(full_name       ORDER BY prio) FILTER (WHERE full_name       IS NOT NULL))[1] AS full_name,
      (array_agg(bio             ORDER BY prio) FILTER (WHERE bio             IS NOT NULL))[1] AS bio,
      (array_agg(profile_pic_url ORDER BY prio) FILTER (WHERE profile_pic_url IS NOT NULL))[1] AS profile_pic_url,
      (array_agg(is_private      ORDER BY prio) FILTER (WHERE is_private      IS NOT NULL))[1] AS is_private,
      (array_agg(is_verified     ORDER BY prio) FILTER (WHERE is_verified     IS NOT NULL))[1] AS is_verified,
      (array_agg(is_bussiness_account ORDER BY prio) FILTER (WHERE is_bussiness_account IS NOT NULL))[1] AS is_business_account,
      (array_agg(followers_count ORDER BY prio) FILTER (WHERE followers_count IS NOT NULL))[1] AS followers_count,
      (array_agg(following_count ORDER BY prio) FILTER (WHERE following_count IS NOT NULL))[1] AS following_count,
      (array_agg(email           ORDER BY prio) FILTER (WHERE email           IS NOT NULL))[1] AS email,
      (array_agg(phones          ORDER BY prio) FILTER (WHERE phones          IS NOT NULL))[1] AS phones,
      (array_agg(social_links_j  ORDER BY prio) FILTER (WHERE social_links_j  IS NOT NULL))[1] AS social_links,
      (array_agg(src_id          ORDER BY prio))[1]                                            AS source_id,
      max(proc_at)                                                                             AS processed_at
    FROM sumber
    GROUP BY social_account_id, tgl, followers_ig_id
  )
  INSERT INTO l0_harmonization.instagram_follower (
    social_account_id, date, follower_platform_id, username, full_name, bio, profile_pic_url, is_private, is_verified, is_business_account, followers_count, following_count, email, phones, social_links, source, source_table, source_id, processed_at)
  SELECT g.social_account_id, g.tgl, g.followers_ig_id, g.username, g.full_name, g.bio,
         g.profile_pic_url, g.is_private, g.is_verified, g.is_business_account,
         g.followers_count, g.following_count, g.email, g.phones, g.social_links,
         'apify', 'l0_raw.ig_followers_apify', g.source_id, g.processed_at
  FROM gabung g
  ON CONFLICT (social_account_id, follower_platform_id, date) DO UPDATE SET
    username = COALESCE(EXCLUDED.username, instagram_follower.username),
    full_name = COALESCE(EXCLUDED.full_name, instagram_follower.full_name),
    bio = COALESCE(EXCLUDED.bio, instagram_follower.bio),
    profile_pic_url = COALESCE(EXCLUDED.profile_pic_url, instagram_follower.profile_pic_url),
    is_private = COALESCE(EXCLUDED.is_private, instagram_follower.is_private),
    is_verified = COALESCE(EXCLUDED.is_verified, instagram_follower.is_verified),
    is_business_account = COALESCE(EXCLUDED.is_business_account, instagram_follower.is_business_account),
    followers_count = COALESCE(EXCLUDED.followers_count, instagram_follower.followers_count),
    following_count = COALESCE(EXCLUDED.following_count, instagram_follower.following_count),
    email = COALESCE(EXCLUDED.email, instagram_follower.email),
    phones = COALESCE(EXCLUDED.phones, instagram_follower.phones),
    social_links = COALESCE(EXCLUDED.social_links, instagram_follower.social_links),
    source = EXCLUDED.source,
    source_table = EXCLUDED.source_table,
    source_id = EXCLUDED.source_id,
    processed_at = EXCLUDED.processed_at
  WHERE instagram_follower.processed_at < EXCLUDED.processed_at;

  -- dari official -- TIDAK diubah; sumbernya masih 0 baris (lihat header)
  INSERT INTO l0_harmonization.instagram_follower (
    social_account_id, date, follower_platform_id, username, full_name, bio, profile_pic_url, is_private, is_verified, is_business_account, followers_count, following_count, email, phones, social_links, source, source_table, source_id, processed_at)
  SELECT s.social_account_id, COALESCE(s.fetched_at, now())::date, s.followers_ig_id, s.username, s.full_name, s.bio, s.profile_pic_url, s.is_private, s.is_verified, s.is_bussiness_account, s.followers_count, s.following_count, s.email, s.phones, CASE WHEN s.social_links IS NULL OR btrim(s.social_links)='' THEN NULL
         WHEN s.social_links ~ '^\s*[\[{]' THEN s.social_links::jsonb
         ELSE to_jsonb(s.social_links) END, 'official', 'l0_raw.ig_followers_official', s.id, COALESCE(s.fetched_at, now())
  FROM l0_raw.ig_followers_official s
  WHERE s.social_account_id IS NOT NULL AND s.followers_ig_id IS NOT NULL
  ON CONFLICT (social_account_id, follower_platform_id, date) DO UPDATE SET
    username = COALESCE(EXCLUDED.username, instagram_follower.username),
    full_name = COALESCE(EXCLUDED.full_name, instagram_follower.full_name),
    bio = COALESCE(EXCLUDED.bio, instagram_follower.bio),
    profile_pic_url = COALESCE(EXCLUDED.profile_pic_url, instagram_follower.profile_pic_url),
    is_private = COALESCE(EXCLUDED.is_private, instagram_follower.is_private),
    is_verified = COALESCE(EXCLUDED.is_verified, instagram_follower.is_verified),
    is_business_account = COALESCE(EXCLUDED.is_business_account, instagram_follower.is_business_account),
    followers_count = COALESCE(EXCLUDED.followers_count, instagram_follower.followers_count),
    following_count = COALESCE(EXCLUDED.following_count, instagram_follower.following_count),
    email = COALESCE(EXCLUDED.email, instagram_follower.email),
    phones = COALESCE(EXCLUDED.phones, instagram_follower.phones),
    social_links = COALESCE(EXCLUDED.social_links, instagram_follower.social_links),
    source = EXCLUDED.source,
    source_table = EXCLUDED.source_table,
    source_id = EXCLUDED.source_id,
    processed_at = EXCLUDED.processed_at
  WHERE instagram_follower.processed_at < EXCLUDED.processed_at;

  SELECT (SELECT count(*) FROM l0_raw.ig_followers_apify) + (SELECT count(*) FROM l0_raw.ig_followers_official) INTO v_baca;
  SELECT count(*) INTO v_masuk FROM l0_harmonization.instagram_follower;

  UPDATE l0_harmonization.sync_log
  SET status='success', rows_read=v_baca, rows_inserted=v_masuk - v_sebelum,
      rows_updated=v_sebelum, finished_at=now(),
      duration_seconds=EXTRACT(EPOCH FROM (now()-started_at))
  WHERE id=v_log_id;

EXCEPTION WHEN OTHERS THEN
  UPDATE l0_harmonization.sync_log
  SET status='failed', error_message=SQLERRM, finished_at=now()
  WHERE id=v_log_id;
  RAISE;
END $procedure$;

COMMIT;
