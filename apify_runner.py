"""Inti pemanggilan Apify Actor yang dipakai bersama Instagram dan TikTok.

Bagian yang paling halus di sini adalah penanganan biaya: profil yang sudah
ditagih Apify tidak boleh hilang atau dibayar dua kali. Logika itu ditulis satu
kali di sini supaya perbaikan tidak perlu diterapkan dua kali di dua pipeline.

Turunan cukup menyediakan tiga hal:
    build_input(usernames)  -> dict input actor
    item_username(item)     -> username dari satu item hasil, atau None
    empty_is_failure        -> apakah run "SUCCEEDED tapi 0 item" dianggap gagal
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Sequence

from apify_client import ApifyClient
from apify_client.errors import (
    ForbiddenError,
    InvalidRequestError,
    NotFoundError,
    UnauthorizedError,
)

from config import ApifyConfig

logger = logging.getLogger(__name__)

# Status run Apify yang dianggap selesai sukses.
SUCCEEDED = "SUCCEEDED"

# Error yang tidak akan sembuh dengan diulang: token salah, kredit habis, akses
# ditolak, actor tidak ada, input tidak valid. Mengulanginya hanya membuang waktu
# dan menunda kegagalan yang sudah pasti.
FATAL_ERRORS = (UnauthorizedError, ForbiddenError, NotFoundError, InvalidRequestError)


class ApifyRunError(RuntimeError):
    """Run actor gagal atau tidak menghasilkan dataset."""


class FatalApifyError(RuntimeError):
    """Kegagalan yang tidak mungkin pulih; seluruh pipeline harus berhenti."""


def chunked(items: Sequence[str], size: int) -> list[list[str]]:
    if size <= 0:
        raise ValueError("batch size harus > 0")
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


@dataclass
class BatchResult:
    """Hasil satu run actor untuk satu batch username."""

    batch_index: int
    usernames: list[str]
    run_id: str | None = None
    dataset_id: str | None = None
    status: str | None = None
    cost_usd: float | None = None
    items: list[dict] = field(default_factory=list)
    error: str | None = None
    partial: bool = False
    # Diisi oleh scraper supaya `missing` tahu cara membaca username dari item.
    _username_of: object = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def missing(self) -> list[str]:
        """Username yang dikirim tapi tidak muncul sama sekali di hasil."""
        if self._username_of is None:
            return []
        seen = {u for u in (self._username_of(i) for i in self.items) if u}
        return [u for u in self.usernames if u not in seen]


class ProfileScraper:
    """Menjalankan actor per batch dan menarik item dari dataset-nya."""

    # Diisi turunan.
    empty_is_failure = False
    # Sebagian actor menolak plafon biaya di bawah nilai tertentu. Plafon yang
    # lebih rendah dari ini dinaikkan, bukan dibiarkan menggagalkan run.
    min_charge_usd: float | None = None
    # Kalau run SUCCEEDED tapi sebagian username tidak mengembalikan apa pun,
    # coba lagi khusus yang belum ada hasilnya. Berguna untuk actor yang
    # sesekali diblokir platform (TikTok), tapi mubazir untuk actor yang
    # mengembalikan item error eksplisit untuk akun yang memang tidak ada.
    retry_missing = False
    # Perkiraan waktu per username. Batas waktu run dihitung dari angka ini
    # dikali jumlah username, supaya batch besar tidak dipotong di tengah jalan
    # hanya karena batas tetap yang terlalu pendek.
    seconds_per_username = 10

    def __init__(
        self,
        cfg: ApifyConfig,
        actor_id: str | None = None,
        timeout_secs: int = 900,
        max_retries: int = 2,
        max_charge_usd: float | None = None,
    ):
        self._client = ApifyClient(cfg.token)
        self._cfg = cfg
        self._actor_id = actor_id or cfg.actor_id
        self._timeout_secs = timeout_secs
        self._max_retries = max_retries
        # Batas biaya per run; Apify menghentikan run kalau plafon ini tercapai.
        if (
            max_charge_usd is not None
            and self.min_charge_usd is not None
            and max_charge_usd < self.min_charge_usd
        ):
            logger.info(
                "Plafon biaya dinaikkan dari $%.4f ke $%.2f (minimum yang diterima actor)",
                max_charge_usd,
                self.min_charge_usd,
            )
            max_charge_usd = self.min_charge_usd
        self._max_charge_usd = max_charge_usd

    # --- wajib diisi turunan -------------------------------------------------

    def build_input(self, usernames: Sequence[str]) -> dict:
        raise NotImplementedError

    def item_username(self, item: dict) -> str | None:
        raise NotImplementedError

    # --- inti ----------------------------------------------------------------

    def scrape_batch(self, usernames: Sequence[str], batch_index: int = 0) -> BatchResult:
        """Jalankan actor untuk satu batch, dengan retry kalau run gagal.

        Dua hal penting soal biaya:

        - Kalau run berakhir tidak SUCCEEDED (timeout, kena plafon biaya, dibatalkan),
          dataset-nya bisa sudah berisi sebagian profil yang SUDAH ditagih. Item itu
          tetap diambil, bukan dibuang.
        - Retry hanya mengirim ulang username yang belum ada hasilnya, supaya profil
          yang sudah berhasil tidak dibayar dua kali.

        Melempar FatalApifyError untuk kegagalan yang tidak mungkin pulih.
        """
        result = BatchResult(
            batch_index=batch_index,
            usernames=list(usernames),
            _username_of=self.item_username,
        )
        collected: dict[str, dict] = {}
        last_error: str | None = None

        for attempt in range(1, self._max_retries + 2):
            pending = [u for u in usernames if u not in collected]
            if not pending:
                break

            try:
                logger.info(
                    "Batch %d: menjalankan actor untuk %d username (attempt %d)",
                    batch_index,
                    len(pending),
                    attempt,
                )
                run = self._client.actor(self._actor_id).call(**self._call_kwargs(pending))
                if run is None:
                    raise ApifyRunError("actor.call() tidak mengembalikan run")

                status = getattr(run.status, "value", run.status)
                result.run_id = run.id
                result.dataset_id = run.default_dataset_id
                result.status = status
                if run.usage_total_usd:
                    result.cost_usd = (result.cost_usd or 0.0) + float(run.usage_total_usd)

                # Ambil isi dataset lebih dulu, apa pun statusnya. Run yang gagal
                # di tengah jalan tetap meninggalkan profil yang sudah dibayar.
                salvaged = 0
                if run.default_dataset_id:
                    for item in self._fetch_dataset_items(run.default_dataset_id):
                        key = self.item_username(item)
                        if key and key not in collected:
                            collected[key] = item
                            salvaged += 1

                if status == SUCCEEDED and (salvaged or not self.empty_is_failure):
                    belum = [u for u in usernames if u not in collected]
                    if belum and self.retry_missing and attempt <= self._max_retries:
                        # Run-nya sendiri sukses, tapi sebagian profil tidak
                        # terambil. Untuk TikTok ini biasanya pemblokiran
                        # sementara, jadi layak dicoba lagi.
                        logger.info(
                            "Batch %d: %d username belum ada hasil, mencoba lagi",
                            batch_index,
                            len(belum),
                        )
                        time.sleep(5)
                        continue

                    result.items = list(collected.values())
                    result.error = None
                    result.partial = attempt > 1
                    logger.info(
                        "Batch %d: run %s sukses, %d item (biaya $%.4f)",
                        batch_index,
                        run.id,
                        len(result.items),
                        result.cost_usd or 0.0,
                    )
                    return result

                if status == SUCCEEDED:
                    # Beberapa actor (TikTok) tetap melaporkan SUCCEEDED walau
                    # semua request diblokir dan tidak ada satu pun profil terambil.
                    raise ApifyRunError(
                        "run SUCCEEDED tapi tidak menghasilkan item sama sekali "
                        "(kemungkinan diblokir platform)"
                    )

                raise ApifyRunError(
                    f"run selesai dengan status {status}"
                    + (f"; {salvaged} item terselamatkan dari dataset" if salvaged else "")
                )

            except FATAL_ERRORS as exc:
                # Token salah, kredit habis, atau actor tidak ada: percuma diulang.
                result.items = list(collected.values())
                result.error = f"{type(exc).__name__}: {exc}"
                raise FatalApifyError(
                    f"Batch {batch_index} gagal permanen ({type(exc).__name__}): {exc}"
                ) from exc

            except Exception as exc:  # noqa: BLE001 - batch gagal tidak menghentikan batch lain
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("Batch %d gagal (attempt %d): %s", batch_index, attempt, last_error)
                if attempt <= self._max_retries:
                    backoff = 5 * attempt
                    logger.info(
                        "Retry batch %d dalam %ds (%d username tersisa)",
                        batch_index,
                        backoff,
                        len(usernames) - len(collected),
                    )
                    time.sleep(backoff)

        result.items = list(collected.values())
        if collected:
            # Sebagian berhasil: jangan tandai gagal total, hasilnya tetap dipakai.
            result.partial = True
            result.error = None
            logger.warning(
                "Batch %d selesai sebagian: %d dari %d username (error terakhir: %s)",
                batch_index,
                len(collected),
                len(usernames),
                last_error,
            )
        else:
            result.error = last_error
        return result

    def _run_timeout_secs(self, usernames: Sequence[str]) -> int:
        """Batas waktu run, minimal `timeout_secs` dan menyesuaikan ukuran batch."""
        return max(self._timeout_secs, len(usernames) * self.seconds_per_username)

    def _call_kwargs(self, usernames: Sequence[str]) -> dict:
        batas = self._run_timeout_secs(usernames)
        if batas > self._timeout_secs:
            logger.info(
                "Batas waktu run disesuaikan ke %d detik untuk %d username",
                batas,
                len(usernames),
            )
        kwargs = {
            "run_input": self.build_input(usernames),
            "run_timeout": timedelta(seconds=batas),
            # Log actor tidak diteruskan ke stdout supaya progress pipeline terbaca.
            "logger": None,
        }
        if self._max_charge_usd is not None:
            kwargs["max_total_charge_usd"] = Decimal(str(self._max_charge_usd))
        return kwargs

    def _fetch_dataset_items(self, dataset_id: str) -> list[dict]:
        items: list[dict] = []
        for item in self._client.dataset(dataset_id).iterate_items():
            items.append(item if isinstance(item, dict) else dict(item))
        return items
