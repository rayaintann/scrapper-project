"""Parsing + cleaning item clockworks/tiktok-scraper untuk l0_raw.tt_profile_apify.

Actor ini berorientasi video: setiap item adalah satu video, dan data profilnya
menempel di `authorMeta`. Modul ini menarik bagian profil itu, membersihkannya
memakai aturan yang sama dengan Instagram (clean.py), lalu menyusunnya sesuai
kolom tabel TikTok — yang namanya berbeda dari tabel Instagram
(`display_name`, `bio_description`, `follower_count`).
"""

import logging
from typing import Any

from clean import clean_line, clean_text
from transform import normalize_username

logger = logging.getLogger(__name__)


def _author(item: dict) -> dict:
    meta = item.get("authorMeta")
    return meta if isinstance(meta, dict) else {}


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_username(item: dict) -> str | None:
    """Username TikTok dari satu item hasil.

    Diambil berurutan dari authorMeta.name, profileUrl, lalu `input` (nilai yang
    kita kirimkan sendiri) sebagai cadangan terakhir.
    """
    meta = _author(item)
    for source in (
        meta.get("name"),
        meta.get("profileUrl"),
        item.get("input"),
    ):
        cleaned = normalize_username(source)
        if cleaned:
            return cleaned
    return None


def is_error_item(item: dict) -> bool:
    """Item yang tidak membawa data profil yang bisa dipakai."""
    if item.get("error"):
        return True
    meta = _author(item)
    if not meta:
        return True
    # Tanpa id maupun jumlah follower, tidak ada yang bisa disimpan.
    return meta.get("id") in (None, "") and _as_int(meta.get("fans")) is None


def to_raw_row(item: dict) -> dict | None:
    """Susun satu baris l0_raw.tt_profile_apify dari satu item.

    Kolom teks sudah dibersihkan di sini (sesuai alur yang diminta), sedangkan
    `raw_payload` tetap menyimpan item aslinya utuh sehingga tidak ada informasi
    yang hilang dan hasilnya bisa diolah ulang kapan pun.
    """
    username = extract_username(item)
    if not username or is_error_item(item):
        return None

    meta = _author(item)
    avatar = meta.get("originalAvatarUrl") or meta.get("avatar")
    verified = meta.get("verified")

    return {
        "username": username,
        "display_name": clean_line(meta.get("nickName")),
        "bio_description": clean_text(meta.get("signature")),
        "avatar_url": avatar if isinstance(avatar, str) and avatar.strip() else None,
        "is_verified": bool(verified) if isinstance(verified, bool) else None,
        "follower_count": _as_int(meta.get("fans")),
        "following_count": _as_int(meta.get("following")),
        "likes_count": _as_int(meta.get("heart")),
        "video_count": _as_int(meta.get("video")),
    }


def flatten_for_csv(item: dict) -> dict:
    """Versi ringkas satu item untuk file CSV ringkasan."""
    meta = _author(item)
    row = to_raw_row(item) or {"username": extract_username(item)}
    return {
        "username": row.get("username"),
        "tiktok_user_id": meta.get("id"),
        "display_name": row.get("display_name"),
        "follower_count": row.get("follower_count"),
        "following_count": row.get("following_count"),
        "likes_count": row.get("likes_count"),
        "video_count": row.get("video_count"),
        "is_verified": row.get("is_verified"),
        "is_private": meta.get("privateAccount"),
        "bio_link": meta.get("bioLink"),
        "avatar_url": row.get("avatar_url"),
        "bio_description": (row.get("bio_description") or "").replace("\n", " ") or None,
        "error": item.get("error"),
    }
