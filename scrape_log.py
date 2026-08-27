"""Catatan hasil scraping per akun ke `public.scheduler_logs`.

Kenapa tabel ini, bukan tabel baru: `scheduler_logs` sudah ada dan sudah punya
`kol_account_id` ber-foreign key ke `public.kol_directory(id)`.

Migration 028 menambahkan tujuh kolom NULLABLE (username, actor,
profiles_processed, posts_fetched, posts_saved, duplicates_skipped,
duration_seconds) untuk kebutuhan Scheduler Engine. Tidak ada tabel, schema,
maupun view logging tambahan: `public.scheduler_logs` adalah satu-satunya
penyimpanan, jadi riwayat post_pipeline dan riwayat scheduler tidak terpecah ke
dua tempat. Keduanya dibedakan lewat `job_name`.

Pemetaan kolom:

    kol_account_id  -> kol_directory.id (NULL untuk baris ringkasan run)
    platform        -> 'instagram' | 'tiktok'
    job_name        -> 'post_scrape' (post_pipeline) | 'scheduled_scrape' (scheduler)
    category        -> 'post' (post_pipeline & pekerjaan post scheduler)
                       'profile' (pekerjaan profile scheduler)
    status          -> 'success' atau salah satu kode di post_errors.ERROR_CODES
    error_message   -> keterangan apa adanya dari actor/exception
    records_synced  -> jumlah baris L0 yang masuk untuk akun itu
    run_id          -> satu uuid per eksekusi pipeline
    started_at / finished_at -> rentang waktu

Sejak migration 028 username punya kolomnya sendiri dan selalu diisi. Untuk
baris yang tidak punya pasangan `kol_directory`, username tetap juga ditulis di
depan `error_message` — perilaku lama dipertahankan supaya baris yang sudah
pernah ditulis dan yang baru bisa dibaca dengan cara yang sama.

**Koneksi sendiri, commit sendiri.** Ini disengaja. Audit menemukan procedure
`sp_sync_*` menulis status 'failed' lalu `RAISE`, sehingga tulisannya ikut
di-rollback dan kegagalan tidak meninggalkan jejak. Logger ini tidak boleh
mengulang kesalahan itu: ia memakai koneksi terpisah dengan autocommit, jadi
apa pun yang terjadi pada transaksi ingest, catatannya tetap ada.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import psycopg2

from config import PostgresConfig
from post_errors import SUCCESS

logger = logging.getLogger(__name__)

TABLE = "public.scheduler_logs"
JOB_NAME = "post_scrape"
CATEGORY = "post"

# Dipakai Scheduler Engine (scheduler_engine.py). Nilai ini yang membedakan
# baris log scheduler dari baris log post_pipeline di tabel yang sama.
SCHEDULER_JOB_NAME = "scheduled_scrape"

# Profile dan post adalah dua pekerjaan terpisah dan dicatat sebagai dua baris,
# walau keduanya bisa berasal dari satu run actor yang sama. Yang menyatukannya
# adalah `run_id`, bukan barisnya digabung.
SCHEDULER_CATEGORY_PROFILE = "profile"
SCHEDULER_CATEGORY_POST = "post"

# Kolom setelah `kol_account_id` ditambahkan migration 028 dan semuanya
# NULLABLE, jadi pemanggil lama yang tidak mengisinya tetap menghasilkan baris
# yang sah.
_INSERT = f"""
    INSERT INTO {TABLE}
        (run_id, job_name, platform, category, status,
         records_synced, error_message, started_at, finished_at, kol_account_id,
         username, actor, profiles_processed, posts_fetched, posts_saved,
         duplicates_skipped, duration_seconds)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
"""


@dataclass
class AccountOutcome:
    """Hasil satu akun dalam satu run scraping."""

    username: str
    platform: str
    status: str
    kol_directory_id: str | None = None
    records: int = 0
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def ok(self) -> bool:
        return self.status == SUCCESS


@dataclass
class LogSummary:
    run_id: str
    written: int = 0
    failed_to_write: int = 0
    by_status: dict[str, int] = field(default_factory=dict)


class ScrapeLogger:
    """Penulis `scheduler_logs` dengan koneksi dan transaksi sendiri.

    Kegagalan menulis log tidak boleh menjatuhkan pipeline: kalau database tidak
    bisa dihubungi, log dicatat ke logger Python dan pipeline jalan terus.
    """

    def __init__(
        self,
        pg: PostgresConfig,
        run_id: str | None = None,
        job_name: str = JOB_NAME,
        category: str = CATEGORY,
    ):
        self._pg = pg
        self.run_id = run_id or str(uuid.uuid4())
        # Scheduler Engine memakai job_name/category sendiri supaya barisnya
        # bisa dipisahkan dari baris post_pipeline tanpa tabel terpisah.
        self._job_name = job_name
        self._category = category
        self._conn = None

    # --- daur hidup koneksi --------------------------------------------------

    def _connection(self):
        if self._conn is not None and self._conn.closed == 0:
            return self._conn
        try:
            conn = psycopg2.connect(connect_timeout=15, **self._pg.as_connect_kwargs())
            # Autocommit: tiap baris log berdiri sendiri dan tidak ikut
            # di-rollback kalau transaksi ingest gagal.
            conn.autocommit = True
            self._conn = conn
        except Exception as exc:  # noqa: BLE001 - log tidak boleh menjatuhkan pipeline
            logger.error("Tidak bisa membuka koneksi untuk %s: %s", TABLE, exc)
            self._conn = None
        return self._conn

    def close(self) -> None:
        if self._conn is not None and self._conn.closed == 0:
            self._conn.close()
        self._conn = None

    def __enter__(self) -> "ScrapeLogger":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # --- penulisan -----------------------------------------------------------

    def _write(
        self,
        *,
        platform: str,
        status: str,
        kol_directory_id: str | None,
        records: int,
        message: str | None,
        started_at: datetime | None,
        finished_at: datetime | None,
        username: str | None = None,
        actor: str | None = None,
        profiles_processed: int | None = None,
        posts_fetched: int | None = None,
        posts_saved: int | None = None,
        duplicates_skipped: int | None = None,
        duration_seconds: float | None = None,
        category: str | None = None,
    ) -> bool:
        conn = self._connection()
        if conn is None:
            return False
        mulai = started_at or datetime.now(timezone.utc)
        selesai = finished_at or datetime.now(timezone.utc)
        if duration_seconds is None:
            duration_seconds = round((selesai - mulai).total_seconds(), 3)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT,
                    (
                        self.run_id,
                        self._job_name,
                        platform,
                        category or self._category,
                        status,
                        records,
                        message,
                        mulai,
                        selesai,
                        kol_directory_id,
                        username,
                        actor,
                        profiles_processed,
                        posts_fetched,
                        # posts_saved menggandakan records_synced dengan sengaja:
                        # kolom lama tetap berarti sama untuk baris post_pipeline,
                        # kolom baru yang dibaca pembaca log scheduler.
                        records if posts_saved is None else posts_saved,
                        duplicates_skipped,
                        duration_seconds,
                    ),
                )
                cur.fetchone()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Gagal menulis %s (status=%s): %s", TABLE, status, exc)
            # Koneksi bisa jadi sudah rusak; paksa buka ulang di panggilan berikut.
            self.close()
            return False

    def log_account(self, outcome: AccountOutcome) -> bool:
        """Satu baris untuk satu akun."""
        message = outcome.message
        if not outcome.kol_directory_id:
            # Tanpa kol_account_id, username tidak bisa di-join balik. Simpan di
            # pesan supaya tetap bisa diaudit.
            prefix = f"[username={outcome.username}] "
            message = prefix + (message or "tidak ada pasangan di kol_directory")
        return self._write(
            platform=outcome.platform,
            status=outcome.status,
            kol_directory_id=outcome.kol_directory_id,
            records=outcome.records,
            message=message,
            started_at=outcome.started_at,
            finished_at=outcome.finished_at,
            username=outcome.username,
        )

    def log_run(
        self,
        *,
        platform: str,
        status: str,
        records: int = 0,
        message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> bool:
        """Baris ringkasan satu run, `kol_account_id` sengaja NULL.

        Dipakai untuk menyimpan id run Apify, id dataset, dan kegagalan yang
        tidak bisa ditimpakan ke satu akun tertentu.
        """
        return self._write(
            platform=platform,
            status=status,
            kol_directory_id=None,
            records=records,
            message=message,
            started_at=started_at,
            finished_at=finished_at,
        )

    def log_cycle(
        self,
        *,
        category: str,
        platform: str,
        status: str,
        username: str | None,
        actor: str | None,
        kol_directory_id: str | None = None,
        profiles_processed: int = 0,
        posts_fetched: int = 0,
        posts_saved: int = 0,
        duplicates_skipped: int = 0,
        message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> bool:
        """Satu baris untuk satu pekerjaan Scheduler Engine.

        `category` WAJIB diisi: `profile` atau `post`. Satu eksekusi menghasilkan
        dua baris dengan `run_id` yang sama, sehingga keduanya bisa ditelusuri
        sebagai satu kesatuan tanpa menggabungkan angkanya.

        Menulis langsung ke `public.scheduler_logs`, termasuk tujuh kolom
        tambahan dari migration 028. Sengaja TIDAK menggantikan
        `log_account`/`log_run` yang masih dipakai post_pipeline.

        Mengembalikan True kalau barisnya masuk. Nilai False berarti log gagal
        ditulis — pemanggil tetap tidak boleh berhenti karenanya.
        """
        return self._write(
            category=category,
            platform=platform,
            status=status,
            kol_directory_id=kol_directory_id,
            records=posts_saved,
            message=message,
            started_at=started_at,
            finished_at=finished_at,
            username=username,
            actor=actor,
            profiles_processed=profiles_processed,
            posts_fetched=posts_fetched,
            posts_saved=posts_saved,
            duplicates_skipped=duplicates_skipped,
        )

    def log_many(self, outcomes) -> LogSummary:
        summary = LogSummary(run_id=self.run_id)
        for outcome in outcomes:
            if self.log_account(outcome):
                summary.written += 1
            else:
                summary.failed_to_write += 1
            summary.by_status[outcome.status] = summary.by_status.get(outcome.status, 0) + 1
        return summary
