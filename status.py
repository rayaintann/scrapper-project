"""Cek cepat: apakah scraping masih berjalan, dan sudah berapa yang masuk DB.

Read-only. Aman dijalankan kapan saja, termasuk saat pipeline sedang jalan.

    python status.py
"""

import subprocess
import sys
from datetime import datetime, timezone

from apify_client import ApifyClient

from config import ConfigError, load_config
from db import connect

TABEL = {
    "Instagram": "l0_raw.ig_profile_apify",
    "TikTok": "l0_raw.tt_profile_apify",
}
ACTORS = {
    "Instagram": "apify/instagram-profile-scraper",
    "TikTok": "clockworks/tiktok-scraper",
}


def proses_pipeline() -> list[str]:
    """Proses pipeline yang masih hidup (Windows)."""
    if not sys.platform.startswith("win"):
        return []
    perintah = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -match 'pipeline.py' } | "
        "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"
    )
    try:
        hasil = subprocess.run(
            ["powershell", "-NoProfile", "-Command", perintah],
            capture_output=True, text=True, timeout=30,
        )
        return [b.strip() for b in hasil.stdout.splitlines() if b.strip()]
    except Exception:
        return []


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        cfg = load_config()
    except ConfigError as exc:
        print(exc)
        return 1

    print("=" * 62)
    print("1. APAKAH MASIH BERJALAN?")
    print("=" * 62)
    berjalan = proses_pipeline()
    if berjalan:
        print(f"  YA - {len(berjalan)} proses pipeline aktif:")
        for b in berjalan:
            pid, _, cmd = b.partition(" ")
            print(f"    PID {pid}: {cmd[:90]}")
    else:
        print("  TIDAK - tidak ada proses pipeline yang berjalan")

    client = ApifyClient(cfg.apify.token)
    now = datetime.now(timezone.utc)
    print("\n  Run Apify yang masih aktif:")
    aktif = 0
    for label, actor in ACTORS.items():
        try:
            runs = client.actor(actor).runs().list(limit=5, desc=True).items
        except Exception as exc:
            print(f"    {label}: gagal dicek ({type(exc).__name__})")
            continue
        for r in runs:
            st = getattr(r.status, "value", r.status)
            if st not in ("RUNNING", "READY", "ABORTING"):
                continue
            aktif += 1
            menit = (now - r.started_at).total_seconds() / 60 if r.started_at else 0
            try:
                n = client.dataset(r.default_dataset_id).get().item_count
            except Exception:
                n = "?"
            print(f"    {label}: {r.id} | {st} | {menit:.1f} menit | {n} item terkumpul")
    if not aktif:
        print("    (tidak ada)")

    print("\n" + "=" * 62)
    print("2. SUDAH BERAPA YANG MASUK DATABASE?")
    print("=" * 62)
    with connect(cfg.postgres) as conn:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            for label, tabel in TABEL.items():
                cur.execute(
                    f"""SELECT count(*), count(DISTINCT username),
                               count(DISTINCT scrape_run_id), max(fetched_at)
                        FROM {tabel};"""
                )
                total, unik, run, terakhir = cur.fetchone()
                waktu = f"{terakhir:%Y-%m-%d %H:%M UTC}" if terakhir else "-"
                print(f"  {label:<10} {tabel:<28} {total:>5} baris | "
                      f"{unik:>5} unik | {run} run | terakhir {waktu}")

    print("\n" + "=" * 62)
    print("3. SISA KREDIT APIFY")
    print("=" * 62)
    try:
        d = client.user("me").limits().model_dump()
        pakai = d["current"]["monthly_usage_usd"]
        batas = d["limits"]["max_monthly_usage_usd"]
        siklus = d["monthly_usage_cycle"]["end_at"]
        print(f"  terpakai ${pakai:.4f} dari ${batas:.2f} | sisa ${batas - pakai:.4f}")
        print(f"  siklus berakhir: {siklus}")
    except Exception as exc:
        print(f"  gagal dicek: {type(exc).__name__}: {exc}")

    print()
    if berjalan or aktif:
        print("KESIMPULAN: masih berjalan. Angka database baru bertambah")
        print("            setelah SELURUH batch selesai.")
    else:
        print("KESIMPULAN: tidak ada yang berjalan. Angka database di atas sudah final.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
