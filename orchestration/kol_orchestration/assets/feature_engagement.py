"""Feature assets — engagement per akun (Fase 1).

Dua asset, satu per tabel:
    ig_engagement_analysis  -> feature.ig_engagement_analysis
    tt_engagement_analysis  -> feature.tt_engagement_analysis

Keduanya bergrain PER AKUN (`social_account_id`) dan membaca sumber yang sama:
`l1_silver.unified_post` untuk metriknya, `l1_silver.unified_profile` untuk
`followers_count` sebagai penyebut engagement rate.

============================================================================
SAMPEL: dua aturan yang sudah disepakati
============================================================================

    WHERE likes_hidden IS NOT TRUE AND is_collaboration IS NOT TRUE

`likes_hidden`  — Instagram memakai `likes = -1` sebagai sentinel "jumlah like
                  disembunyikan", bukan angka nol. Post-nya dikeluarkan dari
                  sampel, bukan dinolkan.
`is_collaboration` — pemilik asli post berbeda dari akun yang di-scrape, jadi
                  engagement-nya sebagian milik akun lain.

Keduanya sudah berupa KOLOM di `unified_post` (diisi migration 015 dan
`sp_build_unified_post()`), jadi asset ini cukup memfilter — tidak perlu
menurunkan ulang aturannya. Itu sebabnya aturannya dijadikan kolom: satu
definisi, dipakai semua konsumen.

Dampak pada data saat ini: Instagram 82 dari 130 post lolos, TikTok 91 dari 91.

============================================================================
KEPUTUSAN DESAIN
============================================================================

1. SATU SAMPEL UNTUK SEMUA ANGKA DALAM SATU BARIS.
   `posts_analyzed_count`, seluruh `total_*`, dan `engagement_rate` dihitung
   dari sampel yang sama, supaya angka dalam satu baris bisa direkonsiliasi.

2. AKUN TANPA SAMPEL TETAP DAPAT BARIS.
   Agregasi memakai `FILTER (WHERE lolos)` di atas SEMUA post akun, bukan
   `WHERE lolos` di klausa FROM. Akun yang seluruh post-nya terbuang tetap
   muncul dengan `posts_analyzed_count = 0` dan metrik NULL — supaya bedanya
   "sudah dianalisis, hasilnya tidak diketahui" dengan "belum pernah
   dianalisis" tetap terlihat.

3. KOLOM BLOCKED TIDAK DITULIS SAMA SEKALI.
   Tidak disebut di daftar INSERT, jadi tetap NULL. Tidak ditebak, tidak
   dinolkan. Yang dibiarkan NULL:
     ig: total_shares, total_saves  (unified_post.shares/saved 0/130 — actor
         Instagram tidak menyediakannya)
         reel_shares, story_replies, story_exits_rate  (Insights API)
         engagement_trend  (sampel terlalu jarang: 10 post/akun tersebar
                            rata-rata 297 hari)
     tt: engagement_trend  (alasan sama)

4. ER: NULL, BUKAN 0, KALAU TIDAK BISA DIHITUNG.
   Sampel kosong atau followers tidak diketahui -> NULL.
   Kolomnya `numeric(5,2)` (maks 999,99) sehingga hasilnya perlu di-clamp,
   TAPI `LEAST()` MENGABAIKAN argumen NULL — `LEAST(NULL, 999.99)` = 999.99.
   Karena itu clamp dibungkus `CASE WHEN ... IS NULL THEN NULL ELSE LEAST(...)`.
   Tanpa penjaga itu, akun tanpa sampel akan tercatat ber-engagement 999,99%.

5. UPSERT, BUKAN TRUNCATE.
   `ON CONFLICT (social_account_id) DO UPDATE` memakai constraint
   `uq_{ig,tt}_engagement_analysis` (migration 016). Rerun aman dan tidak
   menghapus akun yang kebetulan tidak ikut batch.
   Kolom turunan memakai penugasan LANGSUNG (`= EXCLUDED.x`), bukan
   `COALESCE(EXCLUDED.x, existing.x)`: hasil hitung NULL harus menimpa nilai
   lama, kalau tidak metriknya jadi basi.

6. AGREGASI DI SQL, BUKAN DI PYTHON.
   Data tidak ditarik ke Python lalu dikirim balik. Satu statement
   INSERT ... SELECT mengerjakan semuanya di server.
"""

from __future__ import annotations

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

GROUP = "feature"
_POST = AssetKey("unified_post")
_PROFILE = AssetKey("unified_profile")


# ---------------------------------------------------------------------------
# CTE bersama: followers per akun + seluruh post platform tsb beserta flag lolos
# ---------------------------------------------------------------------------
def _cte_dasar(platform_key: str) -> str:
    return f"""
    WITH post AS (
        SELECT u.social_account_id, u.likes, u.comments, u.views, u.shares,
               u.saved, u.media_type, u.posted_at,
               -- followers PADA TANGGAL POST, bukan snapshot terbaru. Pola yang
               -- sama dipakai l2_gold.kol_metric_daily.followers_at_post_date dan
               -- l1_silver.sp_build_unified_post() (migration 024). NULL kalau
               -- post lebih tua dari snapshot profil pertama -- tidak ditebak.
               foll.followers_count,
               -- dua aturan sampel, sudah berupa kolom di unified_post
               (u.likes_hidden IS NOT TRUE AND u.is_collaboration IS NOT TRUE) AS lolos
        FROM l1_silver.unified_post u
        JOIN public.platforms pl
          ON pl.id = u.platform_id AND pl.key = '{platform_key}'
        LEFT JOIN LATERAL (
            SELECT pr.followers_count
            FROM l1_silver.unified_profile pr
            WHERE pr.social_account_id = u.social_account_id
              AND pr.date <= (u.posted_at AT TIME ZONE 'Asia/Jakarta')::date
            ORDER BY pr.date DESC
            LIMIT 1
        ) foll ON true
    )"""


# Engagement sesuai DEFINISI BISNIS: Like + Comment + Share/Repost/Quote.
# Save/Collect TIDAK termasuk. COALESCE per komponen wajib: tanpa itu satu
# komponen NULL membuang seluruh baris dari agregat -- dan `shares` Instagram
# memang selalu NULL, sehingga seluruh ER Instagram akan lenyap.
_ENG = "COALESCE(likes, 0) + COALESCE(comments, 0) + COALESCE(shares, 0)"

# ER per akun: penyebut ADITIF (jumlah followers-pada-tanggal-post tiap post),
# bukan avg(engagement) / followers-terbaru. Pembilang DISELARASKAN dengan
# penyebut -- hanya post yang followers-nya diketahui yang ikut, di kedua sisi.
# Pola yang sama dipakai kol_metric_monthly.engagement_for_er_sum.
_ER_AKUN = f"""round(
                 sum({_ENG}) FILTER (WHERE lolos AND followers_count IS NOT NULL)::numeric
                 / NULLIF(sum(followers_count)
                          FILTER (WHERE lolos AND followers_count IS NOT NULL), 0)
                 * 100, 2)"""


# --- Instagram --------------------------------------------------------------
SQL_IG = _cte_dasar("instagram") + f""",
    agg AS (
        SELECT social_account_id,
               count(*) FILTER (WHERE lolos)                                AS n_sampel,
               sum(likes)    FILTER (WHERE lolos)                           AS total_likes,
               sum(comments) FILTER (WHERE lolos)                           AS total_comments,
               sum(views)    FILTER (WHERE lolos AND media_type = 'clips')  AS reel_plays,
               {_ER_AKUN}                                               AS er_mentah
        FROM post
        GROUP BY 1
    ),
    format AS (
        SELECT social_account_id,
               jsonb_object_agg(media_type,
                   jsonb_build_object('posts', n, 'avg_engagement', avg_eng)
               ) AS format_performance
        FROM (
            SELECT social_account_id, media_type, count(*) AS n,
                   round(avg({_ENG}), 2) AS avg_eng
            FROM post WHERE lolos AND media_type IS NOT NULL
            GROUP BY 1, 2
        ) x GROUP BY 1
    ),
    heatmap AS (
        SELECT social_account_id,
               jsonb_agg(jsonb_build_object(
                   'dow', dow, 'hour', jam, 'posts', n, 'avg_engagement', avg_eng
               ) ORDER BY dow, jam) AS heat
        FROM (
            -- WIB, mengikuti tampilan UI
            SELECT social_account_id,
                   EXTRACT(DOW  FROM posted_at AT TIME ZONE 'Asia/Jakarta')::int AS dow,
                   EXTRACT(HOUR FROM posted_at AT TIME ZONE 'Asia/Jakarta')::int AS jam,
                   count(*) AS n, round(avg({_ENG}), 2) AS avg_eng
            FROM post WHERE lolos AND posted_at IS NOT NULL
            GROUP BY 1, 2, 3
        ) y GROUP BY 1
    )
    INSERT INTO feature.ig_engagement_analysis (
        social_account_id, analyzed_at, posts_analyzed_count,
        total_likes, total_comments, reel_plays,
        engagement_rate, format_performance, best_posting_time_heatmap,
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): total_shares, total_saves,
        -- reel_shares, story_replies, story_exits_rate, engagement_trend
    )
    SELECT a.social_account_id, now(), a.n_sampel,
           a.total_likes, a.total_comments, a.reel_plays,
           -- LEAST() mengabaikan NULL; penjaga CASE wajib
           CASE WHEN a.er_mentah IS NULL THEN NULL
                ELSE LEAST(a.er_mentah, 999.99) END,
           f.format_performance, h.heat,
           now(), now()
    FROM agg a
    LEFT JOIN format  f USING (social_account_id)
    LEFT JOIN heatmap h USING (social_account_id)
    ON CONFLICT (social_account_id) DO UPDATE SET
        analyzed_at               = EXCLUDED.analyzed_at,
        posts_analyzed_count      = EXCLUDED.posts_analyzed_count,
        total_likes               = EXCLUDED.total_likes,
        total_comments            = EXCLUDED.total_comments,
        reel_plays                = EXCLUDED.reel_plays,
        engagement_rate           = EXCLUDED.engagement_rate,
        format_performance        = EXCLUDED.format_performance,
        best_posting_time_heatmap = EXCLUDED.best_posting_time_heatmap,
        updated_at                = now()
"""

# --- TikTok -----------------------------------------------------------------
# Tabelnya tidak punya analyzed_at, format_performance, maupun reel_plays,
# tapi PUNYA total_views/total_shares/total_saves yang Instagram tidak punya.
SQL_TT = _cte_dasar("tiktok") + f""",
    agg AS (
        SELECT social_account_id,
               count(*) FILTER (WHERE lolos)      AS n_sampel,
               sum(views)    FILTER (WHERE lolos) AS total_views,
               sum(likes)    FILTER (WHERE lolos) AS total_likes,
               sum(comments) FILTER (WHERE lolos) AS total_comments,
               sum(shares)   FILTER (WHERE lolos) AS total_shares,
               sum(saved)    FILTER (WHERE lolos) AS total_saves,
               {_ER_AKUN} AS er_mentah
        FROM post
        GROUP BY 1
    ),
    heatmap AS (
        SELECT social_account_id,
               jsonb_agg(jsonb_build_object(
                   'dow', dow, 'hour', jam, 'posts', n, 'avg_engagement', avg_eng
               ) ORDER BY dow, jam) AS heat
        FROM (
            SELECT social_account_id,
                   EXTRACT(DOW  FROM posted_at AT TIME ZONE 'Asia/Jakarta')::int AS dow,
                   EXTRACT(HOUR FROM posted_at AT TIME ZONE 'Asia/Jakarta')::int AS jam,
                   count(*) AS n, round(avg({_ENG}), 2) AS avg_eng
            FROM post WHERE lolos AND posted_at IS NOT NULL
            GROUP BY 1, 2, 3
        ) y GROUP BY 1
    )
    INSERT INTO feature.tt_engagement_analysis (
        social_account_id, videos_analyzed_count,
        total_views, total_likes, total_comments, total_shares, total_saves,
        engagement_rate, best_posting_time_heatmap,
        created_at, updated_at
        -- SENGAJA tidak disebut (tetap NULL): engagement_trend
    )
    SELECT a.social_account_id, a.n_sampel,
           a.total_views, a.total_likes, a.total_comments,
           a.total_shares, a.total_saves,
           CASE WHEN a.er_mentah IS NULL THEN NULL
                ELSE LEAST(a.er_mentah, 999.99) END,
           h.heat,
           now(), now()
    FROM agg a
    LEFT JOIN heatmap h USING (social_account_id)
    ON CONFLICT (social_account_id) DO UPDATE SET
        videos_analyzed_count     = EXCLUDED.videos_analyzed_count,
        total_views               = EXCLUDED.total_views,
        total_likes               = EXCLUDED.total_likes,
        total_comments            = EXCLUDED.total_comments,
        total_shares              = EXCLUDED.total_shares,
        total_saves               = EXCLUDED.total_saves,
        engagement_rate           = EXCLUDED.engagement_rate,
        best_posting_time_heatmap = EXCLUDED.best_posting_time_heatmap,
        updated_at                = now()
"""


# --- Statistik untuk metadata Dagster ---------------------------------------
def _sql_stats(platform_key: str) -> str:
    return _cte_dasar(platform_key) + """
    SELECT count(DISTINCT social_account_id)                          AS akun,
           count(*)                                                   AS post_total,
           count(*) FILTER (WHERE lolos)                              AS post_sampel,
           count(*) FILTER (WHERE NOT lolos)                          AS post_dibuang,
           count(DISTINCT social_account_id) FILTER (WHERE followers_count IS NULL
                                                       OR followers_count = 0)
                                                                      AS akun_tanpa_followers
    FROM post
    """


def _jalankan(postgres: PostgresResource, platform_key: str, sql_upsert: str,
              tabel: str) -> Output:
    """Hitung statistik, jalankan UPSERT, lalu laporkan metadata.

    Sumber kosong TIDAK dianggap gagal: asset selesai dengan 0 baris dan
    metadata yang menjelaskan kenapa. Merah palsu tiap hari membuat orang
    berhenti memperhatikan dashboard.
    """
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(_sql_stats(platform_key))
            akun, post_total, post_sampel, post_dibuang, akun_tanpa_foll = cur.fetchone()

            if post_total == 0:
                conn.rollback()
                return Output(
                    0,
                    metadata={
                        "tabel": tabel,
                        "baris_ditulis": 0,
                        "catatan": MetadataValue.text(
                            f"Tidak ada post {platform_key} di l1_silver.unified_post — "
                            "tidak ada yang bisa diagregasi. Bukan kegagalan."
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
            "post_masuk_sampel": post_sampel,
            "post_dibuang_aturan_A_B": post_dibuang,
            "akun_tanpa_followers_ER_null": akun_tanpa_foll,
        },
    )


@asset(
    name="ig_engagement_analysis",
    group_name=GROUP,
    deps=[_POST, _PROFILE],
    kinds={"postgres"},
    description=(
        "feature.ig_engagement_analysis — engagement per akun Instagram. "
        "Sampel mengecualikan post ber-likes_hidden dan post kolaborasi. "
        "total_shares/total_saves/reel_shares/story_*/engagement_trend sengaja "
        "dibiarkan NULL (sumbernya belum ada)."
    ),
)
def ig_engagement_analysis(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "instagram", SQL_IG, "feature.ig_engagement_analysis")


@asset(
    name="tt_engagement_analysis",
    group_name=GROUP,
    deps=[_POST, _PROFILE],
    kinds={"postgres"},
    description=(
        "feature.tt_engagement_analysis — engagement per akun TikTok. "
        "TikTok menyediakan shares dan saved yang Instagram tidak punya. "
        "engagement_trend sengaja dibiarkan NULL (sampel terlalu jarang)."
    ),
)
def tt_engagement_analysis(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "tiktok", SQL_TT, "feature.tt_engagement_analysis")


feature_engagement_assets = [ig_engagement_analysis, tt_engagement_analysis]
