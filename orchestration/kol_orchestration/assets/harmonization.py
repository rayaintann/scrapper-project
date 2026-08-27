"""Asset L0 Harmonization — Fase 1b.

Empat asset, satu per procedure:

    instagram_profile  -> CALL l0_harmonization.sp_sync_instagram_profile()
    tiktok_profile     -> CALL l0_harmonization.sp_sync_tiktok_profile()
    instagram_post     -> CALL l0_harmonization.sp_sync_instagram_post()
    tiktok_post        -> CALL l0_harmonization.sp_sync_tiktok_post()

Masing-masing membaca pasangan tabel `l0_raw.*_apify` + `l0_raw.*_official`
dan menulis satu tabel `l0_harmonization.*`. Keempatnya SALING INDEPENDEN —
target tabelnya berbeda-beda — jadi Dagster boleh menjalankannya paralel.

============================================================================
KEPUTUSAN DESAIN
============================================================================

1. SATU ASSET PER PROCEDURE, BUKAN SATU ASSET UNTUK `sp_sync_all`.
   `sp_sync_all()` membungkus ke-13 pemanggilannya dengan
   `EXCEPTION WHEN OTHERS THEN RAISE NOTICE`, jadi procedure itu SELALU
   sukses — bahkan kalau semua anaknya gagal. Membungkusnya sebagai satu
   asset berarti dashboard hijau permanen yang tidak berarti apa-apa.

   Memanggil ke-4 pekerja langsung memberi tiga hal yang `sp_sync_all` tidak
   bisa: kegagalan per-tabel terlihat, yang sehat tetap jalan saat satu
   rusak, dan retry bisa menyasar satu tabel saja.

   `sp_sync_all` juga tidak memanggil `sp_sync_roster_rate_card` (yang justru
   menghasilkan seluruh 9.210 rate card) tapi memanggil dua procedure rate
   card yang sumbernya kosong — cacat yang ikut hilang kalau ia tidak dipakai.

2. KEGAGALAN TIDAK BOLEH DITELAN.
   Tidak ada `try/except` di sekitar pemanggilan procedure. Kalau procedure
   melempar, `call_procedure()` melemparkannya lagi dan asset-nya MERAH.
   Ini kebalikan dari perilaku `sp_sync_all` dan memang disengaja.

   Procedure-nya sendiri punya `EXCEPTION` handler, tapi handler itu hanya
   menandai `sync_log` jadi 'failed' lalu `RAISE` ulang — jadi error tetap
   sampai ke Dagster.

3. `sync_log` DIBACA, TIDAK DITULIS.
   Tiap procedure sudah menulis satu baris `l0_harmonization.sync_log`
   sendiri. Asset ini hanya MEMBACA baris itu dan mengangkatnya jadi metadata
   Dagster. Tidak ada mekanisme logging baru, tidak ada baris tambahan,
   tidak ada data yang berubah.

   Menulis log kedua dari Dagster akan menciptakan dua sumber kebenaran yang
   bisa berbeda; membaca yang sudah ada memberi satu penulis, dua tampilan.

4. HANYA SUMBER YANG BERISI.
   Sembilan procedure sync lain (audience, comment, follower, story,
   tagged_post, rate_card) TIDAK dibuatkan asset: tabel `l0_raw` sumbernya
   0 baris, jadi asset-nya hanya akan jadi kotak hijau yang selalu
   menghasilkan 0. Begitu sumbernya berisi, menambahkannya di sini sepele.

5. TABEL `l0_raw` BELUM DIMODELKAN SEBAGAI ASSET.
   Yang mengisinya adalah pipeline scraping Python di luar Dagster
   (`post_pipeline.py`, `pipeline.py`). Keempat asset ini sengaja tanpa
   `deps` supaya Dagster tidak mengaku memiliki sesuatu yang tidak
   dijalankannya. Itu pekerjaan fase berikutnya, bukan Fase 1b.
"""

from __future__ import annotations

from dagster import MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

GROUP = "l0_harmonization"


def _watermark(postgres: PostgresResource, target_table: str):
    """Waktu mulai baris `sync_log` TERAKHIR untuk tabel ini, sebelum kita jalan.

    Dipakai untuk mengenali baris yang dibuat pemanggilan kita sendiri, bukan
    sisa run sebelumnya. Dikembalikan NULL kalau tabelnya belum pernah disync.
    """
    return postgres.scalar(
        "SELECT max(started_at) FROM l0_harmonization.sync_log WHERE target_table = %s",
        (target_table,),
    )


def _baris_sync_log(postgres: PostgresResource, target_table: str, sesudah):
    """Baris `sync_log` yang baru saja ditulis procedure. READ-ONLY.

    Dikembalikan None kalau tidak ada baris baru — lebih baik metadata-nya
    kosong daripada menampilkan angka dari run sebelumnya seolah-olah baru.
    """
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, rows_read, rows_inserted, rows_updated,
                       rows_skipped, duration_seconds, error_message, source
                FROM l0_harmonization.sync_log
                WHERE target_table = %s
                  AND (%s::timestamptz IS NULL OR started_at > %s::timestamptz)
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (target_table, sesudah, sesudah),
            )
            return cur.fetchone()
    finally:
        conn.close()


def _jalankan(postgres: PostgresResource, procedure: str, tabel: str,
              sumber: str) -> Output:
    """Panggil satu procedure harmonization lalu laporkan metadatanya.

    SENGAJA tanpa try/except: kalau procedure gagal, asset harus ikut gagal.
    """
    penuh = f"l0_harmonization.{tabel}"
    sebelum = postgres.count_rows(penuh)
    tanda = _watermark(postgres, tabel)

    # Kalau ini melempar, asset-nya merah. Itu yang diinginkan.
    postgres.call_procedure(f"CALL l0_harmonization.{procedure}()")

    sesudah = postgres.count_rows(penuh)
    log = _baris_sync_log(postgres, tabel, tanda)

    metadata = {
        "procedure": f"CALL l0_harmonization.{procedure}()",
        "tabel": penuh,
        "sumber": MetadataValue.text(sumber),
        "baris_sebelum": sebelum,
        "baris_sesudah": sesudah,
        "baris_bertambah": sesudah - sebelum,
    }

    if log is None:
        metadata["sync_log"] = MetadataValue.text(
            "Tidak ada baris sync_log baru untuk tabel ini. Procedure selesai "
            "tanpa error, jadi ini kemungkinan perubahan pada procedure-nya — "
            "bukan kegagalan sync."
        )
    else:
        status, baca, masuk, ubah, lewat, durasi, pesan, src = log
        metadata.update({
            "sync_log_status": status,
            "sync_log_rows_read": baca,
            "sync_log_rows_inserted": masuk,
            "sync_log_rows_skipped": lewat,
            "sync_log_source": src,
        })
        if durasi is not None:
            metadata["sync_log_durasi_detik"] = float(durasi)
        if pesan:
            metadata["sync_log_error"] = MetadataValue.text(pesan)
        # `rows_updated` sengaja TIDAK diangkat: procedure mengisinya dengan
        # jumlah baris SEBELUM sync, bukan jumlah baris yang ter-update.
        # Menampilkannya apa adanya akan menyesatkan. `baris_bertambah` di
        # atas dihitung sendiri dan artinya jelas.

    return Output(sesudah, metadata=metadata)


@asset(
    name="instagram_profile",
    group_name=GROUP,
    kinds={"postgres"},
    description=(
        "l0_harmonization.instagram_profile — grain (social_account_id, date). "
        "CALL sp_sync_instagram_profile(): menggabungkan ig_profile_apify "
        "(identitas + metrik publik) dan ig_profile_official (metrik Insights). "
        "Prioritasnya recency lewat processed_at, digabung per kolom dengan "
        "COALESCE sehingga NULL dari satu sumber tidak menghapus nilai sumber lain."
    ),
)
def instagram_profile(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "sp_sync_instagram_profile", "instagram_profile",
                     "l0_raw.ig_profile_apify + l0_raw.ig_profile_official")


@asset(
    name="tiktok_profile",
    group_name=GROUP,
    kinds={"postgres"},
    description=(
        "l0_harmonization.tiktok_profile — grain (social_account_id, date). "
        "CALL sp_sync_tiktok_profile(). Tabelnya tidak punya kolom Insights "
        "seperti padanan Instagram-nya."
    ),
)
def tiktok_profile(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "sp_sync_tiktok_profile", "tiktok_profile",
                     "l0_raw.tt_profile_apify + l0_raw.tt_profile_official")


@asset(
    name="instagram_post",
    group_name=GROUP,
    kinds={"postgres"},
    description=(
        "l0_harmonization.instagram_post — grain (social_account_id, media_id, date), "
        "jadi satu post bisa punya banyak snapshot harian. "
        "CALL sp_sync_instagram_post(). Sejak migration 019 sumbernya di-dedup "
        "DISTINCT ON supaya dua hasil scrape di hari yang sama tidak memicu "
        "SQLSTATE 21000."
    ),
)
def instagram_post(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "sp_sync_instagram_post", "instagram_post",
                     "l0_raw.ig_media_snapshots_apify + l0_raw.ig_media_snapshots_official")


@asset(
    name="tiktok_post",
    group_name=GROUP,
    kinds={"postgres"},
    description=(
        "l0_harmonization.tiktok_post — grain (social_account_id, video_id, date). "
        "CALL sp_sync_tiktok_post(). Dedup DISTINCT ON dari migration 019, "
        "alasan yang sama dengan instagram_post."
    ),
)
def tiktok_post(postgres: PostgresResource) -> Output:
    return _jalankan(postgres, "sp_sync_tiktok_post", "tiktok_post",
                     "l0_raw.tt_video_apify + l0_raw.tt_video_official")


harmonization_assets = [
    instagram_profile,
    tiktok_profile,
    instagram_post,
    tiktok_post,
]
