"""Brand Match di background: dipicu Brand Profile dan pipeline KOL.

APA INI
=======
Brand Match dihitung oleh Autometric (`src/lib/discover/whatMatters/brandMatch.ts`)
dan disimpan per agency di `public.brand_match_result` (Autometric
`migrations/kol/010`). Modul ini TIDAK menghitung ulang Brand Match di Python --
rumusnya hanya ada satu, di Autometric. Job di sini hanya MEMANGGIL perhitungan
itu (`npm run brand-match:recalc`), sebagai langkah terakhir setelah datanya siap.

DUA PEMICU
==========
1. `brand_profile_changed_sensor` -- Brand Profile disimpan.
   Sidik jari `public.brand_profile` = (count(*), max(updated_at)), pola yang
   sama dengan `l0_raw_new_data_sensor`: cursor bawaan Dagster + run_key dari
   sidik jari, jadi keadaan yang sama tidak diproses dua kali.

2. `brand_match_after_transform` -- `transform_chain_job` SELESAI SUKSES.
   run_status_sensor, jadi Brand Match hanya jalan setelah L2 selesai ditulis --
   tidak pernah di tengah rantai. Run yang gagal tidak memicu apa pun.

`transform_chain_job` dan asset-assetnya TIDAK diubah.

KONSISTENSI & KEGAGALAN
=======================
Perhitungan di Autometric mengunci per agency (advisory lock), membaca versi
profil + sidik jari data sebelum dan sesudah menghitung, dan hanya menulis kalau
keduanya tidak berubah -- jadi hasil tidak pernah campuran versi lama dan baru.
Kalau gagal (mis. DB KOL tidak terjangkau), script keluar dengan kode != 0, op
ini melempar `Failure`, dan RetryPolicy mengulang. Tidak ada hasil yang ditulis
untuk agency yang gagal.

DEFAULT STOPPED
===============
Sama dengan `l0_raw_new_data_sensor`: kedua sensor harus dinyalakan sadar-sadar
(`dagster sensor start ...`), tidak otomatis hidup saat kode di-deploy.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess

from dagster import (
    Backoff,
    DagsterRunStatus,
    DefaultSensorStatus,
    Failure,
    RetryPolicy,
    RunRequest,
    SensorEvaluationContext,
    SensorResult,
    SkipReason,
    job,
    op,
    run_status_sensor,
    sensor,
)

from kol_orchestration.one_shot import transform_chain_job
from kol_orchestration.resources import PostgresResource

JOB_NAME = "brand_match_job"

#: Repo Autometric -- tempat perhitungan Brand Match. Bisa di-override lewat env.
AUTOMETRIC_DIR = os.getenv("AUTOMETRIC_DIR", r"D:\intern\autometric engkol\autometric")

#: Batas waktu satu perhitungan penuh (semua agency x semua creator aktif).
TIMEOUT_SECONDS = 30 * 60

PROFILE_SENSOR = "brand_profile_changed_sensor"
AFTER_TRANSFORM_SENSOR = "brand_match_after_transform"


@op(
    config_schema={"trigger": str},
    retry_policy=RetryPolicy(max_retries=2, delay=60, backoff=Backoff.EXPONENTIAL),
)
def recalculate_brand_match(context) -> dict:
    """Menjalankan `npm run brand-match:recalc -- --all` di repo Autometric."""
    trigger = context.op_config["trigger"]
    npm = shutil.which("npm") or "npm"
    cmd = [npm, "run", "brand-match:recalc", "--", "--all", "--trigger", trigger]
    context.log.info("Menjalankan %s di %s", " ".join(cmd), AUTOMETRIC_DIR)
    try:
        hasil = subprocess.run(cmd, cwd=AUTOMETRIC_DIR, capture_output=True, text=True,
                               timeout=TIMEOUT_SECONDS, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise Failure(description=f"Brand Match melewati batas {TIMEOUT_SECONDS} detik") from exc

    baris = [b for b in (hasil.stdout or "").splitlines() if b.startswith("{")]
    for b in baris:
        context.log.info(b)
    if hasil.returncode != 0:
        raise Failure(
            description=f"brand-match:recalc keluar dengan kode {hasil.returncode}",
            metadata={"stdout_tail": "\n".join((hasil.stdout or "").splitlines()[-20:]),
                      "stderr_tail": "\n".join((hasil.stderr or "").splitlines()[-20:])},
        )
    ringkasan = next((json.loads(b) for b in reversed(baris) if '"summary"' in b), {})
    return {"trigger": trigger, "agencies": ringkasan.get("agencies"), "failed": ringkasan.get("failed")}


@job(
    name=JOB_NAME,
    description=(
        "Menghitung ulang Brand Match semua agency ber-Brand Profile memakai "
        "perhitungan Autometric, lalu menyimpannya di public.brand_match_result. "
        "Dipicu Brand Profile disimpan atau transform_chain_job sukses."
    ),
)
def brand_match_job() -> None:
    recalculate_brand_match()


def _sidik_profil(postgres: PostgresResource) -> str:
    """(count, max(updated_at)) public.brand_profile, sebagai satu string stabil."""
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), COALESCE(max(updated_at)::text, '') "
                        "FROM public.brand_profile")
            n, maks = cur.fetchone()
    finally:
        conn.close()
    return f"{n}|{maks}"


@sensor(
    name=PROFILE_SENSOR,
    job=brand_match_job,
    minimum_interval_seconds=30,
    default_status=DefaultSensorStatus.STOPPED,
    description="Brand Profile berubah (count/max(updated_at)) -> brand_match_job.",
)
def brand_profile_changed_sensor(context: SensorEvaluationContext,
                                 postgres: PostgresResource) -> SensorResult:
    sidik = _sidik_profil(postgres)
    if context.cursor == sidik:
        return SensorResult(skip_reason=SkipReason("Brand Profile tidak berubah."), cursor=sidik)
    # Kunci dari PERUBAHAN (lama -> baru), bukan dari keadaan baru saja: tabel
    # bisa kembali ke keadaan lama (mis. profil dihapus -> "0|"), dan run_key yang
    # sama akan ditolak Dagster -- hasil profil yang dihapus tidak akan dibersihkan.
    kunci = "profil:" + hashlib.sha256(f"{context.cursor}->{sidik}".encode()).hexdigest()[:24]
    context.log.info("Brand Profile berubah (%s -> %s).", context.cursor, sidik)
    return SensorResult(
        run_requests=[RunRequest(
            run_key=kunci,
            run_config={"ops": {"recalculate_brand_match": {"config": {"trigger": "brand_profile"}}}},
            tags={"brand_match/trigger": "brand_profile", "brand_match/profile_fingerprint": sidik},
        )],
        cursor=sidik,
    )


@run_status_sensor(
    name=AFTER_TRANSFORM_SENSOR,
    run_status=DagsterRunStatus.SUCCESS,
    monitored_jobs=[transform_chain_job],
    request_job=brand_match_job,
    minimum_interval_seconds=30,
    default_status=DefaultSensorStatus.STOPPED,
    description="transform_chain_job sukses (L2 selesai) -> brand_match_job.",
)
def brand_match_after_transform(context):
    run_id = context.dagster_run.run_id
    return RunRequest(
        run_key=f"setelah-transform:{run_id}",
        run_config={"ops": {"recalculate_brand_match": {"config": {"trigger": "kol_data"}}}},
        tags={"brand_match/trigger": "kol_data", "brand_match/after_run": run_id},
    )


brand_match_jobs = [brand_match_job]
brand_match_sensors = [brand_profile_changed_sensor, brand_match_after_transform]
