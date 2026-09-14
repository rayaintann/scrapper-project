"""Akses Postgres: ambil username Instagram dan tulis balik hasil scrape."""

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence

import psycopg2
import psycopg2.extras

import campaign_cost_metrics as ccm
import kol_attribute_taxonomy as kat
import what_matters_scoring as wm
from config import PostgresConfig
from transform import normalize_username

logger = logging.getLogger(__name__)

# Versi SQL dari transform.normalize_username: buang query string, path, dan '@'.
_SQL_NORMALIZED_USERNAME = (
    "ltrim(lower(btrim(split_part(split_part(k.username, '?', 1), '/', 1))), '@')"
)

# Urutan pengambilan kandidat. Dipilih lewat --order di pipeline.py.
ORDER_CLAUSES = {
    # KOL terbesar dulu, paling berguna untuk uji coba awal.
    "followers": "k.followers_count DESC NULLS LAST, k.username ASC",
    # Yang paling lama tidak di-refresh dulu.
    "stale": "k.last_refreshed_at ASC NULLS FIRST, k.username ASC",
    "username": "k.username ASC",
    "random": "random()",
}


# ===========================================================================
# GROWTH: Growth %, Daily Growth, dan proyeksi 30 hari
# ===========================================================================
# SATU-SATUNYA definisi ketiga angka ini, dan sekarang dipakai DUA konsumen:
#
#   1. jalur baca di file ini (`fetch_growth_metrics`, `_SEARCH_QUERY`);
#   2. `gold_profile.py`, yang meng-IMPOR `SQL_GROWTH_CTE` dari sini untuk
#      mengisi kolom `daily_growth`/`projected_30d` di l2_gold.kol_profile_card.
#
# Awalnya rumus ini hanya hidup di jalur baca, karena kartu L2 memang belum
# punya kolomnya. Migration 037 menambahkan kolom itu -- bukan supaya rumusnya
# disalin ke sana, melainkan supaya UI (Next.js, query Postgres LANGSUNG dan
# tidak bisa memanggil db.py) bisa membacanya tanpa menyalin rumus ke repo lain.
# Karena gold_profile.py mengimpor konstanta ini alih-alih menulis ulang
# SQL-nya, definisinya tetap satu.
#
# YANG TIDAK DIHITUNG ULANG DI SINI
# ---------------------------------
# `growth_pct` DIBAWA APA ADANYA dari `l1_silver.unified_profile.followers_growth`,
# yang diisi `l1_silver.sp_build_unified_profile()`. Rumusnya sengaja tidak
# disalin ke sini -- menyalinnya berarti rumus yang sama hidup di dua tempat,
# dan cepat atau lambat keduanya berbeda. Alasan yang sama dipakai
# gold_profile.py butir 2.
#
# KENAPA `previous` BUKAN SEKADAR lag(followers_count)
# ----------------------------------------------------
# Sanity guard migration 035 me-NULL-kan followers yang tidak masuk akal
# (mis. akun Mega yang scrape-nya mengembalikan 8 follower). Baris seperti itu
# harus DILEWATI: bukan dipakai sebagai pembanding, dan bukan memutus rantai.
# Pola gaps-and-islands di bawah -- count() sebagai penanda pulau, lalu
# first_value() membawa nilai valid terakhir maju -- SAMA PERSIS dengan yang
# dipakai 035 untuk `prev_followers_count`. Dengan begitu `previous_followers`
# di sini identik dengan penyebut yang dipakai L1 saat menghitung
# `followers_growth`; kalau tidak identik, Growth % dan daily growth akan
# bercerita tentang dua pasang snapshot yang berbeda.
#
# GROWTH 30D ADALAH PROYEKSI, DAN `projected_30d` ADALAH SELISIHNYA
# ------------------------------------------------------------------
#     projected_30d           = daily_growth * 30          <- DELTA follower
#     projected_followers_30d = current_followers + projected_30d
#
# Contoh yang jadi acuan:
#     previous = 100, current = 125, jarak 25 hari
#     -> daily_growth            = 25 / 25 = 1 follower/hari
#     -> projected_30d           = 1 * 30 = 30 follower
#     -> projected_followers_30d = 125 + 30 = 155
#
# DEFINISINYA BERUBAH, DAN PERUBAHANNYA DISENGAJA.
# Versi sebelumnya menghitung `previous_followers + daily_growth * 30` = 130,
# yaitu "berapa follower 30 hari setelah snapshot SEBELUMNYA". Keputusan
# terbaru memindahkan titik acuannya ke snapshot SEKARANG dan mengubah arti
# `projected_30d` dari jumlah absolut menjadi selisih. Kolomnya dipakai ulang,
# bukan diduplikasi -- lihat migration 040 untuk komentar kolom yang ikut
# diperbarui.
#
# INI PROYEKSI, BUKAN PERTUMBUHAN 30 HARI YANG TERAMATI.
# Jarak snapshot nyata di data sekarang 10-15 hari, bukan 30. Angka ini
# mengekstrapolasi laju harian yang terukur ke 30 hari; ia TIDAK boleh dibaca
# sebagai "pertumbuhan yang benar-benar terjadi selama 30 hari", dan tidak
# pernah menuntut snapshotnya berjarak tepat 30 hari.
#
# NULL, BUKAN TEBAKAN
# -------------------
# daily_growth dan projected_30d NULL kalau salah satu benar:
#   * belum ada snapshot pembanding   (previous_followers/previous_date NULL)
#   * previous_followers = 0          (Growth % tidak terdefinisi)
#   * current_followers NULL          (di-NULL-kan sanity guard)
#   * days_between <= 0               (tanggal sama atau mundur)
# Tidak ada 0 sebagai pengganti NULL: 0 berarti "tidak tumbuh", NULL berarti
# "belum bisa dihitung". Keduanya jawaban yang berbeda.
# Sumber dibuat parameter SATU-SATUNYA supaya rumus di bawah bisa diuji
# terhadap Postgres sungguhan tanpa menulis apa pun: test memasukkan klausa
# VALUES sebagai `sumber`, produksi memakai tabel L1. Yang diuji dengan begitu
# adalah SQL yang benar-benar dijalankan, bukan tiruannya di Python.
# `sumber` HARUS beralias `p` dan menyediakan kolom social_account_id, date,
# followers_count, followers_growth.
_GROWTH_CTE_TEMPLATE = """
    riwayat AS (
        SELECT p.social_account_id,
               p.date,
               p.followers_count,
               p.followers_growth,
               -- Penanda pulau: naik satu tiap ketemu followers_count non-NULL,
               -- jadi baris NULL mewarisi nomor pulau baris di atasnya.
               count(p.followers_count) OVER (
                   PARTITION BY p.social_account_id ORDER BY p.date
                   ROWS UNBOUNDED PRECEDING) AS pulau
          FROM {sumber}
         WHERE p.social_account_id IS NOT NULL
    ),
    bawa_maju AS (
        -- Nilai dan tanggal valid TERAKHIR, dibawa maju melewati baris NULL.
        SELECT r.social_account_id, r.date, r.followers_count, r.followers_growth,
               first_value(r.followers_count) OVER w AS followers_valid,
               first_value(r.date)            OVER w AS date_valid
          FROM riwayat r
        WINDOW w AS (PARTITION BY r.social_account_id, r.pulau ORDER BY r.date)
    ),
    berpasangan AS (
        SELECT b.social_account_id,
               b.date              AS current_snapshot_date,
               b.followers_count   AS current_followers,
               b.followers_growth  AS growth_pct,
               lag(b.followers_valid) OVER w AS previous_followers,
               lag(b.date_valid)      OVER w AS previous_snapshot_date
          FROM bawa_maju b
        WINDOW w AS (PARTITION BY b.social_account_id ORDER BY b.date)
    ),
    dihitung AS (
        SELECT s.social_account_id,
               s.previous_snapshot_date,
               s.current_snapshot_date,
               s.previous_followers,
               s.current_followers,
               s.growth_pct,
               (s.current_snapshot_date - s.previous_snapshot_date) AS days_between,
               CASE
                   WHEN s.previous_followers IS NULL
                     OR s.previous_followers = 0
                     OR s.current_followers IS NULL
                     OR s.previous_snapshot_date IS NULL
                     OR (s.current_snapshot_date - s.previous_snapshot_date) <= 0
                   THEN NULL
                   ELSE (s.current_followers - s.previous_followers)::numeric
                        / (s.current_snapshot_date - s.previous_snapshot_date)
               END AS daily_growth
          FROM berpasangan s
    ),
    growth AS (
        -- Satu baris per akun: pasangan snapshot TERBARU. Urutan tanggal
        -- menurun dipakai eksplisit supaya hasilnya deterministik antar-run.
        SELECT DISTINCT ON (d.social_account_id)
               d.social_account_id,
               d.previous_snapshot_date,
               d.current_snapshot_date,
               d.previous_followers,
               d.current_followers,
               d.days_between,
               d.growth_pct,
               round(d.daily_growth, 4) AS daily_growth,
               -- DELTA 30 hari, bukan jumlah follower absolut.
               CASE WHEN d.daily_growth IS NULL THEN NULL
                    ELSE round(d.daily_growth * 30)
               END AS projected_30d,
               -- Proyeksi jumlah follower: dari snapshot SEKARANG, bukan dari
               -- snapshot sebelumnya. Diturunkan di sini alih-alih disimpan
               -- sebagai kolom keempat: ia hanya penjumlahan dua nilai yang
               -- sudah ada di baris yang sama, dan menyimpannya menambah
               -- tempat ketiga yang bisa bergeser dari kedua sumbernya.
               CASE WHEN d.daily_growth IS NULL OR d.current_followers IS NULL
                    THEN NULL
                    ELSE d.current_followers + round(d.daily_growth * 30)
               END AS projected_followers_30d
          FROM dihitung d
         ORDER BY d.social_account_id, d.current_snapshot_date DESC
    )"""

#: CTE Growth siap pakai untuk produksi. Dipakai `_GROWTH_QUERY` dan
#: `_SEARCH_QUERY`; test memanggil `_GROWTH_CTE_TEMPLATE.format(...)` sendiri
#: dengan sumber VALUES.
SQL_GROWTH_CTE = _GROWTH_CTE_TEMPLATE.format(sumber="l1_silver.unified_profile p")


@dataclass(frozen=True)
class GrowthMetrics:
    """Growth satu akun pada pasangan snapshot TERBARU miliknya.

    Semua field selain `social_account_id` boleh None, dan None berarti
    "belum bisa dihitung" -- bukan nol.
    """

    social_account_id: str
    previous_snapshot_date: object | None
    current_snapshot_date: object | None
    previous_followers: int | None
    current_followers: int | None
    days_between: int | None
    growth_pct: float | None
    daily_growth: float | None
    projected_30d: int | None
    projected_followers_30d: int | None


_GROWTH_QUERY = "WITH " + SQL_GROWTH_CTE + """
    SELECT g.social_account_id, g.previous_snapshot_date, g.current_snapshot_date,
           g.previous_followers, g.current_followers, g.days_between,
           g.growth_pct, g.daily_growth, g.projected_30d,
           g.projected_followers_30d
      FROM growth g
     WHERE (%(ids)s::uuid[] IS NULL OR g.social_account_id = ANY(%(ids)s::uuid[]))
       AND (NOT %(hanya_terhitung)s OR g.daily_growth IS NOT NULL)
     ORDER BY g.social_account_id
     LIMIT %(limit)s
"""


def fetch_growth_metrics(
    conn,
    social_account_ids: Sequence[str] | None = None,
    hanya_terhitung: bool = False,
    limit: int = 500,
) -> list["GrowthMetrics"]:
    """Growth %, daily growth, dan proyeksi 30 hari per akun.

    `social_account_ids` None berarti seluruh akun. `hanya_terhitung=True`
    membuang akun yang belum punya pasangan snapshot -- berguna untuk sampel,
    tapi JANGAN dipakai menghitung coverage: yang dibuang justru mayoritasnya.
    """
    ids = list(social_account_ids) if social_account_ids else None
    params = {
        "ids": ids,
        "hanya_terhitung": bool(hanya_terhitung),
        "limit": max(1, min(int(limit), 10000)),
    }
    with conn.cursor() as cur:
        cur.execute(_GROWTH_QUERY, params)
        hasil = [
            GrowthMetrics(
                social_account_id=str(r[0]),
                previous_snapshot_date=r[1],
                current_snapshot_date=r[2],
                previous_followers=r[3],
                current_followers=r[4],
                days_between=r[5],
                growth_pct=float(r[6]) if r[6] is not None else None,
                daily_growth=float(r[7]) if r[7] is not None else None,
                projected_30d=int(r[8]) if r[8] is not None else None,
                projected_followers_30d=int(r[9]) if r[9] is not None else None,
            )
            for r in cur.fetchall()
        ]
    logger.info("Growth: %d baris (hanya_terhitung=%s)", len(hasil), hanya_terhitung)
    return hasil


@dataclass(frozen=True)
class DirectoryRow:
    """Satu baris kandidat dari public.kol_directory."""

    id: str
    username: str

    @property
    def normalized(self) -> str:
        return normalize_username(self.username)


def open_connection(
    pg: PostgresConfig, connect_timeout: int = 15
) -> psycopg2.extensions.connection:
    """Koneksi Postgres baru yang harus ditutup pemanggil sendiri.

    Keepalive TCP diaktifkan karena run scraping bisa berjam-jam: tanpa itu
    koneksi yang menganggur lama diputus diam-diam oleh NAT/firewall, dan
    kegagalannya baru ketahuan saat INSERT terakhir — persis setelah semua
    profil selesai dibayar.
    """
    # Tanpa connect_timeout, host yang tidak merespons membuat proses menggantung
    # tanpa batas alih-alih gagal dengan pesan yang jelas.
    return psycopg2.connect(
        connect_timeout=connect_timeout,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        **pg.as_connect_kwargs(),
    )


@contextmanager
def connect(pg: PostgresConfig, connect_timeout: int = 15) -> Iterator[psycopg2.extensions.connection]:
    conn = open_connection(pg, connect_timeout=connect_timeout)
    try:
        yield conn
    finally:
        conn.close()


def fetch_instagram_usernames(
    conn,
    limit: int = 1000,
    order: str = "followers",
    only_unscraped: bool = False,
) -> list[DirectoryRow]:
    """Pintasan untuk fetch_usernames(platform_key='instagram')."""
    return fetch_usernames(
        conn, "instagram", limit=limit, order=order, only_unscraped=only_unscraped
    )


def fetch_usernames(
    conn,
    platform_key: str,
    limit: int = 1000,
    order: str = "followers",
    only_unscraped: bool = False,
) -> list[DirectoryRow]:
    """Ambil maksimal `limit` username satu platform dari public.kol_directory.

    Platform difilter lewat join ke public.platforms (key = 'instagram' atau
    'tiktok'), bukan dengan UUID hardcode, supaya tetap benar kalau data platform
    diseed ulang di environment lain.
    """
    if order not in ORDER_CLAUSES:
        raise ValueError(
            f"order '{order}' tidak dikenal, pilih salah satu dari {sorted(ORDER_CLAUSES)}"
        )

    unscraped_filter = (
        "AND (k.scrape_status IS NULL OR k.scrape_status <> 'success')"
        if only_unscraped
        else ""
    )
    query = f"""
        SELECT k.id, k.username
        FROM public.kol_directory k
        JOIN public.platforms p ON p.id = k.platform_id
        WHERE p.key = %s
          AND k.username IS NOT NULL
          AND btrim(k.username) <> ''
          {unscraped_filter}
        ORDER BY {ORDER_CLAUSES[order]}
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (platform_key, limit))
        rows = [DirectoryRow(id=str(r[0]), username=r[1]) for r in cur.fetchall()]

    logger.info("Mengambil %d username %s dari kol_directory", len(rows), platform_key)
    return rows


def fetch_rows_by_usernames(conn, usernames: Sequence[str]) -> list[DirectoryRow]:
    """Cari baris kol_directory Instagram untuk daftar username tertentu.

    Dipakai oleh ingest.py, yang berangkat dari file hasil scrape dan perlu
    menemukan kembali baris directory-nya.
    """
    keys = sorted({normalize_username(u) for u in usernames if normalize_username(u)})
    if not keys:
        return []

    query = f"""
        SELECT k.id, k.username
        FROM public.kol_directory k
        JOIN public.platforms p ON p.id = k.platform_id
        WHERE p.key = 'instagram'
          AND {_SQL_NORMALIZED_USERNAME} = ANY(%s)
    """
    with conn.cursor() as cur:
        cur.execute(query, (keys,))
        rows = [DirectoryRow(id=str(r[0]), username=r[1]) for r in cur.fetchall()]

    logger.info("Cocok %d baris directory untuk %d username", len(rows), len(keys))
    return rows


def fetch_social_account_ids(
    conn, usernames: Sequence[str], platform_key: str = "instagram"
) -> dict[str, str]:
    """Peta username -> public.social_account.id untuk satu platform.

    Dipakai untuk mengisi kolom FK social_account_id di tabel l0_raw. Sengaja
    mengambil id dari social_account, BUKAN dari kol_directory: keduanya punya
    id yang sama sekali berbeda dan FK-nya menunjuk social_account.

    Kalau satu username punya lebih dari satu baris social_account, yang
    username-nya sudah bersih dimenangkan, lalu id terkecil, supaya hasilnya
    tidak berubah-ubah antar run.
    """
    keys = sorted({normalize_username(u) for u in usernames if normalize_username(u)})
    if not keys:
        return {}

    query = """
        SELECT DISTINCT ON (uname) uname, id
        FROM (
            SELECT ltrim(lower(btrim(split_part(s.username, '?', 1))), '@') AS uname,
                   s.id,
                   (s.username = ltrim(lower(btrim(split_part(s.username, '?', 1))), '@')) AS is_clean
            FROM public.social_account s
            JOIN public.platforms p ON p.id = s.platform_id
            WHERE p.key = %s
              AND ltrim(lower(btrim(split_part(s.username, '?', 1))), '@') = ANY(%s)
        ) t
        ORDER BY uname, is_clean DESC, id
    """
    with conn.cursor() as cur:
        cur.execute(query, (platform_key, keys))
        mapping = {row[0]: str(row[1]) for row in cur.fetchall()}

    logger.info(
        "Cocok %d social_account (%s) untuk %d username", len(mapping), platform_key, len(keys)
    )
    return mapping


# ---------------------------------------------------------------------------
# Pencarian KOL Discovery — READ-ONLY
# ---------------------------------------------------------------------------
# Bagian ini melayani KOL Discovery, bukan pipeline scraping. Hanya membaca;
# tidak ada jalur tulis dari sini.


@dataclass(frozen=True)
class SearchResult:
    """Satu baris hasil pencarian KOL Discovery."""

    id: str
    username: str | None
    display_name: str | None
    platform: str | None
    followers_count: int | None
    discovery_category: str | None
    # --- Growth ---------------------------------------------------------
    # Semuanya None untuk akun yang belum punya dua snapshot. None di sini
    # berarti "belum bisa dihitung", bukan nol -- konsumen harus menampilkan
    # tanda kosong, bukan 0%.
    #
    # `growth_pct` dibawa apa adanya dari L1; `daily_growth` dan
    # `projected_30d` dihitung saat dibaca. Lihat SQL_GROWTH_CTE.
    previous_snapshot_date: object | None = None
    current_snapshot_date: object | None = None
    previous_followers: int | None = None
    # SENGAJA dibawa terpisah dari `followers_count` di atas. Keduanya angka
    # follower, tapi dari sumber yang BERBEDA: `followers_count` berasal dari
    # `public.kol_directory` (nilai roster/impor), sedangkan `current_followers`
    # adalah followers pada snapshot L1 yang jadi pembilang Growth. Untuk
    # cristiano keduanya 679.264.838 vs 679.697.682 -- membandingkan
    # `previous_followers` dengan `followers_count` akan memberi selisih yang
    # tidak pernah dipakai rumus mana pun. Pasangkan previous dengan current.
    current_followers: int | None = None
    days_between: int | None = None
    growth_pct: float | None = None
    daily_growth: float | None = None
    # DELTA follower 30 hari (daily_growth x 30), bukan jumlah absolut.
    projected_30d: int | None = None
    # current_followers + projected_30d. Proyeksi, bukan pertumbuhan teramati.
    projected_followers_30d: int | None = None
    # --- Metrik kalkulasi lain, dari l2_gold.kol_profile_card ------------
    # None = "belum bisa dihitung", bukan nol. Konsumen menampilkan em dash.
    #
    # `paid_signal_count` dan `observation_days` adalah PENYEBUT-nya, dibawa
    # supaya "0% karena tidak ada yang berbayar" bisa dibedakan dari "0%
    # karena tidak ada yang diketahui". `gender_known_pct` berperan sama
    # untuk female/male: pada data sekarang unknown mendominasi.
    paid_ratio: float | None = None
    paid_signal_count: int | None = None
    share_rate: float | None = None
    post_frequency_monthly: float | None = None
    observation_days: int | None = None
    female_pct: float | None = None
    male_pct: float | None = None
    gender_known_pct: float | None = None
    # --- Label (migration 038) -------------------------------------------
    # Ambang KERJA, bukan kesepakatan final. Nilainya diisi gold_profile.py
    # dari `metrics_thresholds.py`; di sini hanya dibaca.
    #
    # None berarti "belum bisa dinilai". Khususnya: `monitoring_priority`
    # None BUKAN "Low", dan `growth_class` None BUKAN "Negative Growth".
    growth_class: str | None = None
    gender_reliability: str | None = None
    post_frequency_daily: float | None = None
    post_frequency_count: int | None = None
    post_frequency_reliability: str | None = None
    monitoring_er_pct: float | None = None
    monitoring_priority: str | None = None
    # --- Filter Discovery (migration 039) --------------------------------
    # `*_source` membedakan turunan dari teramati: `content_topic_source`
    # bernilai 'creator_category_fallback' berarti topiknya BUKAN hasil
    # klasifikasi konten, dan `audience_interest_source` bernilai
    # 'content_inferred' berarti minatnya diturunkan dari konten creator
    # karena minat audiens seluruhnya unknown.
    #
    # `rising_creator` None BUKAN False: False berarti "diukur, tidak naik
    # cukup", None berarti "Growth belum terukur".
    save_rate: float | None = None
    viral_frequency: float | None = None
    viral_post_count: int | None = None
    content_topic: str | None = None
    content_topic_source: str | None = None
    format_dominant: str | None = None
    audience_quality_score: float | None = None
    audience_quality_tier: str | None = None
    audience_interest_top: str | None = None
    audience_interest_source: str | None = None
    er_stddev_pp: float | None = None
    er_periods: int | None = None
    performance_stability: str | None = None
    rising_creator: bool | None = None
    # --- What Matters Most ----------------------------------------------
    # Hanya terisi kalau `search_kol_directory(matters=[...])` dipanggil;
    # None kalau tidak diminta, dan None juga kalau seluruh kriteria terpilih
    # belum punya nilai untuk KOL ini.
    #
    # `what_matters_contributing` WAJIB dibaca bersama skornya: skor 100 dari
    # satu kriteria tidak sebanding dengan 100 dari lima, dan tanpa angka ini
    # keduanya terlihat sama.
    what_matters_score: float | None = None
    what_matters_contributing: int | None = None


def _like_escape(term: str) -> str:
    """Netralkan wildcard LIKE di dalam kata kunci dari pengguna.

    Tanpa ini, mengetik '50%' membuat pola menjadi '%50%%' yang mencocokkan
    hampir semua baris, dan '_' mencocokkan sembarang satu karakter. Backslash
    di-escape lebih dulu supaya tidak merusak escape berikutnya.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# JOIN biasa, bukan LATERAL. Keduanya memberi hasil identik (30 baris untuk
# 'beauty'), tapi LATERAL berjalan 2.080 ms karena kol_social_account tidak
# punya indeks di kol_id sehingga nested loop men-scan tabel 7.720 kali.
# Versi hash join di bawah: 11 ms — 185x lebih cepat.
#
# JOIN ini tidak menggandakan baris pada data sekarang: setiap kol_directory
# punya tepat satu kol_social_account (7.496 baris, tidak ada yang dua) dan
# tepat satu kol_profile_card. Kalau nanti satu KOL boleh punya akun di dua
# platform sekaligus, tambahkan DISTINCT ON (k.id) — sampai saat itu DISTINCT
# hanya menambah sort tanpa mengubah hasil.
#
# Kategori dibaca lewat kol_categories.taxonomy_key (Discovery Category),
# bukan nama kategori mentah. EXISTS dipakai supaya category_ids yang
# multi-nilai tidak melipatgandakan baris.
#
# GROWTH ikut dibawa lewat LEFT JOIN ke CTE `growth` (lihat SQL_GROWTH_CTE).
# LEFT, bukan INNER: 98,7% akun belum punya pasangan snapshot, dan mereka harus
# tetap muncul di hasil pencarian dengan kolom Growth NULL -- bukan hilang.
# Biayanya kecil: `l1_silver.unified_profile` hanya ~2.000 baris, jadi window
# function di CTE itu tidak mengubah profil performa query ini.
_SEARCH_BODY_TEMPLATE = """
    SELECT k.id,
           k.username,
           pc.display_name,
           p.key AS platform,
           k.followers_count,
           (SELECT string_agg(DISTINCT c.taxonomy_key, ', ' ORDER BY c.taxonomy_key)
              FROM public.kol_categories c
             WHERE c.id = ANY(k.category_ids)
               AND c.taxonomy_key IS NOT NULL) AS discovery_category,
           g.previous_snapshot_date,
           g.current_snapshot_date,
           g.previous_followers,
           g.current_followers,
           g.days_between,
           g.growth_pct,
           g.daily_growth,
           g.projected_30d,
           g.projected_followers_30d,
           -- Metrik kalkulasi lain DIBACA DARI KARTU L2, tidak dihitung di
           -- sini. Rumusnya sudah dijalankan layer feature dan dibawa
           -- gold_profile.py; menghitungnya ulang di jalur baca berarti dua
           -- definisi. Growth turunan di atas adalah pengecualian yang
           -- disengaja: ia memakai SQL_GROWTH_CTE yang SAMA dengan yang
           -- diimpor gold_profile.py, jadi tetap satu definisi.
           pc.paid_ratio,
           pc.paid_signal_count,
           pc.share_rate,
           pc.post_frequency_monthly,
           pc.observation_days,
           pc.female_pct,
           pc.male_pct,
           pc.gender_known_pct,
           -- Label migration 038. Dibaca dari kartu, TIDAK diklasifikasikan
           -- ulang di sini: ambangnya hidup di metrics_thresholds.py dan
           -- sudah diterapkan gold_profile.py. Mengklasifikasikan ulang di
           -- jalur baca berarti dua tempat yang harus diubah bersamaan.
           pc.growth_class,
           pc.gender_reliability,
           pc.post_frequency_daily,
           pc.post_frequency_count,
           pc.post_frequency_reliability,
           pc.monitoring_er_pct,
           pc.monitoring_priority,
           -- Filter Discovery migration 039. Dibaca dari kartu; tidak ada
           -- yang dihitung ulang di jalur baca.
           pc.save_rate,
           pc.viral_frequency,
           pc.viral_post_count,
           pc.content_topic,
           pc.content_topic_source,
           pc.format_dominant,
           pc.audience_quality_score,
           pc.audience_quality_tier,
           pc.audience_interest_top,
           pc.audience_interest_source,
           pc.er_stddev_pp,
           pc.er_periods,
           pc.performance_stability,
           pc.rising_creator{kolom_tambahan}
      FROM public.kol_directory k
      LEFT JOIN public.platforms p            ON p.id = k.platform_id
      LEFT JOIN public.kol_social_account ksa ON ksa.kol_id = k.id
      LEFT JOIN l2_gold.kol_profile_card pc   ON pc.social_account_id = ksa.social_account_id
      LEFT JOIN growth g                      ON g.social_account_id = ksa.social_account_id
     WHERE (%(q_contains)s::text IS NULL
            OR k.username      ILIKE %(q_contains)s
            OR pc.display_name ILIKE %(q_contains)s
            OR k.bio           ILIKE %(q_contains)s)
       AND (%(taxonomy)s::text IS NULL
            OR EXISTS (SELECT 1
                         FROM public.kol_categories c
                        WHERE c.id = ANY(k.category_ids)
                          AND c.taxonomy_key = %(taxonomy)s))
       -- Style & Personality (migration 045). Dua grup TERPISAH: OR di dalam
       -- masing-masing, AND di antara keduanya. Memilih dua Style berarti
       -- "salah satunya" (pola yang sama dengan Category yang memakai
       -- overlap); menambah Personality MEMPERSEMPIT hasil, tidak melebarkan.
       --
       -- Keduanya taxonomy yang BERBEDA dari kol_categories dan tidak
       -- menyentuhnya: Category menjawab "kreator ini bidang apa",
       -- Style/Personality menjawab "bagaimana ia membuat konten".
       AND (%(style)s::text[] IS NULL OR """ + kat.sql_filter_atribut(
           "%(style)s::text[]") + """)
       AND (%(personality)s::text[] IS NULL OR """ + kat.sql_filter_atribut(
           "%(personality)s::text[]") + """)
"""

#: Urutan relevansi bawaan, dipakai kalau What Matters tidak diminta.
_SEARCH_ORDER_RELEVANSI = """
     ORDER BY
           CASE WHEN %(q_contains)s::text IS NULL              THEN 0
                WHEN k.username      ILIKE %(q_prefix)s        THEN 1
                WHEN k.username      ILIKE %(q_contains)s      THEN 2
                WHEN pc.display_name ILIKE %(q_contains)s      THEN 3
                ELSE 4
           END,
           k.followers_count DESC NULLS LAST,
           k.id
     LIMIT %(limit)s OFFSET %(offset)s
"""

#: Jalur baca biasa — tanpa kolom tambahan, perilakunya tidak berubah.
_SEARCH_QUERY = ("WITH " + SQL_GROWTH_CTE
                 + _SEARCH_BODY_TEMPLATE.format(kolom_tambahan="")
                 + _SEARCH_ORDER_RELEVANSI)

#: Ranking What Matters. Tie-break-nya sama dengan jalur biasa supaya urutan
#: tetap deterministik saat skornya seri.
_SEARCH_ORDER_MATTERS = """
     ORDER BY what_matters_score DESC NULLS LAST,
           k.followers_count DESC NULLS LAST,
           k.id
     LIMIT %(limit)s OFFSET %(offset)s
"""


def _query_what_matters(dipilih: Sequence[str]) -> str:
    """Query pencarian yang SAMA, plus dua kolom skor dan rankingnya.

    Body-nya `_SEARCH_BODY_TEMPLATE` yang identik dengan jalur biasa — tidak
    ada kolom yang disimpan, tidak ada tabel baru, dan tidak ada definisi
    kedua atas metric mana pun.

    Bentuk query ini ditentukan oleh `percent_rank()`: window function
    dievaluasi SETELAH WHERE tapi SEBELUM ORDER BY dan LIMIT, jadi
    persentilnya dihitung atas SELURUH populasi yang lolos filter — bukan atas
    satu halaman. Menghitung per halaman akan membuat peringkat seorang KOL
    berubah hanya karena orang menggeser halaman.

    Konsekuensi yang disengaja: populasi pembandingnya adalah hasil pencarian,
    bukan seluruh direktori. "Seberapa tinggi kreator ini dibanding kandidat
    yang sedang saya lihat" adalah pertanyaan yang memang ditanyakan Discovery.
    """
    ekspresi = wm.sql_ekspresi_skor()
    tambahan = (
        f",\n           ({wm.sql_what_matters(dipilih, ekspresi)})"
        f" AS what_matters_score"
        f",\n           ({wm.sql_jumlah_kontributor(dipilih, ekspresi)})"
        f" AS what_matters_contributing"
    )
    return ("WITH " + SQL_GROWTH_CTE
            + _SEARCH_BODY_TEMPLATE.format(kolom_tambahan=tambahan)
            + _SEARCH_ORDER_MATTERS)


def search_kol_directory(
    conn,
    q: str | None = None,
    taxonomy_key: str | None = None,
    limit: int = 50,
    offset: int = 0,
    matters: str | Sequence[str] | None = None,
    style: str | Sequence[str] | None = None,
    personality: str | Sequence[str] | None = None,
) -> list[SearchResult]:
    """Cari KOL di public.kol_directory untuk KOL Discovery.

    Field yang dicari hanya yang benar-benar ada isinya di database:

        k.username          7.497 dari 7.720  (97,1%)
        pc.display_name     1.958             (25,4%, lewat kol_profile_card)
        k.bio                 902             (11,7%)

    Urutan hasil sengaja berjenjang, bukan sekadar followers: cocok di awal
    username lebih relevan daripada cocok di tengahnya, dan cocok di bio paling
    lemah karena kata bisa muncul di tengah kalimat. Tanpa penjenjangan itu,
    'beauty' mengembalikan 135 baris yang tercampur rata; dengan penjenjangan,
    14 yang usernamenya benar-benar mengandung 'beauty' muncul lebih dulu.

    `taxonomy_key` menyaring lewat Discovery Category (kol_categories.taxonomy_key),
    bukan nama kategori mentah — satu Discovery Category bisa menaungi beberapa
    kategori mentah sekaligus.

    q dan taxonomy_key yang None atau kosong berarti "jangan saring" — memanggil
    tanpa argumen sama dengan menelusuri seluruh direktori.

    `matters` menyalakan ranking What Matters Most. Bisa string dari query
    param (`"engagement,consistency"`) atau daftar kunci. Kunci tak dikenal
    diabaikan. Kalau tidak ada satu pun kunci sah, urutannya kembali ke
    relevansi seperti biasa dan kedua kolom skor tetap None.

    Kriteria yang dipilih tapi nilainya NULL DIKELUARKAN dari penyebut, bukan
    dihitung nol — lihat `what_matters_scoring.what_matters_score`. Karena itu
    `what_matters_contributing` ikut dikembalikan: skornya harus dibaca
    bersama berapa kriteria yang benar-benar menyumbang.
    """
    term = (q or "").strip()
    taxonomy = (taxonomy_key or "").strip() or None
    dipilih = (wm.parse_matters(matters) if isinstance(matters, str)
               else [k for k in (matters or []) if k in wm.KRITERIA])
    # Divalidasi terhadap master taxonomy: kunci tak dikenal dibuang, jadi
    # salah ketik tidak pernah berubah jadi filter yang menyaring sembarangan.
    gaya = kat.parse_attribute_keys(style, kind=kat.STYLE)
    kepribadian = kat.parse_attribute_keys(personality, kind=kat.PERSONALITY)

    if term:
        escaped = _like_escape(term)
        q_contains: str | None = f"%{escaped}%"
        q_prefix: str | None = f"{escaped}%"
    else:
        q_contains = None
        q_prefix = None

    # Batas atas menjaga satu panggilan tidak menarik seluruh direktori ke
    # memori karena salah ketik argumen.
    params = {
        "q_contains": q_contains,
        "q_prefix": q_prefix,
        "taxonomy": taxonomy,
        # None berarti "jangan saring"; daftar kosong akan menyaring semuanya
        # habis, jadi keduanya sengaja tidak disamakan.
        "style": gaya or None,
        "personality": kepribadian or None,
        "limit": max(1, min(int(limit), 200)),
        "offset": max(0, int(offset)),
    }

    with conn.cursor() as cur:
        cur.execute(_query_what_matters(dipilih) if dipilih else _SEARCH_QUERY,
                    params)
        rows = [
            SearchResult(
                id=str(r[0]),
                username=r[1],
                display_name=r[2],
                platform=r[3],
                followers_count=r[4],
                discovery_category=r[5],
                previous_snapshot_date=r[6],
                current_snapshot_date=r[7],
                previous_followers=r[8],
                current_followers=r[9],
                days_between=r[10],
                growth_pct=float(r[11]) if r[11] is not None else None,
                daily_growth=float(r[12]) if r[12] is not None else None,
                projected_30d=int(r[13]) if r[13] is not None else None,
                projected_followers_30d=int(r[14]) if r[14] is not None else None,
                paid_ratio=float(r[15]) if r[15] is not None else None,
                paid_signal_count=r[16],
                share_rate=float(r[17]) if r[17] is not None else None,
                post_frequency_monthly=float(r[18]) if r[18] is not None else None,
                observation_days=r[19],
                female_pct=float(r[20]) if r[20] is not None else None,
                male_pct=float(r[21]) if r[21] is not None else None,
                gender_known_pct=float(r[22]) if r[22] is not None else None,
                growth_class=r[23],
                gender_reliability=r[24],
                post_frequency_daily=float(r[25]) if r[25] is not None else None,
                post_frequency_count=r[26],
                post_frequency_reliability=r[27],
                monitoring_er_pct=float(r[28]) if r[28] is not None else None,
                monitoring_priority=r[29],
                save_rate=float(r[30]) if r[30] is not None else None,
                viral_frequency=float(r[31]) if r[31] is not None else None,
                viral_post_count=r[32],
                content_topic=r[33],
                content_topic_source=r[34],
                format_dominant=r[35],
                audience_quality_score=float(r[36]) if r[36] is not None else None,
                audience_quality_tier=r[37],
                audience_interest_top=r[38],
                audience_interest_source=r[39],
                er_stddev_pp=float(r[40]) if r[40] is not None else None,
                er_periods=r[41],
                performance_stability=r[42],
                rising_creator=r[43],
                what_matters_score=(
                    float(r[44]) if dipilih and r[44] is not None else None),
                what_matters_contributing=(
                    int(r[45]) if dipilih and r[45] is not None else None),
            )
            for r in cur.fetchall()
        ]

    logger.info(
        "Search KOL: %d hasil (q=%r, taxonomy=%r, style=%r, personality=%r, "
        "matters=%r, limit=%d, offset=%d)",
        len(rows),
        term or None,
        taxonomy,
        gaya or None,
        kepribadian or None,
        dipilih or None,
        params["limit"],
        params["offset"],
    )
    return rows


# ---------------------------------------------------------------------------
# CPE — Cost Per Engagement, grain campaign x KOL
# ---------------------------------------------------------------------------
# Read-only, dan SENGAJA terpisah dari `search_kol_directory`.
#
# CPE bergrain (campaign, KOL); Discovery bergrain KOL. Satu KOL bisa ikut
# banyak campaign dengan `deal_price` yang berbeda-beda, jadi CPE bukan satu
# angka yang menempel pada kreator dan tidak bisa jadi kolom di hasil
# pencarian. Memaksakannya ke sana berarti memilih diam-diam campaign mana
# yang diwakilkan.
#
# Rumus dan sumber costnya hidup di `campaign_cost_metrics`, bukan di sini.


@dataclass(frozen=True)
class CampaignKolCPE:
    """CPE satu KOL dalam satu campaign."""

    campaign_kol_id: str
    campaign_id: str | None
    agency_kol_account_id: str | None
    deal_price: float | None
    currency: str | None
    # SUM(likes + comments_count + shares) atas satu baris performa per
    # deliverable. None berarti tidak ada satu komponen pun yang terukur --
    # bukan nol.
    total_engagement: int | None
    deliverable_count: int | None
    # Berapa deliverable yang `shares`-nya TIDAK NULL. Instagram tidak
    # mengembalikan shares, jadi angka ini yang membedakan "tidak diukur"
    # dari "nol".
    deliverable_shares: int | None
    # deal_price / total_engagement. None kalau salah satunya tidak ada,
    # atau engagement-nya nol.
    cpe: float | None


def fetch_campaign_kol_cpe(
    conn,
    campaign_id: str | None = None,
    agregasi: str = ccm.AGREGASI_DEFAULT,
) -> list[CampaignKolCPE]:
    """CPE per campaign x KOL.

        CPE = campaign_kols.deal_price / (likes + comments_count + shares)

    Biaya per SATU engagement: tanpa pengali 1.000, tanpa pengali 100, dan
    tanpa views di penyebut.

    `campaign_orders.total_amount` tidak dipakai dan tidak boleh dipakai --
    satu order bisa mencakup beberapa creator, dan nilainya sudah termasuk
    platform fee serta pajak. Membaginya rata ke KOL akan mengarang biaya
    yang tidak pernah dinegosiasikan.

    Kolom performa `campaign_content_performance` bersifat KUMULATIF sampai
    snapshot-nya, jadi beberapa snapshot per deliverable digabung dengan
    mengambil SATU baris terbaru/final -- prioritas `is_final`, lalu
    `snapshot_date`, lalu `id` -- dan TIDAK dijumlahkan. Menjumlahkannya akan
    menghitung satu deliverable sebanyak jumlah harinya dipantau.
    """
    sql = ccm.sql_cpe_campaign_kol(agregasi=agregasi)
    with conn.cursor() as cur:
        cur.execute(sql, {"campaign_id": campaign_id})
        hasil = [
            CampaignKolCPE(
                campaign_kol_id=str(r[0]),
                campaign_id=str(r[1]) if r[1] is not None else None,
                agency_kol_account_id=str(r[2]) if r[2] is not None else None,
                deal_price=float(r[3]) if r[3] is not None else None,
                currency=r[4],
                total_engagement=int(r[5]) if r[5] is not None else None,
                deliverable_count=int(r[6]) if r[6] is not None else None,
                deliverable_shares=int(r[7]) if r[7] is not None else None,
                cpe=float(r[8]) if r[8] is not None else None,
            )
            for r in cur.fetchall()
        ]

    logger.info("CPE campaign x KOL: %d baris (campaign_id=%r, agregasi=%r)",
                len(hasil), campaign_id, agregasi)
    return hasil


@dataclass(frozen=True)
class CampaignKolCPV:
    """CPV satu KOL dalam satu campaign."""

    campaign_kol_id: str
    campaign_id: str | None
    agency_kol_account_id: str | None
    deal_price: float | None
    currency: str | None
    # SUM(views) atas SATU baris terbaru/final per deliverable. None berarti
    # tidak ada satu deliverable pun yang views-nya terukur -- bukan nol.
    total_views: int | None
    deliverable_count: int | None
    # deal_price / total_views, biaya per SATU view. None kalau salah satunya
    # tidak ada, atau views-nya nol.
    cpv: float | None


def fetch_campaign_kol_cpv(
    conn,
    campaign_id: str | None = None,
    agregasi: str = ccm.AGREGASI_DEFAULT,
) -> list[CampaignKolCPV]:
    """CPV per campaign x KOL.

        CPV = campaign_kols.deal_price / SUM(views)

    Biaya per SATU view: tanpa pengali 1.000, tanpa engagement di penyebut,
    dan tanpa ER.

    Sumber cost dan aturan snapshot identik dengan `fetch_campaign_kol_cpe` --
    keduanya memakai CTE `performa` yang sama, jadi CPE dan CPV tidak mungkin
    membaca baris snapshot yang berbeda. Yang berbeda hanya penyebutnya.

    `campaign_orders.total_amount` tidak dipakai: satu order bisa mencakup
    beberapa creator dan nilainya sudah termasuk platform fee serta pajak.
    Rate card juga tidak -- itu harga daftar, bukan biaya campaign.
    """
    sql = ccm.sql_cpv_campaign_kol(agregasi=agregasi)
    with conn.cursor() as cur:
        cur.execute(sql, {"campaign_id": campaign_id})
        hasil = [
            CampaignKolCPV(
                campaign_kol_id=str(r[0]),
                campaign_id=str(r[1]) if r[1] is not None else None,
                agency_kol_account_id=str(r[2]) if r[2] is not None else None,
                deal_price=float(r[3]) if r[3] is not None else None,
                currency=r[4],
                total_views=int(r[5]) if r[5] is not None else None,
                deliverable_count=int(r[6]) if r[6] is not None else None,
                cpv=float(r[7]) if r[7] is not None else None,
            )
            for r in cur.fetchall()
        ]

    logger.info("CPV campaign x KOL: %d baris (campaign_id=%r, agregasi=%r)",
                len(hasil), campaign_id, agregasi)
    return hasil


def dedupe_rows(rows: Sequence[DirectoryRow]) -> dict[str, list[DirectoryRow]]:
    """Kelompokkan baris per username ternormalisasi.

    Apify menagih per profil, jadi username yang sama cukup dikirim sekali dan
    hasilnya dipakai untuk semua baris directory yang cocok.
    """
    grouped: dict[str, list[DirectoryRow]] = {}
    for row in rows:
        key = row.normalized
        if key:
            grouped.setdefault(key, []).append(row)
    return grouped


def update_profiles(conn, updates: Iterable[dict], commit: bool = True) -> int:
    """Tulis hasil scrape ke public.kol_directory.

    `updates` adalah dict hasil transform.to_db_update(). Kolom yang nilainya
    None dilewati (COALESCE), supaya field yang tidak dikembalikan Apify tidak
    menimpa data lama dengan NULL.
    """
    payload = [
        (
            u["id"],
            u.get("platform_user_id"),
            u.get("username"),
            u.get("username_normalized"),
            u.get("followers_count"),
            u.get("engagement_rate"),
            u.get("avatar_url"),
            u.get("profile_url"),
            u.get("bio"),
            u.get("verified_status"),
            u["scrape_status"],
        )
        for u in updates
    ]
    if not payload:
        return 0

    query = """
        UPDATE public.kol_directory AS k
        SET platform_user_id     = COALESCE(v.platform_user_id, k.platform_user_id),
            username             = COALESCE(v.username, k.username),
            username_normalized  = COALESCE(v.username_normalized, k.username_normalized),
            followers_count      = COALESCE(v.followers_count, k.followers_count),
            engagement_rate      = COALESCE(v.engagement_rate, k.engagement_rate),
            avatar_url           = COALESCE(v.avatar_url, k.avatar_url),
            profile_url          = COALESCE(v.profile_url, k.profile_url),
            bio                  = COALESCE(v.bio, k.bio),
            verified_status      = COALESCE(v.verified_status, k.verified_status),
            scrape_status        = v.scrape_status,
            last_refreshed_at    = now(),
            updated_at           = now()
        FROM (VALUES %s) AS v (
            id, platform_user_id, username, username_normalized,
            followers_count, engagement_rate, avatar_url, profile_url,
            bio, verified_status, scrape_status
        )
        WHERE k.id = v.id
        RETURNING k.id
    """
    # Cast eksplisit di baris VALUES pertama supaya Postgres tidak menebak
    # tipe 'unknown' untuk kolom yang semua nilainya NULL.
    template = (
        "(%s::uuid, %s::varchar, %s::varchar, %s::varchar, %s::integer,"
        " %s::numeric, %s::text, %s::text, %s::text, %s::varchar, %s::varchar)"
    )
    with conn.cursor() as cur:
        # cur.rowcount hanya mencerminkan halaman terakhir yang dieksekusi
        # execute_values, jadi hitung dari RETURNING agar totalnya benar.
        returned = psycopg2.extras.execute_values(
            cur, query, payload, template=template, page_size=200, fetch=True
        )
        affected = len(returned)
    if commit:
        conn.commit()
    logger.info("Update %d baris kol_directory (commit=%s)", affected, commit)
    return affected
