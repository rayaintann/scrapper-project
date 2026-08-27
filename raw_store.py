"""Tulis hasil scrape ke raw layer l0_raw.ig_profile_apify.

Tabel ini bersifat append-only: setiap run menambah baris baru dengan
`scrape_run_id` yang sama, jadi riwayat scrape sebelumnya tetap utuh dan bisa
diolah lagi di layer l1_silver.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import psycopg2.extras

from db import fetch_social_account_ids
from transform import extract_username, is_error_item

logger = logging.getLogger(__name__)

RAW_TABLE = "l0_raw.ig_profile_apify"


@dataclass
class RawInsertStats:
    scrape_run_id: str
    inserted: int = 0
    linked: int = 0
    unlinked: int = 0
    skipped_failed: int = 0
    skipped_no_username: int = 0
    link_blocked_reason: str | None = None


def fk_targets(conn, table: str = RAW_TABLE, column: str = "social_account_id") -> set[str]:
    """Tabel tujuan semua foreign key yang menempel di satu kolom."""
    query = """
        SELECT DISTINCT c.confrelid::regclass::text
        FROM pg_constraint c
        JOIN unnest(c.conkey) AS k(attnum) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype = 'f'
          AND c.conrelid = %s::regclass
          AND a.attname = %s
    """
    with conn.cursor() as cur:
        cur.execute(query, (table, column))
        return {row[0] for row in cur.fetchall()}


def count_existing(conn, scraped_at: datetime, source_actor: str) -> int:
    """Berapa baris dari scrape yang sama sudah pernah masuk.

    Tabel ini append-only, jadi ingest file yang sama dua kali akan menggandakan
    baris. Pemanggil memakai angka ini untuk memperingatkan lebih dulu.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {RAW_TABLE} WHERE scraped_at = %s AND source_actor = %s",
            (scraped_at, source_actor),
        )
        return cur.fetchone()[0]


def social_account_link_blocked(conn) -> str | None:
    """Cek apakah social_account_id bisa diisi.

    Di database ini kolom tersebut punya dua foreign key sekaligus, ke
    social_account(id) dan ke kol_directory(id), padahal kedua tabel itu tidak
    berbagi satu id pun. Akibatnya nilai apa pun selain NULL pasti ditolak.
    Selama itu belum dibereskan, kolomnya diisi NULL supaya data tetap masuk;
    begitu FK yang keliru dihapus, penautan jalan otomatis tanpa ubah kode.
    """
    targets = fk_targets(conn)
    if len(targets) > 1:
        return (
            f"kolom social_account_id punya foreign key ke {' dan '.join(sorted(targets))} "
            "sekaligus, jadi tidak ada nilai yang bisa memenuhi keduanya"
        )
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _website(item: dict) -> str | None:
    url = item.get("externalUrl")
    if isinstance(url, str) and url.strip():
        return url.strip()
    # Sebagian profil hanya mengisi externalUrls (bisa lebih dari satu tautan).
    urls = item.get("externalUrls")
    if isinstance(urls, list):
        for entry in urls:
            if isinstance(entry, dict) and isinstance(entry.get("url"), str):
                return entry["url"]
            if isinstance(entry, str) and entry.strip():
                return entry.strip()
    return None


def insert_profiles(
    conn,
    items: Sequence[dict],
    source_actor: str,
    scraped_at: datetime,
    scrape_run_id: str | None = None,
    include_failed: bool = False,
    commit: bool = True,
    account_ids: dict[str, str] | None = None,
) -> RawInsertStats:
    """Masukkan item Apify ke l0_raw.ig_profile_apify.

    Item yang dibalas Apify sebagai error (not_found, restricted) dilewati
    kecuali `include_failed` diaktifkan, karena tabel ini menyimpan profil.
    Payload aslinya tetap disimpan utuh di kolom `raw_payload`.

    `account_ids` memetakan username -> social_account.id. Kalau diisi, peta itu
    dipakai apa adanya dan pencarian lewat username DILEWATI. Scheduler Engine
    memakainya karena sudah memegang social_account_id yang sah dari
    `public.kol_social_account`; mencarinya ulang lewat username akan
    memasukkan kembali ambiguitas yang justru dihindari jembatan itu.
    """
    stats = RawInsertStats(scrape_run_id=scrape_run_id or str(uuid.uuid4()))
    fetched_at = datetime.now(timezone.utc)

    usable: list[tuple[str, dict]] = []
    for item in items:
        username = extract_username(item)
        if not username:
            stats.skipped_no_username += 1
            continue
        if is_error_item(item) and not include_failed:
            stats.skipped_failed += 1
            continue
        usable.append((username, item))

    if not usable:
        logger.warning("Tidak ada item yang bisa dimasukkan ke %s", RAW_TABLE)
        return stats

    if account_ids is None:
        stats.link_blocked_reason = social_account_link_blocked(conn)
        if stats.link_blocked_reason:
            logger.warning(
                "social_account_id dikosongkan: %s. Data tetap masuk dan bisa "
                "ditautkan lewat kolom username.",
                stats.link_blocked_reason,
            )
            account_ids = {}
        else:
            account_ids = fetch_social_account_ids(conn, [u for u, _ in usable])
    else:
        logger.info(
            "%s: memakai %d social_account_id dari pemanggil (tanpa cocok username)",
            RAW_TABLE, len(account_ids),
        )

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
                # fetched_at = kapan baris ini mendarat di DB, scraped_at =
                # kapan Apify mengambilnya. Keduanya beda kalau ingest menyusul.
                fetched_at,
                username,
                item.get("fullName"),
                item.get("biography"),
                _website(item),
                _as_int(item.get("followersCount")),
                _as_int(item.get("followsCount")),
                _as_int(item.get("postsCount")),
                stats.scrape_run_id,
                source_actor,
                psycopg2.extras.Json(item),
                scraped_at,
            )
        )

    query = f"""
        INSERT INTO {RAW_TABLE} (
            social_account_id, fetched_at, username, name, biography, website,
            followers_count, follows_count, media_count,
            scrape_run_id, source_actor, raw_payload, scraped_at
        )
        VALUES %s
        RETURNING id
    """
    template = (
        "(%s::uuid, %s::timestamptz, %s::varchar, %s::varchar, %s::text, %s::text,"
        " %s::integer, %s::integer, %s::integer,"
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
