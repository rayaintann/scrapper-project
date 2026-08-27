"""Tulis hasil scraping POST/VIDEO ke raw layer.

    Instagram -> l0_raw.ig_media_snapshots_apify
    TikTok    -> l0_raw.tt_video_apify

Tiga jaminan yang dipegang modul ini:

1. **Item error tidak pernah masuk sebagai post.** Item yang dikenali
   `post_errors.is_error_item` disaring lebih dulu dan dikembalikan sebagai
   daftar kegagalan, bukan disimpan sebagai baris konten. Tidak ada opsi untuk
   memaksanya masuk — berbeda dari `raw_store.insert_profiles` yang punya
   `include_failed`, karena tabel post tidak punya kolom status.

2. **Append-only, tidak pernah menghapus.** Kedua tabel tidak punya unique
   constraint dan flow existing tidak mendukung replacement. Refresh yang gagal
   tidak boleh menyentuh data lama, jadi modul ini sama sekali tidak punya
   jalur DELETE atau UPDATE.

3. **Pemetaan kolom identik dengan baris yang sudah ada.** Setiap pemetaan di
   bawah diverifikasi ulang terhadap 130 baris Instagram dan 91 baris TikTok
   yang sudah ada di database, supaya hasil sukses tetap masuk persis seperti
   sekarang.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

import psycopg2.extras

from db import fetch_social_account_ids
from post_errors import classify_item, is_error_item
from raw_store import fk_targets

logger = logging.getLogger(__name__)

IG_TABLE = "l0_raw.ig_media_snapshots_apify"
TT_TABLE = "l0_raw.tt_video_apify"


@dataclass
class PostInsertStats:
    scrape_run_id: str
    table: str
    inserted: int = 0
    linked: int = 0
    unlinked: int = 0
    skipped_error: int = 0
    skipped_no_username: int = 0
    skipped_no_content_id: int = 0
    link_blocked_reason: str | None = None
    # (username, kode, pesan) untuk tiap item error yang disaring.
    errors: list[tuple[str | None, str, str]] = field(default_factory=list)
    # username -> jumlah baris yang benar-benar masuk
    per_account: dict[str, int] = field(default_factory=dict)


# --- pembantu ---------------------------------------------------------------


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _content_id(item: dict) -> str | None:
    value = item.get("id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _child_count(item: dict) -> int | None:
    """Jumlah anak carousel; NULL kalau bukan carousel.

    Daftar kosong sengaja jadi NULL, bukan 0 — mengikuti 130 baris yang sudah
    ada, di mana kolom ini hanya terisi untuk post yang benar-benar carousel.
    """
    children = item.get("childPosts")
    if isinstance(children, list) and children:
        return len(children)
    return None


def _ig_views(item: dict) -> int | None:
    """`videoPlayCount`, jatuh ke `videoViewCount` kalau tidak ada.

    Dari 130 baris existing, 129 memakai `videoPlayCount`; satu baris hanya
    punya `videoViewCount`, dan nilainya yang dipakai.
    """
    plays = _as_int(item.get("videoPlayCount"))
    return plays if plays is not None else _as_int(item.get("videoViewCount"))


def _link_blocked(conn, table: str) -> str | None:
    """Sama seperti raw_store: tolak menautkan kalau kolomnya punya FK ganda."""
    targets = fk_targets(conn, table=table, column="social_account_id")
    if len(targets) > 1:
        return (
            f"kolom social_account_id di {table} punya foreign key ke "
            f"{' dan '.join(sorted(targets))} sekaligus, jadi tidak ada nilai "
            "yang bisa memenuhi keduanya"
        )
    return None


def _partition(
    items: Sequence[dict], username_of, stats: PostInsertStats
) -> list[tuple[str, dict]]:
    """Pisahkan item sah dari item error, sambil mengisi `stats`."""
    usable: list[tuple[str, dict]] = []
    for item in items:
        username = username_of(item) if callable(username_of) else None
        if is_error_item(item):
            code, message = classify_item(item)
            stats.errors.append((username, code, message))
            stats.skipped_error += 1
            continue
        if not username:
            stats.skipped_no_username += 1
            continue
        if not _content_id(item):
            stats.skipped_no_content_id += 1
            continue
        usable.append((username, item))
    return usable


def _account_ids(
    conn,
    stats: PostInsertStats,
    usable,
    platform_key: str,
    diberikan: dict[str, str] | None = None,
) -> dict[str, str]:
    """Peta username -> social_account.id untuk baris yang akan ditulis.

    Kalau `diberikan` diisi, peta itu dipakai apa adanya. Scheduler Engine selalu
    mengisinya dengan id yang berasal dari `public.kol_social_account`, supaya
    post tidak pernah mendarat di akun yang salah gara-gara dua KOL berbagi
    username yang sama.
    """
    if diberikan is not None:
        logger.info(
            "%s: memakai %d social_account_id dari pemanggil (tanpa cocok username)",
            stats.table, len(diberikan),
        )
        return diberikan
    stats.link_blocked_reason = _link_blocked(conn, stats.table)
    if stats.link_blocked_reason:
        logger.warning("social_account_id dikosongkan: %s", stats.link_blocked_reason)
        return {}
    return fetch_social_account_ids(conn, [u for u, _ in usable], platform_key=platform_key)


# --- deduplication ----------------------------------------------------------
#
# Kedua tabel post sengaja TIDAK punya unique constraint: keduanya menyimpan
# *snapshot*, jadi satu post yang sama boleh muncul lagi di tanggal scrape
# berbeda dan metriknya ikut berubah. Menambahkan UNIQUE(social_account_id,
# content_id) akan mematahkan sifat itu untuk post_pipeline.
#
# Scheduler Engine berjalan tiap 5 menit dan actor mengembalikan post yang sama
# terus-menerus, jadi penyaringan dilakukan di sisi aplikasi: post yang
# content_id-nya sudah ada untuk akun itu tidak dikirim ke INSERT sama sekali.
# Aman untuk pipeline lain karena tidak ada perubahan skema.

# Kolom id konten per tabel.
CONTENT_ID_COLUMN = {
    IG_TABLE: "media_id",
    TT_TABLE: "video_id",
}


def existing_content_ids(
    conn,
    table: str,
    content_ids: Sequence[str],
    social_account_id: str | None = None,
) -> set[str]:
    """content_id yang SUDAH ada di `table`, dari daftar yang ditanyakan.

    Kalau `social_account_id` diketahui, pencarian dibatasi ke akun itu — id
    konten hanya dijamin unik per akun. Kalau tidak (penautan FK terhalang),
    pencarian jatuh ke seluruh tabel; lebih ketat, dan konsekuensinya hanya
    melewatkan post yang memang sudah tersimpan.
    """
    column = CONTENT_ID_COLUMN.get(table)
    if column is None:
        raise ValueError(f"tabel {table} bukan tabel post yang dikenal")
    keys = sorted({str(c) for c in content_ids if c})
    if not keys:
        return set()

    query = f"SELECT DISTINCT {column} FROM {table} WHERE {column} = ANY(%s)"
    params: list = [keys]
    if social_account_id:
        query += " AND social_account_id = %s"
        params.append(social_account_id)

    with conn.cursor() as cur:
        cur.execute(query, params)
        return {row[0] for row in cur.fetchall() if row[0]}


def split_new_and_duplicate(
    conn,
    table: str,
    items: Sequence[dict],
    social_account_id: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Pisahkan item jadi (belum pernah masuk, sudah pernah masuk).

    Item error dan item tanpa id konten dibiarkan lewat sebagai "baru": yang
    berhak menyaringnya adalah `_partition` di dalam insert_*, dan menahannya
    di sini akan menyembunyikan kegagalan dari log.
    """
    ids = [cid for cid in (_content_id(i) for i in items if isinstance(i, dict)) if cid]
    sudah_ada = existing_content_ids(conn, table, ids, social_account_id)
    if not sudah_ada:
        return list(items), []

    baru: list[dict] = []
    duplikat: list[dict] = []
    for item in items:
        cid = _content_id(item) if isinstance(item, dict) else None
        if cid and cid in sudah_ada:
            duplikat.append(item)
        else:
            baru.append(item)
    logger.info(
        "%s: %d item baru, %d duplikat dilewati", table, len(baru), len(duplikat)
    )
    return baru, duplikat


# --- Instagram --------------------------------------------------------------


def insert_ig_posts(
    conn,
    items: Sequence[dict],
    username_of,
    source_actor: str,
    scraped_at: datetime,
    scrape_run_id: str | None = None,
    commit: bool = True,
    account_ids: dict[str, str] | None = None,
) -> PostInsertStats:
    """Masukkan post Instagram ke `l0_raw.ig_media_snapshots_apify`."""
    stats = PostInsertStats(
        scrape_run_id=scrape_run_id or str(uuid.uuid4()), table=IG_TABLE
    )
    fetched_at = datetime.now(timezone.utc)

    usable = _partition(items, username_of, stats)
    if not usable:
        logger.warning("Tidak ada post Instagram yang bisa dimasukkan ke %s", IG_TABLE)
        return stats

    account_ids = _account_ids(conn, stats, usable, "instagram", account_ids)

    payload = []
    for username, item in usable:
        social_account_id = account_ids.get(username)
        if social_account_id:
            stats.linked += 1
        else:
            stats.unlinked += 1
        payload.append(
            (
                social_account_id,
                _content_id(item),
                fetched_at,
                _text(item.get("timestamp")),
                _text(item.get("caption")),
                _text(item.get("productType")),
                _text(item.get("url")),
                _text(item.get("displayUrl")),
                _as_int(item.get("commentsCount")),
                _as_int(item.get("likesCount")),
                _ig_views(item),
                _as_num(item.get("videoDuration")),
                _child_count(item),
                _as_bool(item.get("paidPartnership")),
                stats.scrape_run_id,
                source_actor,
                psycopg2.extras.Json(item),
                scraped_at,
            )
        )
        stats.per_account[username] = stats.per_account.get(username, 0) + 1

    query = f"""
        INSERT INTO {IG_TABLE} (
            social_account_id, media_id, fetched_at, posted_at, caption,
            media_type, permalink, cover_image, comments, likes, views,
            video_duration, carousel_media_count, is_sponsored,
            scrape_run_id, source_actor, raw_payload, scraped_at
        )
        VALUES %s
        RETURNING id
    """
    template = (
        "(%s::uuid, %s::varchar, %s::timestamptz, %s::timestamptz, %s::text,"
        " %s::varchar, %s::text, %s::text, %s::integer, %s::integer, %s::integer,"
        " %s::numeric, %s::integer, %s::boolean,"
        " %s::uuid, %s::varchar, %s::jsonb, %s::timestamptz)"
    )
    with conn.cursor() as cur:
        returned = psycopg2.extras.execute_values(
            cur, query, payload, template=template, page_size=100, fetch=True
        )
        stats.inserted = len(returned)

    if commit:
        conn.commit()

    logger.info(
        "%s: %d baris masuk, %d item error disaring (scrape_run_id=%s)",
        IG_TABLE,
        stats.inserted,
        stats.skipped_error,
        stats.scrape_run_id,
    )
    return stats


# --- TikTok -----------------------------------------------------------------


def insert_tt_videos(
    conn,
    items: Sequence[dict],
    username_of,
    source_actor: str,
    scraped_at: datetime,
    scrape_run_id: str | None = None,
    commit: bool = True,
    account_ids: dict[str, str] | None = None,
) -> PostInsertStats:
    """Masukkan video TikTok ke `l0_raw.tt_video_apify`."""
    stats = PostInsertStats(
        scrape_run_id=scrape_run_id or str(uuid.uuid4()), table=TT_TABLE
    )
    fetched_at = datetime.now(timezone.utc)

    usable = _partition(items, username_of, stats)
    if not usable:
        logger.warning("Tidak ada video TikTok yang bisa dimasukkan ke %s", TT_TABLE)
        return stats

    account_ids = _account_ids(conn, stats, usable, "tiktok", account_ids)

    payload = []
    for username, item in usable:
        social_account_id = account_ids.get(username)
        if social_account_id:
            stats.linked += 1
        else:
            stats.unlinked += 1
        meta = item.get("videoMeta") if isinstance(item.get("videoMeta"), dict) else {}
        payload.append(
            (
                social_account_id,
                _content_id(item),
                fetched_at,
                _text(item.get("createTimeISO")),
                # Actor tidak mengembalikan `title`; kolomnya tetap NULL,
                # sama seperti 91 baris yang sudah ada.
                _text(item.get("title")),
                _text(item.get("text")),
                _as_int(meta.get("duration")),
                _text(meta.get("coverUrl")),
                _text(item.get("webVideoUrl")),
                _as_int(item.get("diggCount")),
                _as_int(item.get("commentCount")),
                _as_int(item.get("shareCount")),
                _as_int(item.get("playCount")),
                stats.scrape_run_id,
                source_actor,
                psycopg2.extras.Json(item),
                scraped_at,
            )
        )
        stats.per_account[username] = stats.per_account.get(username, 0) + 1

    query = f"""
        INSERT INTO {TT_TABLE} (
            social_account_id, video_id, fetched_at, posted_at, title,
            description, duration, cover_image_url, share_url,
            like_count, comment_count, share_count, view_count,
            scrape_run_id, source_actor, raw_payload, scraped_at
        )
        VALUES %s
        RETURNING id
    """
    template = (
        "(%s::uuid, %s::varchar, %s::timestamptz, %s::timestamptz, %s::text,"
        " %s::text, %s::integer, %s::text, %s::text,"
        " %s::bigint, %s::bigint, %s::bigint, %s::bigint,"
        " %s::uuid, %s::varchar, %s::jsonb, %s::timestamptz)"
    )
    with conn.cursor() as cur:
        returned = psycopg2.extras.execute_values(
            cur, query, payload, template=template, page_size=100, fetch=True
        )
        stats.inserted = len(returned)

    if commit:
        conn.commit()

    logger.info(
        "%s: %d baris masuk, %d item error disaring (scrape_run_id=%s)",
        TT_TABLE,
        stats.inserted,
        stats.skipped_error,
        stats.scrape_run_id,
    )
    return stats
