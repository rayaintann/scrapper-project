"""Memperkaya follower yang SUDAH ada di L1 dengan detail profil.

    python enrich_follower_profiles.py --platform instagram --yes

Actor: `apify/instagram-profile-scraper` -- actor yang SAMA yang sudah dipakai
project ini untuk profil KOL, lewat kelas `InstagramProfileScraper` yang sudah
ada. Tidak ada actor baru, tidak ada kelas baru.

============================================================================
KENAPA INI MEMPERKAYA, BUKAN MENGGANTI
============================================================================

Scrape follower-list sebelumnya memakai actor yang memang tidak mengembalikan
bio maupun jumlah followers/following:

    l1_silver.unified_follower (instagram)  1.300 baris
        bio              0/1.300
        followers_count  0/1.300
        following_count  0/1.300

Baris follower-nya sendiri VALID dan tetap dipakai. Yang ditambahkan hanya
kolom yang kosong.

Tiga hal membuat penambahan ini tidak merusak data lama:

  1. `source_actor` BERBEDA (`apify/instagram-profile-scraper`). Penghapusan
     di `follower_raw_store.simpan()` dibatasi per (akun, source_actor,
     tanggal), jadi 1.300 baris dari actor follower-list tidak tersentuh.

  2. `scraped_at` DISAMAKAN dengan tanggal baris lama. Kunci konflik di
     harmonization adalah (social_account_id, follower_platform_id, date)
     dengan `date` diturunkan dari `scraped_at`. Memakai tanggal hari ini akan
     menghasilkan BARIS BARU, bukan penggabungan.

  3. Procedure yang sudah ada memang menggabungkan dengan COALESCE:

         bio = COALESCE(EXCLUDED.bio, instagram_follower.bio)

     Nilai baru mengisi yang kosong; nilai lama tidak pernah ditimpa NULL.
     Berlaku di `sp_sync_instagram_follower()` maupun
     `sp_build_unified_follower()`. Karena COALESCE, urutan pemrosesan kedua
     sumber tidak berpengaruh.

Tidak ada tabel baru, procedure baru, atau migration.

============================================================================
KENAPA USERNAME UNIK, BUKAN PER BARIS
============================================================================

1.300 baris follower Instagram hanya berisi 1.221 username unik -- 79 baris
adalah orang yang sama mengikuti lebih dari satu KOL. Actor menagih per profil
yang dikembalikan, jadi men-scrape per baris berarti membayar 79 profil dua
kali untuk data yang identik.

Satu profil hasil scrape lalu ditulis ke SEMUA pasangan (akun KOL, follower)
yang memakai username itu, sehingga seluruh 1.300 baris tetap ikut diperkaya.

============================================================================
PENCOCOKAN
============================================================================

Pemetaan `username` <-> `follower_platform_id` di L1 sudah diperiksa dan
bersifat 1:1 ketat (0 username dengan >1 id, 0 id dengan >1 username), jadi
pencocokan lewat username tidak ambigu.

`follower_platform_id` yang ditulis diambil dari L1, BUKAN dari item actor.
Itu yang menjamin kunci konflik cocok sehingga barisnya digabung. Kalau `id`
dari actor ternyata berbeda, itu TIDAK dipakai diam-diam -- selisihnya dihitung
dan dilaporkan.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2

from apify_ig import InstagramProfileScraper, chunked
from config import PRICE_PER_PROFILE_USD, load_config
from follower_raw_store import petakan

logger = logging.getLogger("enrich")

ACTOR_IG = "apify/instagram-profile-scraper"

SQL_TARGET = """
    SELECT f.username, f.social_account_id, f.follower_platform_id, f.date
    FROM l1_silver.unified_follower f
    JOIN public.platforms pl ON pl.id = f.platform_id
    WHERE pl.key = %s
      AND f.username IS NOT NULL
      AND f.social_account_id IS NOT NULL
"""


def _conn():
    from dotenv import load_dotenv
    load_dotenv()
    return psycopg2.connect(
        host=os.environ["PG_HOST"], port=os.getenv("PG_PORT", "5432"),
        dbname=os.environ["PG_DB"], user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"], connect_timeout=15)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Perkaya follower L1 dengan detail profil.")
    p.add_argument("--platform", choices=["instagram"], default="instagram",
                   help="TikTok belum termasuk; jalur dan actor-nya berbeda.")
    p.add_argument("--batch-size", type=int, default=100)
    p.add_argument("--cap-total", type=float, default=4.49,
                   help="Plafon biaya TOTAL yang disetujui, USD. Plafon per batch "
                        "diturunkan dari sini, bukan sebaliknya (default 4.49).")
    p.add_argument("--akun-file", default=None, metavar="FILE",
                   help="Batasi ke social_account_id KOL di file ini (satu per baris). "
                        "Tanpa ini seluruh follower L1 platform itu jadi target.")
    p.add_argument("--hanya-belum", action="store_true",
                   help="Lewati username yang sudah pernah diperkaya actor ini -- "
                        "profilnya sudah dibayar, termasuk yang bio-nya memang kosong.")
    p.add_argument("--lewati-file", default=None, metavar="FILE",
                   help="Username yang TIDAK boleh dikirim ke actor (satu per baris), mis. "
                        "semua username yang sudah pernah dibayar. --hanya-belum saja tidak "
                        "cukup: profil privat/terhapus tidak pernah tertulis ke L0, jadi "
                        "tanpa ini mereka dikirim -- dan ditagih -- ulang tiap batch.")
    p.add_argument("--maks-batch", type=int, default=None, metavar="N",
                   help="Berhenti setelah N batch. Dipakai untuk menjalankan satu "
                        "batch per proses dan memeriksa kondisi mesin di antaranya.")
    p.add_argument("--dari-run", default=None, metavar="RUN_ID",
                   help="Tulis dari dataset run Apify yang SUDAH dibayar, tanpa "
                        "memanggil actor (pemulihan run yang terputus sebelum ditulis).")
    p.add_argument("--dry-run", action="store_true",
                   help="Tampilkan target dan estimasi biaya lalu berhenti. Nol biaya.")
    p.add_argument("--yes", action="store_true", help="Lewati konfirmasi biaya.")
    return p.parse_args(argv)


SQL_SUDAH_DIPERKAYA = """
    SELECT DISTINCT username FROM l0_raw.ig_followers_apify
     WHERE source_actor = %s AND username IS NOT NULL
"""


#: `scraped_at` TERAKHIR baris asli (actor follower-list) per (akun, follower,
#: tanggal). Dibaca supaya baris enrichment bisa ditempatkan SESUDAHNYA.
SQL_SCRAPED_ASLI = """
    SELECT social_account_id::text, followers_ig_id,
           (scraped_at AT TIME ZONE 'UTC')::date, max(scraped_at)
      FROM l0_raw.ig_followers_apify
     WHERE source_actor IS DISTINCT FROM %s AND social_account_id::text = ANY(%s)
     GROUP BY 1, 2, 3
"""


def _scraped_at(tgl, asli: datetime | None = None) -> datetime:
    """`scraped_at` baris enrichment untuk satu baris follower.

    Dua syarat, keduanya dari `sp_sync_instagram_follower`:

    1. TANGGAL sama dengan baris itu -- kunci konflik harmonization adalah
       (akun, follower, date). Dulu satu tanggal dipakai untuk semua baris
       (`baris[0][3]`), sehingga follower tanggal lain tidak pernah tergabung.
    2. WAKTU sesudah baris asli -- procedure hanya meng-update kalau
       `processed_at` baru lebih besar, dan `processed_at` grup = `scraped_at`
       terbaru. Jam 12:00 tetap (desain lama) membuat enrichment untuk baris
       yang di-scrape sore hari tidak pernah diterapkan (22 September: 7 bio).

    Maka: 1 detik sesudah baris asli, dibatasi tetap di tanggal yang sama;
    tanpa baris asli, 12:00 UTC seperti sebelumnya.
    """
    siang = datetime(tgl.year, tgl.month, tgl.day, 12, 0, 0, tzinfo=timezone.utc)
    if asli is None:
        return siang
    akhir_hari = datetime(tgl.year, tgl.month, tgl.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
    return max(siang, min(asli + timedelta(seconds=1), akhir_hari))


def _tulis_batch(conn, run_id: str, items: dict, peta: dict, sekarang: datetime,
                 hasil: dict) -> None:
    """Tulis satu batch lalu COMMIT. Batch berikutnya gagal pun, yang ini tetap.

    Angkanya dikumpulkan LOKAL dan baru digabung ke `hasil` sesudah COMMIT
    berhasil. Kalau ditambahkan langsung, batch yang di-rollback caller tetap
    meninggalkan hitungannya, dan laporan akhir mengaku menulis baris yang
    sebenarnya tidak ada di database -- justru pada pekerjaan yang tugasnya
    mempertanggungjawabkan profil berbayar.
    """
    lokal = {"berhasil_user": 0, "gagal_user": [], "id_beda": [], "err_item": 0,
             "ditulis": 0, "dihapus": 0}
    with conn.cursor() as cur:
        for uname, item in items.items():
            if item.get("error"):
                lokal["err_item"] += 1
            m = petakan(item, "instagram")
            if not (m["bio"] or m["followers_count"] is not None
                    or m["following_count"] is not None):
                # Tidak ada satu pun field yang kita cari -> tidak berguna.
                lokal["gagal_user"].append(uname)
                continue
            lokal["berhasil_user"] += 1
            for sid, pid, tgl, asli in peta[uname]:
                if m["follower_id"] and m["follower_id"] != pid:
                    lokal["id_beda"].append((uname, pid, m["follower_id"]))
                scraped_at = _scraped_at(tgl, asli)
                # Rerun MENGGANTI enrichment pasangan ini saja; baris dari actor
                # follower-list (source_actor beda) tidak tersentuh.
                cur.execute("""DELETE FROM l0_raw.ig_followers_apify
                               WHERE source_actor = %s AND social_account_id = %s
                                 AND followers_ig_id = %s
                                 AND (scraped_at AT TIME ZONE 'UTC')::date = %s""",
                            (ACTOR_IG, sid, pid, scraped_at.date()))
                lokal["dihapus"] += cur.rowcount or 0
                cur.execute("""
                    INSERT INTO l0_raw.ig_followers_apify (
                        social_account_id, scrape_run_id, followers_ig_id, username,
                        full_name, is_private, is_verified, profile_pic_url,
                        is_bussiness_account, followers_count, following_count, bio,
                        email, phones, social_links, raw_payload, scraped_at,
                        source_actor, insert_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (sid, run_id,
                     # id dari L1, BUKAN dari actor -- ini yang menjamin merge.
                     pid, uname, m["nama"], m["is_private"], m["is_verified"],
                     m["foto"], m["is_business"], m["followers_count"],
                     m["following_count"], m["bio"], m["email"], m["phones"],
                     m["social_links"], json.dumps(item, ensure_ascii=False),
                     scraped_at, ACTOR_IG, sekarang))
                lokal["ditulis"] += 1
    conn.commit()
    # Hanya sesudah COMMIT: sejak titik ini angkanya benar-benar ada di DB.
    for k, v in lokal.items():
        if isinstance(v, list):
            hasil[k].extend(v)
        else:
            hasil[k] += v


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()

    conn = _conn()
    akun = None
    if args.akun_file:
        with open(args.akun_file, encoding="utf-8") as fh:
            akun = sorted({b.strip() for b in fh if b.strip()})
    with conn.cursor() as cur:
        if akun is None:
            cur.execute(SQL_TARGET, (args.platform,))
        else:
            cur.execute(SQL_TARGET + " AND f.social_account_id::text = ANY(%s)",
                        (args.platform, akun))
        baris = cur.fetchall()
        sudah: set[str] = set()
        if args.hanya_belum:
            cur.execute(SQL_SUDAH_DIPERKAYA, (ACTOR_IG,))
            sudah = {r[0] for r in cur.fetchall()}
        if args.lewati_file:
            with open(args.lewati_file, encoding="utf-8") as fh:
                sudah |= {b.strip() for b in fh if b.strip()}
        cur.execute(SQL_SCRAPED_ASLI, (ACTOR_IG, sorted({str(b[1]) for b in baris})))
        asli = {(sid, pid, tgl): ts for sid, pid, tgl, ts in cur.fetchall()}
    # SELECT pun membuka transaksi. Tanpa ini koneksi menggantung
    # "idle in transaction" selama actor batch pertama berjalan (menit-menit).
    conn.rollback()

    # username -> daftar (social_account_id, follower_platform_id, date, scraped_at asli)
    peta: dict[str, list[tuple]] = {}
    for uname, sid, pid, tgl in baris:
        if uname in sudah:
            continue
        peta.setdefault(uname, []).append((sid, pid, tgl, asli.get((str(sid), pid, tgl))))

    if not peta:
        print("Tidak ada follower yang bisa diperkaya.")
        conn.close()
        return 1

    usernames = sorted(peta)
    estimasi = len(usernames) * PRICE_PER_PROFILE_USD
    print(f"Akun KOL dibatasi : {len(akun) if akun is not None else 'tidak (semua)'}")
    print(f"Baris follower L1 : {len(baris)}")
    print(f"Sudah diperkaya   : {len(sudah & {b[0] for b in baris})} username dilewati")
    print(f"Username target   : {len(usernames)}")
    # Kalau kunci (akun, follower, tanggal) meleset -- mis. tipe kolom L0 dan
    # L1 berbeda -- SEMUA baris diam-diam jatuh ke 12:00 dan bug yang sudah
    # diperbaiki kembali tanpa satu pun error. Angka ini yang menampakkannya.
    tanpa_asli = sum(1 for v in peta.values() for *_, a in v if a is None)
    print(f"Tanpa scraped_at asli: {tanpa_asli} dari "
          f"{sum(len(v) for v in peta.values())} baris (jatuh ke 12:00 UTC)")
    print(f"Estimasi biaya    : ${estimasi:.2f} "
          f"(${PRICE_PER_PROFILE_USD}/profil)")
    print(f"Tanggal baris     : {sorted({str(t) for v in peta.values() for _s, _p, t, _a in v})}")

    if args.dry_run:
        print("\ncontoh 10 username:", usernames[:10])
        conn.close()
        return 0

    if not args.yes:
        print("Jalankan ulang dengan --yes untuk melanjutkan.")
        conn.close()
        return 0

    if args.dari_run:
        # Nol biaya: hanya membaca dataset run yang sudah dibayar.
        from apify_client import ApifyClient
        client = ApifyClient(cfg.apify.token)
        run = client.run(args.dari_run).get()
        ds = run.get("defaultDatasetId") if isinstance(run, dict) else run.default_dataset_id
        items: dict[str, dict] = {}
        for it in client.dataset(ds).iterate_items():
            u = (dict(it).get("username") or "").strip()
            if u in peta:
                items[u] = dict(it)
        hasil = {"berhasil_user": 0, "gagal_user": [], "id_beda": [], "err_item": 0,
                 "ditulis": 0, "dihapus": 0}
        _tulis_batch(conn, str(uuid.uuid4()), items, peta, datetime.now(timezone.utc), hasil)
        conn.close()
        print(f"PEMULIHAN run {args.dari_run}: {len(items)} profil cocok target, "
              f"{hasil['berhasil_user']} berguna, {hasil['ditulis']} baris ditulis, "
              f"id beda {len(hasil['id_beda'])}")
        return 0

    # Potong dulu, baru periksa plafon. `--maks-batch` ada justru untuk
    # menjalankan sebagian target ketika keseluruhannya TIDAK muat di plafon;
    # kalau plafon diuji atas seluruh target, opsi itu selalu ditolak persis
    # pada satu-satunya keadaan yang membuatnya berguna.
    chunks = chunked(usernames, args.batch_size)
    total_batch = len(chunks)
    if args.maks_batch is not None:
        chunks = chunks[:args.maks_batch]
    akan_dijalankan = sum(len(c) for c in chunks)
    biaya_dijalankan = akan_dijalankan * PRICE_PER_PROFILE_USD

    if biaya_dijalankan > args.cap_total:
        print(f"DIHENTIKAN: estimasi ${biaya_dijalankan:.2f} untuk {akan_dijalankan} "
              f"profil melewati plafon ${args.cap_total:.2f}.")
        conn.close()
        return 3

    # Plafon per batch DITURUNKAN dari plafon total yang disetujui, bukan dari
    # rumus 1.5x di pipeline.py. Rumus itu menghasilkan $0.39/batch x 13 batch =
    # $5.07, di atas plafon yang disetujui. Membagi plafon total ke jumlah batch
    # membuat batas yang disetujui benar-benar mengikat.
    jml_batch = max(1, len(chunks))
    plafon = round(args.cap_total / jml_batch, 4)
    scraper = InstagramProfileScraper(cfg.apify, actor_id=ACTOR_IG,
                                      max_charge_usd=plafon)
    print(f"Plafon total      : ${args.cap_total} (disetujui)")
    print(f"Plafon per batch  : ${plafon} x {jml_batch} batch")

    run_id = str(uuid.uuid4())
    print(f"scrape_run_id     : {run_id}")
    print("scraped_at dipakai: tanggal baris follower masing-masing, 1 detik "
          "sesudah baris aslinya (minimum 12:00 UTC, maksimum akhir hari)")

    print(f"Total batch       : {total_batch}")
    if args.maks_batch is not None:
        print(f"Dijalankan kali ini: {len(chunks)} batch (--maks-batch), "
              f"{akan_dijalankan} profil, estimasi ${biaya_dijalankan:.2f}")
    print()

    hasil = {"berhasil_user": 0, "gagal_user": [], "id_beda": [], "err_item": 0,
             "ditulis": 0, "dihapus": 0}
    total_biaya = 0.0
    gagal_batch = 0
    sekarang = datetime.now(timezone.utc)

    # Tulis & COMMIT per batch: proses yang terhenti di tengah tidak membuang
    # profil yang sudah dibayar, dan memori tidak menampung seluruh hasil.
    for i, chunk in enumerate(chunks, 1):
        try:
            b = scraper.scrape_batch(chunk, batch_index=i)
        except Exception as exc:  # noqa: BLE001
            gagal_batch += 1
            logger.error("Batch %d gagal: %s", i, exc)
            hasil["gagal_user"].extend(chunk)
            continue
        if b.cost_usd:
            total_biaya += b.cost_usd
        items: dict[str, dict] = {}
        for it in b.items:
            u = (it.get("username") or "").strip()
            if u in peta:
                items[u] = it
        hasil["gagal_user"].extend(u for u in chunk if u not in items)
        try:
            _tulis_batch(conn, run_id, items, peta, sekarang, hasil)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            gagal_batch += 1
            logger.error("Batch %d gagal ditulis: %s", i, exc)
            continue
        logger.info("Batch %d/%d: %d profil, biaya $%.4f (kumulatif $%.4f), baris ditulis %d",
                    i, len(chunks), len(items), b.cost_usd or 0.0, total_biaya,
                    hasil["ditulis"])
    conn.close()

    print("\n" + "=" * 74)
    print("HASIL ENRICHMENT")
    print("=" * 74)
    print(f"  username target        : {len(usernames)}")
    print(f"  profil kembali berguna : {hasil['berhasil_user']}")
    print(f"  gagal / tanpa field    : {len(hasil['gagal_user'])}")
    print(f"  item ber-error dr actor: {hasil['err_item']}")
    print(f"  batch gagal            : {gagal_batch}")
    print(f"  baris L0 dihapus (rerun): {hasil['dihapus']}")
    print(f"  baris L0 ditulis       : {hasil['ditulis']}")
    print(f"  id L1 != id actor      : {len(hasil['id_beda'])}")
    print(f"  biaya aktual           : ${total_biaya:.4f}")
    print(f"  estimasi               : ${estimasi:.4f}")
    if hasil["gagal_user"][:10]:
        print(f"  contoh gagal           : {hasil['gagal_user'][:10]}")
    if hasil["id_beda"][:5]:
        print(f"  contoh id beda         : {hasil['id_beda'][:5]}")
    return 0 if not gagal_batch else 1


if __name__ == "__main__":
    raise SystemExit(main())
