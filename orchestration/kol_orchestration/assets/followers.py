"""Asset rantai follower: L0 raw -> Harmonization -> L1 Silver.

    instagram_follower -> l0_harmonization.instagram_follower
    tiktok_follower    -> l0_harmonization.tiktok_follower
    unified_follower   -> l1_silver.unified_follower

Ketiganya hanya MEMANGGIL procedure/function yang sudah lama ada di database.
Tidak ada logic transformasi baru di sini, dan tidak ada procedure baru yang
dibuat -- yang ditambahkan cuma pembungkus Dagster supaya tahap-tahap ini
punya jejak, urutan, dan metadata seperti tahap lain di pipeline.

Dipisah dari `harmonization.py` dan `silver.py` supaya rantai follower bisa
dijalankan dan dibaca sebagai satu kesatuan, tanpa ikut menjalankan asset
profile/post yang tidak berhubungan.

============================================================================
DARI MANA L0-NYA DIISI
============================================================================

`l0_raw.{ig,tt}_followers_apify` diisi di LUAR Dagster oleh
`scrape_followers.py`, mengikuti pola project ini: scraping (berbiaya, memanggil
pihak ketiga) ada di luar; transformasi (murah, deterministik, bisa diulang)
ada di dalam.

Artinya asset di sini bisa dijalankan ulang sesering apa pun tanpa biaya Apify
sepeser pun.
"""

from __future__ import annotations

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

GROUP_HARM = "l0_harmonization"
GROUP_SILVER = "l1_silver"


def _jalankan_harm(postgres: PostgresResource, procedure: str, tabel: str,
                   sumber: str) -> Output:
    """Panggil procedure harmonization follower lalu laporkan metadatanya.

    SENGAJA tanpa try/except: kalau procedure gagal, asset harus ikut gagal.
    """
    penuh = f"l0_harmonization.{tabel}"
    sebelum = postgres.count_rows(penuh)
    postgres.call_procedure(f"CALL l0_harmonization.{procedure}()")
    sesudah = postgres.count_rows(penuh)
    return Output(
        sesudah,
        metadata={
            "procedure": f"CALL l0_harmonization.{procedure}()",
            "tabel": penuh,
            "sumber": MetadataValue.text(sumber),
            "baris_sebelum": sebelum,
            "baris_sesudah": sesudah,
            "baris_bertambah": sesudah - sebelum,
        },
    )


@asset(
    name="instagram_follower",
    group_name=GROUP_HARM,
    kinds={"postgres"},
    description=(
        "CALL sp_sync_instagram_follower(): menyatukan l0_raw.ig_followers_apify "
        "dan ig_followers_official jadi l0_harmonization.instagram_follower."
    ),
)
def instagram_follower(postgres: PostgresResource) -> Output:
    return _jalankan_harm(
        postgres, "sp_sync_instagram_follower", "instagram_follower",
        "l0_raw.ig_followers_apify + l0_raw.ig_followers_official")


@asset(
    name="tiktok_follower",
    group_name=GROUP_HARM,
    kinds={"postgres"},
    description=(
        "CALL sp_sync_tiktok_follower(): menyatukan l0_raw.tt_followers_apify "
        "dan tt_followers_official jadi l0_harmonization.tiktok_follower."
    ),
)
def tiktok_follower(postgres: PostgresResource) -> Output:
    return _jalankan_harm(
        postgres, "sp_sync_tiktok_follower", "tiktok_follower",
        "l0_raw.tt_followers_apify + l0_raw.tt_followers_official")


@asset(
    name="unified_follower",
    group_name=GROUP_SILVER,
    deps=[AssetKey("instagram_follower"), AssetKey("tiktok_follower")],
    kinds={"postgres"},
    description=(
        "SELECT sp_build_unified_follower(): menggabungkan instagram_follower "
        "dan tiktok_follower jadi l1_silver.unified_follower. Grain "
        "(social_account_id, follower_platform_id, date) dijaga UNIQUE, jadi "
        "rerun tidak menghasilkan duplikat."
    ),
)
def unified_follower(postgres: PostgresResource) -> Output:
    penuh = "l1_silver.unified_follower"
    sebelum = postgres.count_rows(penuh)
    postgres.call_function("SELECT l1_silver.sp_build_unified_follower()")
    sesudah = postgres.count_rows(penuh)
    return Output(
        sesudah,
        metadata={
            "function": "SELECT l1_silver.sp_build_unified_follower()",
            "tabel": penuh,
            "sumber": MetadataValue.text(
                "l0_harmonization.instagram_follower + tiktok_follower"),
            "baris_sebelum": sebelum,
            "baris_sesudah": sesudah,
            "baris_bertambah": sesudah - sebelum,
            "grain": MetadataValue.text(
                "UNIQUE (social_account_id, follower_platform_id, date)"),
        },
    )


follower_assets = [instagram_follower, tiktok_follower, unified_follower]
