"""Wrapper Apify Actor clockworks/tiktok-scraper."""

import logging
from typing import Sequence

from apify_runner import ProfileScraper
from config import TikTokConfig
from tiktok_transform import extract_username

logger = logging.getLogger(__name__)


class TikTokProfileScraper(ProfileScraper):
    """clockworks/tiktok-scraper: input berupa daftar `profiles`.

    Berbeda dari actor Instagram, actor ini tetap melaporkan status SUCCEEDED
    walaupun seluruh request diblokir TikTok dan tidak ada satu pun profil
    terambil. Karena itu dataset kosong diperlakukan sebagai kegagalan yang
    layak di-retry, bukan sebagai "memang tidak ada hasil".
    """

    empty_is_failure = True

    # Actor ini menolak max_total_charge_usd di bawah $0.50. Ini plafon, bukan
    # tagihan: biaya sebenarnya tetap dihitung per hasil.
    min_charge_usd = 0.50

    # Pemblokiran TikTok bersifat intermiten: profil yang gagal pada satu run
    # sering berhasil pada run berikutnya. Retry hanya untuk yang belum kembali,
    # jadi profil yang sudah didapat tidak dibayar ulang.
    retry_missing = True

    # Terukur dari run nyata: TikTok butuh ~10 detik per profil karena melewati
    # residential proxy. Batas 15 menit yang tetap membuat batch 50 terpotong di
    # profil ke-36. Angka 30 detik memberi kelonggaran untuk profil yang lambat.
    seconds_per_username = 30

    def __init__(self, cfg: TikTokConfig, **kwargs):
        # ProfileScraper hanya memakai .token dan .actor_id dari config.
        super().__init__(cfg, actor_id=cfg.actor_id, **kwargs)
        self._tiktok = cfg

    def build_input(self, usernames: Sequence[str]) -> dict:
        run_input = {
            "profiles": list(usernames),
            "profileScrapeSections": ["videos"],
            # Data profil menempel di authorMeta setiap video, jadi satu video
            # per profil sudah cukup — dan tiap video dihitung sebagai satu
            # hasil berbayar, jadi angka ini yang menentukan biaya.
            "resultsPerPage": self._tiktok.results_per_page,
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
            # Tanpa residential proxy, TikTok memblokir hampir semua request dan
            # run berakhir SUCCEEDED dengan 0 profil.
            run_input["proxyCountryCode"] = self._tiktok.proxy_country
        return run_input

    def item_username(self, item: dict) -> str | None:
        return extract_username(item)
