"""Asset enrichment profil FOLLOWER untuk KOL dari "Add New KOL" (Instagram).

    Add New KOL (website) -> l0_raw.ig_followers_apify (daftar follower, tanpa bio)
        -> instagram_follower -> unified_follower
        -> follower_profile_enrichment          (modul ini; BERBAYAR, default OFF)
              apify/instagram-profile-scraper -> bio, followers_count, following_count
              -> l0_raw.ig_followers_apify (baris enrichment)
              -> sp_sync_instagram_follower + sp_build_unified_follower
        -> audience_feature -> audience_gold    (inferensi dari full_name + bio)

Daftar follower dari Add KOL tidak membawa bio. Tanpa bio, `audience_inference`
hanya punya nama, jadi interest/lokasi/umur audiens KOL baru nyaris semuanya
`unknown`. Asset ini memanggil enrichment yang SUDAH ADA
(`enrich_follower_profiles.py`: actor, pemetaan, plafon, tulis-per-batch) untuk
follower KOL baru itu saja. Tidak ada actor, pemetaan, atau aturan inferensi baru.

DEFAULT OFF -- TIDAK ADA BIAYA TANPA KEPUTUSAN EKSPLISIT
========================================================
Asset ini satu-satunya di `transform_chain_job` yang bisa memanggil Apify, dan
job itu dipicu sensor. Karena itu ia tidak melakukan apa pun yang berbayar kecuali
environment mengizinkannya:

    FOLLOWER_ENRICHMENT_MODE      off (default) | allowlist | auto
    FOLLOWER_ENRICHMENT_KOL_IDS   mode allowlist: kol_directory.id dipisah koma.
                                  Hanya KOL di daftar ini yang diproses.
    FOLLOWER_ENRICHMENT_SINCE     mode auto: WAJIB. Tanggal/waktu ISO-8601; hanya Add
                                  KOL yang follower-nya selesai pada/sesudah waktu ini.
                                  Tanpa nilai ini mode auto tidak memproses apa pun --
                                  backlog Add KOL lama tidak pernah diproses diam-diam.
    FOLLOWER_ENRICHMENT_CAP_USD   opsional, hanya bisa MENURUNKAN plafon; batas atasnya
                                  `enrich_follower_profiles.CAP_TOTAL_DEFAULT`.

Mode off tetap membaca kandidat (read-only) dan melaporkannya di metadata.

SCOPE -- HANYA FOLLOWER DARI ADD KOL
====================================
    akun      `public.add_kol_scrape_log`: platform instagram, step `followers`,
              status `success`; KOL-nya `directory_status = 'active'`.
    follower  baris `l1_silver.unified_follower` akun itu yang baris L0-nya ditulis
              RUN ADD KOL itu sendiri (`l0_raw.ig_followers_apify.scrape_run_id =
              add_kol_scrape_log.run_id`). Follower akun yang sama dari scraping
              massal (`scrape_followers.py`) TIDAK ikut.
    belum     username yang belum punya baris enrichment (`source_actor` = actor
              enrichment) -- aturan `--hanya-belum` yang sudah ada.

TikTok, roster lama, dan follower KOL lain tidak pernah masuk query.

SATU AKUN PER RUN, PLAFON PER AKUN
==================================
Satu run memproses paling banyak `MAKS_AKUN_PER_RUN` akun (1). Estimasi dihitung
atas username akun ITU, dibandingkan dengan plafon; di atas plafon -> tidak ada
panggilan actor. Batas tagihan run actor = min(plafon, 1,5 x estimasi), jadi
plafon $4,49 tidak menjadi cek kosong untuk target 50 profil. Scraper dibuat
dengan `max_retries=0`: satu eksekusi asset hanya punya satu kesempatan memanggil
actor per batch, sehingga batas tagihan run itu juga batas biaya eksekusinya.

IDEMPOTEN, TANPA DELETE, TANPA PUTARAN
======================================
Setiap percobaan dicatat satu baris di `public.scheduler_logs`
(`job_name = add_kol_follower_enrichment`) lewat `ScrapeLogger` yang sudah ada:

    sudah ada baris `success`      -> akun tidak pernah diproses lagi. Profil yang
                                      privat/terhapus tidak ditagih ulang tiap run.
    gagal >= MAKS_PERCOBAAN kali   -> berhenti mencoba otomatis.

Baris ditulis dengan `ganti=False`: tidak ada DELETE. Menulis ke
`l0_raw.ig_followers_apify` memang membuat `l0_raw_new_data_sensor` memicu SATU
run susulan; di run itu akun tadi sudah bercatatan `success`, jadi tidak ada
panggilan actor, tidak ada tulisan L0 baru, dan sensor diam.

KEGAGALAN TIDAK MENJATUHKAN RANTAI
==================================
Apa pun yang gagal di sini (Apify, plafon, kunci, DB) dicatat di metadata/log dan
asset tetap selesai, supaya `audience_feature` / `audience_gold` tetap menghitung
dari data yang ada. Token Apify dan kredensial DB tidak pernah ditulis ke log.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import enrich_follower_profiles as E  # noqa: E402
from config import PRICE_PER_PROFILE_USD, load_config  # noqa: E402
from run_lock import LockTaken, RunLock  # noqa: E402
from scrape_log import AccountOutcome, ScrapeLogger  # noqa: E402

logger = logging.getLogger(__name__)

GROUP = "audience"
PLATFORM = "instagram"

#: Pembeda baris `public.scheduler_logs` milik asset ini.
JOB_NAME = "add_kol_follower_enrichment"
CATEGORY = "follower_enrichment"
STATUS_SUKSES = "success"
STATUS_GAGAL = "enrichment_failed"

#: Paling banyak sekian akun Add KOL per run.
MAKS_AKUN_PER_RUN = 1
#: Percobaan gagal per akun sebelum berhenti mencoba otomatis.
MAKS_PERCOBAAN = 2
#: Batas tagihan run actor relatif terhadap estimasi (rumus yang sama dengan pipeline.py).
FAKTOR_PLAFON_RUN = 1.5
LOCK_NAME = "add_kol_follower_enrichment"

ENV_MODE = "FOLLOWER_ENRICHMENT_MODE"
ENV_KOL_IDS = "FOLLOWER_ENRICHMENT_KOL_IDS"
ENV_SINCE = "FOLLOWER_ENRICHMENT_SINCE"
ENV_CAP = "FOLLOWER_ENRICHMENT_CAP_USD"
MODE_OFF, MODE_ALLOWLIST, MODE_AUTO = "off", "allowlist", "auto"

#: Akun Instagram yang follower-nya berhasil diambil "Add New KOL".
SQL_AKUN_ADD_KOL = """
    SELECT k.id::text, l.social_account_id::text, k.username, max(l.finished_at)
      FROM public.add_kol_scrape_log l
      JOIN public.kol_directory k ON k.id = l.kol_directory_id
     WHERE l.platform = 'instagram' AND l.step = 'followers' AND l.status = 'success'
       AND l.social_account_id IS NOT NULL
       AND k.directory_status = 'active'
     GROUP BY 1, 2, 3
     ORDER BY 4, 1"""

#: Riwayat percobaan asset ini per KOL: (kol_id, jumlah sukses, jumlah gagal).
SQL_RIWAYAT = """
    SELECT kol_account_id::text,
           count(*) FILTER (WHERE status = %s),
           count(*) FILTER (WHERE status <> %s)
      FROM public.scheduler_logs
     WHERE job_name = %s AND kol_account_id IS NOT NULL
     GROUP BY 1"""

#: Follower L1 satu akun yang baris L0-nya ditulis run Add KOL akun itu sendiri.
SQL_FOLLOWER_ADD_KOL = """
    SELECT f.username, f.social_account_id, f.follower_platform_id, f.date
      FROM l1_silver.unified_follower f
      JOIN public.platforms pl ON pl.id = f.platform_id
     WHERE pl.key = 'instagram'
       AND f.social_account_id = %(sa)s::uuid
       AND f.username IS NOT NULL
       AND EXISTS (
            SELECT 1
              FROM l0_raw.ig_followers_apify r
              JOIN public.add_kol_scrape_log l
                ON l.run_id = r.scrape_run_id AND l.social_account_id = r.social_account_id
             WHERE l.platform = 'instagram' AND l.step = 'followers' AND l.status = 'success'
               AND r.source_actor IS DISTINCT FROM %(actor)s
               AND r.social_account_id = f.social_account_id
               AND r.followers_ig_id = f.follower_platform_id
               AND (r.scraped_at AT TIME ZONE 'UTC')::date = f.date)"""


# ---------------------------------------------------------------------------
# Pengaturan dari environment (murni)
# ---------------------------------------------------------------------------
@dataclass
class Pengaturan:
    mode: str = MODE_OFF
    kol_ids: frozenset = frozenset()
    sejak: datetime | None = None
    cap_usd: float = E.CAP_TOTAL_DEFAULT
    masalah: list[str] = field(default_factory=list)


def _parse_waktu(teks: str) -> datetime:
    t = datetime.fromisoformat(teks.strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def baca_pengaturan(env=None) -> Pengaturan:
    """Nilai yang tidak dikenali / tidak lengkap SELALU jatuh ke `off`."""
    env = os.environ if env is None else env
    p = Pengaturan()
    mode = (env.get(ENV_MODE) or MODE_OFF).strip().lower()
    if mode not in (MODE_OFF, MODE_ALLOWLIST, MODE_AUTO):
        p.masalah.append(f"{ENV_MODE}={mode!r} tidak dikenal -> off")
        mode = MODE_OFF

    ids = set()
    for x in (env.get(ENV_KOL_IDS) or "").replace(";", ",").split(","):
        x = x.strip().lower()
        if not x:
            continue
        try:
            ids.add(str(uuid.UUID(x)))
        except ValueError:
            p.masalah.append(f"{ENV_KOL_IDS}: {x!r} bukan UUID, diabaikan")
    p.kol_ids = frozenset(ids)

    mentah = (env.get(ENV_SINCE) or "").strip()
    if mentah:
        try:
            p.sejak = _parse_waktu(mentah)
        except ValueError:
            p.masalah.append(f"{ENV_SINCE}={mentah!r} bukan waktu ISO-8601")

    mentah = (env.get(ENV_CAP) or "").strip()
    if mentah:
        try:
            cap = float(mentah)
            if cap <= 0:
                raise ValueError
            # Hanya boleh menurunkan: batas atasnya plafon bawaan yang sudah disetujui.
            p.cap_usd = min(cap, E.CAP_TOTAL_DEFAULT)
            if cap > E.CAP_TOTAL_DEFAULT:
                p.masalah.append(f"{ENV_CAP}={cap} di atas plafon bawaan; dipakai {E.CAP_TOTAL_DEFAULT}")
        except ValueError:
            p.masalah.append(f"{ENV_CAP}={mentah!r} tidak sah; dipakai plafon bawaan")

    if mode == MODE_ALLOWLIST and not p.kol_ids:
        p.masalah.append(f"mode allowlist tanpa {ENV_KOL_IDS} yang sah -> off")
        mode = MODE_OFF
    if mode == MODE_AUTO and p.sejak is None:
        p.masalah.append(f"mode auto tanpa {ENV_SINCE} yang sah -> off")
        mode = MODE_OFF
    p.mode = mode
    return p


# ---------------------------------------------------------------------------
# Pemilihan akun (murni)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Akun:
    kol_id: str
    social_account_id: str
    username: str | None
    follower_selesai: datetime | None


def pilih_akun(akun: list[Akun], riwayat: dict[str, tuple[int, int]],
               p: Pengaturan) -> tuple[list[Akun], dict[str, list[str]]]:
    """(akun yang boleh diproses, urut dari Add KOL terlama; alasan dilewati -> username).

    `riwayat`: kol_id -> (jumlah sukses, jumlah gagal) dari scheduler_logs."""
    boleh: list[Akun] = []
    lewati: dict[str, list[str]] = {}

    def skip(why: str, a: Akun) -> None:
        lewati.setdefault(why, []).append(a.username or a.kol_id)

    for a in akun:
        sukses, gagal = riwayat.get(a.kol_id, (0, 0))
        if sukses:
            skip("sudah diperkaya", a)
        elif gagal >= MAKS_PERCOBAAN:
            skip(f"gagal {MAKS_PERCOBAAN}x, berhenti mencoba otomatis", a)
        elif p.mode == MODE_ALLOWLIST and a.kol_id not in p.kol_ids:
            skip("di luar allowlist", a)
        elif p.mode == MODE_AUTO and (a.follower_selesai is None or a.follower_selesai < p.sejak):
            skip("Add KOL sebelum FOLLOWER_ENRICHMENT_SINCE", a)
        else:
            boleh.append(a)
    return boleh, lewati


def susun_peta(baris, sudah: set, asli: dict) -> dict[str, list[tuple]]:
    """username -> [(social_account_id, follower_platform_id, date, scraped_at asli)],
    tanpa username yang sudah pernah diperkaya. Bentuknya sama dengan `peta` di CLI."""
    peta: dict[str, list[tuple]] = {}
    for uname, sid, pid, tgl in baris:
        if uname in sudah:
            continue
        peta.setdefault(uname, []).append((sid, pid, tgl, asli.get((str(sid), pid, tgl))))
    return peta


def plafon_run(n_username: int, cap_usd: float) -> tuple[float, float | None]:
    """(estimasi USD, batas tagihan run) -- batas None berarti DITOLAK (di atas plafon)."""
    estimasi = n_username * PRICE_PER_PROFILE_USD
    if estimasi > cap_usd:
        return estimasi, None
    return estimasi, round(min(cap_usd, estimasi * FAKTOR_PLAFON_RUN), 4)


def _aman(pesan: object, *rahasia: str | None) -> str:
    """Pesan error untuk log/metadata: dipotong, dan nilai rahasia disamarkan."""
    teks = str(pesan)
    for r in rahasia:
        if r:
            teks = teks.replace(r, "***")
    return teks[:300]


# ---------------------------------------------------------------------------
# DB: baca scope (read-only)
# ---------------------------------------------------------------------------
def baca_akun(cur) -> list[Akun]:
    cur.execute(SQL_AKUN_ADD_KOL)
    return [Akun(*r) for r in cur.fetchall()]


def baca_riwayat(cur) -> dict[str, tuple[int, int]]:
    cur.execute(SQL_RIWAYAT, (STATUS_SUKSES, STATUS_SUKSES, JOB_NAME))
    return {r[0]: (int(r[1]), int(r[2])) for r in cur.fetchall()}


def baca_peta(cur, akun: Akun) -> tuple[dict[str, list[tuple]], int]:
    """(peta target akun itu, jumlah baris follower Add KOL-nya di L1)."""
    cur.execute(SQL_FOLLOWER_ADD_KOL, {"sa": akun.social_account_id, "actor": E.ACTOR_IG})
    baris = cur.fetchall()
    if not baris:
        return {}, 0
    cur.execute(E.SQL_SUDAH_DIPERKAYA, (E.ACTOR_IG,))
    sudah = {r[0] for r in cur.fetchall()}
    cur.execute(E.SQL_SCRAPED_ASLI, (E.ACTOR_IG, [akun.social_account_id]))
    asli = {(sid, pid, tgl): ts for sid, pid, tgl, ts in cur.fetchall()}
    return susun_peta(baris, sudah, asli), len(baris)


# ---------------------------------------------------------------------------
# Eksekusi
# ---------------------------------------------------------------------------
#: Tanpa retry di dalam satu eksekusi: `scrape_batch` mengulang run actor sampai
#: `max_retries` kali, dan TIAP run punya batas tagihannya sendiri. Dengan 0, satu
#: eksekusi asset = paling banyak SATU run actor per batch, jadi batas tagihan run
#: adalah batas biaya eksekusi itu. Percobaan ulang tetap ada, tapi lintas run dan
#: tercatat (`MAKS_PERCOBAAN`). CLI `enrich_follower_profiles.py` tidak terpengaruh.
SCRAPER_MAX_RETRIES = 0


def _buat_scraper(cfg, batas_usd: float):
    return E.InstagramProfileScraper(cfg.apify, actor_id=E.ACTOR_IG, max_charge_usd=batas_usd,
                                     max_retries=SCRAPER_MAX_RETRIES)


def _catat(cfg, run_id: str, akun: Akun, status: str, ditulis: int, pesan: str,
           mulai: datetime) -> bool:
    with ScrapeLogger(cfg.postgres, run_id=run_id, job_name=JOB_NAME, category=CATEGORY) as log:
        return log.log_account(AccountOutcome(
            username=akun.username or "", platform=PLATFORM, status=status,
            kol_directory_id=akun.kol_id, records=ditulis, message=pesan,
            started_at=mulai, finished_at=datetime.now(timezone.utc)))


def _perkaya_akun(postgres: PostgresResource, conn, akun: Akun, peta: dict,
                  batas_usd: float, meta: dict) -> int:
    """Satu akun: actor -> tulis L0 (tanpa DELETE) -> sync L0H/L1 -> catat. Tidak melempar."""
    cfg = load_config()
    run_id = str(uuid.uuid4())
    mulai = datetime.now(timezone.utc)
    usernames = sorted(peta)
    chunks = E.chunked(usernames, 100)
    hasil = E._hasil_kosong()
    biaya, gagal_batch, galat = 0.0, 0, None
    try:
        scraper = _buat_scraper(cfg, round(batas_usd / max(1, len(chunks)), 4))
        biaya, gagal_batch = E._jalankan_batch(scraper, conn, chunks, peta, run_id, mulai,
                                               hasil, ganti=False)
    except Exception as exc:  # noqa: BLE001 - enrichment tidak boleh menjatuhkan rantai
        galat = _aman(exc, cfg.apify.token, cfg.postgres.password)
        logger.error("Enrichment follower @%s gagal: %s", akun.username, galat)

    if hasil["ditulis"]:
        # Supaya audience_feature di run yang SAMA sudah membaca bio-nya. Procedure
        # dan function yang sama dengan asset instagram_follower / unified_follower.
        try:
            postgres.call_procedure("CALL l0_harmonization.sp_sync_instagram_follower()")
            postgres.call_function("SELECT l1_silver.sp_build_unified_follower()")
            meta["l1_disegarkan"] = True
        except Exception as exc:  # noqa: BLE001
            meta["l1_disegarkan"] = False
            meta["galat_sync"] = _aman(exc, cfg.postgres.password)

    sukses = galat is None and gagal_batch == 0
    pesan = (f"target {len(usernames)} username; berguna {hasil['berhasil_user']}; "
             f"tanpa hasil {len(hasil['gagal_user'])}; baris L0 {hasil['ditulis']}; "
             f"biaya ${biaya:.4f}; batch gagal {gagal_batch}"
             + (f"; error: {galat}" if galat else ""))
    tercatat = _catat(cfg, run_id, akun, STATUS_SUKSES if sukses else STATUS_GAGAL,
                      hasil["ditulis"], pesan, mulai)
    meta.update({
        "status": STATUS_SUKSES if sukses else STATUS_GAGAL,
        "scrape_run_id": run_id,
        "username_dikirim": len(usernames),
        "profil_berguna": hasil["berhasil_user"],
        "tanpa_hasil": len(hasil["gagal_user"]),
        "baris_l0_ditulis": hasil["ditulis"],
        "baris_l0_dihapus": hasil["dihapus"],
        "biaya_aktual_usd": round(biaya, 4),
        "batch_gagal": gagal_batch,
        "tercatat_di_scheduler_logs": tercatat,
    })
    if galat:
        meta["galat"] = galat
    return hasil["ditulis"]


def _jalankan(postgres: PostgresResource) -> Output:
    p = baca_pengaturan()
    meta: dict = {"mode": p.mode, "plafon_usd": p.cap_usd}
    if p.masalah:
        meta["pengaturan"] = MetadataValue.json(p.masalah)
    ditulis = 0
    try:
        conn = postgres.get_conn()
        try:
            with conn.cursor() as cur:
                akun = baca_akun(cur)
                boleh, lewati = pilih_akun(akun, baca_riwayat(cur), p)
            conn.rollback()
            meta["akun_add_kol_instagram"] = len(akun)
            meta["dilewati"] = MetadataValue.json({k: len(v) for k, v in lewati.items()})
            meta["kandidat"] = MetadataValue.json([a.username or a.kol_id for a in boleh])
            if p.mode == MODE_OFF:
                meta["status"] = "off -- tidak ada panggilan actor"
                return Output(0, metadata=meta)

            diproses = 0
            for a in boleh:
                if diproses >= MAKS_AKUN_PER_RUN:
                    break
                with conn.cursor() as cur:
                    peta, n_l1 = baca_peta(cur, a)
                # SELECT pun membuka transaksi; jangan menggantung selama actor berjalan.
                conn.rollback()
                if not peta:
                    continue
                estimasi, batas = plafon_run(len(peta), p.cap_usd)
                meta.update({"akun_diproses": a.username or a.kol_id, "kol_id": a.kol_id,
                             "follower_add_kol_l1": n_l1, "username_target": len(peta),
                             "estimasi_usd": round(estimasi, 4)})
                if batas is None:
                    meta["status"] = (f"ditolak: estimasi ${estimasi:.2f} melewati plafon "
                                      f"${p.cap_usd:.2f} -- tidak ada panggilan actor")
                    break
                meta["batas_tagihan_run_usd"] = batas
                try:
                    with RunLock(LOCK_NAME):
                        ditulis = _perkaya_akun(postgres, conn, a, peta, batas, meta)
                except LockTaken as exc:
                    meta["status"] = f"dilewati: {_aman(exc)}"
                diproses += 1
            meta.setdefault("status", "tidak ada akun yang perlu diperkaya")
            meta["akun_menunggu"] = max(0, len(boleh) - diproses)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - audiens tetap harus dihitung dari data yang ada
        logger.error("follower_profile_enrichment dilewati karena error: %s", _aman(exc))
        meta["status"] = "error (rantai tetap dilanjutkan)"
        meta["galat"] = _aman(exc)
    return Output(ditulis, metadata=meta)


@asset(
    name="follower_profile_enrichment",
    group_name=GROUP,
    deps=[AssetKey("unified_follower")],
    kinds={"postgres", "python"},
    description=(
        "Detail profil (bio, followers/following) follower Instagram milik KOL dari "
        "\"Add New KOL\" -> l0_raw.ig_followers_apify, lewat enrichment existing "
        "(apify/instagram-profile-scraper). BERBAYAR dan DEFAULT OFF: hanya jalan "
        "kalau FOLLOWER_ENRICHMENT_MODE = allowlist/auto. Satu akun per run, plafon "
        "per akun, tanpa DELETE, satu kali per akun (tercatat di scheduler_logs). "
        "Kegagalan tidak menghentikan audience_feature."
    ),
)
def follower_profile_enrichment(postgres: PostgresResource) -> Output:
    return _jalankan(postgres)


follower_enrichment_assets = [follower_profile_enrichment]
