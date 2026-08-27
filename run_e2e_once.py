"""Uji end-to-end SEKALI JALAN: kol_directory -> scraping -> L0 -> ... -> L2 Gold.

    python run_e2e_once.py --plan-only     lihat rencana, actor TIDAK dipanggil
    python run_e2e_once.py --no-posts      profil saja, lewati target post
    python run_e2e_once.py                 eksekusi penuh (BERBIAYA, sekali)
    python run_e2e_once.py --transform-only   jalankan rantai transformasi saja

URUTAN
======
    1..4  pilih 1 profil dari kol_directory, tentukan platform, ambil
          social_account_id lewat kol_social_account, verifikasi belum ada di L0
    5..7  scrape profil + post, tulis ke L0 RAW
    8     catat dua baris ke public.scheduler_logs (profile & post)
    9..12 jalankan asset existing: harmonization -> silver -> feature -> gold
    13    verifikasi
    14    STOP — tidak ada eksekusi kedua

KENAPA TRANSFORMASI LEWAT DAGSTER
=================================
Layer harmonization dan silver memang procedure database, tapi Feature dan L2
Gold logikanya hidup di dalam asset Dagster (`orchestration/kol_orchestration/
assets/*.py`), bukan di database. Menjalankannya lewat `dagster.materialize`
berarti memakai perhitungan metric yang sudah ada apa adanya — tidak ada satu
baris SQL metric pun yang ditulis ulang di sini, dan urutan antar layer dijaga
Dagster lewat `deps`.

BIAYA
=====
Hanya langkah 5..7 yang memanggil Apify. Langkah 9..12 gratis dan idempoten,
jadi boleh diulang tanpa menyentuh actor: `--transform-only`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ORCHESTRATION = PROJECT_ROOT / "orchestration"
if str(ORCHESTRATION) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATION))

from config import ConfigError, load_config  # noqa: E402
from db import connect  # noqa: E402
from scheduler_engine import (  # noqa: E402
    CANDIDATE_ORDERS,
    build_plan,
    print_plan,
    print_results,
    run_once,
)

logger = logging.getLogger("run_e2e_once")


def run_transform_chain() -> bool:
    """Jalankan rantai L0 Harmonization -> L2 Gold memakai asset existing.

    Diimpor di dalam fungsi, bukan di puncak modul: paket Dagster berat dan
    `--plan-only` tidak membutuhkannya sama sekali.
    """
    from dagster import AssetKey, materialize
    from kol_orchestration.one_shot import TRANSFORM_ASSETS
    from kol_orchestration.repository import _build_connection_string
    from kol_orchestration.resources import PostgresResource

    # Kumpulkan objek asset yang sesungguhnya dari repository, supaya definisi
    # yang dijalankan persis sama dengan yang dipakai UI Dagster.
    from kol_orchestration.assets.audience import audience_assets
    from kol_orchestration.assets.feature_engagement import feature_engagement_assets
    from kol_orchestration.assets.feature_post import feature_post_assets
    from kol_orchestration.assets.followers import follower_assets
    from kol_orchestration.assets.gold import gold_assets
    from kol_orchestration.assets.gold_profile import gold_profile_assets
    from kol_orchestration.assets.harmonization import harmonization_assets
    from kol_orchestration.assets.silver import silver_assets

    semua = [
        *harmonization_assets, *silver_assets,
        *feature_engagement_assets, *feature_post_assets,
        *gold_assets, *gold_profile_assets,
        *follower_assets, *audience_assets,
    ]
    pilihan = [AssetKey(n) for n in TRANSFORM_ASSETS]

    print("\n" + "=" * 72)
    print(f"RANTAI TRANSFORMASI — {len(pilihan)} asset (gratis, idempoten)")
    print("=" * 72)

    hasil = materialize(
        assets=semua,
        selection=pilihan,
        resources={"postgres": PostgresResource(
            connection_string=_build_connection_string()
        )},
        raise_on_error=False,
    )

    for ev in hasil.get_asset_materialization_events():
        key = ev.event_specific_data.materialization.asset_key.to_user_string()
        meta = ev.event_specific_data.materialization.metadata
        ringkas = ", ".join(
            f"{k}={v.value}" for k, v in list(meta.items())[:3]
            if hasattr(v, "value") and not isinstance(v.value, (dict, list))
        )
        print(f"   OK   {key:26s} {ringkas[:90]}")

    if not hasil.success:
        gagal = [
            e.step_key for e in hasil.all_events
            if e.event_type_value == "STEP_FAILURE"
        ]
        print(f"\n   GAGAL: {', '.join(gagal) if gagal else '(lihat log di atas)'}")
    return hasil.success


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--platform", choices=("instagram", "tiktok"), default=None,
                   help="batasi kandidat profil ke satu platform")
    p.add_argument("--order", choices=sorted(CANDIDATE_ORDERS), default="followers",
                   help="urutan kandidat profil (default: %(default)s)")
    p.add_argument("--username", default=None,
                   help="kunci ke satu kandidat; syarat 'belum ada di L0' tetap berlaku")
    p.add_argument("--no-posts", action="store_true",
                   help="pekerjaan profile saja, lewati target post")
    p.add_argument("--plan-only", action="store_true",
                   help="tampilkan rencana lalu berhenti; actor TIDAK dipanggil")
    p.add_argument("--transform-only", action="store_true",
                   help="lewati scraping, jalankan rantai transformasi saja")
    p.add_argument("--skip-transform", action="store_true",
                   help="scraping saja, jangan jalankan rantai transformasi")
    return p.parse_args(argv)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s | %(message)s")
    args = parse_args(argv)

    try:
        cfg = load_config()
    except ConfigError as exc:
        logger.error("%s", exc)
        return 1

    if args.transform_only:
        return 0 if run_transform_chain() else 1

    # --- langkah 1-4: rencana + bukti kondisi awal --------------------------
    with connect(cfg.postgres) as conn:
        plan = build_plan(
            conn, args.platform, with_posts=not args.no_posts,
            order=args.order, username=args.username,
        )
    print_plan(plan)

    if args.plan_only:
        print("\n[--plan-only] actor TIDAK dipanggil. Tidak ada biaya.")
        return 0

    # --- langkah 5-8: SATU eksekusi scraping + log --------------------------
    hasil = run_once(
        cfg,
        platform=args.platform,
        with_posts=not args.no_posts,
        plan=plan,
    )
    print_results(hasil)

    if args.skip_transform:
        print("\n[--skip-transform] rantai transformasi tidak dijalankan.")
        return 0 if all(h.ok for h in hasil) else 1

    # --- langkah 9-12: rantai transformasi ---------------------------------
    # Dijalankan walau scraping gagal sebagian: data yang sudah masuk L0 tetap
    # berhak mengalir, dan rantainya idempoten.
    sukses_transform = run_transform_chain()

    print("\n" + "=" * 72)
    print("SELESAI — tidak ada eksekusi kedua")
    print("=" * 72)
    for h in hasil:
        print(f"   scraping {h.category:8s}: {h.status}")
    print(f"   transformasi      : {'success' if sukses_transform else 'failed'}")
    return 0 if all(h.ok for h in hasil) and sukses_transform else 1


if __name__ == "__main__":
    sys.exit(main())
