"""Pipeline scraping profil TikTok: kol_directory -> Apify -> file/DB.

Alurnya sama dengan pipeline.py (Instagram), dengan tiga perbedaan penting:

  - Actor clockworks/tiktok-scraper berorientasi video; data profil diambil dari
    authorMeta setiap video, dan satu video per profil sudah cukup.
  - Wajib memakai residential proxy (proxyCountryCode). Tanpa itu TikTok
    memblokir request dan run berakhir SUCCEEDED dengan 0 profil.
  - Biayanya lebih mahal: ~$0.005/profil, bukan $0.0026.

Pengaman biaya dan ketahanan untuk run besar:

  - `--skip-existing` membuang username yang sudah punya baris di
    l0_raw.tt_profile_apify. Ini juga cara melanjutkan run yang terputus:
    jalankan lagi perintah yang sama, yang sudah masuk tidak dibayar dua kali.
    (`--only-unscraped` membaca kol_directory.scrape_status, yang tidak pernah
    diisi jalur TikTok, jadi untuk TikTok flag itu tidak menyaring apa pun.)
  - `--max-total-cost-usd` menghentikan sisa batch begitu biaya kumulatif satu
    run melewati plafon. `--max-cost-usd` hanya membatasi satu run actor.
  - Hasil tiap batch langsung ditulis ke JSONL dan langsung di-commit ke DB
    dengan koneksi yang diperiksa ulang, jadi run panjang tidak lagi kehilangan
    seluruh hasilnya gara-gara satu koneksi yang mati di akhir.

Contoh:
    python tiktok_pipeline.py --limit 50 --dry-run
    python tiktok_pipeline.py --limit 1000 --batch-size 50 --skip-existing --yes
    python tiktok_pipeline.py --usernames-file gagal.txt --yes
"""

import argparse
import csv
import json
import logging
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from apify_runner import BatchResult, FatalApifyError, chunked
from apify_tiktok import TikTokProfileScraper
from config import PRICE_PER_TIKTOK_PROFILE_USD, Config, ConfigError, PostgresConfig, load_config
from db import ORDER_CLAUSES, connect, dedupe_rows, fetch_usernames, open_connection
from tiktok_transform import flatten_for_csv
from transform import normalize_username
from tt_raw_store import RAW_TABLE, RawInsertStats, existing_usernames, insert_profiles

logger = logging.getLogger("tiktok")

PLATFORM_KEY = "tiktok"
MAX_LIMIT = 5000


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--limit", type=int, default=100,
                        help=f"jumlah username (maksimal {MAX_LIMIT}, default 100)")
    parser.add_argument("--batch-size", type=int, default=25,
                        help="username per run actor (default 25; batch kecil "
                             "membatasi kerugian kalau satu run terpotong)")
    parser.add_argument("--order", choices=sorted(ORDER_CLAUSES), default="followers",
                        help="urutan pemilihan kandidat (default followers)")
    parser.add_argument("--only-unscraped", action="store_true",
                        help="hanya baris yang scrape_status-nya belum 'success' "
                             "(catatan: kolom itu tidak diisi jalur TikTok; "
                             "pakai --skip-existing)")
    parser.add_argument("--usernames", nargs="+", metavar="USERNAME",
                        help="scrape daftar username ini saja, lewati kol_directory")
    parser.add_argument("--usernames-file", type=Path, metavar="FILE",
                        help="file berisi satu username per baris (# = komentar)")
    parser.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=False,
                        help=f"buang username yang sudah ada di {RAW_TABLE} "
                             "(default: tidak, tapi jumlahnya selalu dilaporkan)")
    parser.add_argument("--write-raw", action=argparse.BooleanOptionalAction, default=True,
                        help=f"tulis ke {RAW_TABLE} (default: aktif)")
    parser.add_argument("--dry-run", action="store_true",
                        help="hanya ambil daftar username, tidak memanggil Apify")
    parser.add_argument("--yes", action="store_true", help="lewati konfirmasi biaya")
    parser.add_argument("--max-cost-usd", type=float, default=None,
                        help="plafon biaya per batch (0 = tanpa plafon)")
    parser.add_argument("--max-total-cost-usd", type=float, default=None,
                        help="plafon biaya seluruh run; sisa batch dibatalkan "
                             "begitu terlampaui")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def read_usernames_file(path: Path) -> list[str]:
    """Baca daftar username: satu per baris, '#' dianggap komentar."""
    if not path.exists():
        raise FileNotFoundError(f"file username tidak ditemukan: {path}")
    hasil = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            hasil.append(line)
    return hasil


def dedupe_preserving_order(usernames: list[str]) -> list[str]:
    """Normalisasi + buang duplikat, urutan pertama menang.

    Apify menagih per hasil, jadi username yang sama tidak boleh dikirim dua kali
    dalam satu run.
    """
    terlihat: dict[str, None] = {}
    for raw in usernames:
        key = normalize_username(raw)
        if key:
            terlihat.setdefault(key, None)
    return list(terlihat)


def select_usernames(conn, args: argparse.Namespace) -> tuple[list[str], str]:
    """Daftar username yang akan dikirim, beserta asalnya."""
    manual: list[str] = []
    if args.usernames_file:
        manual.extend(read_usernames_file(args.usernames_file))
    if args.usernames:
        manual.extend(args.usernames)

    if manual:
        usernames = dedupe_preserving_order(manual)[:MAX_LIMIT]
        sumber = "daftar manual"
        if args.usernames_file:
            sumber = f"daftar manual ({args.usernames_file.name})"
        return usernames, sumber

    limit = max(1, min(args.limit, MAX_LIMIT))
    rows = fetch_usernames(
        conn, PLATFORM_KEY, limit=limit, order=args.order,
        only_unscraped=args.only_unscraped,
    )
    usernames = list(dedupe_rows(rows))
    logger.info("%d baris directory -> %d username unik", len(rows), len(usernames))
    return usernames, f"kol_directory (order={args.order}, limit={limit})"


def confirm_cost(jumlah: int, skip_prompt: bool) -> bool:
    estimasi = jumlah * PRICE_PER_TIKTOK_PROFILE_USD
    print(
        f"Akan men-scrape {jumlah} profil TikTok. "
        f"Estimasi biaya Apify ~${estimasi:.2f} "
        f"(${PRICE_PER_TIKTOK_PROFILE_USD}/profil: hasil + residential proxy)."
    )
    if skip_prompt:
        return True
    if not sys.stdin.isatty():
        print("Stdin bukan terminal; jalankan ulang dengan --yes untuk melanjutkan.")
        return False
    return input("Lanjutkan? [y/N] ").strip().lower() in {"y", "yes"}


class RawWriter:
    """Menulis hasil tiap batch ke raw table, satu commit per batch.

    Versi sebelumnya memakai satu koneksi yang dibuka di awal run dan baru
    dipakai menulis setelah semua batch selesai. Pada run 100 profil yang
    memakan sembilan jam, koneksi itu sudah mati saat INSERT dijalankan dan
    seluruh hasil yang sudah dibayar gagal masuk DB. Sekarang:

      - setiap batch di-commit sendiri, jadi kegagalan di batch ke-40 tidak
        menghanguskan 39 batch sebelumnya;
      - koneksi diperiksa (SELECT 1) sebelum dipakai dan dibuka ulang kalau
        sudah mati, lalu penulisan dicoba sekali lagi.

    Satu run tetap memakai satu `scrape_run_id` supaya batch-batchnya bisa
    dikenali sebagai satu kesatuan di layer berikutnya.
    """

    def __init__(self, pg: PostgresConfig, source_actor: str, scraped_at: datetime,
                 scrape_run_id: str | None = None):
        self._pg = pg
        self._source_actor = source_actor
        self._scraped_at = scraped_at
        self.scrape_run_id = scrape_run_id or str(uuid.uuid4())
        self._conn = None
        self.total = RawInsertStats(scrape_run_id=self.scrape_run_id)
        self.failures: list[tuple[int, str]] = []

    def _discard(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except psycopg2.Error:
                pass
            self._conn = None

    def _connection(self):
        if self._conn is not None:
            try:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
                self._conn.rollback()
                return self._conn
            except psycopg2.Error:
                logger.warning("Koneksi DB sudah mati; membuka koneksi baru.")
                self._discard()
        self._conn = open_connection(self._pg)
        return self._conn

    def _accumulate(self, stats: RawInsertStats) -> None:
        self.total.inserted += stats.inserted
        self.total.linked += stats.linked
        self.total.unlinked += stats.unlinked
        self.total.skipped_failed += stats.skipped_failed
        self.total.skipped_no_username += stats.skipped_no_username
        if stats.link_blocked_reason:
            self.total.link_blocked_reason = stats.link_blocked_reason

    def write(self, items: list[dict], batch_index: int) -> bool:
        """Tulis satu batch. False kalau gagal — hasilnya tetap aman di JSONL."""
        if not items:
            return True
        for attempt in (1, 2):
            conn = self._connection()
            try:
                stats = insert_profiles(
                    conn, items,
                    source_actor=self._source_actor,
                    scraped_at=self._scraped_at,
                    scrape_run_id=self.scrape_run_id,
                    commit=True,
                )
            except psycopg2.Error as exc:
                try:
                    conn.rollback()
                except psycopg2.Error:
                    pass
                # Koneksi dibuang supaya percobaan kedua benar-benar memakai
                # koneksi baru, bukan koneksi yang sama yang baru saja gagal.
                self._discard()
                pesan = f"{type(exc).__name__}: {exc}".strip()
                if attempt == 1:
                    logger.warning("Batch %d gagal ditulis (%s); mencoba koneksi baru.",
                                   batch_index, type(exc).__name__)
                    continue
                logger.error("Batch %d gagal ditulis ke DB: %s", batch_index, pesan)
                self.failures.append((batch_index, pesan))
                return False
            self._accumulate(stats)
            return True
        return False

    def close(self) -> None:
        self._discard()


def write_outputs(output_dir: Path, stamp: str, batches: list[BatchResult],
                  items: list[dict], raw_path: Path, scrape_run_id: str | None = None,
                  raw_inserted: int = 0, db_failures: list[tuple[int, str]] | None = None,
                  aborted: str | None = None) -> dict[str, Path]:
    """CSV ringkasan + metadata run. JSONL sudah ditulis bertahap saat scraping."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "raw": raw_path,
        "csv": output_dir / f"tiktok_profiles_{stamp}.csv",
        "meta": output_dir / f"run_metadata_tiktok_{stamp}.json",
    }

    rows = [flatten_for_csv(item) for item in items]
    if rows:
        with paths["csv"].open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    meta = {
        "platform": PLATFORM_KEY,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "total_items": len(items),
        # Dicatat supaya baris di DB bisa ditelusuri balik ke file ini, dan
        # supaya ketahuan kalau ada batch yang hasilnya belum masuk DB.
        "scrape_run_id": scrape_run_id,
        "raw_inserted": raw_inserted,
        "db_failures": [{"batch_index": i, "error": e} for i, e in (db_failures or [])],
        "aborted": aborted,
        "batches": [
            {
                "batch_index": b.batch_index,
                "username_count": len(b.usernames),
                "run_id": b.run_id,
                "dataset_id": b.dataset_id,
                "status": b.status,
                "item_count": len(b.items),
                "cost_usd": b.cost_usd,
                "partial": b.partial,
                "missing": b.missing,
                "error": b.error,
            }
            for b in batches
        ],
        "total_cost_usd": round(sum(b.cost_usd or 0.0 for b in batches), 4),
    }
    paths["meta"].write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return paths


def run(args: argparse.Namespace, cfg: Config) -> int:
    # Koneksi ini hanya untuk memilih kandidat, lalu ditutup. Loop scraping bisa
    # berjam-jam, dan koneksi menganggur selama itu tidak bisa dipercaya.
    with connect(cfg.postgres) as conn:
        usernames, sumber = select_usernames(conn, args)
        if not usernames:
            logger.warning("Tidak ada kandidat username TikTok. Berhenti.")
            return 0

        sudah_ada = existing_usernames(conn, usernames)

    if sudah_ada:
        if args.skip_existing:
            usernames = [u for u in usernames if u not in sudah_ada]
            logger.info("%d username dilewati karena sudah ada di %s",
                        len(sudah_ada), RAW_TABLE)
        else:
            logger.warning(
                "%d dari %d username sudah ada di %s dan akan dibayar lagi "
                "(~$%.2f). Pakai --skip-existing untuk melewatinya.",
                len(sudah_ada), len(usernames), RAW_TABLE,
                len(sudah_ada) * PRICE_PER_TIKTOK_PROFILE_USD,
            )

    if not usernames:
        print(f"Semua kandidat sudah ada di {RAW_TABLE}; tidak ada yang perlu di-scrape.")
        return 0

    w = 24
    print("\n=== Rencana run TikTok ===")
    print(f"{'Sumber username':<{w}}: {sumber}")
    print(f"{'Akan di-scrape':<{w}}: {len(usernames)} username")
    print(f"{'Sudah ada di raw table':<{w}}: {len(sudah_ada)} "
          f"({'dilewati' if args.skip_existing else 'TETAP dikirim'})")
    print(f"{'Batch':<{w}}: {len(chunked(usernames, args.batch_size))} "
          f"x {args.batch_size}")
    print(f"{'Estimasi biaya':<{w}}: ~${len(usernames) * PRICE_PER_TIKTOK_PROFILE_USD:.2f}")
    estimasi = len(usernames) * PRICE_PER_TIKTOK_PROFILE_USD
    if args.max_total_cost_usd:
        print(f"{'Plafon biaya run':<{w}}: ${args.max_total_cost_usd:.2f}")
        if estimasi > args.max_total_cost_usd:
            print(f"{'  catatan':<{w}}: plafon di bawah estimasi; sisa batch akan "
                  "dibatalkan sebelum semua username terkirim")

    if args.dry_run:
        print(f"\n[dry-run] 10 pertama: {', '.join(usernames[:10])}")
        print("[dry-run] Apify tidak dipanggil, tidak ada biaya.")
        return 0

    if not confirm_cost(len(usernames), args.yes):
        logger.info("Dibatalkan oleh user.")
        return 1

    if args.max_cost_usd is None:
        max_charge = round(args.batch_size * PRICE_PER_TIKTOK_PROFILE_USD * 1.5, 4)
    else:
        max_charge = args.max_cost_usd or None

    scraper = TikTokProfileScraper(cfg.tiktok, max_charge_usd=max_charge)
    batches: list[BatchResult] = []
    all_items: list[dict] = []
    chunks = chunked(usernames, args.batch_size)
    logger.info("Total %d batch (batch size %d), proxy=%s",
                len(chunks), args.batch_size, cfg.tiktok.proxy_country)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or cfg.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"tiktok_profiles_{stamp}.jsonl"
    scraped_at = datetime.now(timezone.utc)

    writer = RawWriter(cfg.postgres, cfg.tiktok.actor_id, scraped_at) if args.write_raw else None

    # Setiap batch langsung ditulis ke disk dan ke DB, supaya proses yang mati di
    # tengah tidak menghanguskan profil yang sudah dibayar.
    aborted: str | None = None
    biaya = 0.0
    try:
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

                if writer:
                    writer.write(batch.items, index)

                biaya += batch.cost_usd or 0.0
                logger.info("Progress: batch %d/%d selesai, total item %d, biaya $%.4f",
                            index, len(chunks), len(all_items), biaya)

                if args.max_total_cost_usd and biaya >= args.max_total_cost_usd:
                    aborted = (f"plafon biaya total ${args.max_total_cost_usd:.2f} tercapai "
                               f"(terpakai ${biaya:.4f})")
                    logger.error("%s; sisa batch dibatalkan.", aborted)
                    break
    finally:
        if writer:
            writer.close()

    paths = write_outputs(
        output_dir, stamp, batches, all_items, raw_path,
        scrape_run_id=writer.scrape_run_id if writer else None,
        raw_inserted=writer.total.inserted if writer else 0,
        db_failures=writer.failures if writer else None,
        aborted=aborted,
    )

    raw_stats = writer.total if writer else None
    failed_batches = [b.batch_index for b in batches if not b.ok]
    tidak_kembali = sorted({u for b in batches for u in b.missing})
    alasan: Counter = Counter()
    for b in batches:
        if b.partial:
            alasan["batch_sebagian"] += 1

    print("\n=== Ringkasan TikTok ===")
    print(f"Username dikirim   : {len(usernames)}")
    print(f"Item dari Apify    : {len(all_items)}")
    print(f"Profil tersimpan   : {raw_stats.inserted if raw_stats else 0}")
    print(f"Tidak ada hasil    : {len(tidak_kembali)}")
    print(f"Biaya Apify (USD)  : {biaya:.4f}")
    if raw_stats:
        print(f"{RAW_TABLE}: {raw_stats.inserted} baris "
              f"(scrape_run_id={raw_stats.scrape_run_id})")
        print(f"  tertaut social_account : {raw_stats.linked}")
        print(f"  tanpa pasangan         : {raw_stats.unlinked}")
        if raw_stats.skipped_failed:
            print(f"  dilewati (tanpa profil): {raw_stats.skipped_failed}")
    for label, count in alasan.most_common():
        print(f"  {label:<21}: {count}")
    if failed_batches:
        print(f"Batch gagal        : {failed_batches}")
    if tidak_kembali:
        print(f"Belum berhasil     : {', '.join(tidak_kembali[:10])}"
              + (" ..." if len(tidak_kembali) > 10 else ""))
    if aborted:
        print(f"DIHENTIKAN         : {aborted}")
    if writer and writer.failures:
        print(f"GAGAL tulis DB     : batch {[i for i, _ in writer.failures]}")
        print(f"  hasilnya aman di {raw_path}; masukkan dengan:")
        print(f"  python ingest_tiktok.py {raw_path} --yes")
    for label, path in paths.items():
        print(f"{label:<19}: {path}")

    if (writer and writer.failures) or aborted:
        return 3
    return 0 if not failed_batches else 2


def main(argv: list[str] | None = None) -> int:
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
    try:
        return run(args, cfg)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
