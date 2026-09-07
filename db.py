"""Akses Postgres: ambil username Instagram dan tulis balik hasil scrape."""

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence

import psycopg2
import psycopg2.extras

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
_SEARCH_QUERY = """
    SELECT k.id,
           k.username,
           pc.display_name,
           p.key AS platform,
           k.followers_count,
           (SELECT string_agg(DISTINCT c.taxonomy_key, ', ' ORDER BY c.taxonomy_key)
              FROM public.kol_categories c
             WHERE c.id = ANY(k.category_ids)
               AND c.taxonomy_key IS NOT NULL) AS discovery_category
      FROM public.kol_directory k
      LEFT JOIN public.platforms p            ON p.id = k.platform_id
      LEFT JOIN public.kol_social_account ksa ON ksa.kol_id = k.id
      LEFT JOIN l2_gold.kol_profile_card pc   ON pc.social_account_id = ksa.social_account_id
     WHERE (%(q_contains)s::text IS NULL
            OR k.username      ILIKE %(q_contains)s
            OR pc.display_name ILIKE %(q_contains)s
            OR k.bio           ILIKE %(q_contains)s)
       AND (%(taxonomy)s::text IS NULL
            OR EXISTS (SELECT 1
                         FROM public.kol_categories c
                        WHERE c.id = ANY(k.category_ids)
                          AND c.taxonomy_key = %(taxonomy)s))
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


def search_kol_directory(
    conn,
    q: str | None = None,
    taxonomy_key: str | None = None,
    limit: int = 50,
    offset: int = 0,
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
    """
    term = (q or "").strip()
    taxonomy = (taxonomy_key or "").strip() or None

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
        "limit": max(1, min(int(limit), 200)),
        "offset": max(0, int(offset)),
    }

    with conn.cursor() as cur:
        cur.execute(_SEARCH_QUERY, params)
        rows = [
            SearchResult(
                id=str(r[0]),
                username=r[1],
                display_name=r[2],
                platform=r[3],
                followers_count=r[4],
                discovery_category=r[5],
            )
            for r in cur.fetchall()
        ]

    logger.info(
        "Search KOL: %d hasil (q=%r, taxonomy=%r, limit=%d, offset=%d)",
        len(rows),
        term or None,
        taxonomy,
        params["limit"],
        params["offset"],
    )
    return rows


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
