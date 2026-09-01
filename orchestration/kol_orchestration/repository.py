"""Titik masuk Dagster untuk pipeline KOL.

Di sinilah seluruh asset, job, schedule, sensor, dan resource didaftarkan.
`workspace.yaml` menunjuk ke modul ini.

FASE 5 (awal) — L2 Gold pertama, di atas jalur Fase 1b yang sudah lengkap.

Terdaftar sekarang (20 asset):
    l0_harmonization
        instagram_profile        @asset      CALL sp_sync_instagram_profile()
        tiktok_profile           @asset      CALL sp_sync_tiktok_profile()
        instagram_post           @asset      CALL sp_sync_instagram_post()
        tiktok_post              @asset      CALL sp_sync_tiktok_post()
    l1_silver
        unified_profile          @asset      SELECT sp_build_unified_profile()
        unified_post             @asset      SELECT sp_build_unified_post()
                                             (setelah unified_profile)
    feature
        ig_engagement_analysis   @asset      grain: social_account_id
        tt_engagement_analysis   @asset      grain: social_account_id
        ig_post_analysis         @asset      grain: social_account_id + media_id
        tt_post_analysis         @asset      grain: social_account_id + video_id
    l2_gold
        kol_metric_daily         @asset      grain: akun + platform + tanggal tayang
        post_metric              @asset      grain: akun + platform + content_id
        content_format_daily     @asset      grain: akun + platform + tanggal
                                             + media_type

Dua AssetSpec L1 dari Fase 1a diganti @asset bernama sama, jadi jumlah asset
bertambah 4 (bukan 6): unified_profile dan unified_post sudah terdaftar sejak
Fase 1a sebagai asset eksternal.

`sp_sync_all()` SENGAJA tidak dipakai — ia membungkus semua anaknya dengan
EXCEPTION handler sehingga selalu sukses walau anaknya gagal. Keempat pekerja
harmonization dipanggil langsung supaya kegagalan per tabel terlihat.

JOB ONE-SHOT (bukan asset, TIDAK ada schedule)
    one_shot_scrape_job    job   BERBIAYA — 1 profil uji dari kol_directory
                                 + maks 10 post terbaru per target. Jalankan
                                 MANUAL, sekali. Tanpa retry otomatis.
    transform_chain_job    job   GRATIS — asset job L0 Harmonization -> L1
                                 Silver -> Feature -> L2 Gold. Aman diulang.

SENSOR (event-based, BUKAN schedule)
    l0_raw_new_data_sensor  sensor  Memantau 8 tabel sumber `l0_raw` lewat
                                    sidik jari (count(*), max(fetched_at)).
                                    Kalau ada baris baru -> menjalankan
                                    `transform_chain_job`. GRATIS: tidak pernah
                                    memanggil Apify. Anti-trigger-ganda lewat
                                    cursor sensor + run_key. Lihat `sensors.py`.

Tidak ada `ScheduleDefinition` sama sekali: requirement cron 5 menit dibatalkan,
dan tidak boleh ada jalur yang memanggil actor sendiri. Otomatisasi transformasi
dikerjakan sensor di atas, yang bereaksi pada DATA, bukan pada jam dinding.

Job scraping sengaja TIDAK jadi asset: ia memanggil Apify dan ditagih per hasil,
sedangkan asset di atas semuanya transformasi murah yang boleh diulang. Lihat
`one_shot.py` untuk alasan lengkapnya.

Rencana berikutnya (lihat rancangan arsitektur):
    Fase 2   cpe
    Fase 3   comments / follower / Insights
    Fase 4   metrik yang menunggu definisi algoritma
    Fase 5   L2 Gold lanjutan (audience lanjutan, brand_fit, comments)

KREDENSIAL — tidak pernah ditulis di kode.
Dibaca dari environment (file `.env` di root project, sudah di-.gitignore):

    KOL_DB_URL   postgresql://user:password@host:port/kol
                 kalau diisi, ini yang dipakai.

    Kalau KOL_DB_URL kosong, connection string dirakit dari variabel yang
    sudah dipakai pipeline scraping supaya kredensialnya tidak terduplikasi:
        PG_USER, PG_PASSWORD, PG_HOST, PG_PORT, PG_DB
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from dagster import Definitions

from kol_orchestration.resources import PostgresResource
from kol_orchestration.assets.harmonization import harmonization_assets
from kol_orchestration.assets.silver import silver_assets
from kol_orchestration.assets.feature_engagement import feature_engagement_assets
from kol_orchestration.assets.feature_post import feature_post_assets
from kol_orchestration.assets.gold import gold_assets
from kol_orchestration.assets.gold_post import gold_post_assets
from kol_orchestration.assets.gold_profile import gold_profile_assets
from kol_orchestration.assets.followers import follower_assets
from kol_orchestration.assets.audience import audience_assets
from kol_orchestration.one_shot import one_shot_jobs, one_shot_schedules
from kol_orchestration.sensors import l0_raw_sensors

# .env ada di root project (satu tingkat di atas folder orchestration/).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


def _build_connection_string() -> str:
    """Rakit connection string ke database `kol` dari environment.

    Diutamakan KOL_DB_URL bila diisi. Kalau tidak, dirakit dari PG_* yang
    sudah dipakai pipeline scraping — supaya kredensial hanya ada di satu
    tempat, tidak diduplikasi antara scraper dan orchestrator.

    Password di-URL-encode: password yang mengandung '@', ':', atau '/' akan
    merusak URL kalau ditempel mentah, dan gejalanya menyesatkan
    ("host tidak ditemukan", bukan "password salah").
    """
    url = os.getenv("KOL_DB_URL")
    if url:
        return url

    wajib = ("PG_USER", "PG_PASSWORD", "PG_HOST", "PG_DB")
    kurang = [k for k in wajib if not os.getenv(k)]
    if kurang:
        raise RuntimeError(
            "Koneksi database belum lengkap. Isi KOL_DB_URL, atau lengkapi "
            f"variabel berikut di {_PROJECT_ROOT / '.env'}: {', '.join(kurang)}. "
            "Contoh formatnya ada di orchestration/.env.example."
        )

    user = quote_plus(os.environ["PG_USER"])
    password = quote_plus(os.environ["PG_PASSWORD"])
    host = os.environ["PG_HOST"]
    port = os.getenv("PG_PORT", "5432")
    database = os.environ["PG_DB"]
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


defs = Definitions(
    assets=[
        *harmonization_assets,       # l0_harmonization: 4 sp_sync_* (Fase 1b)
        *silver_assets,              # l1_silver: 2 sp_build_unified_* (Fase 1b)
        *feature_engagement_assets,  # feature: engagement per akun (Fase 1a)
        *feature_post_assets,        # feature: analisis per post (Fase 1c)
        *gold_assets,                # l2_gold: rekap harian per KOL (SCRUM-513)
        *gold_post_assets,           # l2_gold: per konten + per format (SCRUM-515/517)
        *gold_profile_assets,        # l2_gold: kartu profil per KOL (SCRUM-514)
        *follower_assets,            # l0_harm + l1: rantai daftar follower
        *audience_assets,            # feature + l2_gold: audiens hasil inferensi
    ],
    jobs=one_shot_jobs,
    # Sengaja kosong: tidak ada schedule/cron apa pun di project ini.
    schedules=one_shot_schedules,
    # Event-based, bukan waktu-based. Lihat sensors.py: memantau baris baru di
    # 8 tabel sumber l0_raw, lalu menjalankan transform_chain_job. Tidak pernah
    # memanggil Apify.
    sensors=l0_raw_sensors,
    resources={
        "postgres": PostgresResource(
            connection_string=_build_connection_string(),
        ),
    },
)
