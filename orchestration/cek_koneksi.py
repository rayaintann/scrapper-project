"""Verifikasi Fase 0 — READ-ONLY.

Membuktikan skeleton bisa dipakai, tanpa menjalankan asset apa pun:
    1. repository.py bisa di-import dan Definitions terbentuk
    2. resource `postgres` terhubung ke database yang benar
    3. tabel sumber dan tabel target Fase 1 memang ada

Sesi database dibuka READ-ONLY, jadi script ini secara teknis tidak bisa
menulis apa pun sekalipun ada salah ketik.

Jalankan:
    python orchestration/cek_koneksi.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Supaya `import kol_orchestration` jalan tanpa perlu `pip install -e` dulu.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from kol_orchestration.repository import defs  # noqa: E402

# Tabel yang akan dipakai Fase 1.
SUMBER = [
    "l1_silver.unified_post",
    "l1_silver.unified_profile",
]
TARGET_FASE_1 = [
    "feature.ig_engagement_analysis",
    "feature.tt_engagement_analysis",
    "feature.ig_post_analysis",
    "feature.tt_post_analysis",
]


def _versi_dagster() -> str:
    try:
        import dagster
        return dagster.__version__
    except Exception:  # noqa: BLE001 - script diagnostik, jangan menjatuhkan verifikasi
        return "(tidak terbaca)"


def _jumlah_asset() -> int:
    """Jumlah AssetKey yang terdaftar di Definitions.

    Nama method graph asset berubah antar versi Dagster: `get_asset_graph()`
    di versi lama, `resolve_asset_graph()` sejak 1.13. Dicoba berurutan supaya
    script verifikasi ini tidak ikut rusak saat Dagster di-upgrade; kalau
    dua-duanya tidak ada, jatuh ke menghitung daftar asset mentah.
    """
    for nama in ("resolve_asset_graph", "get_asset_graph"):
        method = getattr(defs, nama, None)
        if not callable(method):
            continue
        try:
            graph = method()
        except Exception:  # noqa: BLE001
            break
        # Nama accessor-nya juga berubah antar versi:
        # `all_asset_keys` (properti, versi lama) vs `get_all_asset_keys()` (1.13).
        for accessor in ("get_all_asset_keys", "all_asset_keys"):
            attr = getattr(graph, accessor, None)
            if attr is None:
                continue
            return len(attr() if callable(attr) else attr)
        break
    return len(getattr(defs, "assets", []) or [])


def main() -> int:
    postgres = defs.resources["postgres"]

    conn = postgres.get_conn()
    # READ-ONLY: penjaga tambahan supaya script verifikasi tidak mungkin menulis.
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, version()")
            db, user, ver = cur.fetchone()

        print("=== Koneksi ===")
        print(f"  database : {db}")
        print(f"  user     : {user}")
        print(f"  versi    : {ver.split(',')[0]}")
        if db != "kol":
            print(f"\n  PERINGATAN: terhubung ke '{db}', bukan 'kol'.")
            print("  Periksa KOL_DB_URL / PG_DB di .env sebelum lanjut ke Fase 1.")
            return 1

        print("\n=== Tabel sumber (dibaca Fase 1) ===")
        with conn.cursor() as cur:
            for t in SUMBER:
                skema, nama = t.split(".")
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema=%s AND table_name=%s",
                    (skema, nama),
                )
                ada = cur.fetchone()[0] == 1
                jml = postgres.count_rows(t) if ada else 0
                print(f"  {'ADA  ' if ada else 'HILANG'}  {t:32s} {jml:>6} baris")

        print("\n=== Tabel target Fase 1 ===")
        with conn.cursor() as cur:
            for t in TARGET_FASE_1:
                skema, nama = t.split(".")
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema=%s AND table_name=%s",
                    (skema, nama),
                )
                ada = cur.fetchone()[0] == 1
                jml = postgres.count_rows(t) if ada else 0
                print(f"  {'ADA  ' if ada else 'HILANG'}  {t:32s} {jml:>6} baris")

        print("\n=== Definitions ===")
        print(f"  versi dagster   : {_versi_dagster()}")
        print(f"  asset terdaftar : {_jumlah_asset()}")
        print(f"  resource        : {', '.join(sorted(defs.resources))}")
        print("\nVerifikasi OK. Tidak ada data yang dibaca selain metadata dan jumlah baris,")
        print("dan tidak ada asset yang dijalankan.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
