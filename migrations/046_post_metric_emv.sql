-- 046_post_metric_emv.sql
--
-- Dua kolom EMV di `l2_gold.post_metric`:
--
--     emv_min = engagement x 500   IDR
--     emv_max = engagement x 2.000 IDR
--     engagement = likes + comments
--
-- Migrasi ini HANYA menambah kolom. Tidak ada tabel baru, tidak ada schema
-- baru, tidak ada perubahan tipe, tidak ada DROP, dan tidak satu baris pun
-- diubah atau dihapus. Pola yang sama dengan 036-041.
--
-- ============================================================================
-- KENAPA KOLOM, PADAHAL EMV ADALAH TURUNAN MURNI
-- ============================================================================
--
-- Alasannya SAMA PERSIS dengan migration 037 untuk daily_growth/projected_30d:
-- UI Autometric adalah Next.js yang query Postgres LANGSUNG dan tidak bisa
-- memanggil `emv.py`. Tanpa kolom, rumusnya harus disalin ke repo lain -- dan
-- rumus yang hidup di dua repo cepat atau lambat berbeda. Kolom di sini
-- membuat definisinya tetap satu, dibaca siapa pun.
--
-- ============================================================================
-- KENAPA GENERATED ALWAYS, BUKAN KOLOM BIASA YANG DIISI PIPELINE
-- ============================================================================
--
-- Kolom biasa menuntut tiga hal sekaligus: backfill sekali, INSERT/UPDATE di
-- `gold_post.py` diperluas, dan penjaga `IS DISTINCT FROM` ikut ditambah.
-- Lupa salah satunya -> EMV basi tanpa ada yang tahu, karena angkanya tetap
-- terlihat wajar.
--
-- GENERATED ALWAYS ... STORED menghapus ketiganya:
--
--   * Postgres yang menghitung, jadi EMV TIDAK MUNGKIN tidak sinkron dengan
--     likes/comments di barisnya sendiri -- termasuk saat pipeline meng-UPDATE
--     likes lewat ON CONFLICT.
--   * Nilai untuk 503 baris yang sudah ada terisi saat ALTER dijalankan; tidak
--     ada langkah backfill yang bisa terlewat.
--   * `gold_post.py` TIDAK PERLU DIUBAH SAMA SEKALI. INSERT-nya menyebut kolom
--     satu per satu dan tidak menyebut emv_*, ON CONFLICT DO UPDATE-nya juga
--     tidak. Keduanya memang TIDAK BOLEH menyebut kolom generated, dan itu
--     otomatis sudah terpenuhi.
--
-- Konsekuensi yang diterima: nilainya tidak bisa ditimpa manual. Untuk angka
-- yang seluruhnya turunan, itu justru yang diinginkan.
--
-- ============================================================================
-- KENAPA `likes_hidden` JADI NULL, BUKAN 0
-- ============================================================================
--
-- Instagram mengizinkan kreator menyembunyikan jumlah like. Baris seperti itu
-- menyimpan `likes = -1` sebagai PENANDA, bukan nilai; ada 22 baris begini.
--
--   * dijumlah apa adanya -> engagement berkurang 1, dan EMV ikut salah
--   * -1 dianggap 0       -> EMV mengaku terukur padahal like-nya tidak pernah
--                            diketahui
--
-- Keduanya salah, jadi EMV-nya NULL: tidak terukur, dan terbaca tidak terukur.
-- Ini sebabnya `engagement_public` yang sudah ada TIDAK dipakai ulang di sini
-- -- kolom itu memuat -1 apa adanya (contoh nyata: -1 + 14 = 13).
--
-- ============================================================================
-- YANG TIDAK IKUT, DAN KENAPA
-- ============================================================================
--
--   shares  hanya terisi di TikTok (291 dari 503 post). Memasukkannya membuat
--           EMV Instagram terlihat lebih rendah semata karena Apify tidak
--           mengirim field itu, bukan karena kontennya lebih buruk.
--   saves   masalah cakupan yang sama persis dengan shares.
--   clicks  tidak ada di database mana pun.
--   views / reach / impressions
--           jangkauan, bukan interaksi. `reach` juga 0 dari 503 terisi.
--
-- EMV di sini TIDAK menyentuh campaign cost (`campaign_kols.deal_price`,
-- `campaign_kol_deliverables.subtotal`, `campaign_orders.total_amount`),
-- TIDAK menyentuh rate card (`unified_rate_card.fee` -- itu harga jasa yang
-- diminta kreator, bukan nilai yang dihasilkan konten), dan TIDAK menyentuh
-- TSDB. Satu-satunya input adalah `likes` dan `comments` di baris ini sendiri.
--
-- ============================================================================
-- TIPE
-- ============================================================================
--
-- `bigint` memadai: engagement terbesar saat ini 39.452.389, dikali 2.000 jadi
-- 7,9e10 -- jauh di bawah batas bigint 9,2e18. numeric tidak diperlukan karena
-- rupiah di sini selalu bulat (tidak ada pecahan sen).

BEGIN;

ALTER TABLE l2_gold.post_metric
    ADD COLUMN IF NOT EXISTS emv_min bigint
        GENERATED ALWAYS AS (
            CASE WHEN likes_hidden IS TRUE OR likes < 0 THEN NULL
                 ELSE (COALESCE(likes, 0) + COALESCE(comments, 0)) * 500
            END
        ) STORED,
    ADD COLUMN IF NOT EXISTS emv_max bigint
        GENERATED ALWAYS AS (
            CASE WHEN likes_hidden IS TRUE OR likes < 0 THEN NULL
                 ELSE (COALESCE(likes, 0) + COALESCE(comments, 0)) * 2000
            END
        ) STORED;

COMMENT ON COLUMN l2_gold.post_metric.emv_min IS
    'EMV batas bawah, IDR. (likes + comments) x 500. NULL kalau likes_hidden '
    'atau likes < 0 -- jumlah like tidak diketahui, jadi EMV tidak diketahui. '
    'shares/saves/clicks/views/reach TIDAK ikut. Tidak memakai campaign cost, '
    'rate card, atau TSDB. Dihitung Postgres (GENERATED), bukan pipeline.';

COMMENT ON COLUMN l2_gold.post_metric.emv_max IS
    'EMV batas atas, IDR. (likes + comments) x 2000. Aturan NULL dan komponen '
    'sama persis dengan emv_min; emv_max selalu 4x emv_min.';


DO $verifikasi$
DECLARE
    n              int;
    n_hidden       int;
    n_salah_min    int;
    n_salah_max    int;
    n_hidden_isi   int;
BEGIN
    -- 1. Kedua kolom terpasang dan benar-benar GENERATED.
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'post_metric'
       AND column_name IN ('emv_min', 'emv_max')
       AND is_generated = 'ALWAYS';
    IF n <> 2 THEN
        RAISE EXCEPTION 'emv_min/emv_max tidak terpasang sebagai GENERATED (ketemu %)', n;
    END IF;

    -- 2. Kolom sumber yang dipakai rumus harus utuh.
    SELECT count(*) INTO n
      FROM information_schema.columns
     WHERE table_schema = 'l2_gold' AND table_name = 'post_metric'
       AND column_name IN ('likes', 'comments', 'likes_hidden');
    IF n <> 3 THEN
        RAISE EXCEPTION 'Kolom sumber EMV tinggal % dari 3', n;
    END IF;

    -- 3. Nilainya benar untuk baris yang terukur.
    SELECT count(*) INTO n_salah_min
      FROM l2_gold.post_metric
     WHERE emv_min IS NOT NULL
       AND emv_min <> (COALESCE(likes, 0) + COALESCE(comments, 0)) * 500;
    SELECT count(*) INTO n_salah_max
      FROM l2_gold.post_metric
     WHERE emv_max IS NOT NULL
       AND emv_max <> (COALESCE(likes, 0) + COALESCE(comments, 0)) * 2000;
    IF n_salah_min <> 0 OR n_salah_max <> 0 THEN
        RAISE EXCEPTION 'EMV menyimpang: % baris min, % baris max',
              n_salah_min, n_salah_max;
    END IF;

    -- 4. Baris likes_hidden / likes<0 WAJIB NULL, satu pun tidak boleh terisi.
    SELECT count(*) INTO n_hidden
      FROM l2_gold.post_metric WHERE likes_hidden IS TRUE OR likes < 0;
    SELECT count(*) INTO n_hidden_isi
      FROM l2_gold.post_metric
     WHERE (likes_hidden IS TRUE OR likes < 0)
       AND (emv_min IS NOT NULL OR emv_max IS NOT NULL);
    IF n_hidden_isi <> 0 THEN
        RAISE EXCEPTION '% baris likes_hidden justru punya EMV', n_hidden_isi;
    END IF;

    -- 5. Tidak ada EMV negatif.
    SELECT count(*) INTO n
      FROM l2_gold.post_metric WHERE emv_min < 0 OR emv_max < 0;
    IF n <> 0 THEN
        RAISE EXCEPTION '% baris EMV negatif', n;
    END IF;

    RAISE NOTICE 'OK: emv_min/emv_max terpasang. % baris tak terukur (likes_hidden) -> NULL.',
          n_hidden;
END $verifikasi$;

COMMIT;
