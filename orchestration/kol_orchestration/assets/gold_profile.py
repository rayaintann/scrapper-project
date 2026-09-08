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
"""

from __future__ import annotations

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

GROUP = "l2_gold"
_PROFILE = AssetKey("unified_profile")


# ---------------------------------------------------------------------------
# CTE bersama untuk statistik dan upsert
# ---------------------------------------------------------------------------
_CTE = """
    WITH badge AS (
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
               p.followers_growth
        FROM l1_silver.unified_profile p
        JOIN public.platforms pl ON pl.id = p.platform_id
        LEFT JOIN badge b
               ON b.social_account_id = p.social_account_id
              AND b.platform = pl.key
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
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): rate_card, rate_card_currency,
        -- rate_card_min_fee, rate_card_max_fee, rate_card_post_types
    )
    SELECT t.social_account_id, t.platform,
           t.username, t.display_name, t.avatar_url, t.profile_url,
           t.bio, t.website, t.is_verified, t.is_private,
           t.followers_count, t.following_count, t.media_count, t.tier,
           t.profile_snapshot_date, t.followers_growth,
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
       OR kol_profile_card.is_private      IS DISTINCT FROM EXCLUDED.is_private
       OR kol_profile_card.followers_count IS DISTINCT FROM EXCLUDED.followers_count
       OR kol_profile_card.following_count IS DISTINCT FROM EXCLUDED.following_count
       OR kol_profile_card.media_count     IS DISTINCT FROM EXCLUDED.media_count
       OR kol_profile_card.tier            IS DISTINCT FROM EXCLUDED.tier
       OR kol_profile_card.profile_snapshot_date
                                           IS DISTINCT FROM EXCLUDED.profile_snapshot_date
       OR kol_profile_card.followers_growth
                                           IS DISTINCT FROM EXCLUDED.followers_growth
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
           max(profile_snapshot_date)                            AS snapshot_terbaru
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
             snapshot_tertua, snapshot_terbaru) = cur.fetchone()

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
    deps=[_PROFILE],
    kinds={"postgres"},
    description=(
        "l2_gold.kol_profile_card — kartu profil KOL, grain "
        "(social_account_id, platform), satu kartu per akun tanpa dimensi "
        "tanggal. Sumber l1_silver.unified_profile snapshot TERBARU per akun; "
        "profile_snapshot_date mencatat snapshot mana yang dipakai. "
        "followers_growth dibawa apa adanya dari snapshot itu dan satuannya "
        "PERSEN, bukan jumlah orang — ini rumah account-grain untuk growth, "
        "yang tidak bisa diisi di kol_metric_daily karena grain-nya digerakkan "
        "posted_at. Kolom rate_card_* sengaja dibiarkan NULL."
    ),
)
def kol_profile_card(postgres: PostgresResource) -> Output:
    return _jalankan(postgres)


gold_profile_assets = [kol_profile_card]
