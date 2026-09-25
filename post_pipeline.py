"""Pipeline scraping POST Instagram dan VIDEO TikTok, dengan error handling.

Yang dijamin pipeline ini:

- **Setiap akun yang diminta selalu berakhir sebagai satu baris
  `public.scheduler_logs`**, sukses maupun gagal, lengkap dengan
  `kol_account_id`, platform, status/kode error, pesan, dan rentang waktu.
- **Item error tidak pernah masuk L0** sebagai post. Penyaringan ada di
  `post_raw_store`, dan hasil saringannya jadi bahan log.
- **Kegagalan satu akun tidak menghentikan akun lain.** Kegagalan batch
  ditangani `apify_runner` (retry + penyelamatan sebagian), dan kegagalan yang
  tersisa hanya ditimpakan ke akun di batch itu; batch berikutnya tetap jalan.
- **Tidak ada data lama yang dihapus.** Kedua tabel L0 append-only dan modul
  penulisnya tidak punya jalur DELETE/UPDATE sama sekali.
- Alur L0 -> harmonization -> L1 **tidak disentuh**.

Mode:

    # scrape sungguhan
    python post_pipeline.py --platform instagram --limit 10

    # tanpa memanggil Apify: putar ulang file hasil scrape lama lewat jalur
    # klasifikasi + ingest + logging yang sama persis
    python post_pipeline.py --platform instagram --from-file output/ig_posts_x.jsonl

    # lihat rencananya saja
    python post_pipeline.py --platform tiktok --limit 5 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from apify_posts import InstagramDetailsScraper, InstagramPostScraper, TikTokVideoScraper
from apify_runner import FatalApifyError, chunked
from config import ConfigError, default_max_cost_usd, load_config
from run_lock import jalankan_terkunci
from db import connect, dedupe_rows, fetch_usernames
from post_errors import (
    ACTOR_ERROR,
    PARTIAL,
    SUCCESS,
    classify_exception,
    classify_missing,
    is_error_item,
)
from post_raw_store import insert_ig_posts, insert_tt_videos
from scrape_log import AccountOutcome, ScrapeLogger
from transform import normalize_username

logger = logging.getLogger("post_pipeline")

PLATFORMS = ("instagram", "tiktok")


# --- pembantu ---------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().strftime("%Y%m%dT%H%M%SZ")


def _read_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    # Iterasi file, BUKAN str.splitlines(): splitlines juga memotong di U+2028/
    # U+2029 yang sah muncul di caption (json.dumps ensure_ascii=False menulisnya
    # mentah), sehingga satu post terbelah jadi dua baris rusak dan hilang.
    with path.open(encoding="utf-8", newline="\n") as fh:
        baris = list(fh)
    for line in baris:
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning("Baris JSON rusak dilewati: %s", exc)
    return items


def _write_jsonl(path: Path, items) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def _input_of(platform: str, scraper, item: dict) -> str | None:
    """Username yang DIMINTA (bukan pemilik) untuk satu item hasil actor.

    TikTok membawa `input`; post Instagram membawa `inputUrl` (mode posts
    aslinya, mode details ditempeli di `_posts_dari_details`). Dipakai hanya
    untuk menghitung berapa item yang dikembalikan actor per akun yang diminta.
    """
    if platform == "tiktok":
        v = item.get("input")
        return normalize_username(v) if isinstance(v, str) else None
    url = item.get("inputUrl")
    return scraper.item_username({"inputUrl": url}) if url else None


def _posts_dari_details(details: InstagramDetailsScraper, profil: list[dict],
                        tersedia: dict[str, int]) -> list[dict]:
    """Item profil mode `details` -> daftar post, terbaru dulu.

    Sama dengan jalur `scheduler_engine`: post diambil dari `latestPosts`
    lewat `posts_of`. Item error (akun tidak ada/privat) diteruskan apa adanya
    supaya klasifikasi errornya tetap lewat `post_errors`. Profilnya sendiri
    TIDAK ditulis -- pipeline ini hanya mengurus post.

    `posts_of` mengembalikan daftar kosong untuk TIGA hal yang berbeda: item
    error, akun privat, dan akun yang memang belum punya post. Hanya yang
    pertama boleh diteruskan. Dua sisanya adalah objek profil yang sah --
    punya `id` di level atas, jadi `is_error_item` menganggapnya post dan
    `post_raw_store` menulisnya ke L0 sebagai post palsu ber-`media_id` id
    AKUN, `posted_at` NULL. Karena itu penerusannya disaring dengan predikat
    yang sama dengan yang dipakai penulisnya.
    """
    hasil: list[dict] = []
    for item in profil:
        posts = details.posts_of(item)
        u = details.item_username(item)
        # Dicatat sebelum `continue`: berapa post yang DIMILIKI akun tetap
        # fakta yang berguna untuk menilai kekurangan, termasuk saat 0.
        if u and isinstance(item.get("postsCount"), int):
            tersedia[u] = item["postsCount"]
        if not posts:
            if is_error_item(item):
                hasil.append(item)
            continue
        url = item.get("url") or item.get("inputUrl")
        posts.sort(key=lambda p: p.get("timestamp") or "", reverse=True)
        hasil.extend({**p, "inputUrl": p.get("inputUrl") or url} for p in posts)
    return hasil


def _build_scraper(platform: str, cfg, results: int, max_charge: float | None):
    if platform == "instagram":
        return InstagramPostScraper(
            cfg.apify, results_limit=results, max_charge_usd=max_charge
        )
    return TikTokVideoScraper(
        cfg.tiktok, results_per_page=results, max_charge_usd=max_charge
    )


def _insert(platform: str, conn, items, username_of, actor, scraped_at, run_id,
            per_account_limit=None):
    fn = insert_ig_posts if platform == "instagram" else insert_tt_videos
    return fn(
        conn,
        items,
        username_of=username_of,
        source_actor=actor,
        scraped_at=scraped_at,
        scrape_run_id=run_id,
        commit=True,
        per_account_limit=per_account_limit,
    )


# --- inti: menyusun hasil per akun ------------------------------------------


def _nilai_kekurangan(masuk: int, diminta: int, kembali: int,
                      total_akun: int | None) -> tuple[str, str]:
    """Status akun yang baris L0-nya < diminta.

    success hanya kalau kekurangannya bisa dijelaskan data, bukan kegagalan:
      - actor mengembalikan >= diminta, tapi sebagian milik akun lain dan
        dibuang filter kepemilikan (filter itu tetap dipertahankan);
      - akunnya memang hanya punya sebanyak itu post.
    Selain itu `partial`.
    """
    if kembali >= diminta:
        return SUCCESS, (f"{masuk}/{diminta} post: sisanya dari {kembali} post terbaru "
                         f"milik akun lain (filter kepemilikan)")
    if total_akun is not None and kembali >= total_akun:
        return SUCCESS, f"{masuk}/{diminta} post: akun hanya punya {total_akun} post"
    return PARTIAL, (f"actor hanya mengembalikan {kembali} item untuk akun ini "
                     f"({masuk} masuk L0) dari {diminta} yang diminta")


def build_outcomes(
    *,
    requested: dict[str, list],
    platform: str,
    per_account: dict[str, int],
    item_errors: list[tuple[str | None, str, str]],
    batch_errors: dict[str, tuple[str, str]],
    started_at: datetime,
    finished_at: datetime,
    requested_per_account: int | None = None,
    returned: dict[str, int] | None = None,
    available: dict[str, int] | None = None,
) -> list[AccountOutcome]:
    """Satu `AccountOutcome` untuk SETIAP username yang diminta.

    Urutan penentuan status, dari yang paling kuat buktinya:

      1. ada baris L0 yang masuk        -> success, atau `partial` kalau
                                           barisnya kurang dari yang diminta
                                           dan kekurangannya tidak bisa
                                           dijelaskan data (lih. `_nilai_kekurangan`)
      2. ada item error dari actor      -> kode dari item itu
      3. batch-nya sendiri gagal        -> kode dari exception batch
      4. tidak ada jejak apa pun        -> unknown (bukan ditebak not_found)

    Username yang tidak punya pasangan `kol_directory` tetap dapat baris,
    dengan `kol_directory_id` NULL — supaya kegagalannya tidak hilang.
    """
    by_username: dict[str, tuple[str, str]] = {}
    orphan_errors: list[tuple[str, str, str]] = []
    for username, code, message in item_errors:
        if username:
            # Item error pertama per akun yang dipakai; sisanya cukup diwakili.
            by_username.setdefault(username, (code, message))
        else:
            orphan_errors.append((username or "", code, message))

    outcomes: list[AccountOutcome] = []
    for username, rows in requested.items():
        directory_id = str(rows[0].id) if rows else None
        masuk = per_account.get(username, 0)
        if masuk > 0:
            status, message = SUCCESS, None
            if requested_per_account and returned is not None and masuk < requested_per_account:
                status, message = _nilai_kekurangan(
                    masuk, requested_per_account, returned.get(username, 0),
                    (available or {}).get(username))
        elif username in by_username:
            status, message = by_username[username]
        elif username in batch_errors:
            status, message = batch_errors[username]
        else:
            status, message = classify_missing()
        outcomes.append(
            AccountOutcome(
                username=username,
                platform=platform,
                status=status,
                kol_directory_id=directory_id,
                records=masuk,
                message=message,
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    # Item error yang username-nya tidak terbaca sama sekali: tetap dicatat,
    # tanpa kol_account_id, supaya tidak menghilang tanpa jejak.
    for _, code, message in orphan_errors:
        outcomes.append(
            AccountOutcome(
                username="(tidak terbaca)",
                platform=platform,
                status=code,
                kol_directory_id=None,
                records=0,
                message=message,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
    return outcomes


# --- CLI --------------------------------------------------------------------


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--platform", choices=PLATFORMS, required=True)
    p.add_argument("--limit", type=int, default=10, help="jumlah akun yang diambil dari kol_directory")
    p.add_argument("--batch-size", type=int, default=10, help="username per run actor")
    p.add_argument("--results", type=int, default=10, help="post/video per akun")
    p.add_argument("--order", default="followers", help="urutan kandidat (lihat db.ORDER_CLAUSES)")
    p.add_argument("--max-charge-usd", type=float, default=None, help="plafon biaya per run")
    p.add_argument("--from-file", type=Path, default=None,
                   help="putar ulang file .jsonl hasil scrape, tanpa memanggil Apify")
    p.add_argument("--usernames", nargs="*", default=None,
                   help="batasi ke username tertentu (default: ambil dari kol_directory)")
    p.add_argument("--dry-run", action="store_true", help="tampilkan rencana, jangan scrape/tulis")
    p.add_argument("--no-write", action="store_true", help="scrape/baca file tapi jangan tulis ke L0")
    p.add_argument("--no-log", action="store_true", help="jangan tulis ke scheduler_logs")
    return p.parse_args(argv)


#: Kunci prosedur, DIPISAH PER PLATFORM. Scrape post Instagram dan TikTok
#: memanggil actor berbeda dengan kuota berbeda, jadi menjalankan keduanya
#: bersamaan aman -- yang tidak boleh adalah dua run untuk platform yang sama.
NAMA_KUNCI = "post_pipeline_{platform}"


def _jalankan(args, cfg) -> int:
    platform = args.platform
    started_at = _now()
    run_id = str(uuid.uuid4())
    # Plafon per run: flag menang, lalu environment, lalu default seukuran uji.
    # Budget produksi belum diputuskan bisnis, jadi tidak ada angka besar yang
    # dipasang diam-diam di sini.
    if args.max_charge_usd is None:
        args.max_charge_usd = default_max_cost_usd("SCRAPE_MAX_COST_POST_USD", 1.00)

    actor = _build_scraper(platform, cfg, args.results, args.max_charge_usd)._actor_id
    if args.from_file:
        actor = f"replay:{args.from_file.name}"

    with connect(cfg.postgres) as conn:
        # --- daftar akun yang akan diproses ---------------------------------
        if args.usernames:
            wanted = {normalize_username(u) for u in args.usernames if normalize_username(u)}
            # Daftar eksplisit: KOL inactive boleh dicari lagi (scrape sukses -> active).
            rows = [r for r in fetch_usernames(conn, platform, limit=100000, order=args.order,
                                               include_inactive=True)
                    if r.normalized in wanted]
        else:
            rows = fetch_usernames(conn, platform, limit=args.limit, order=args.order)
        requested = dedupe_rows(rows)

        if args.from_file:
            items_all = _read_jsonl(args.from_file)
            scraper = _build_scraper(platform, cfg, args.results, args.max_charge_usd)
            # Saat replay, daftar akun diambil dari isi file supaya akun yang
            # hanya muncul sebagai item error tetap ikut diproses.
            in_file = {u for u in (scraper.item_username(i) for i in items_all) if u}
            if not args.usernames:
                extra = [r for r in fetch_usernames(conn, platform, limit=100000, order=args.order,
                                                    include_inactive=True)
                         if r.normalized in in_file]
                requested = dedupe_rows(extra)
        else:
            items_all = []
            scraper = _build_scraper(platform, cfg, args.results, args.max_charge_usd)

        if not requested and not args.from_file:
            logger.error("Tidak ada akun %s yang cocok di kol_directory.", platform)
            return 1

        usernames = sorted(requested)
        print(f"Platform   : {platform}")
        print(f"Akun       : {len(usernames)}")
        print(f"Mode       : {'REPLAY ' + str(args.from_file) if args.from_file else 'SCRAPE ' + actor}")
        print(f"run_id     : {run_id}")
        if args.dry_run:
            print("\n[dry-run] tidak ada yang di-scrape maupun ditulis.")
            for u in usernames:
                print(f"  - {u}")
            return 0

        # --- ambil item ------------------------------------------------------
        batch_errors: dict[str, tuple[str, str]] = {}
        # Status run TIDAK boleh disimpulkan dari jumlah baris yang masuk:
        # run yang sehat tetap menghasilkan 0 baris saat --no-write, dan run
        # yang benar-benar gagal fatal harus tetap terlihat gagal.
        fatal_error: str | None = None
        tersedia: dict[str, int] = {}
        if not args.from_file:
            # Instagram: mode `details` (sama dengan scheduler_engine), karena
            # mode `posts` sekarang praktis hanya mengembalikan post yang di-pin.
            pengambil = (InstagramDetailsScraper(cfg.apify, results_limit=args.results,
                                                 max_charge_usd=args.max_charge_usd)
                         if platform == "instagram" else scraper)
            for index, batch in enumerate(chunked(usernames, max(1, args.batch_size))):
                try:
                    result = pengambil.scrape_batch(batch, batch_index=index)
                except FatalApifyError as exc:
                    # Fatal = token/kredit/actor. Sisa batch percuma dicoba,
                    # tapi akun di batch ini tetap harus tercatat.
                    code, message = classify_exception(exc)
                    for u in batch:
                        batch_errors[u] = (code, message)
                    fatal_error = message
                    logger.error("Berhenti: %s", exc)
                    break
                except Exception as exc:  # noqa: BLE001 - satu batch gagal, lanjut
                    code, message = classify_exception(exc)
                    for u in batch:
                        batch_errors[u] = (code, message)
                    logger.warning("Batch %d gagal, lanjut ke batch berikutnya: %s", index, message)
                    continue

                if platform == "instagram":
                    items_all.extend(_posts_dari_details(pengambil, result.items, tersedia))
                else:
                    items_all.extend(result.items)
                if result.error:
                    code, message = classify_exception(RuntimeError(result.error))
                    for u in result.missing:
                        batch_errors[u] = (code, message)

        scraped_at = _now()

        # --- simpan artefak mentah ------------------------------------------
        out_dir = cfg.output_dir
        stamp = _stamp()
        base = "ig_posts" if platform == "instagram" else "tt_videos"
        jsonl_path = out_dir / f"{base}_{stamp}.jsonl"
        if items_all and not args.from_file:
            _write_jsonl(jsonl_path, items_all)

        # --- tulis L0 --------------------------------------------------------
        if args.no_write:
            from post_raw_store import PostInsertStats
            from post_errors import classify_item

            table = "l0_raw.ig_media_snapshots_apify" if platform == "instagram" else "l0_raw.tt_video_apify"
            stats = PostInsertStats(scrape_run_id=run_id, table=table)
            for item in items_all:
                if is_error_item(item):
                    code, message = classify_item(item)
                    stats.errors.append((scraper.item_username(item), code, message))
                    stats.skipped_error += 1
                else:
                    u = scraper.item_username(item)
                    if u:
                        stats.per_account[u] = stats.per_account.get(u, 0) + 1
            logger.info("[--no-write] L0 tidak disentuh.")
        else:
            # `--results` adalah plafon yang diminta ke actor; dipakai lagi di
            # sini sebagai plafon per PEMILIK, karena batas actor terbukti tidak
            # menjamin jumlah maupun kepemilikan.
            stats = _insert(
                platform, conn, items_all, scraper.item_username, actor, scraped_at, run_id,
                per_account_limit=args.results,
            )

        finished_at = _now()

        # --- catat hasil per akun -------------------------------------------
        kembali: dict[str, int] = {}
        for item in items_all:
            if is_error_item(item):
                continue
            u = _input_of(platform, scraper, item)
            if u:
                kembali[u] = kembali.get(u, 0) + 1
            if platform == "tiktok":
                meta = item.get("authorMeta") or {}
                if u and isinstance(meta.get("video"), int):
                    tersedia[u] = meta["video"]

        outcomes = build_outcomes(
            requested=requested,
            platform=platform,
            per_account=stats.per_account,
            item_errors=stats.errors,
            batch_errors=batch_errors,
            started_at=started_at,
            finished_at=finished_at,
            # Penilaian `partial` hanya sah untuk run yang benar-benar
            # memanggil actor. Pada replay `--from-file` jumlah post yang
            # DIMILIKI akun tidak ikut di berkas (hanya post-nya sendiri),
            # sehingga akun yang memang cuma punya 3 post akan dinilai
            # kurang dari `--results` dan salah ditandai partial.
            requested_per_account=None if args.from_file else args.results,
            returned=kembali,
            available=tersedia,
        )

        summary = None
        if not args.no_log:
            with ScrapeLogger(cfg.postgres, run_id=run_id) as slog:
                summary = slog.log_many(outcomes)
                slog.log_run(
                    platform=platform,
                    status=ACTOR_ERROR if fatal_error else SUCCESS,
                    records=stats.inserted,
                    message=(
                        (f"FATAL: {fatal_error} | " if fatal_error else "")
                        + f"actor={actor} item={len(items_all)} "
                        f"masuk_L0={stats.inserted} item_error={stats.skipped_error} "
                        f"gagal={sum(1 for o in outcomes if not o.ok)}/{len(outcomes)} akun "
                        f"file={jsonl_path.name if items_all and not args.from_file else args.from_file}"
                    ),
                    started_at=started_at,
                    finished_at=finished_at,
                )

        # --- laporan ---------------------------------------------------------
        by_status: dict[str, int] = {}
        for o in outcomes:
            by_status[o.status] = by_status.get(o.status, 0) + 1

        print("\n--- hasil ---")
        print(f"item dari actor/file : {len(items_all)}")
        print(f"masuk L0             : {stats.inserted}")
        print(f"item error disaring  : {stats.skipped_error}")
        print(f"tanpa username       : {stats.skipped_no_username}")
        print(f"tanpa content_id     : {stats.skipped_no_content_id}")
        print("\nstatus per akun:")
        for status in sorted(by_status):
            print(f"  {status:22s}: {by_status[status]}")
        if summary:
            print(f"\nscheduler_logs       : {summary.written} baris ditulis"
                  f"{', ' + str(summary.failed_to_write) + ' gagal' if summary.failed_to_write else ''}")
            print(f"run_id               : {summary.run_id}")

        gagal = [o for o in outcomes if not o.ok]
        if gagal:
            print("\nakun gagal:")
            for o in gagal:
                print(f"  {o.username:24s} {o.status:22s} {(o.message or '')[:70]}")
        return 0


def main(argv=None) -> int:
    """Titik masuk: siapkan env & konfigurasi, lalu jalankan di bawah kunci.

    Kunci dipasang per platform supaya dua Scheduled Task -- satu Instagram,
    satu TikTok -- tetap bisa berjalan bersamaan, sementara dua eksekusi
    Instagram yang tumpang tindih ditolak.
    """
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

    # dry-run dan --from-file tidak memanggil Apify sama sekali.
    if args.dry_run or args.from_file:
        return _jalankan(args, cfg)
    return jalankan_terkunci(NAMA_KUNCI.format(platform=args.platform),
                             _jalankan, args, cfg)


if __name__ == "__main__":
    sys.exit(main())
