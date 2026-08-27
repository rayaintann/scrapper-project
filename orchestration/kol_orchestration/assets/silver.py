"""Asset L1 Silver — Fase 1b.

Dua asset, satu per function:

    unified_profile -> SELECT l1_silver.sp_build_unified_profile()
    unified_post    -> SELECT l1_silver.sp_build_unified_post()

Menggantikan dua `AssetSpec` di `silver_sources.py` (Fase 1a) yang hanya
MENGAMATI kedua tabel ini. AssetKey-nya sengaja sama persis — `unified_profile`
dan `unified_post` — sehingga `deps` di keempat asset feature tidak perlu
disentuh sama sekali. Yang berubah cuma satu: kotaknya kini punya tombol
materialize, karena Dagster benar-benar mengisinya.

============================================================================
KEPUTUSAN DESAIN
============================================================================

1. `call_function()`, BUKAN `call_procedure()`.
   Di database `kol`, pengisi L1 adalah FUNCTION yang mengembalikan void,
   sedangkan pengisi harmonization adalah PROCEDURE. `CALL` ke function akan
   gagal, begitu juga `SELECT` ke procedure. Resource menyediakan dua method
   terpisah persis supaya salah pakai ketahuan saat review, bukan saat runtime.

2. URUTAN: PROFILE DULU, BARU POST.
   `sp_build_unified_post()` membaca `l1_silver.unified_profile` lewat
   LATERAL untuk dua hal:
     - `followers_count`  -> penyebut `engagement_rate` per post
     - `username`         -> pembanding untuk menandai `is_collaboration`
   Kalau post dibangun sebelum profile, kedua kolom itu jadi NULL untuk akun
   yang profilnya belum ada. Ketergantungan ini dinyatakan lewat `deps`, jadi
   Dagster yang menjaga urutannya — bukan catatan di dokumen.

3. HULU HARMONIZATION IKUT DINYATAKAN.
   `unified_profile` bergantung pada `instagram_profile` + `tiktok_profile`,
   `unified_post` pada `instagram_post` + `tiktok_post`. Ini bukan hiasan
   grafik: menjalankan builder L1 sebelum harmonization-nya segar akan
   menghasilkan L1 yang diam-diam basi, bukan error.

4. KEGAGALAN TIDAK DITELAN.
   Tidak ada try/except. Kedua function ini memang tidak punya EXCEPTION
   handler sama sekali, jadi error apa pun langsung naik ke Dagster.

5. TIDAK MENULIS `sync_log`.
   Berbeda dari procedure harmonization, kedua function L1 TIDAK menulis
   `sync_log` — dan asset ini tidak menambahkannya. Menambah penulis baru
   berarti mengubah data, dan itu di luar cakupan Fase 1b. Yang dilaporkan
   sebagai metadata cukup hitungan baris sebelum/sesudah, yang dibaca
   read-only.

6. LAYER FEATURE TETAP MEMBACA L1.
   Keempat asset feature membaca `l1_silver.unified_post` dan
   `l1_silver.unified_profile`, tidak pernah `l0_harmonization` atau `l0_raw`.
   Fase 1b tidak mengubah satu baris pun di keempatnya — hanya membuat
   upstream-nya benar-benar dimiliki Dagster.
"""

from __future__ import annotations

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

GROUP = "l1_silver"

_IG_PROFILE = AssetKey("instagram_profile")
_TT_PROFILE = AssetKey("tiktok_profile")
_IG_POST = AssetKey("instagram_post")
_TT_POST = AssetKey("tiktok_post")
_UNIFIED_PROFILE = AssetKey("unified_profile")


def _jalankan(postgres: PostgresResource, function: str, tabel: str,
              sumber: str, catatan: str) -> Output:
    """Panggil satu function L1 lalu laporkan metadatanya.

    SENGAJA tanpa try/except: kalau function gagal, asset harus ikut gagal.
    """
    penuh = f"l1_silver.{tabel}"
    sebelum = postgres.count_rows(penuh)

    postgres.call_function(f"SELECT l1_silver.{function}()")

    sesudah = postgres.count_rows(penuh)

    return Output(
        sesudah,
        metadata={
            "function": f"SELECT l1_silver.{function}()",
            "tabel": penuh,
            "sumber": MetadataValue.text(sumber),
            "baris_sebelum": sebelum,
            "baris_sesudah": sesudah,
            "baris_bertambah": sesudah - sebelum,
            "catatan": MetadataValue.text(catatan),
        },
    )


@asset(
    name="unified_profile",
    group_name=GROUP,
    deps=[_IG_PROFILE, _TT_PROFILE],
    kinds={"postgres"},
    description=(
        "l1_silver.unified_profile — snapshot profil, grain (social_account_id, date). "
        "SELECT sp_build_unified_profile(): menyatukan instagram_profile dan "
        "tiktok_profile, menghitung tier dari public.kol_tiers dan followers_growth "
        "lewat LAG per akun. Dipakai asset feature sebagai penyebut engagement rate."
    ),
)
def unified_profile(postgres: PostgresResource) -> Output:
    return _jalankan(
        postgres, "sp_build_unified_profile", "unified_profile",
        "l0_harmonization.instagram_profile + l0_harmonization.tiktok_profile",
        "followers_growth memakai LAG(followers_count) per akun urut tanggal. "
        "Selama tiap akun baru punya SATU snapshot, kolom itu akan tetap NULL — "
        "itu batas data scraping, bukan kegagalan asset.",
    )


@asset(
    name="unified_post",
    group_name=GROUP,
    deps=[_IG_POST, _TT_POST, _UNIFIED_PROFILE],
    kinds={"postgres"},
    description=(
        "l1_silver.unified_post — satu baris per konten, grain "
        "(social_account_id, content_id). SELECT sp_build_unified_post(), WAJIB "
        "setelah unified_profile karena membaca followers_count dan username "
        "dari sana. Sumber tunggal seluruh metrik engagement, termasuk penanda "
        "likes_hidden dan is_collaboration."
    ),
)
def unified_post(postgres: PostgresResource) -> Output:
    return _jalankan(
        postgres, "sp_build_unified_post", "unified_post",
        "l0_harmonization.instagram_post + l0_harmonization.tiktok_post "
        "+ l1_silver.unified_profile",
        "Grain sumber (akun, konten, TANGGAL) diciutkan ke (akun, konten) dengan "
        "DISTINCT ON dari migration 019: snapshot TERBARU yang menang. Riwayat "
        "per tanggal tetap utuh di l0_harmonization.",
    )


silver_assets = [unified_profile, unified_post]
