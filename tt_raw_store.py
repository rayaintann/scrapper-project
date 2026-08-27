"""Tulis hasil scrape TikTok ke raw layer l0_raw.tt_profile_apify.

Sama seperti versi Instagram: append-only, satu `scrape_run_id` per run, dan
`social_account_id` diambil dari public.social_account.id — bukan kol_directory.id.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import psycopg2.extras

from db import fetch_social_account_ids
from raw_store import fk_targets
from tiktok_transform import extract_username, to_raw_row

logger = logging.getLogger(__name__)

RAW_TABLE = "l0_raw.tt_profile_apify"
PLATFORM_KEY = "tiktok"


@dataclass
class RawInsertStats:
    scrape_run_id: str
    inserted: int = 0
    linked: int = 0
    unlinked: int = 0
    skipped_failed: int = 0
    skipped_no_username: int = 0
    link_blocked_reason: str | None = None


def social_account_link_blocked(conn) -> str | None:
    """Cek apakah social_account_id di tabel TikTok bisa diisi.

    Sebelum migrasi 002, kolom ini punya dua foreign key yang saling meniadakan.
    Pemeriksaan tetap dipertahankan supaya pipeline tidak berhenti total kalau
    dijalankan di database yang belum dimigrasi.
    """
    targets = fk_targets(conn, RAW_TABLE)
    if len(targets) > 1:
        return (
            f"kolom social_account_id punya foreign key ke {' dan '.join(sorted(targets))} "
            "sekaligus, jadi tidak ada nilai yang bisa memenuhi keduanya"
        )
    return None


def existing_usernames(conn, usernames: Sequence[str]) -> set[str]:
    """Username yang sudah punya baris di RAW_TABLE.

    Dipakai pipeline untuk melaporkan (dan opsional melewati) profil yang sudah
    pernah diambil. Apify menagih per hasil, jadi ini satu-satunya pengaman yang
    benar-benar menahan biaya: kol_directory.scrape_status tidak pernah diisi
    oleh jalur TikTok, sehingga --only-unscraped tidak menyaring apa pun.
    """
    keys = sorted({u for u in usernames if u})
    if not keys:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT DISTINCT username FROM {RAW_TABLE} WHERE username = ANY(%s)",
            (keys,),
        )
        return {row[0] for row in cur.fetchall()}


def count_existing(conn, scraped_at: datetime, source_actor: str) -> int:
    """Berapa baris dari scrape yang sama sudah pernah masuk (tabel append-only)."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {RAW_TABLE} WHERE scraped_at = %s AND source_actor = %s",
            (scraped_at, source_actor),
        )
        return cur.fetchone()[0]


def insert_profiles(
    conn,
    items: Sequence[dict],
    source_actor: str,
    scraped_at: datetime,
    scrape_run_id: str | None = None,
    commit: bool = True,
) -> RawInsertStats:
    """Masukkan item TikTok ke l0_raw.tt_profile_apify."""
    stats = RawInsertStats(scrape_run_id=scrape_run_id or str(uuid.uuid4()))
    fetched_at = datetime.now(timezone.utc)

    # Satu profil bisa mengembalikan lebih dari satu video; yang pertama dipakai.
    rows_by_username: dict[str, dict] = {}
    for item in items:
        username = extract_username(item)
        if not username:
            stats.skipped_no_username += 1
            continue
        if username in rows_by_username:
            continue
        row = to_raw_row(item)
        if row is None:
            stats.skipped_failed += 1
            continue
        row["_payload"] = item
        rows_by_username[username] = row

    if not rows_by_username:
        logger.warning("Tidak ada item yang bisa dimasukkan ke %s", RAW_TABLE)
        return stats

    stats.link_blocked_reason = social_account_link_blocked(conn)
    if stats.link_blocked_reason:
        logger.warning(
            "social_account_id dikosongkan: %s. Data tetap masuk dan bisa "
            "ditautkan lewat kolom username.",
            stats.link_blocked_reason,
        )
        account_ids: dict[str, str] = {}
    else:
        account_ids = fetch_social_account_ids(conn, list(rows_by_username), PLATFORM_KEY)

    payload = []
    for username, row in rows_by_username.items():
        social_account_id = account_ids.get(username)
        if social_account_id:
            stats.linked += 1
        else:
            stats.unlinked += 1
        payload.append(
            (
                social_account_id,
                fetched_at,
                username,
                row["display_name"],
                row["bio_description"],
                row["avatar_url"],
                row["is_verified"],
                row["follower_count"],
                row["following_count"],
                row["likes_count"],
                row["video_count"],
                stats.scrape_run_id,
                source_actor,
                psycopg2.extras.Json(row["_payload"]),
                scraped_at,
            )
        )

    query = f"""
        INSERT INTO {RAW_TABLE} (
            social_account_id, fetched_at, username, display_name, bio_description,
            avatar_url, is_verified, follower_count, following_count,
            likes_count, video_count,
            scrape_run_id, source_actor, raw_payload, scraped_at
        )
        VALUES %s
        RETURNING id
    """
    template = (
        "(%s::uuid, %s::timestamptz, %s::varchar, %s::varchar, %s::text,"
        " %s::text, %s::boolean, %s::integer, %s::integer,"
        " %s::bigint, %s::integer,"
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
        "%s: %d baris masuk (scrape_run_id=%s, terhubung ke social_account=%d, tanpa pasangan=%d)",
        RAW_TABLE,
        stats.inserted,
        stats.scrape_run_id,
        stats.linked,
        stats.unlinked,
    )
    return stats
