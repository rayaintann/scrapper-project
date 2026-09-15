"""Kunci sederhana supaya dua eksekusi prosedur yang sama tidak tumpang tindih.

    from run_lock import RunLock, LockTaken

    try:
        with RunLock("post_scrape_instagram"):
            ...
    except LockTaken as exc:
        print(exc)
        return EXIT_TERKUNCI

============================================================================
KENAPA FILE, BUKAN TABEL
============================================================================

Kebutuhannya: kalau Scheduled Task menjalankan `post_pipeline.py` sementara
eksekusi sebelumnya belum selesai, yang kedua harus BERHENTI -- bukan ikut
memanggil Apify dan menagih dua kali untuk pekerjaan yang sama.

Kunci ini sengaja TIDAK memakai database:

  * Tidak ada tabel baru. Menambah tabel kunci berarti schema baru untuk
    masalah yang tidak butuh schema.
  * Kunci harus bekerja JUSTRU KETIKA database sedang tidak bisa dihubungi.
    Audit 9 September mencatat 1.241 tick sensor gagal karena timeout ke
    Postgres; kalau kunci ikut bergantung pada koneksi itu, ia gagal persis
    saat paling dibutuhkan.
  * Kedua prosedur yang perlu dijaga berjalan di SATU mesin (Scheduled Task
    Windows), jadi kunci selevel host sudah cukup. Kunci terdistribusi akan
    menyelesaikan masalah yang tidak kita punya.

============================================================================
KENAPA `os.open(O_CREAT | O_EXCL)`, BUKAN "cek lalu tulis"
============================================================================

`if not path.exists(): path.write_text(...)` punya celah: dua proses bisa
sama-sama lolos pemeriksaan sebelum salah satunya sempat menulis. `O_EXCL`
memindahkan pemeriksaan-dan-pembuatan ke satu operasi atomik milik sistem
operasi, jadi tepat satu proses yang bisa menang.

============================================================================
KUNCI YATIM (proses mati tanpa sempat membersihkan)
============================================================================

Kalau proses dimatikan paksa (mesin restart, Task Scheduler kill), file kunci
tertinggal dan prosedur itu akan tertolak selamanya. Karena itu file kunci
menyimpan PID penulisnya, dan pemegang berikutnya memeriksa:

    PID masih hidup?  -> kunci sah, menolak jalan
    PID sudah mati?   -> kunci yatim, diambil alih dan dicatat di log

Pemeriksaan PID dilakukan dengan `OpenProcess` lewat ctypes di Windows dan
`os.kill(pid, 0)` di POSIX -- keduanya tidak mengirim sinyal apa pun.

Ada juga batas usia (`max_umur_jam`) sebagai jaring pengaman terakhir untuk
kasus PID didaur ulang sistem operasi: kunci yang lebih tua dari batas itu
dianggap yatim walau PID-nya kebetulan hidup.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: Kunci disimpan di bawah `output/` -- folder yang sudah ada dan sudah
#: di-.gitignore, jadi tidak ada direktori baru yang perlu diurus siapa pun.
DEFAULT_LOCK_DIR = Path(__file__).resolve().parent / "output" / "locks"

#: Jaring pengaman untuk PID yang didaur ulang OS. Longgar dengan sengaja:
#: scraping populasi besar memang bisa berjam-jam, dan kunci yang kedaluwarsa
#: terlalu cepat lebih berbahaya (dua run paralel) daripada kunci yatim yang
#: bertahan sebentar.
DEFAULT_MAX_UMUR_JAM = 12.0

#: Exit code khusus supaya Scheduled Task bisa membedakan "dilewati karena
#: sudah ada yang jalan" dari "gagal". 0 akan menyembunyikan kejadian ini,
#: dan 1 akan membuatnya terlihat seperti kegagalan yang perlu ditindak.
EXIT_TERKUNCI = 75


class LockTaken(RuntimeError):
    """Prosedur yang sama sedang berjalan di proses lain."""


@dataclass(frozen=True)
class InfoKunci:
    pid: int
    dibuat: str
    perintah: str

    @property
    def umur_jam(self) -> float:
        try:
            dibuat = datetime.fromisoformat(self.dibuat)
        except ValueError:
            return 0.0
        if dibuat.tzinfo is None:
            dibuat = dibuat.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dibuat).total_seconds() / 3600.0


def _proses_hidup(pid: int) -> bool:
    """True kalau PID masih ada. Tidak mengirim sinyal apa pun."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        # PROCESS_QUERY_LIMITED_INFORMATION: cukup untuk bertanya, dan tidak
        # butuh hak istimewa seperti PROCESS_QUERY_INFORMATION.
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Ada, tapi milik user lain. Tetap dianggap hidup.
        return True
    return True


class RunLock:
    """Context manager: satu pemegang untuk satu `nama` pada satu mesin."""

    def __init__(
        self,
        nama: str,
        lock_dir: Path | None = None,
        max_umur_jam: float = DEFAULT_MAX_UMUR_JAM,
    ):
        self.nama = nama
        self._dir = Path(lock_dir) if lock_dir else DEFAULT_LOCK_DIR
        self._path = self._dir / f"{nama}.lock"
        self._max_umur_jam = max_umur_jam
        self._dipegang = False

    @property
    def path(self) -> Path:
        return self._path

    def _baca(self) -> InfoKunci | None:
        try:
            isi = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # File kunci rusak atau hilang di antara dua langkah. Diperlakukan
            # sebagai yatim: lebih baik satu run kelewat dari macet selamanya.
            return None
        return InfoKunci(
            pid=int(isi.get("pid", 0)),
            dibuat=str(isi.get("dibuat", "")),
            perintah=str(isi.get("perintah", "")),
        )

    def _rebut_kalau_yatim(self) -> None:
        info = self._baca()
        if info is None:
            self._path.unlink(missing_ok=True)
            return
        if not _proses_hidup(info.pid):
            logger.warning(
                "Kunci %s yatim (PID %d sudah mati, dibuat %s) -- diambil alih.",
                self.nama, info.pid, info.dibuat,
            )
            self._path.unlink(missing_ok=True)
            return
        if info.umur_jam > self._max_umur_jam:
            logger.warning(
                "Kunci %s berumur %.1f jam melebihi batas %.1f jam -- "
                "PID %d dianggap didaur ulang OS, kunci diambil alih.",
                self.nama, info.umur_jam, self._max_umur_jam, info.pid,
            )
            self._path.unlink(missing_ok=True)
            return
        raise LockTaken(
            f"Prosedur '{self.nama}' sedang berjalan di PID {info.pid} "
            f"(mulai {info.dibuat}, {info.umur_jam:.2f} jam lalu). "
            f"Eksekusi ini dilewati supaya tidak ada dua run bersamaan. "
            f"Perintah pemegang kunci: {info.perintah}"
        )

    def acquire(self) -> "RunLock":
        self._dir.mkdir(parents=True, exist_ok=True)
        muatan = json.dumps(
            {
                "pid": os.getpid(),
                "dibuat": datetime.now(timezone.utc).isoformat(),
                "perintah": " ".join(sys.argv)[:500],
                "host": os.environ.get("COMPUTERNAME") or os.uname().nodename
                if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", ""),
            },
            ensure_ascii=False,
        )
        for percobaan in (1, 2):
            try:
                # Atomik: buat-kalau-belum-ada. Inilah keseluruhan kuncinya.
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if percobaan == 2:
                    # Sudah sempat direbut ulang tapi tetap ada -- berarti
                    # proses lain memenangkan perlombaan. Itu jawaban yang sah.
                    info = self._baca()
                    raise LockTaken(
                        f"Prosedur '{self.nama}' sedang berjalan "
                        f"(PID {info.pid if info else '?'})."
                    ) from None
                self._rebut_kalau_yatim()
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(muatan)
            self._dipegang = True
            logger.info("Kunci %s diambil (PID %d).", self.nama, os.getpid())
            return self
        raise LockTaken(f"Prosedur '{self.nama}' sedang berjalan.")

    def release(self) -> None:
        if not self._dipegang:
            return
        # Hanya hapus kalau memang milik proses ini: kalau kunci sempat direbut
        # proses lain, menghapusnya di sini akan membuka pintu untuk run ketiga.
        info = self._baca()
        if info is not None and info.pid != os.getpid():
            logger.warning(
                "Kunci %s sekarang dipegang PID %d, bukan %d -- tidak dihapus.",
                self.nama, info.pid, os.getpid(),
            )
            self._dipegang = False
            return
        self._path.unlink(missing_ok=True)
        self._dipegang = False
        logger.info("Kunci %s dilepas.", self.nama)

    def __enter__(self) -> "RunLock":
        return self.acquire()

    def __exit__(self, *_exc) -> None:
        self.release()


def jalankan_terkunci(nama: str, fungsi, *args, **kwargs) -> int:
    """Jalankan `fungsi` di bawah kunci; kembalikan EXIT_TERKUNCI kalau bentrok.

    Dipakai `main()` tiap entry point supaya pola "kunci -> jalan -> lepas"
    tidak ditulis ulang di lima tempat dengan lima cara berbeda.
    """
    try:
        with RunLock(nama):
            return fungsi(*args, **kwargs)
    except LockTaken as exc:
        # Bukan kegagalan: pesannya masuk stderr dan exit code-nya khusus,
        # supaya riwayat Scheduled Task bisa membedakannya dari error.
        print(f"[dilewati] {exc}", file=sys.stderr)
        logger.warning("Dilewati karena kunci: %s", exc)
        return EXIT_TERKUNCI
