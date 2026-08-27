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
from datetime import datetime, timezone

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
    p.add_argument("--dry-run", action="store_true",
                   help="Tampilkan target dan estimasi biaya lalu berhenti. Nol biaya.")
    p.add_argument("--yes", action="store_true", help="Lewati konfirmasi biaya.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config()

    conn = _conn()
    with conn.cursor() as cur:
        cur.execute(SQL_TARGET, (args.platform,))
        baris = cur.fetchall()

    if not baris:
        print("Tidak ada follower yang bisa diperkaya.")
        conn.close()
        return 1

    # username -> daftar (social_account_id, follower_platform_id, date)
    peta: dict[str, list[tuple]] = {}
    for uname, sid, pid, tgl in baris:
        peta.setdefault(uname, []).append((sid, pid, tgl))

    usernames = sorted(peta)
    estimasi = len(usernames) * PRICE_PER_PROFILE_USD
    print(f"Baris follower L1 : {len(baris)}")
    print(f"Username unik     : {len(usernames)}")
    print(f"Estimasi biaya    : ${estimasi:.2f} "
          f"(${PRICE_PER_PROFILE_USD}/profil)")

    if args.dry_run:
        print("\ncontoh 10 username:", usernames[:10])
        conn.close()
        return 0

    if not args.yes:
        print("Jalankan ulang dengan --yes untuk melanjutkan.")
        conn.close()
        return 0

    # Plafon per batch DITURUNKAN dari plafon total yang disetujui, bukan dari
    # rumus 1.5x di pipeline.py. Rumus itu menghasilkan $0.39/batch x 13 batch =
    # $5.07, di atas plafon yang disetujui. Membagi plafon total ke jumlah batch
    # membuat batas yang disetujui benar-benar mengikat.
    jml_batch = max(1, (len(usernames) + args.batch_size - 1) // args.batch_size)
    plafon = round(args.cap_total / jml_batch, 4)
    scraper = InstagramProfileScraper(cfg.apify, actor_id=ACTOR_IG,
                                      max_charge_usd=plafon)
    print(f"Plafon total      : ${args.cap_total} (disetujui)")
    print(f"Plafon per batch  : ${plafon} x {jml_batch} batch")

    run_id = str(uuid.uuid4())
    # Tanggal DISAMAKAN dengan baris follower yang sudah ada, supaya digabung
    # dan bukan membuat baris harmonization baru.
    tgl_kunci = baris[0][3]
    scraped_at = datetime(tgl_kunci.year, tgl_kunci.month, tgl_kunci.day,
                          12, 0, 0, tzinfo=timezone.utc)
    print(f"scrape_run_id     : {run_id}")
    print(f"scraped_at dipakai: {scraped_at.isoformat()} (mengikuti baris lama)")

    chunks = chunked(usernames, args.batch_size)
    print(f"Total batch       : {len(chunks)}\n")

    semua_item: dict[str, dict] = {}
    total_biaya = 0.0
    gagal_batch = 0

    for i, chunk in enumerate(chunks, 1):
        try:
            b = scraper.scrape_batch(chunk, batch_index=i)
        except Exception as exc:  # noqa: BLE001
            gagal_batch += 1
            logger.error("Batch %d gagal: %s", i, exc)
            continue
        if b.cost_usd:
            total_biaya += b.cost_usd
        for it in b.items:
            u = (it.get("username") or "").strip()
            if u:
                semua_item[u] = it
        logger.info("Batch %d/%d: %d item, biaya $%.4f (kumulatif $%.4f)",
                    i, len(chunks), len(b.items), b.cost_usd or 0.0, total_biaya)

    # --- tulis ke L0 --------------------------------------------------------
    ditulis = 0
    berhasil_user = 0
    gagal_user: list[str] = []
    id_beda: list[tuple] = []
    err_item = 0
    sekarang = datetime.now(timezone.utc)

    with conn.cursor() as cur:
        # Bersihkan hasil enrichment sebelumnya untuk tanggal & actor yang sama,
        # supaya menjalankan ulang MENGGANTI hasil enrichment, bukan menumpuk.
        # Baris dari actor follower-list TIDAK ikut karena source_actor beda.
        cur.execute("""DELETE FROM l0_raw.ig_followers_apify
                       WHERE source_actor = %s
                         AND (scraped_at AT TIME ZONE 'UTC')::date = %s""",
                    (ACTOR_IG, scraped_at.date()))
        dihapus = cur.rowcount or 0

        for uname in usernames:
            item = semua_item.get(uname)
            if item is None:
                gagal_user.append(uname)
                continue
            if item.get("error"):
                err_item += 1
            m = petakan(item, "instagram")
            if not (m["bio"] or m["followers_count"] is not None
                    or m["following_count"] is not None):
                # Tidak ada satu pun field yang kita cari -> tidak berguna.
                gagal_user.append(uname)
                continue
            berhasil_user += 1

            for sid, pid, _tgl in peta[uname]:
                if m["follower_id"] and m["follower_id"] != pid:
                    id_beda.append((uname, pid, m["follower_id"]))
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
                ditulis += 1
    conn.commit()
    conn.close()

    print("\n" + "=" * 74)
    print("HASIL ENRICHMENT")
    print("=" * 74)
    print(f"  username target        : {len(usernames)}")
    print(f"  profil kembali berguna : {berhasil_user}")
    print(f"  gagal / tanpa field    : {len(gagal_user)}")
    print(f"  item ber-error dr actor: {err_item}")
    print(f"  batch gagal            : {gagal_batch}")
    print(f"  baris L0 dihapus (rerun): {dihapus}")
    print(f"  baris L0 ditulis       : {ditulis}")
    print(f"  id L1 != id actor      : {len(id_beda)}")
    print(f"  biaya aktual           : ${total_biaya:.4f}")
    print(f"  estimasi               : ${estimasi:.4f}")
    if gagal_user[:10]:
        print(f"  contoh gagal           : {gagal_user[:10]}")
    if id_beda[:5]:
        print(f"  contoh id beda         : {id_beda[:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
