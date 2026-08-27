"""Scraper daftar follower lewat Apify, untuk Instagram dan TikTok.

    Instagram : apify/instagram-followers-following-scraper
    TikTok    : clockworks/tiktok-followers-scraper

Keduanya sevendor dengan actor yang sudah dipakai project ini
(`apify/instagram-profile-scraper`, `clockworks/tiktok-scraper`), jadi bentuk
kredensial dan pola pemanggilannya tidak berubah.

============================================================================
CAP BIAYA -- ALASAN UTAMA MODUL INI DITULIS TERPISAH
============================================================================

Kedua actor menagih PER ITEM yang masuk dataset, bukan per run:

    apify/instagram-followers-following-scraper  $0,00175 / profil  (tier BRONZE)
    clockworks/tiktok-followers-scraper          $0,00100 / hasil   (tier BRONZE)

Artinya salah menaruh limit langsung jadi tagihan. `cristiano` punya 679 juta
follower; tanpa limit, satu akun saja bisa menghabiskan ribuan dolar.

Karena itu limitnya dipasang EMPAT LAPIS, sengaja berlebihan:

  1. Di input actor        -- `resultsLimit` (IG) / `maxFollowersPerProfile` (TT).
                              Ini yang diminta actor untuk berhenti sendiri.
  2. `max_items`           -- dipaksakan PLATFORM Apify, bukan actor. Dataset
                              dipotong di sisi server meski actor mengabaikan
                              limit di input.
  3. `max_total_charge_usd`-- plafon tagihan per run, juga dipaksakan Apify.
                              Run dihentikan begitu plafon tercapai. Ini satu-
                              satunya lapis yang membatasi UANG secara langsung,
                              bukan jumlah item.
  4. Di sisi kita          -- hasil dipotong `[:limit]` setelah diterima, dan
                              `_validasi_limit()` menolak limit di luar 1..100
                              sebelum satu pun request dikirim.

Lapis 1 dan 4 saja tidak cukup: keduanya bergantung pada actor berkelakuan
benar, dan lapis 4 baru bekerja SETELAH item dibuat -- artinya sudah ditagih.
Lapis 2 dan 3 dijalankan Apify sendiri, jadi itu yang benar-benar menjaga
tagihan kalau actor pihak ketiga berperilaku di luar dugaan.

`maxFollowingPerProfile=0` pada TikTok BUKAN default. Actor-nya mewajibkan
kedua field, dan kalau following ikut diambil, tagihannya berlipat untuk data
yang tidak kita pakai sama sekali.

============================================================================
KENAPA TIDAK MEMAKAI ProfileScraper DI apify_runner.py
============================================================================

`ProfileScraper` di sana dibangun untuk pola "satu username -> satu profil":
retry-nya menghitung username yang belum kembali, dan `empty_is_failure`
menganggap dataset kosong sebagai indikasi diblokir.

Follower polanya "satu username -> N follower", dan dataset kosong adalah hasil
yang SAH (akun tanpa follower, atau follower tersembunyi). Memaksakannya ke
kelas itu akan memicu retry berbayar untuk kondisi yang sebenarnya normal.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Any, Sequence

from apify_client import ApifyClient

logger = logging.getLogger(__name__)

# Actor default; bisa dioverride lewat .env tanpa mengubah kode.
DEFAULT_IG_FOLLOWERS_ACTOR = "apify/instagram-followers-following-scraper"
DEFAULT_TT_FOLLOWERS_ACTOR = "clockworks/tiktok-followers-scraper"

# Batas keras. Bukan sekadar default -- limit di luar rentang ini ditolak.
LIMIT_MIN = 1
LIMIT_MAX = 100

# Plafon tagihan PER AKUN, dipaksakan Apify. Dihitung longgar terhadap tarif
# tier BRONZE (IG $0,00175/profil, TT $0,00100/hasil): 100 follower seharusnya
# $0,175 dan $0,10. Plafon $0,50 memberi ruang kalau tarif naik atau tier
# berubah, tapi tetap menghentikan run yang melenceng jauh sebelum jadi mahal.
PLAFON_USD_PER_AKUN = Decimal("0.50")


class FollowerScrapeError(RuntimeError):
    """Gagal mengambil follower untuk satu akun. Akun lain tetap diproses."""


@dataclass
class HasilAkun:
    """Hasil satu akun. `items` sudah dipotong ke limit."""

    username: str
    platform: str
    items: list[dict] = field(default_factory=list)
    error: str | None = None
    run_id: str | None = None
    dataset_id: str | None = None
    # Diisi dari statistik run Apify, bukan ditebak dari jumlah item.
    biaya_usd: float | None = None

    @property
    def berhasil(self) -> bool:
        return self.error is None

    @property
    def jumlah(self) -> int:
        return len(self.items)


def _validasi_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError(f"limit harus int, dapat {type(limit).__name__}")
    if limit < LIMIT_MIN or limit > LIMIT_MAX:
        raise ValueError(
            f"limit {limit} di luar batas aman {LIMIT_MIN}..{LIMIT_MAX}. "
            "Batas ini menjaga tagihan Apify -- naikkan LIMIT_MAX secara sadar "
            "kalau memang diperlukan."
        )
    return limit


def _field(obj: Any, *nama: str) -> Any:
    """Baca field dari objek Run apify-client, apa pun bentuknya.

    apify-client 3.x mengembalikan model Pydantic (`run.id`, `run.status`),
    sedangkan versi 2.x mengembalikan dict (`run["id"]`). Kode ini dipakai di
    kedua jalur supaya upgrade/downgrade klien tidak membuat scrape gagal
    SETELAH actor-nya jalan -- kegagalan di titik itu berarti sudah ditagih
    tapi datanya tidak terambil.
    """
    for n in nama:
        if isinstance(obj, dict):
            if n in obj and obj[n] is not None:
                return obj[n]
        else:
            v = getattr(obj, n, None)
            if v is not None:
                return v
    return None


def _biaya_run(client: ApifyClient, run_id: str) -> float | None:
    """Ambil biaya AKTUAL dari run Apify.

    Dibaca dari `usageTotalUsd` milik run, bukan dihitung dari jumlah item x
    tarif -- tarif berjenjang per tier dan bisa berubah, jadi menghitung sendiri
    hampir pasti meleset.
    """
    try:
        info = client.run(run_id).get()
        if not info:
            return None
        nilai = _field(info, "usage_total_usd", "usageTotalUsd")
        return float(nilai) if nilai is not None else None
    except Exception as exc:  # noqa: BLE001 - biaya tidak boleh menggagalkan scrape
        logger.warning("Gagal membaca biaya run %s: %s", run_id, exc)
        return None


def _jalankan(
    client: ApifyClient,
    actor_id: str,
    run_input: dict[str, Any],
    limit: int,
    timeout_detik: int,
    plafon_usd: Decimal,
) -> tuple[list[dict], str | None, str | None]:
    """Panggil actor sekali, kembalikan (items, run_id, dataset_id).

    `max_items` dan `max_total_charge_usd` adalah lapis 2 dan 3 dari cap biaya:
    keduanya dipaksakan platform Apify, bukan oleh actor.
    """
    run = client.actor(actor_id).call(
        run_input=run_input,
        max_items=limit,
        max_total_charge_usd=plafon_usd,
        run_timeout=timedelta(seconds=timeout_detik),
    )
    if not run:
        raise FollowerScrapeError("Apify tidak mengembalikan info run.")

    status = str(_field(run, "status") or "")
    run_id = _field(run, "id")
    dataset_id = _field(run, "default_dataset_id", "defaultDatasetId")

    # Status bisa berupa enum; bandingkan lewat sufiksnya supaya
    # 'ActorJobStatus.SUCCEEDED' maupun 'SUCCEEDED' sama-sama diterima.
    if not status.endswith("SUCCEEDED"):
        raise FollowerScrapeError(f"Run berakhir dengan status {status!r}.")
    if not dataset_id:
        raise FollowerScrapeError("Run sukses tapi tidak punya dataset.")

    items = list(client.dataset(dataset_id).iterate_items())
    return items, run_id, dataset_id


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------
def scrape_instagram_followers(
    token: str,
    usernames: Sequence[str],
    limit: int,
    actor_id: str = DEFAULT_IG_FOLLOWERS_ACTOR,
    timeout_detik: int = 900,
    jeda_detik: float = 2.0,
    plafon_usd: Decimal = PLAFON_USD_PER_AKUN,
) -> list[HasilAkun]:
    """Ambil hingga `limit` follower per username Instagram.

    SATU RUN PER USERNAME, bukan satu run untuk semua. Alasannya bukan gaya:
    `resultsLimit` actor ini berlaku per username, tapi kalau satu username
    gagal di tengah run gabungan, kita tidak bisa tahu username mana yang
    hasilnya utuh dan mana yang terpotong. Per-username membuat kegagalan satu
    akun tidak mencemari akun lain, dan biayanya sama karena tagihannya per item.
    """
    _validasi_limit(limit)
    client = ApifyClient(token)
    hasil: list[HasilAkun] = []

    for i, username in enumerate(usernames):
        if i:
            time.sleep(jeda_detik)  # jeda sopan antar-run
        h = HasilAkun(username=username, platform="instagram")
        try:
            items, run_id, ds_id = _jalankan(
                client,
                actor_id,
                {
                    "usernames": [username],
                    "dataToScrape": "followers",
                    "resultsLimit": limit,
                },
                limit,
                timeout_detik,
                plafon_usd,
            )
            # Lapis kedua cap: actor bisa saja mengirim lebih.
            h.items = items[:limit]
            h.run_id, h.dataset_id = run_id, ds_id
            h.biaya_usd = _biaya_run(client, run_id) if run_id else None
            logger.info("IG %s: %d follower", username, h.jumlah)
        except Exception as exc:  # noqa: BLE001 - satu akun gagal, lanjut akun lain
            h.error = str(exc)
            logger.warning("IG %s GAGAL: %s", username, exc)
        hasil.append(h)

    return hasil


# ---------------------------------------------------------------------------
# TikTok
# ---------------------------------------------------------------------------
def scrape_tiktok_followers(
    token: str,
    usernames: Sequence[str],
    limit: int,
    actor_id: str = DEFAULT_TT_FOLLOWERS_ACTOR,
    timeout_detik: int = 900,
    jeda_detik: float = 2.0,
    plafon_usd: Decimal = PLAFON_USD_PER_AKUN,
) -> list[HasilAkun]:
    """Ambil hingga `limit` follower per username TikTok.

    `maxFollowingPerProfile=0` disetel eksplisit: actor mewajibkan field itu,
    dan following yang ikut terambil akan ditagih padahal tidak dipakai.
    """
    _validasi_limit(limit)
    client = ApifyClient(token)
    hasil: list[HasilAkun] = []

    for i, username in enumerate(usernames):
        if i:
            time.sleep(jeda_detik)
        h = HasilAkun(username=username, platform="tiktok")
        try:
            items, run_id, ds_id = _jalankan(
                client,
                actor_id,
                {
                    "profiles": [username],
                    "maxFollowersPerProfile": limit,
                    "maxFollowingPerProfile": 0,
                },
                limit,
                timeout_detik,
                plafon_usd,
            )
            h.items = items[:limit]
            h.run_id, h.dataset_id = run_id, ds_id
            h.biaya_usd = _biaya_run(client, run_id) if run_id else None
            logger.info("TT %s: %d follower", username, h.jumlah)
        except Exception as exc:  # noqa: BLE001
            h.error = str(exc)
            logger.warning("TT %s GAGAL: %s", username, exc)
        hasil.append(h)

    return hasil
