"""Wrapper Apify Actor untuk scraping POST Instagram dan VIDEO TikTok.

Logika retry, penyelamatan biaya, dan pelacakan username yang tidak kembali
sudah ada di `apify_runner.ProfileScraper`; di sini hanya bentuk input dan cara
membaca username dari satu item hasil.

Perbedaan penting dari scraper profil: item **error** juga harus bisa dikenali
pemiliknya. Actor Instagram mengembalikan
``{"error": "not_found", "url": "https://www.instagram.com/<user>/"}`` tanpa
`ownerUsername`. Kalau username-nya tidak bisa dibaca dari situ, akun yang gagal
akan tercatat dua kali — sekali sebagai item error tanpa pemilik, sekali lagi
sebagai "tidak muncul di hasil".
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from apify_runner import ProfileScraper
from config import ApifyConfig, TikTokConfig
from transform import extract_username, normalize_username

logger = logging.getLogger(__name__)

DEFAULT_IG_POST_ACTOR = "apify/instagram-scraper"
DEFAULT_TT_VIDEO_ACTOR = "clockworks/tiktok-scraper"

# https://www.instagram.com/<username>/ ... -> <username>
_IG_URL = re.compile(r"instagram\.com/([^/?#]+)", re.I)
# https://www.tiktok.com/@<username>/video/... -> <username>
_TT_URL = re.compile(r"tiktok\.com/@([^/?#]+)", re.I)

_SKIP_PATH = {"p", "reel", "reels", "tv", "explore", "stories", "s"}


def _from_url(value: object, pattern: re.Pattern[str]) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    match = pattern.search(value)
    if not match:
        return None
    candidate = normalize_username(match.group(1))
    if not candidate or candidate in _SKIP_PATH:
        return None
    return candidate


class InstagramPostScraper(ProfileScraper):
    """`apify/instagram-scraper` mode posts, satu profil per URL.

    Actor ini mengembalikan item error eksplisit untuk profil yang tidak ada,
    jadi dataset kosong memang berarti tidak ada hasil dan bukan pemblokiran —
    `empty_is_failure` tetap False, sama seperti scraper profil Instagram.
    """

    empty_is_failure = False
    retry_missing = False
    seconds_per_username = 20

    def __init__(self, cfg: ApifyConfig, results_limit: int = 10, **kwargs):
        actor_id = kwargs.pop("actor_id", None) or DEFAULT_IG_POST_ACTOR
        super().__init__(cfg, actor_id=actor_id, **kwargs)
        self._results_limit = results_limit

    def build_input(self, usernames: Sequence[str]) -> dict:
        return {
            "directUrls": [f"https://www.instagram.com/{u}/" for u in usernames],
            "resultsType": "posts",
            "resultsLimit": self._results_limit,
            "searchType": "user",
            "addParentData": False,
        }

    def item_username(self, item: dict) -> str | None:
        if not isinstance(item, dict):
            return None
        owner = item.get("ownerUsername")
        if isinstance(owner, str) and owner.strip():
            return normalize_username(owner)
        # Item error: pemiliknya hanya ada di URL yang diminta.
        for key in ("inputUrl", "url", "input"):
            found = _from_url(item.get(key), _IG_URL)
            if found:
                return found
        return None


class InstagramDetailsScraper(ProfileScraper):
    """`apify/instagram-scraper` mode **details**: profil + post dalam satu run.

    Kenapa mode ini, bukan dua run terpisah: Scheduler Engine wajib memakai
    `apify/instagram-scraper` untuk profil DAN post. Mode `details`
    mengembalikan satu objek profil per URL yang sudah membawa `latestPosts`,
    jadi satu run memenuhi keduanya dan profilnya hanya ditagih sekali.

    Bentuk field profilnya (`fullName`, `biography`, `externalUrl`,
    `followersCount`, `followsCount`, `postsCount`) identik dengan keluaran
    `apify/instagram-profile-scraper`, sehingga `raw_store.insert_profiles`
    bisa dipakai apa adanya tanpa pemetaan baru.

    `latestPosts` TIDAK membawa `ownerUsername` — pemiliknya hanya diketahui
    dari URL profil yang diminta. `posts_of()` yang menempelkannya, supaya
    `post_raw_store.insert_ig_posts` bisa mengenali pemilik tiap post lewat
    `InstagramPostScraper.item_username` yang sudah ada.
    """

    # Sama seperti scraper profil Instagram: actor mengembalikan item error
    # eksplisit untuk akun yang tidak ada, jadi dataset kosong memang berarti
    # tidak ada hasil dan bukan pemblokiran.
    empty_is_failure = False
    retry_missing = False
    seconds_per_username = 30

    def __init__(self, cfg: ApifyConfig, results_limit: int = 10, **kwargs):
        actor_id = kwargs.pop("actor_id", None) or DEFAULT_IG_POST_ACTOR
        super().__init__(cfg, actor_id=actor_id, **kwargs)
        self._results_limit = results_limit

    def build_input(self, usernames: Sequence[str]) -> dict:
        return {
            "directUrls": [f"https://www.instagram.com/{u}/" for u in usernames],
            "resultsType": "details",
            # Membatasi jumlah `latestPosts` yang dibawa tiap profil.
            "resultsLimit": self._results_limit,
            "searchType": "user",
            "addParentData": False,
        }

    def item_username(self, item: dict) -> str | None:
        if not isinstance(item, dict):
            return None
        # Objek profil membawa `username` langsung.
        found = extract_username(item)
        if found:
            return found
        # Item error hanya membawa URL yang diminta.
        for key in ("inputUrl", "url", "input"):
            found = _from_url(item.get(key), _IG_URL)
            if found:
                return found
        return None

    def posts_of(self, item: dict) -> list[dict]:
        """Post terbaru dari satu item profil, sudah ditempeli `ownerUsername`.

        Item error tidak punya `latestPosts` dan menghasilkan daftar kosong —
        klasifikasinya diserahkan ke `post_errors`, bukan ditebak di sini.
        """
        if not isinstance(item, dict):
            return []
        posts = item.get("latestPosts")
        if not isinstance(posts, list):
            return []
        owner = self.item_username(item)
        hasil = []
        for post in posts:
            if not isinstance(post, dict):
                continue
            if owner and not post.get("ownerUsername"):
                # Salin, jangan ubah item aslinya: `raw_payload` profil harus
                # tetap persis seperti yang dikembalikan actor.
                post = {**post, "ownerUsername": owner}
            hasil.append(post)
        return hasil


class TikTokVideoScraper(ProfileScraper):
    """`clockworks/tiktok-scraper` mode videos, N video per profil.

    Sama seperti scraper profil TikTok: run bisa berakhir SUCCEEDED walau semua
    request diblokir, jadi dataset kosong diperlakukan sebagai kegagalan yang
    layak di-retry.
    """

    empty_is_failure = True
    retry_missing = True
    min_charge_usd = 0.50
    seconds_per_username = 30

    def __init__(self, cfg: TikTokConfig, results_per_page: int = 10, **kwargs):
        actor_id = kwargs.pop("actor_id", None) or cfg.actor_id or DEFAULT_TT_VIDEO_ACTOR
        super().__init__(cfg, actor_id=actor_id, **kwargs)
        self._tiktok = cfg
        self._results_per_page = results_per_page

    def build_input(self, usernames: Sequence[str]) -> dict:
        run_input = {
            "profiles": list(usernames),
            "profileScrapeSections": ["videos"],
            "resultsPerPage": self._results_per_page,
            "excludePinnedPosts": False,
            # Tidak ada file yang perlu diunduh; semuanya menambah biaya.
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadAvatars": False,
            "shouldDownloadMusicCovers": False,
            "shouldDownloadSlideshowImages": False,
            "shouldDownloadSubtitles": False,
        }
        if self._tiktok.proxy_country and self._tiktok.proxy_country != "None":
            run_input["proxyCountryCode"] = self._tiktok.proxy_country
        return run_input

    def item_username(self, item: dict) -> str | None:
        if not isinstance(item, dict):
            return None
        meta = item.get("authorMeta")
        if isinstance(meta, dict):
            for key in ("name", "uniqueId", "nickName"):
                value = meta.get(key)
                if isinstance(value, str) and value.strip():
                    return normalize_username(value)
        for key in ("webVideoUrl", "url", "input", "inputUrl"):
            found = _from_url(item.get(key), _TT_URL)
            if found:
                return found
        return None
