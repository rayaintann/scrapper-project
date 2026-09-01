"""Sensor Dagster: L0 RAW berisi data baru -> jalankan `transform_chain_job`.

TIDAK ADA SCHEDULE / CRON DI SINI
=================================
Modul ini memakai `@sensor`, bukan `ScheduleDefinition`. Sensor bereaksi pada
KEADAAN DATA (ada baris baru di `l0_raw`), bukan pada jam dinding. Kalau tidak
ada data baru, tidak ada run -- walau sensor dievaluasi terus-menerus.
`minimum_interval_seconds` di bawah HANYA mengatur seberapa sering sensor boleh
MENGECEK; ia bukan jadwal eksekusi dan tidak pernah menghasilkan run sendiri.

SENSOR INI TIDAK PERNAH MEMANGGIL APIFY
=======================================
Yang dijalankan sensor hanya satu SELECT agregat read-only ke `l0_raw`, lalu
`transform_chain_job` -- asset job yang isinya murni SQL transformasi. Scraping
tetap terpisah di `one_shot_scrape_job` dan `scheduler_engine.py`, dan modul ini
sengaja TIDAK mengimpor satu pun modul `apify_*`.

BAGAIMANA "DATA BARU" DIKENALI
==============================
Ini bagian yang paling gampang salah, jadi pilihannya dijelaskan lengkap.

Yang TIDAK dipakai, dan alasannya:

    id (uuid)          `DEFAULT gen_random_uuid()` -- acak, tidak monoton.
                       Tidak ada urutan yang bisa dijadikan watermark.
    scrape_run_id      uuid acak juga; tidak bisa diurutkan.
    now() / waktu tick Selalu berubah tiap evaluasi, jadi sensor akan trigger
                       terus-menerus walau tidak ada data baru sama sekali.
    ukuran/mtime tabel Ikut berubah karena VACUUM dan ANALYZE, bukan hanya
                       karena data baru.

Yang DIPAKAI -- sidik jari dua bagian per tabel:

    count(*)           Seluruh penulis `l0_raw` (raw_store.py, post_raw_store.py,
                       tt_raw_store.py) hanya melakukan INSERT; tidak ada satu
                       pun `ON CONFLICT ... DO UPDATE` ke schema ini. Tabelnya
                       append-only, jadi jumlah baris naik TEPAT ketika ada data
                       baru, dan diam ketika tidak ada.

    max(fetched_at)    Diisi `datetime.now(utc)` SEKALI saat baris mendarat di
                       database, lalu tidak pernah di-update. Jadi nilainya
                       stabil untuk data yang sama, dan naik hanya kalau ada
                       baris baru. Kolom ini ada di kedelapan tabel sumber.

Keduanya dipakai bersama supaya kasus langka "jumlah baris kebetulan sama"
(mis. sebagian baris dihapus manual lalu masuk baris baru) tetap terdeteksi.
Keduanya kolom/agregat yang SUDAH ADA -- tidak ada kolom, tabel, atau tabel log
baru yang dibuat untuk sensor ini.

ANTI-TRIGGER BERULANG (dua lapis, keduanya bawaan Dagster)
==========================================================
1. CURSOR. Sidik jari terakhir yang sudah ditindaklanjuti disimpan di cursor
   sensor bawaan Dagster (`SensorResult(cursor=...)`), bukan di tabel sendiri.
   Tick berikutnya membandingkan sidik jari baru dengan isi cursor; kalau sama,
   hasilnya `SkipReason` dan tidak ada run.

2. RUN KEY. `RunRequest.run_key` adalah hash dari sidik jari itu sendiri. Dagster
   menolak membuat run kedua untuk run_key yang sudah pernah dipakai sensor ini.
   Jadi walau cursor hilang (mis. instance di-reset), keadaan data yang sama
   tetap tidak akan ditransformasi dua kali.

TICK PERTAMA = BASELINE, BUKAN TRIGGER
======================================
Saat cursor masih kosong, sensor belum punya pembanding: seluruh isi `l0_raw`
akan terlihat "baru", padahal mungkin sudah lama ditransformasi. Karena itu tick
pertama hanya MENCATAT sidik jari dan skip. Data lama yang belum pernah diolah
tinggal dikejar sekali dengan menjalankan `transform_chain_job` manual -- job itu
gratis dan idempoten.

TABEL YANG DIPANTAU
===================
Hanya delapan tabel yang benar-benar jadi sumber rantai transformasi, yaitu
pasangan `_apify` + `_official` yang dibaca keempat procedure harmonization.
Tabel `l0_raw` lain (comments, stories, tagged_posts, followers, roster) sengaja
TIDAK dipantau: tidak ada asset di `transform_chain_job` yang membacanya, jadi
memicu rantai karenanya hanya menghasilkan run kosong.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from dagster import (
    DefaultSensorStatus,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    sensor,
)

from kol_orchestration.one_shot import TRANSFORM_JOB_NAME, transform_chain_job
from kol_orchestration.resources import PostgresResource

SENSOR_NAME = "l0_raw_new_data_sensor"

#: Versi format cursor. Dinaikkan kalau bentuk sidik jari berubah, supaya cursor
#: lama tidak salah dibaca sebagai format baru (dan sebaliknya).
CURSOR_VERSION = 1

#: Interval MINIMUM antar-pengecekan, bukan jadwal. Sensor tidak menghasilkan
#: run kalau sidik jari tidak berubah, seberapa sering pun ia dievaluasi.
MINIMUM_INTERVAL_SECONDS = 60

#: Tabel `l0_raw` yang benar-benar jadi sumber `transform_chain_job`.
#: Urutannya dipertahankan supaya SQL dan cursor deterministik.
#: Kedelapan tabel ini punya kolom `fetched_at` -- sudah diverifikasi langsung
#: ke information_schema, bukan diasumsikan.
TABEL_DIPANTAU: tuple[str, ...] = (
    "ig_profile_apify",
    "ig_profile_official",
    "tt_profile_apify",
    "tt_profile_official",
    "ig_media_snapshots_apify",
    "ig_media_snapshots_official",
    "tt_video_apify",
    "tt_video_official",
)

SCHEMA = "l0_raw"


@dataclass(frozen=True)
class Sidik:
    """Sidik jari satu tabel `l0_raw` pada satu saat.

    `baris`     jumlah baris; naik hanya kalau ada INSERT (tabelnya append-only).
    `watermark` `max(fetched_at)`; waktu baris TERBARU mendarat di database.
                None kalau tabelnya kosong atau kolomnya belum pernah diisi.
    """

    baris: int
    watermark: datetime | None

    def lebih_baru_dari(self, lama: "Sidik | None") -> bool:
        """True kalau sidik ini menandakan ada data baru dibanding `lama`.

        Sengaja HANYA arah maju. Jumlah baris yang BERKURANG (mis. seseorang
        menghapus baris manual) bukan "data baru" dan tidak boleh memicu
        transformasi -- cursor tetap diperbarui supaya sensor tidak tersangkut
        membandingkan dengan angka yang sudah tidak ada.
        """
        if lama is None:
            return self.baris > 0
        if self.baris > lama.baris:
            return True
        if self.watermark is None:
            return False
        if lama.watermark is None:
            return True
        return self.watermark > lama.watermark


def sql_sidik_jari(tabel: tuple[str, ...] = TABEL_DIPANTAU) -> str:
    """SQL satu-jalan yang mengambil sidik jari semua tabel sekaligus.

    Satu round-trip, dan seluruhnya read-only: hanya `count` dan `max`. Nama
    tabel di-interpolasi dari konstanta modul ini saja -- tidak pernah dari
    input pengguna atau dari database.
    """
    bagian = [
        "SELECT '{t}' AS tabel, count(*) AS baris, max(fetched_at) AS watermark "
        "FROM {s}.{t}".format(t=t, s=SCHEMA)
        for t in tabel
    ]
    return "\nUNION ALL\n".join(bagian)


def ambil_sidik_jari(postgres: PostgresResource,
                     tabel: tuple[str, ...] = TABEL_DIPANTAU) -> dict[str, Sidik]:
    """Baca sidik jari terkini dari database. READ-ONLY, tidak menulis apa pun."""
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql_sidik_jari(tabel))
            baris = cur.fetchall()
    finally:
        conn.close()
    return {nama: Sidik(baris=int(n), watermark=w) for nama, n, w in baris}


# --- cursor: satu-satunya state sensor, memakai mekanisme bawaan Dagster ----


def tulis_cursor(sidik: dict[str, Sidik]) -> str:
    """Serialisasi sidik jari jadi string cursor Dagster.

    Kunci diurutkan supaya keadaan data yang sama selalu menghasilkan string
    yang sama -- itu yang membuat `run_key` di bawah stabil.
    """
    return json.dumps(
        {
            "versi": CURSOR_VERSION,
            "tabel": {
                nama: {
                    "baris": s.baris,
                    "watermark": s.watermark.isoformat() if s.watermark else None,
                }
                for nama, s in sorted(sidik.items())
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def baca_cursor(mentah: str | None) -> dict[str, Sidik] | None:
    """Kebalikan `tulis_cursor`. None kalau cursor kosong atau tidak terbaca.

    Cursor yang rusak atau berversi lain diperlakukan seperti cursor kosong:
    tick itu jadi baseline lagi. Lebih aman daripada menebak isinya dan salah
    memutuskan ada/tidaknya data baru. Kalaupun baseline ini melewatkan satu
    run, `run_key` masih mencegah run ganda untuk data yang sama.
    """
    if not mentah:
        return None
    try:
        isi = json.loads(mentah)
    except (ValueError, TypeError):
        return None
    if not isinstance(isi, dict) or isi.get("versi") != CURSOR_VERSION:
        return None
    tabel = isi.get("tabel")
    if not isinstance(tabel, dict):
        return None

    hasil: dict[str, Sidik] = {}
    for nama, nilai in tabel.items():
        if not isinstance(nilai, dict):
            return None
        try:
            w = nilai.get("watermark")
            hasil[nama] = Sidik(
                baris=int(nilai["baris"]),
                watermark=datetime.fromisoformat(w) if w else None,
            )
        except (KeyError, TypeError, ValueError):
            return None
    return hasil


def kunci_run(sidik: dict[str, Sidik]) -> str:
    """`run_key` deterministik dari keadaan data, bukan dari waktu.

    Keadaan `l0_raw` yang sama SELALU menghasilkan kunci yang sama, dan Dagster
    menolak run kedua dengan run_key yang sudah pernah dipakai sensor ini. Jadi
    ini lapis pengaman kedua di luar cursor: cursor hilang pun, data yang sama
    tidak ditransformasi ulang.
    """
    sidik_jari = tulis_cursor(sidik).encode("utf-8")
    return "l0raw-" + hashlib.sha256(sidik_jari).hexdigest()[:16]


def tabel_dengan_data_baru(lama: dict[str, Sidik] | None,
                           baru: dict[str, Sidik]) -> list[str]:
    """Nama tabel yang punya data baru dibanding cursor sebelumnya.

    Fungsi murni, tanpa database dan tanpa Dagster -- supaya keputusan
    trigger/tidak-trigger bisa diuji sendiri.
    """
    if lama is None:
        return []
    return sorted(
        nama for nama, s in baru.items() if s.lebih_baru_dari(lama.get(nama))
    )


def _ringkas(sidik: dict[str, Sidik], nama_tabel: list[str]) -> str:
    return ", ".join("{}={} baris".format(n, sidik[n].baris) for n in nama_tabel)


# --- sensor -----------------------------------------------------------------


@sensor(
    name=SENSOR_NAME,
    job=transform_chain_job,
    minimum_interval_seconds=MINIMUM_INTERVAL_SECONDS,
    # STOPPED: sensor harus dinyalakan sadar-sadar dari UI atau CLI. Tidak ada
    # yang mulai berjalan hanya karena kode ini di-deploy.
    default_status=DefaultSensorStatus.STOPPED,
    description=(
        "Event-based, BUKAN schedule. Mendeteksi baris baru di 8 tabel sumber "
        "l0_raw lewat sidik jari (count(*), max(fetched_at)), lalu menjalankan "
        + TRANSFORM_JOB_NAME + ": L0 RAW -> L0 Harmonization -> L1 Silver -> "
        "Feature -> L2 Gold. Tidak pernah memanggil Apify; scraping tetap "
        "terpisah di one_shot_scrape_job."
    ),
)
def l0_raw_new_data_sensor(context: SensorEvaluationContext,
                           postgres: PostgresResource) -> SensorResult:
    """Satu tick: baca sidik jari, bandingkan dengan cursor, putuskan.

    Cursor SELALU ikut ditulis di hasil -- termasuk saat skip -- supaya keadaan
    yang sudah dilihat tidak dievaluasi ulang dari nol di tick berikutnya.
    Dagster menyimpan cursor dan membuat run dalam satu langkah, jadi tidak ada
    celah "cursor sudah maju tapi run gagal dibuat".
    """
    sekarang = ambil_sidik_jari(postgres)
    sebelumnya = baca_cursor(context.cursor)
    cursor_baru = tulis_cursor(sekarang)

    if sebelumnya is None:
        total = sum(s.baris for s in sekarang.values())
        context.log.info(
            "Tick baseline: mencatat %d baris di %d tabel l0_raw tanpa memicu run.",
            total, len(sekarang),
        )
        return SensorResult(
            skip_reason=SkipReason(
                "Tick pertama (atau cursor di-reset): {} baris di {} tabel l0_raw "
                "dicatat sebagai baseline, tanpa memicu run. Kalau data L0 yang "
                "sudah ada belum pernah diolah, jalankan {} manual sekali -- job "
                "itu gratis dan aman diulang.".format(
                    total, len(sekarang), TRANSFORM_JOB_NAME
                )
            ),
            cursor=cursor_baru,
        )

    baru = tabel_dengan_data_baru(sebelumnya, sekarang)
    if not baru:
        return SensorResult(
            skip_reason=SkipReason(
                "Tidak ada data baru di l0_raw: jumlah baris dan max(fetched_at) "
                "kedelapan tabel sumber sama dengan tick sebelumnya. {} tidak "
                "dijalankan.".format(TRANSFORM_JOB_NAME)
            ),
            # Cursor tetap ditulis ulang: kalau ada tabel yang jumlah barisnya
            # BERKURANG (bukan data baru), pembandingnya ikut turun sehingga
            # sensor tidak tersangkut pada angka yang sudah tidak ada.
            cursor=cursor_baru,
        )

    run_key = kunci_run(sekarang)
    context.log.info(
        "Data baru di l0_raw (%s). Memicu %s dengan run_key=%s.",
        _ringkas(sekarang, baru), TRANSFORM_JOB_NAME, run_key,
    )
    return SensorResult(
        run_requests=[
            RunRequest(
                run_key=run_key,
                tags={
                    "l0_raw/tabel_baru": ",".join(baru)[:400],
                    "l0_raw/pemicu": SENSOR_NAME,
                },
            )
        ],
        cursor=cursor_baru,
    )


#: Didaftarkan di `repository.py`. Daftar, bukan objek tunggal, supaya menambah
#: sensor berikutnya tidak perlu mengubah bentuk impor di repository.
l0_raw_sensors = [l0_raw_new_data_sensor]
