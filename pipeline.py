"""Pipeline scraping profil Instagram: kol_directory -> Apify -> file/DB.

Contoh pakai:
    # lihat kandidat tanpa memanggil Apify (gratis)
    python pipeline.py --limit 1000 --dry-run

    # scrape 50 username teratas, hasil ke folder output/
    python pipeline.py --limit 50

    # scrape 1000 username dan tulis balik ke kol_directory
    python pipeline.py --limit 1000 --update-db --yes
"""

import argparse
import csv
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from apify_ig import BatchResult, FatalApifyError, InstagramProfileScraper, chunked
from config import PRICE_PER_PROFILE_USD, Config, ConfigError, load_config
from db import ORDER_CLAUSES, connect, dedupe_rows, fetch_instagram_usernames, update_profiles
from raw_store import RAW_TABLE, insert_profiles
from transform import extract_username, flatten_for_csv, to_db_update

logger = logging.getLogger("pipeline")

MAX_LIMIT = 1000


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_LIMIT,
        help=f"jumlah username yang diambil (maksimal {MAX_LIMIT}, default {MAX_LIMIT})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="jumlah username per run actor (default 100)",
    )
    parser.add_argument(
        "--order",
        choices=sorted(ORDER_CLAUSES),
        default="followers",
        help="urutan pemilihan kandidat (default followers)",
    )
    parser.add_argument(
        "--only-unscraped",
        action="store_true",
        help="hanya ambil baris yang scrape_status-nya belum 'success'",
    )
    parser.add_argument(
        "--write-raw",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=f"tulis payload mentah ke {RAW_TABLE} (default: aktif)",
    )
    parser.add_argument(
        "--update-db",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="tulis hasil balik ke public.kol_directory (default: aktif; matikan dengan --no-update-db)",
    )
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help=f"ikut memasukkan item not_found/restricted ke {RAW_TABLE}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="hanya ambil daftar username dari DB, tidak memanggil Apify",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="lewati konfirmasi estimasi biaya",
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=None,
        help=(
            "plafon biaya Apify per batch dalam USD; 0 berarti tanpa plafon "
            "(default: 1.5x estimasi harga satu batch)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="folder output (default: output/ atau OUTPUT_DIR di .env)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="level logging: DEBUG/INFO/WARNING (default INFO)",
    )
    return parser.parse_args(argv)


def confirm_cost(unique_count: int, skip_prompt: bool) -> bool:
    estimate = unique_count * PRICE_PER_PROFILE_USD
    print(
        f"Akan men-scrape {unique_count} profil. "
        f"Estimasi biaya Apify <= ${estimate:.2f} "
        f"(${PRICE_PER_PROFILE_USD}/profil pada plan FREE)."
    )
    if skip_prompt:
        return True
    if not sys.stdin.isatty():
        print("Stdin bukan terminal; jalankan ulang dengan --yes untuk melanjutkan.")
        return False
    answer = input("Lanjutkan? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def write_outputs(
    output_dir: Path,
    stamp: str,
    batches: list[BatchResult],
    items: list[dict],
    raw_path: Path | None = None,
) -> dict[str, Path]:
    """Simpan ringkasan (CSV) dan metadata run (JSON).

    File JSONL mentah sudah ditulis bertahap per batch selama scraping, jadi
    di sini hanya dicatat lokasinya. `raw_path=None` dipakai kalau pemanggil
    ingin JSONL-nya ditulis sekaligus di akhir.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "raw": raw_path or (output_dir / f"instagram_profiles_{stamp}.jsonl"),
        "csv": output_dir / f"instagram_profiles_{stamp}.csv",
        "meta": output_dir / f"run_metadata_{stamp}.json",
    }

    if raw_path is None:
        with paths["raw"].open("w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")

    rows = [flatten_for_csv(item) for item in items]
    if rows:
        with paths["csv"].open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    meta = {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "total_items": len(items),
        "batches": [
            {
                "batch_index": b.batch_index,
                "username_count": len(b.usernames),
                "run_id": b.run_id,
                "dataset_id": b.dataset_id,
                "status": b.status,
                "item_count": len(b.items),
                "cost_usd": b.cost_usd,
                "error": b.error,
            }
            for b in batches
        ],
        "total_cost_usd": round(sum(b.cost_usd or 0.0 for b in batches), 4),
    }
    paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return paths


def run(args: argparse.Namespace, cfg: Config) -> int:
    limit = max(1, min(args.limit, MAX_LIMIT))
    if args.limit > MAX_LIMIT:
        logger.warning("--limit dibatasi ke %d", MAX_LIMIT)

    with connect(cfg.postgres) as conn:
        rows = fetch_instagram_usernames(
            conn,
            limit=limit,
            order=args.order,
            only_unscraped=args.only_unscraped,
        )
        if not rows:
            logger.warning("Tidak ada kandidat username Instagram yang cocok. Berhenti.")
            return 0

        grouped = dedupe_rows(rows)
        usernames = list(grouped)
        logger.info("%d baris directory -> %d username unik", len(rows), len(usernames))

        if args.dry_run:
            preview = ", ".join(usernames[:10])
            print(f"[dry-run] {len(usernames)} username unik. 10 pertama: {preview}")
            return 0

        if not confirm_cost(len(usernames), args.yes):
            logger.info("Dibatalkan oleh user.")
            return 1

        if args.max_cost_usd is None:
            # Beri kelonggaran 1.5x supaya batch normal tidak terpotong plafon.
            max_charge = round(args.batch_size * PRICE_PER_PROFILE_USD * 1.5, 4)
        else:
            max_charge = args.max_cost_usd or None

        scraper = InstagramProfileScraper(cfg.apify, max_charge_usd=max_charge)
        batches: list[BatchResult] = []
        all_items: list[dict] = []
        chunks = chunked(usernames, args.batch_size)
        logger.info("Total %d batch (batch size %d)", len(chunks), args.batch_size)

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = args.output_dir or cfg.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = output_dir / f"instagram_profiles_{stamp}.jsonl"

        # Setiap batch langsung ditulis ke disk. Kalau proses mati di tengah
        # (Ctrl-C, listrik, error), profil yang sudah dibayar tetap tersimpan dan
        # bisa dimasukkan menyusul lewat: python ingest.py <file>
        aborted: str | None = None
        with raw_path.open("w", encoding="utf-8") as raw_file:
            for index, chunk in enumerate(chunks, start=1):
                try:
                    batch = scraper.scrape_batch(chunk, batch_index=index)
                except FatalApifyError as exc:
                    aborted = str(exc)
                    logger.error("%s", aborted)
                    logger.error("Menghentikan sisa batch; hasil sejauh ini tetap disimpan.")
                    break
                except KeyboardInterrupt:
                    aborted = "dihentikan oleh user (Ctrl-C)"
                    logger.warning("Dihentikan; hasil sejauh ini tetap disimpan.")
                    break

                batches.append(batch)
                all_items.extend(batch.items)
                for item in batch.items:
                    raw_file.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
                raw_file.flush()

                logger.info(
                    "Progress: batch %d/%d selesai, total item %d",
                    index,
                    len(chunks),
                    len(all_items),
                )

        paths = write_outputs(output_dir, stamp, batches, all_items, raw_path=raw_path)

        # Petakan item hasil ke baris directory lewat username ternormalisasi.
        items_by_username: dict[str, dict] = {}
        unmatched_items = 0
        for item in all_items:
            key = extract_username(item)
            if key and key in grouped:
                items_by_username[key] = item
            else:
                unmatched_items += 1

        updates: list[dict] = []
        failure_reasons: Counter[str] = Counter()
        for key, directory_rows in grouped.items():
            item = items_by_username.get(key)
            for row in directory_rows:
                if item is None:
                    # Username dikirim tapi tidak ada item balasan sama sekali.
                    updates.append({"id": row.id, "scrape_status": "failed"})
                    failure_reasons["tanpa_item"] += 1
                    continue
                update = to_db_update(row.id, item)
                updates.append(update)
                if update["scrape_status"] != "success":
                    failure_reasons[str(item.get("error") or "tidak_diketahui")] += 1

        success = sum(1 for u in updates if u["scrape_status"] == "success")
        failed = len(updates) - success
        failed_batches = [b.batch_index for b in batches if not b.ok]

        # Scraping sudah dibayar di titik ini. Kegagalan menulis ke DB tidak boleh
        # muncul sebagai traceback mentah — file hasilnya sudah aman di disk dan
        # bisa dimasukkan menyusul tanpa scrape ulang.
        raw_stats = None
        db_error: str | None = None
        try:
            if args.write_raw:
                raw_stats = insert_profiles(
                    conn,
                    all_items,
                    source_actor=cfg.apify.actor_id,
                    scraped_at=datetime.now(timezone.utc),
                    include_failed=args.include_failed,
                )
            if args.update_db:
                update_profiles(conn, updates)
        except psycopg2.Error as exc:
            conn.rollback()
            db_error = f"{type(exc).__name__}: {exc}".strip()
            logger.error("Penulisan ke database GAGAL: %s", db_error)
            logger.error(
                "Hasil scraping AMAN di %s. Masukkan menyusul dengan:\n"
                "    python ingest.py %s --yes",
                paths["raw"],
                paths["raw"],
            )

        if not args.write_raw and not args.update_db:
            logger.info("Penulisan ke DB dimatikan. Hasilnya bisa dimasukkan "
                        "menyusul lewat: python ingest.py --latest")

        print("\n=== Ringkasan ===")
        print(f"Username dikirim   : {len(usernames)}")
        print(f"Item dari Apify    : {len(all_items)}")
        print(f"Cocok / sukses     : {success}")
        print(f"Gagal / tidak ada  : {failed}")
        for reason, count in failure_reasons.most_common():
            print(f"  - {reason:<15}: {count}")
        if unmatched_items:
            print(f"Item tanpa pasangan: {unmatched_items}")
        if failed_batches:
            print(f"Batch gagal        : {failed_batches}")
        print(f"Biaya Apify (USD)  : {sum(b.cost_usd or 0.0 for b in batches):.4f}")
        if raw_stats:
            print(f"{RAW_TABLE}: {raw_stats.inserted} baris "
                  f"(scrape_run_id={raw_stats.scrape_run_id})")
        if db_error:
            kondisi_db = "GAGAL, tidak berubah"
        elif args.update_db:
            kondisi_db = "diupdate"
        else:
            kondisi_db = "tidak diubah"
        print(f"kol_directory      : {kondisi_db}")
        if aborted:
            print(f"DIHENTIKAN         : {aborted}")
            print(f"  batch selesai    : {len(batches)} dari {len(chunks)}")
        if db_error:
            print(f"GAGAL tulis DB     : {db_error}")
            print(f"  pulihkan dengan  : python ingest.py {paths['raw']} --yes")
        for label, path in paths.items():
            print(f"{label:<19}: {path}")

        if db_error or aborted:
            return 3
        return 0 if not failed_batches else 2


def main(argv: list[str] | None = None) -> int:
    # Konsol Windows default-nya cp1252 dan bisa crash saat mencetak emoji dari
    # bio Instagram, jadi paksa UTF-8 di stdout/stderr.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    try:
        cfg = load_config()
    except ConfigError as exc:
        logger.error("%s", exc)
        return 1
    return run(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
