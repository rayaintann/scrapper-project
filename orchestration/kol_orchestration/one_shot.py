"""Eksekusi ONE-SHOT: scraping sekali, lalu rantai transformasi L0 -> L2.

TIDAK ADA SCHEDULE DI SINI
==========================
Modul ini sengaja TIDAK mendefinisikan `ScheduleDefinition` apa pun. Requirement
cron 5 menit sudah dibatalkan, dan file `schedules.py` yang dulu memuatnya sudah
dihapus. Yang tersisa hanya job yang harus dijalankan MANUAL — dari UI Dagster
atau CLI. Tidak ada jalur yang bisa memanggil actor sendiri.

DUA JOB, SATU RANTAI
====================
    one_shot_scrape_job      berbiaya  — Apify -> L0 RAW -> ... -> L2 Gold
    transform_chain_job      gratis    — hanya L0 -> L2, boleh diulang

`one_shot_scrape_job` berisi DUA op berurutan:

    scrape_once_op  ->  transform_to_gold_op

Urutan dijamin oleh aliran data antar-op: `transform_to_gold_op` menerima
keluaran `scrape_once_op` sebagai argumen, jadi Dagster tidak akan menjalankannya
sebelum scraping selesai. Kalau scraping gagal, `scrape_once_op` melempar
`Failure` dan op transformasi TIDAK dijalankan sama sekali — data L0 yang tidak
berubah tidak perlu diolah ulang.

`transform_chain_job` tetap ada dan berdiri sendiri. Rantai transformasi
idempoten dan gratis, jadi harus bisa dijalankan ulang tanpa memanggil actor
lagi — misalnya setelah memperbaiki procedure, atau untuk menyusul data L0 yang
masuk lewat jalur lain.

`run_e2e_once.py` di root memakai fungsi yang sama (`jalankan_transform_chain`),
sehingga jalur CLI dan jalur Dagster tidak bisa berbeda perilaku.

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
    In,
    MetadataValue,
    Nothing,
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
    "post_metric",
    "content_format_daily",
)


# --- rantai transformasi (dipakai op Dagster DAN CLI) -----------------------


def _semua_asset():
    """Seluruh objek asset yang terdaftar, diambil dari modulnya langsung.

    Tidak lewat `repository.py` supaya tidak terjadi impor melingkar —
    `repository` yang mengimpor modul ini, bukan sebaliknya.
    """
    from kol_orchestration.assets.audience import audience_assets
    from kol_orchestration.assets.feature_engagement import feature_engagement_assets
    from kol_orchestration.assets.feature_post import feature_post_assets
    from kol_orchestration.assets.followers import follower_assets
    from kol_orchestration.assets.gold import gold_assets
    from kol_orchestration.assets.gold_post import gold_post_assets
    from kol_orchestration.assets.gold_profile import gold_profile_assets
    from kol_orchestration.assets.harmonization import harmonization_assets
    from kol_orchestration.assets.silver import silver_assets

    return [
        *harmonization_assets, *silver_assets,
        *feature_engagement_assets, *feature_post_assets,
        *gold_assets, *gold_post_assets, *gold_profile_assets,
        *follower_assets, *audience_assets,
    ]


def jalankan_transform_chain(logger=None):
    """Materialize 15 asset L0 Harmonization -> L2 Gold. Tidak memanggil actor.

    Memakai definisi asset yang sama persis dengan yang dipakai UI Dagster, jadi
    tidak ada perhitungan metric yang ditulis ulang di sini. Urutan antar layer
    dijaga Dagster lewat `deps` antar asset.

    Seluruh asset memakai `ON CONFLICT ... DO UPDATE` dengan kunci unik yang
    jelas, sehingga menjalankan ini berkali-kali tidak menghasilkan duplikat.

    Mengembalikan `(sukses, daftar_ringkasan_per_asset)`.
    """
    from dagster import materialize

    # Diimpor saat dipanggil: `repository` mengimpor modul ini, jadi impor di
    # puncak modul akan melingkar.
    from kol_orchestration.repository import _build_connection_string
    from kol_orchestration.resources import PostgresResource

    hasil = materialize(
        assets=_semua_asset(),
        selection=[AssetKey(n) for n in TRANSFORM_ASSETS],
        resources={"postgres": PostgresResource(
            connection_string=_build_connection_string()
        )},
        raise_on_error=False,
    )

    ringkasan = []
    for ev in hasil.get_asset_materialization_events():
        mat = ev.event_specific_data.materialization
        nama = mat.asset_key.to_user_string()
        detail = ", ".join(
            f"{k}={v.value}" for k, v in list(mat.metadata.items())[:3]
            if hasattr(v, "value") and not isinstance(v.value, (dict, list))
        )
        baris = f"{nama}: {detail}"
        ringkasan.append(baris)
        if logger:
            logger.info("  OK %s", baris[:120])

    if not hasil.success:
        gagal = [e.step_key for e in hasil.all_events
                 if e.event_type_value == "STEP_FAILURE"]
        if logger:
            logger.error("Rantai transformasi GAGAL: %s", ", ".join(gagal) or "(lihat log)")
    return hasil.success, ringkasan


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


@op(
    name="transform_to_gold",
    description=(
        "L0 RAW -> L0 Harmonization -> L1 Silver -> Feature -> L2 Gold "
        "memakai 13 asset existing. Tidak memanggil actor, idempoten."
    ),
    ins={"hasil_scrape": In(dagster_type=Nothing)},
)
def transform_to_gold_op(context) -> Output[dict]:
    """Jalankan rantai transformasi setelah scraping selesai.

    `hasil_scrape` bertipe `Nothing`: nilainya tidak dipakai, keberadaannya
    hanya untuk memberi tahu Dagster bahwa op ini bergantung pada
    `scrape_once_op` dan tidak boleh berjalan lebih dulu.

    Op ini TIDAK akan dijalankan kalau scraping gagal, karena `scrape_once_op`
    melempar `Failure` dan Dagster menghentikan langkah di hilirnya.
    """
    context.log.info("Scraping selesai. Menjalankan rantai transformasi L0 -> L2.")
    sukses, ringkasan = jalankan_transform_chain(logger=context.log)

    metadata = {
        "asset_dimaterialisasi": MetadataValue.int(len(ringkasan)),
        "asset_diminta": MetadataValue.int(len(TRANSFORM_ASSETS)),
        "ringkasan": MetadataValue.md(
            "\n".join(f"- `{b}`" for b in ringkasan) or "_(tidak ada)_"
        ),
    }
    if not sukses:
        raise Failure(
            description=(
                "Rantai transformasi gagal. Data L0 RAW hasil scraping sudah "
                "tersimpan dan tidak hilang — jalankan transform_chain_job "
                "untuk mengulang tanpa memanggil actor lagi."
            ),
            metadata=metadata,
        )

    return Output(
        {"asset_dimaterialisasi": len(ringkasan), "sukses": True},
        metadata=metadata,
    )


@job(
    name=SCRAPE_JOB_NAME,
    description=(
        "ONE-SHOT (BERBIAYA — memanggil Apify): scraping 1 profil + maks 10 post, "
        "lalu OTOMATIS meneruskan L0 RAW -> Harmonization -> L1 -> Feature -> "
        "L2 Gold. Jalankan manual, sekali. Tanpa retry actor."
    ),
)
def one_shot_scrape_job() -> None:
    # Keluaran op pertama jadi masukan op kedua: itulah yang membuat Dagster
    # menjalankannya berurutan, bukan paralel.
    transform_to_gold_op(scrape_once_op())


# --- job gratis: rantai transformasi ----------------------------------------

transform_chain_job = define_asset_job(
    name=TRANSFORM_JOB_NAME,
    selection=AssetSelection.assets(*[AssetKey(n) for n in TRANSFORM_ASSETS]),
    description=(
        "L0 Harmonization -> L1 Silver -> Feature -> L2 Gold memakai asset "
        "existing. Hanya SQL, tidak memanggil actor, aman diulang. Job ini "
        "berdiri sendiri: one_shot_scrape_job sudah menjalankan rantai yang "
        "sama secara otomatis, tapi job ini tetap ada untuk mengulang "
        "transformasi tanpa biaya."
    ),
)

one_shot_jobs = [one_shot_scrape_job, transform_chain_job]

#: Sengaja kosong. Tidak ada schedule apa pun di project ini.
one_shot_schedules: list = []
