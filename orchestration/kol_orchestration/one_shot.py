"""Eksekusi ONE-SHOT: scraping sekali, lalu rantai transformasi L0 -> L2.

TIDAK ADA SCHEDULE DI SINI
==========================
Modul ini sengaja TIDAK mendefinisikan `ScheduleDefinition` apa pun. Requirement
cron 5 menit sudah dibatalkan, dan file `schedules.py` yang dulu memuatnya sudah
dihapus. Yang tersisa hanya job yang harus dijalankan MANUAL — dari UI Dagster
atau CLI. Tidak ada jalur yang bisa memanggil actor sendiri.

DUA JOB, SENGAJA TERPISAH
=========================
    one_shot_scrape_job      berbiaya  — memanggil Apify, jalankan SEKALI
    transform_chain_job      gratis    — hanya SQL, boleh diulang berapa kali pun

Pemisahan ini bukan kosmetik. Rantai transformasi idempoten dan aman diulang;
scraping tidak. Menggabungkan keduanya dalam satu job berarti setiap kali ingin
menjalankan ulang transformasi, Anda ikut membayar actor lagi.

`run_e2e_once.py` di root menjalankan keduanya berurutan dalam satu perintah.

RANTAI TRANSFORMASI
===================
`transform_chain_job` memakai asset yang SUDAH ADA — tidak ada perhitungan
metric yang ditulis ulang. Dagster sendiri yang menjaga urutannya lewat `deps`
antar asset:

    l0_harmonization  instagram_profile, tiktok_profile,
                      instagram_post, tiktok_post
        -> l1_silver  unified_profile -> unified_post
        -> feature    ig/tt_engagement_analysis, ig/tt_post_analysis
        -> l2_gold    kol_profile_card,
                      kol_metric_daily -> kol_metric_monthly
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dagster import (
    AssetKey,
    AssetSelection,
    Failure,
    MetadataValue,
    Output,
    define_asset_job,
    job,
    op,
)

# Kode scraping ada di root project, satu tingkat di atas folder orchestration/.
# Pola yang sama sudah dipakai `assets/audience.py` untuk audience_inference.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scheduler_engine import (  # noqa: E402
    POSTS_PER_TARGET,
    PROFILE_TARGET_LIMIT,
    run_once,
)

SCRAPE_JOB_NAME = "one_shot_scrape_job"
TRANSFORM_JOB_NAME = "transform_chain_job"

#: Asset yang membentuk rantai L0 Harmonization -> L2 Gold. Nama-nama ini harus
#: sama persis dengan `name=` di modul asset masing-masing.
TRANSFORM_ASSETS = (
    # l0_harmonization
    "instagram_profile",
    "tiktok_profile",
    "instagram_post",
    "tiktok_post",
    # l1_silver
    "unified_profile",
    "unified_post",
    # feature
    "ig_engagement_analysis",
    "tt_engagement_analysis",
    "ig_post_analysis",
    "tt_post_analysis",
    # l2_gold
    "kol_profile_card",
    "kol_metric_daily",
    "kol_metric_monthly",
)


# --- job berbiaya: scraping -------------------------------------------------


@op(
    name="scrape_once",
    description=(
        f"Satu eksekusi: {PROFILE_TARGET_LIMIT} profil uji dari kol_directory "
        f"+ maks {POSTS_PER_TARGET} post terbaru per target. Menulis dua baris "
        "ke public.scheduler_logs (category=profile dan category=post). "
        "Tanpa retry otomatis."
    ),
)
def scrape_once_op(context) -> Output[dict]:
    """Panggil `scheduler_engine.run_once` dan terjemahkan hasilnya ke metadata.

    Platform kandidat bisa dibatasi lewat `SCHEDULER_PLATFORM`, dan pekerjaan
    post bisa dilewati lewat `SCHEDULER_SKIP_POSTS=1` — keduanya dari environment
    supaya tidak ada kredensial atau daftar target yang tertanam di definisi job.
    """
    lewati_post = (os.getenv("SCHEDULER_SKIP_POSTS") or "").strip().lower() in {
        "1", "true", "yes", "y", "on"
    }
    hasil_semua = run_once(
        platform=os.getenv("SCHEDULER_PLATFORM") or None,
        with_posts=not lewati_post,
    )

    metadata: dict = {}
    ringkas: dict = {}
    for h in hasil_semua:
        metadata[f"{h.category}.status"] = MetadataValue.text(h.status)
        metadata[f"{h.category}.username"] = MetadataValue.text(h.username or "-")
        metadata[f"{h.category}.actor"] = MetadataValue.text(h.actor)
        metadata[f"{h.category}.targets"] = MetadataValue.int(h.targets)
        metadata[f"{h.category}.profiles_processed"] = MetadataValue.int(h.profiles_processed)
        metadata[f"{h.category}.posts_fetched"] = MetadataValue.int(h.posts_fetched)
        metadata[f"{h.category}.posts_saved"] = MetadataValue.int(h.posts_saved)
        metadata[f"{h.category}.duplicates_skipped"] = MetadataValue.int(h.duplicates_skipped)
        metadata[f"{h.category}.duration_seconds"] = MetadataValue.float(h.duration_seconds)
        if h.error_message:
            metadata[f"{h.category}.error"] = MetadataValue.text(h.error_message)
        ringkas[h.category] = {
            "run_id": h.run_id,
            "status": h.status,
            "username": h.username,
            "posts_saved": h.posts_saved,
            "duplicates_skipped": h.duplicates_skipped,
        }

    if hasil_semua:
        metadata["run_id"] = MetadataValue.text(hasil_semua[0].run_id)

    gagal = [h for h in hasil_semua if not h.ok]
    if gagal or not hasil_semua:
        # Baris public.scheduler_logs sudah ditulis di dalam run_once sebelum
        # baris ini tercapai, jadi menandai run gagal tidak menghilangkan jejak.
        raise Failure(
            description="Eksekusi scraping gagal: "
            + "; ".join(f"{h.category}={h.error_message}" for h in gagal),
            metadata=metadata,
        )

    context.log.info(
        "Scraping selesai. run_id=%s", hasil_semua[0].run_id if hasil_semua else "-"
    )
    return Output(ringkas, metadata=metadata)


@job(
    name=SCRAPE_JOB_NAME,
    description=(
        "ONE-SHOT scraping (BERBIAYA — memanggil Apify). Jalankan manual, sekali. "
        "Setelah selesai, jalankan transform_chain_job."
    ),
)
def one_shot_scrape_job() -> None:
    scrape_once_op()


# --- job gratis: rantai transformasi ----------------------------------------

transform_chain_job = define_asset_job(
    name=TRANSFORM_JOB_NAME,
    selection=AssetSelection.assets(*[AssetKey(n) for n in TRANSFORM_ASSETS]),
    description=(
        "L0 Harmonization -> L1 Silver -> Feature -> L2 Gold memakai asset "
        "existing. Hanya SQL, tidak memanggil actor, aman diulang."
    ),
)

one_shot_jobs = [one_shot_scrape_job, transform_chain_job]

#: Sengaja kosong. Tidak ada schedule apa pun di project ini.
one_shot_schedules: list = []
