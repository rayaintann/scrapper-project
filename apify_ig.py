"""Wrapper Apify Actor apify/instagram-profile-scraper.

Logika retry dan penyelamatan biaya ada di apify_runner.ProfileScraper; di sini
hanya bentuk input dan cara membaca username dari item hasil.
"""

import logging
from typing import Sequence

from apify_runner import (  # noqa: F401 - dire-export agar import lama tetap jalan
    ApifyRunError,
    BatchResult,
    FatalApifyError,
    ProfileScraper,
    chunked,
)
from transform import extract_username

logger = logging.getLogger(__name__)


class InstagramProfileScraper(ProfileScraper):
    """apify/instagram-profile-scraper: input berupa daftar `usernames`."""

    # Actor ini mengembalikan item error (not_found) untuk username yang tidak
    # ada, jadi dataset kosong memang berarti tidak ada hasil, bukan diblokir.
    empty_is_failure = False

    def build_input(self, usernames: Sequence[str]) -> dict:
        return {
            "usernames": list(usernames),
            "includeAboutSection": self._cfg.include_about_section,
        }

    def item_username(self, item: dict) -> str | None:
        return extract_username(item)
