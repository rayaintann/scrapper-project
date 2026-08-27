"""Feature assets — analisis per POST (Fase 1c).

Dua asset, satu per tabel:
    ig_post_analysis  -> feature.ig_post_analysis
    tt_post_analysis  -> feature.tt_post_analysis

Bedanya dengan Fase 1a: grain-nya PER KONTEN, bukan per akun.
    feature.ig_post_analysis   UNIQUE (social_account_id, media_id)
    feature.tt_post_analysis   UNIQUE (social_account_id, video_id)
keduanya dari `uq_{ig,tt}_post_analysis` (migration 016).

Sumbernya hanya `l1_silver.unified_post`. `unified_profile` TIDAK dibutuhkan:
`engagement_rate` di sini diteruskan apa adanya dari `unified_post` — kolom itu
sudah dihitung terhadap followers oleh `sp_build_unified_post()`, jadi menghitung
ulang di sini hanya akan membuka peluang dua angka yang berbeda untuk hal sama.

Pemetaan `content_id` -> kolom target:
    unified_post.content_id -> ig_post_analysis.media_id
    unified_post.content_id -> tt_post_analysis.video_id

============================================================================
KEPUTUSAN DESAIN
============================================================================

1. SEMUA POST DAPAT BARIS; YANG DISARING HANYA KOLOM ENGAGEMENT-NYA.
   Post ber-`likes_hidden` atau `is_collaboration` tetap ditulis sebagai baris.
   Post-nya memang ada di feed akun, dan `posted_at`, `media_type`,
   `is_sponsored`, `top_hashtags` adalah fakta yang benar tentang post itu
   terlepas dari layak-tidaknya ia dijadikan sampel engagement.

   Yang dikosongkan untuk post semacam itu hanya dua kolom turunan engagement:
   `engagement_rate` dan `rank` (lihat butir 2 dan 3). Jadi aturan sampel yang
   sama dengan Fase 1a tetap berlaku, hanya diterapkan per kolom, bukan dengan
   membuang barisnya.

   Instagram: 130 baris, 82 di antaranya berhak atas kolom engagement.
   TikTok   :  91 baris,  91 berhak (tidak ada yang tersaring).

2. engagement_rate HANYA UNTUK POST YANG LOLOS SAMPEL.
   Post kolaborasi punya `engagement_rate` terisi di `unified_post`, tapi
   sebagian like/comment-nya datang dari audiens akun lain sementara
   penyebutnya followers akun ini — persis distorsi yang mau dihilangkan
   aturan `is_collaboration`. Diteruskan hanya kalau `lolos`, selain itu NULL.

   Kolom targetnya `numeric(9,4)` di kedua tabel (migration 017 melebarkan
   milik Instagram dari numeric(5,2); migration 018 membuat milik TikTok
   langsung dengan tipe itu), sama-sama berskala 4 seperti sumbernya, jadi
   `round(...,4)` tidak membuang apa pun — nol nilai berubah di kedua
   platform. Sebelum 017, pembulatan ke 2 desimal mengubah 114 dari 115 nilai
   Instagram dan menghancurkan 7 di antaranya menjadi 0,00.

   Clamp `LEAST(..., 99999.9999)` dipasang di dalam CASE yang sudah memastikan
   nilainya bukan NULL — `LEAST()` MENGABAIKAN argumen NULL, jadi
   `LEAST(NULL, 99999.9999)` bernilai 99999,9999, bukan NULL. Nilai tertinggi
   sekarang 11,14 (IG) dan 263,60 (TT), jadi clamp-nya tidak pernah aktif; ia
   ada supaya nilai ekstrem tidak menggagalkan insert, bukan untuk mengoreksi
   data.

3. rank = PERINGKAT ER DALAM AKUN, HANYA DI ANTARA POST YANG LOLOS.
   `row_number()` per `social_account_id`, urut `engagement_rate` menurun.
   Post yang tidak lolos sampel atau tidak punya ER mendapat `rank` NULL.

   Window-nya di-PARTITION juga oleh flag kelayakan, bukan dibungkus CASE di
   atas satu window utuh. Kalau hanya dibungkus CASE, `row_number()` tetap
   menghitung baris yang tidak layak dan nomornya ikut terpakai, sehingga
   peringkat yang tersisa berlubang (1, 3, 6, ...). Dengan ikut mem-partisi,
   kelompok yang layak dinomori rapat 1..N dan kelompok yang tidak dibuang.

   Pengurutan diberi pemecah seri `posted_at DESC, content_id` supaya
   peringkat dua post ber-ER identik tidak berubah-ubah tiap rerun.

4. KOLOM BLOCKED TIDAK DITULIS SAMA SEKALI.
   Tidak disebut di daftar INSERT, jadi tetap NULL. Tidak ditebak.
     ig: reach                    (unified_post.reach 0/130 — actor tidak
                                   menyediakannya, hanya Insights API)
         avg_watch_time_seconds,
         click_through_rate       (Insights API)
         content_category,
         category_percentage,
         sentiment_breakdown,
         ai_recommendation        (butuh klasifikasi/NLP, belum ada)
     tt: avg_watch_time_seconds,
         completion_rate,
         traffic_source           (TikTok Analytics API)
         top_sound                (musicMeta ada di L0 tapi belum diteruskan
                                   ke unified_post — bisa dibuka begitu
                                   harmonisasi meneruskannya)
         content_category,
         sentiment_breakdown,
         ai_recommendation        (butuh klasifikasi/NLP, belum ada)

5. top_hashtags DIISI SEADANYA, TIDAK DIPAKSA.
   `unified_post.hashtags` bertipe `text[]`, targetnya `jsonb`, jadi dikonversi
   dengan `to_jsonb()`. Yang array-nya NULL atau kosong ditulis NULL, BUKAN
   `[]` — supaya "post ini tidak pakai hashtag" tidak tertukar dengan
   "hashtag post ini belum ter-scrape". Saat ini hanya 39/130 (IG) dan 39/91
   (TT) post yang punya hashtag.

6. KEDUA TABEL KINI SEJAJAR, KECUALI `reach`.
   Dulu `tt_post_analysis` tidak punya `posted_at`, `media_type`,
   `engagement_rate`, maupun `reach`. Migration 018 menambahkan ketiga yang
   pertama karena semuanya memang tersedia di `unified_post` — 91/91 untuk
   posted_at dan media_type, 90/91 untuk engagement_rate.

   `reach` sengaja TIDAK ditambahkan: `unified_post.reach` terisi 0 dari 221
   baris karena tidak satu pun actor menyediakannya. Membuat kolomnya hanya
   akan menambah satu kolom kosong permanen dan membuat skema terlihat lebih
   mampu daripada kenyataannya.

7. UPSERT, BUKAN TRUNCATE.
   `ON CONFLICT (social_account_id, media_id/video_id) DO UPDATE`, penugasan
   LANGSUNG (`= EXCLUDED.x`) untuk kolom turunan supaya hasil hitung NULL
   menimpa nilai lama — kalau di-COALESCE, ER dan rank yang sudah tidak berlaku
   akan bertahan selamanya. Sama seperti Fase 1a.

   Baris sumber di-saring `social_account_id IS NOT NULL AND content_id IS NOT
   NULL`: kedua kolom kunci di tabel target nullable, dan NULL tidak pernah
   dianggap bentrok oleh ON CONFLICT sehingga baris seperti itu akan
   menggandakan diri tiap rerun. Saat ini tidak ada yang NULL; saringannya
   dipasang supaya tetap begitu.
"""

from __future__ import annotations

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

GROUP = "feature"
_POST = AssetKey("unified_post")


# ---------------------------------------------------------------------------
# CTE bersama: seluruh post satu platform + flag sampel + peringkat ER
# ---------------------------------------------------------------------------
def _cte_dasar(platform_key: str) -> str:
    return f"""
    WITH post AS (
        SELECT u.social_account_id,
               u.content_id,
               u.posted_at,
               u.media_type,
               u.is_sponsored,
               u.hashtags,
               u.engagement_rate,
               -- dua aturan sampel, sudah berupa kolom di unified_post
               (u.likes_hidden IS NOT TRUE AND u.is_collaboration IS NOT TRUE) AS lolos
        FROM l1_silver.unified_post u
        JOIN public.platforms pl
          ON pl.id = u.platform_id AND pl.key = '{platform_key}'
        WHERE u.social_account_id IS NOT NULL
          AND u.content_id IS NOT NULL
    ),
    layak AS (
        SELECT p.*,
               (p.lolos AND p.engagement_rate IS NOT NULL) AS bisa_dirank
        FROM post p
    ),
    berperingkat AS (
        SELECT l.*,
               -- flag ikut mem-partisi supaya nomornya rapat 1..N;
               -- baris yang tidak layak dinomori terpisah lalu dibuang CASE
               CASE WHEN l.bisa_dirank THEN row_number() OVER (
                        PARTITION BY l.social_account_id, l.bisa_dirank
                        ORDER BY l.engagement_rate DESC,
                                 l.posted_at DESC,
                                 l.content_id
                    ) END AS peringkat
        FROM layak l
    )"""


# Dipakai dua-duanya: NULL kalau tidak lolos sampel, selain itu ER dibulatkan
# ke 4 desimal dan di-clamp. CASE-nya sudah menjamin argumen LEAST bukan NULL.
# Skala 4 dan plafon 99999.9999 menyamai kolom numeric(9,4) di kedua tabel
# (migration 017 untuk Instagram, 018 untuk TikTok).
_ER = """CASE WHEN b.lolos AND b.engagement_rate IS NOT NULL
                THEN LEAST(round(b.engagement_rate, 4), 99999.9999) END"""

# text[] -> jsonb; array kosong/NULL ditulis NULL, bukan '[]'
_HASHTAGS = """CASE WHEN b.hashtags IS NULL OR cardinality(b.hashtags) = 0
                    THEN NULL ELSE to_jsonb(b.hashtags) END"""


# --- Instagram --------------------------------------------------------------
SQL_IG = _cte_dasar("instagram") + f"""
    INSERT INTO feature.ig_post_analysis (
        social_account_id, media_id, posted_at, media_type, is_sponsored,
        top_hashtags, engagement_rate, rank, created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): reach, avg_watch_time_seconds,
        -- click_through_rate, content_category, category_percentage,
        -- sentiment_breakdown, ai_recommendation
    )
    SELECT b.social_account_id, b.content_id, b.posted_at, b.media_type,
           b.is_sponsored, {_HASHTAGS}, {_ER}, b.peringkat, now(), now()
    FROM berperingkat b
    ON CONFLICT (social_account_id, media_id) DO UPDATE SET
        posted_at       = EXCLUDED.posted_at,
        media_type      = EXCLUDED.media_type,
        is_sponsored    = EXCLUDED.is_sponsored,
        top_hashtags    = EXCLUDED.top_hashtags,
        engagement_rate = EXCLUDED.engagement_rate,
        rank            = EXCLUDED.rank,
        updated_at      = now()
"""

# --- TikTok -----------------------------------------------------------------
# Sejak migration 018 tabelnya punya posted_at, media_type, dan engagement_rate
# seperti padanan Instagram-nya, jadi daftar kolomnya kini sejajar. Yang tetap
# tidak ada hanya `reach` — sumbernya 0/221, sengaja tidak dibuatkan kolom.
SQL_TT = _cte_dasar("tiktok") + f"""
    INSERT INTO feature.tt_post_analysis (
        social_account_id, video_id, posted_at, media_type, is_sponsored,
        top_hashtags, engagement_rate, rank, created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): top_sound, avg_watch_time_seconds,
        -- completion_rate, traffic_source, content_category,
        -- sentiment_breakdown, ai_recommendation
    )
    SELECT b.social_account_id, b.content_id, b.posted_at, b.media_type,
           b.is_sponsored, {_HASHTAGS}, {_ER}, b.peringkat, now(), now()
    FROM berperingkat b
    ON CONFLICT (social_account_id, video_id) DO UPDATE SET
        posted_at       = EXCLUDED.posted_at,
        media_type      = EXCLUDED.media_type,
        is_sponsored    = EXCLUDED.is_sponsored,
        top_hashtags    = EXCLUDED.top_hashtags,
        engagement_rate = EXCLUDED.engagement_rate,
        rank            = EXCLUDED.rank,
        updated_at      = now()
"""


# --- Statistik untuk metadata Dagster ---------------------------------------
def _sql_stats(platform_key: str) -> str:
    return _cte_dasar(platform_key) + """
    SELECT count(DISTINCT social_account_id)                  AS akun,
           count(*)                                           AS post_total,
           count(*) FILTER (WHERE lolos)                      AS post_lolos_sampel,
           count(*) FILTER (WHERE NOT lolos)                  AS post_tersaring,
           count(*) FILTER (WHERE peringkat IS NOT NULL)      AS post_dapat_rank,
           count(*) FILTER (WHERE hashtags IS NOT NULL
                              AND cardinality(hashtags) > 0)  AS post_punya_hashtag
    FROM berperingkat
    """


def _jalankan(postgres: PostgresResource, platform_key: str, sql_upsert: str,
              tabel: str, blocked: str) -> Output:
    """Hitung statistik, jalankan UPSERT, lalu laporkan metadata.

    Sumber kosong TIDAK dianggap gagal: asset selesai dengan 0 baris dan
    metadata yang menjelaskan kenapa — sama seperti asset engagement.
    """
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_sql_stats(platform_key))
            (akun, post_total, post_lolos, post_tersaring,
             post_rank, post_hashtag) = cur.fetchone()

            if post_total == 0:
                conn.rollback()
                return Output(
                    0,
                    metadata={
                        "tabel": tabel,
                        "baris_ditulis": 0,
                        "catatan": MetadataValue.text(
                            f"Tidak ada post {platform_key} di "
                            "l1_silver.unified_post — tidak ada yang bisa "
                            "dianalisis. Bukan kegagalan."
                        ),
                    },
                )

            cur.execute(sql_upsert)
            ditulis = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    return Output(
        ditulis,
        metadata={
            "tabel": tabel,
            "baris_ditulis": ditulis,
            "akun": akun,
            "post_total": post_total,
            "post_lolos_sampel": post_lolos,
            "post_tersaring_aturan_A_B": post_tersaring,
            "post_dapat_rank": post_rank,
            "post_punya_hashtag": post_hashtag,
            "kolom_sengaja_null": MetadataValue.text(blocked),
        },
    )


_BLOCKED_IG = (
    "reach, avg_watch_time_seconds, click_through_rate (butuh Instagram "
    "Insights API); content_category, category_percentage, "
    "sentiment_breakdown, ai_recommendation (butuh klasifikasi/NLP)."
)
_BLOCKED_TT = (
    "avg_watch_time_seconds, completion_rate, traffic_source (butuh TikTok "
    "Analytics API); top_sound (musicMeta belum diteruskan ke unified_post); "
    "content_category, sentiment_breakdown, ai_recommendation (butuh "
    "klasifikasi/NLP)."
)


@asset(
    name="ig_post_analysis",
    group_name=GROUP,
    deps=[_POST],
    kinds={"postgres"},
    description=(
        "feature.ig_post_analysis — satu baris per post Instagram "
        "(social_account_id, media_id). engagement_rate diteruskan dari "
        "unified_post dan rank dihitung hanya untuk post yang lolos aturan "
        "sampel; post ber-likes_hidden atau kolaborasi tetap dapat baris "
        "dengan kedua kolom itu NULL. reach dan seluruh metrik Insights/NLP "
        "sengaja dibiarkan NULL."
    ),
)
def ig_post_analysis(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "instagram", SQL_IG,
                     "feature.ig_post_analysis", _BLOCKED_IG)


@asset(
    name="tt_post_analysis",
    group_name=GROUP,
    deps=[_POST],
    kinds={"postgres"},
    description=(
        "feature.tt_post_analysis — satu baris per video TikTok "
        "(social_account_id, video_id). Sejak migration 018 kolomnya sejajar "
        "dengan padanan Instagram: posted_at, media_type, is_sponsored, "
        "top_hashtags, engagement_rate, dan rank semuanya diisi. reach tidak "
        "dibuatkan kolom karena sumbernya 0/221; top_sound dan metrik "
        "Analytics/NLP sengaja dibiarkan NULL."
    ),
)
def tt_post_analysis(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "tiktok", SQL_TT,
                     "feature.tt_post_analysis", _BLOCKED_TT)


feature_post_assets = [ig_post_analysis, tt_post_analysis]
