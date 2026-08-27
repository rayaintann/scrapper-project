"""Ubah item mentah dari Apify menjadi baris update kol_directory."""

import logging
import re
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# Skema + host di awal nilai, hanya kalau diikuti '/'.
_URL_PREFIX = re.compile(r"^(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+/", re.IGNORECASE)

# Nama field di output actor bisa berbeda antar versi build, jadi setiap nilai
# diambil dari beberapa kemungkinan key.
_USERNAME_KEYS = ("username", "userName", "ownerUsername")
_ID_KEYS = ("id", "userId", "ownerId", "pk")
_FOLLOWERS_KEYS = ("followersCount", "followers_count", "edge_followed_by")
_BIO_KEYS = ("biography", "bio")
_AVATAR_KEYS = ("profilePicUrlHD", "profilePicUrl", "profile_pic_url_hd", "profile_pic_url")
_URL_KEYS = ("url", "profileUrl", "inputUrl")


def normalize_username(raw: Any) -> str:
    """Bersihkan username Instagram menjadi handle polos.

    Data di kol_directory sebagian masih berupa potongan URL, misalnya
    'imeyliem?hl=en' atau 'https://instagram.com/foo/'. Kalau dikirim apa adanya
    ke Apify hasilnya pasti not_found, jadi query string, path, dan '@' dibuang
    di sini.
    """
    if not isinstance(raw, str):
        return ""
    value = raw.strip()
    # Buang skema + host kalau nilainya berupa URL, apa pun platformnya
    # (instagram.com/foo, tiktok.com/@foo, dst). Pola ini menuntut ada '/'
    # setelah host, jadi username biasa yang mengandung titik (mis. 'inul.d')
    # tidak ikut terpotong.
    value = _URL_PREFIX.sub("", value)
    value = value.split("?", 1)[0].split("#", 1)[0]
    value = value.strip("/").split("/")[0]
    return value.lstrip("@").strip().lower()


def _first(item: dict, keys: Sequence[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, dict):  # bentuk GraphQL: {"count": 123}
        value = value.get("count")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_username(item: dict) -> str | None:
    """Ambil username dari item, termasuk item error yang hanya punya URL."""
    for source in (_first(item, _USERNAME_KEYS), _first(item, _URL_KEYS)):
        cleaned = normalize_username(source)
        if cleaned:
            return cleaned
    return None


def compute_engagement_rate(item: dict) -> float | None:
    """Engagement rate (persen) dari rata-rata like+comment postingan terakhir.

    Hanya dihitung kalau actor mengembalikan latestPosts beserta jumlah like
    atau komentar. Kalau tidak, kembalikan None supaya nilai lama di DB tidak
    tertimpa.
    """
    followers = _as_int(_first(item, _FOLLOWERS_KEYS))
    posts = item.get("latestPosts")
    if not followers or followers <= 0 or not isinstance(posts, list) or not posts:
        return None

    interactions: list[int] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        likes = _as_int(post.get("likesCount")) or 0
        comments = _as_int(post.get("commentsCount")) or 0
        # likesCount -1 artinya Instagram menyembunyikan jumlah like.
        if likes < 0:
            likes = 0
        if likes or comments:
            interactions.append(likes + comments)

    if not interactions:
        return None

    avg = sum(interactions) / len(interactions)
    return round(avg / followers * 100, 4)


def is_error_item(item: dict) -> bool:
    """Item yang menandakan profil gagal diambil (private/not found/dll)."""
    if item.get("error"):
        return True
    # Tidak ada id maupun jumlah followers -> tidak ada data profil yang berguna.
    return _first(item, _ID_KEYS) is None and _as_int(_first(item, _FOLLOWERS_KEYS)) is None


def to_db_update(row_id: str, item: dict) -> dict:
    """Bentuk payload update untuk satu baris kol_directory."""
    if is_error_item(item):
        return {"id": row_id, "scrape_status": "failed"}

    username = extract_username(item)
    verified = item.get("verified")
    verified_status = None
    if isinstance(verified, bool):
        verified_status = "verified" if verified else "unverified"

    bio = _first(item, _BIO_KEYS)

    return {
        "id": row_id,
        "platform_user_id": str(_first(item, _ID_KEYS)) if _first(item, _ID_KEYS) else None,
        "username": username,
        "username_normalized": username,
        "followers_count": _as_int(_first(item, _FOLLOWERS_KEYS)),
        "engagement_rate": compute_engagement_rate(item),
        "avatar_url": _first(item, _AVATAR_KEYS),
        "profile_url": _first(item, _URL_KEYS)
        or (f"https://www.instagram.com/{username}/" if username else None),
        "bio": bio if isinstance(bio, str) else None,
        "verified_status": verified_status,
        "scrape_status": "success",
    }


def flatten_for_csv(item: dict) -> dict:
    """Versi ringkas satu item untuk file CSV ringkasan."""
    return {
        "username": extract_username(item),
        "platform_user_id": _first(item, _ID_KEYS),
        "full_name": item.get("fullName"),
        "followers_count": _as_int(_first(item, _FOLLOWERS_KEYS)),
        "follows_count": _as_int(item.get("followsCount")),
        "posts_count": _as_int(item.get("postsCount")),
        "engagement_rate": compute_engagement_rate(item),
        "verified": item.get("verified"),
        "is_private": item.get("private"),
        "is_business": item.get("isBusinessAccount"),
        "business_category": item.get("businessCategoryName"),
        "external_url": item.get("externalUrl"),
        "profile_url": _first(item, _URL_KEYS),
        "avatar_url": _first(item, _AVATAR_KEYS),
        "biography": (_first(item, _BIO_KEYS) or "").replace("\n", " ") or None,
        "error": item.get("error"),
        "error_description": item.get("errorDescription"),
    }
