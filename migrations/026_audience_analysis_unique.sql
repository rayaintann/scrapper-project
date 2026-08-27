-- 026_audience_analysis_unique.sql
--
-- Menambahkan UNIQUE (social_account_id) pada feature.ig_audience_analysis dan
-- feature.tt_audience_analysis.
--
-- Hanya CONSTRAINT yang ditambahkan. Tidak ada kolom baru, tidak ada perubahan
-- tipe, tidak ada DROP, tidak ada perubahan data. Tabel lain tidak disentuh.
--
-- ============================================================================
-- KENAPA -- TANPA INI, PIPELINE AUDIENCE TIDAK MUNGKIN IDEMPOTEN
-- ============================================================================
--
-- Kedua tabel sekarang hanya punya PRIMARY KEY (id) yang berupa
-- gen_random_uuid(). Artinya tidak ada yang mencegah satu akun punya dua baris
-- analisis. Tanpa UNIQUE, builder-nya cuma punya dua pilihan yang dua-duanya
-- buruk:
--
--   INSERT biasa      -> tiap rerun menambah 23 baris lagi, menumpuk selamanya
--   DELETE lalu INSERT -> riwayat hilang, dan kegagalan di tengah meninggalkan
--                         tabel kosong
--
-- Dengan UNIQUE, builder bisa memakai `ON CONFLICT ... DO UPDATE` dengan
-- penjaga `IS DISTINCT FROM` -- pola yang sama dipakai kol_metric_daily,
-- kol_metric_monthly, dan kol_profile_card. Rerun jadi benar-benar idempoten.
--
-- ============================================================================
-- KENAPA GRAIN-NYA (social_account_id) SAJA
-- ============================================================================
--
-- Mengikuti tabel saudaranya yang SUDAH terisi dan sudah punya constraint:
--
--     feature.ig_engagement_analysis   UNIQUE (social_account_id)
--     feature.tt_engagement_analysis   UNIQUE (social_account_id)
--
-- Bukan (social_account_id, date): tabel `*_audience_analysis` tidak punya
-- kolom tanggal sama sekali. Bentuknya "kondisi terkini per akun", bukan deret
-- waktu -- sama seperti `*_engagement_analysis`. Menambah dimensi tanggal
-- berarti menambah kolom, dan itu perubahan schema yang lebih besar dari yang
-- dibutuhkan sekarang.
--
-- `platform` juga tidak ikut: tabelnya sudah terpisah per platform (ig_ / tt_),
-- jadi platform sudah tersirat dari nama tabel.
--
-- ============================================================================
-- AMAN
-- ============================================================================
--
--   * Kedua tabel sekarang 0 baris, jadi constraint tidak mungkin ditolak
--     karena data yang sudah ada.
--   * Penjaga di bawah tetap memeriksa duplikat lebih dulu, supaya migrasi ini
--     gagal dengan pesan jelas kalau dijalankan pada database yang tabelnya
--     sudah terisi duplikat -- bukan gagal dengan error constraint mentah.
--   * Aman diulang: keluar diam-diam kalau constraint sudah ada.

BEGIN;

DO $penjaga$
DECLARE
    t            text;
    n_dup        bigint;
    n_baris      bigint;
    sudah_ada    boolean;
    nama_c       text;
BEGIN
    FOREACH t IN ARRAY ARRAY['ig_audience_analysis', 'tt_audience_analysis'] LOOP
        nama_c := 'uq_' || t;

        SELECT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema = 'feature' AND table_name = t
              AND constraint_name = nama_c AND constraint_type = 'UNIQUE'
        ) INTO sudah_ada;

        IF sudah_ada THEN
            RAISE NOTICE 'feature.%: % sudah ada -- dilewati.', t, nama_c;
            CONTINUE;
        END IF;

        -- Tolak kalau ada duplikat, dengan pesan yang bisa ditindaklanjuti.
        EXECUTE format(
            'SELECT count(*) FROM (SELECT social_account_id FROM feature.%I '
            'GROUP BY social_account_id HAVING count(*) > 1) d', t)
        INTO n_dup;

        IF n_dup > 0 THEN
            RAISE EXCEPTION 'feature.% punya % akun berduplikat -- '
                            'bersihkan dulu sebelum menambah UNIQUE.', t, n_dup;
        END IF;

        EXECUTE format('SELECT count(*) FROM feature.%I', t) INTO n_baris;

        EXECUTE format(
            'ALTER TABLE feature.%I ADD CONSTRAINT %I UNIQUE (social_account_id)',
            t, nama_c);

        RAISE NOTICE 'feature.%: UNIQUE (social_account_id) ditambahkan (% baris).',
                     t, n_baris;
    END LOOP;
END $penjaga$;

-- Verifikasi akhir: kalau salah satu constraint tidak terpasang, batalkan.
DO $verifikasi$
DECLARE
    n int;
BEGIN
    SELECT count(*) INTO n
    FROM information_schema.table_constraints
    WHERE table_schema = 'feature'
      AND table_name IN ('ig_audience_analysis', 'tt_audience_analysis')
      AND constraint_type = 'UNIQUE';

    IF n <> 2 THEN
        RAISE EXCEPTION 'Verifikasi gagal: ditemukan % constraint UNIQUE, diharapkan 2.', n;
    END IF;

    RAISE NOTICE 'Verifikasi lolos: 2 constraint UNIQUE terpasang.';
END $verifikasi$;

COMMIT;
