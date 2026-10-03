"""Add KOL -> follower profile enrichment -> audience. OFFLINE: tanpa DB, tanpa Apify.

Scraper, koneksi, kunci, dan logger diganti tiruan; tidak ada satu pun test di sini
yang bisa memanggil actor atau menulis ke database.
"""

from __future__ import annotations

import functools
import sys
import uuid
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestration"))

import enrich_follower_profiles as E  # noqa: E402
from kol_orchestration.assets import follower_enrichment as M  # noqa: E402

K1, K2, K3 = (str(uuid.UUID(int=i)) for i in (1, 2, 3))
S1, S2, S3 = (str(uuid.UUID(int=i)) for i in (101, 102, 103))
T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 3, tzinfo=timezone.utc)


def akun(kid=K1, sa=S1, user="baru", selesai=T1):
    return M.Akun(kid, sa, user, selesai)


# =====================================================================
# 1. Konfigurasi DB: PG_*_KOL lewat config, bukan os.environ["PG_HOST"]
# =====================================================================
def test_conn_membaca_pg_kol_lewat_config(monkeypatch):
    for k in ("PG_HOST", "PG_PORT", "PG_DB", "PG_USER", "PG_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PG_HOST_KOL", "db-kol.example")
    monkeypatch.setenv("PG_PORT_KOL", "6543")
    monkeypatch.setenv("PG_DB_KOL", "postgres")
    monkeypatch.setenv("PG_USER_KOL", "u")
    monkeypatch.setenv("PG_PASSWORD_KOL", "p")
    monkeypatch.setenv("APIFY_API_TOKEN", "dummy")
    terima = {}
    monkeypatch.setattr(E.psycopg2, "connect", lambda **kw: terima.update(kw) or "conn")
    assert E._conn() == "conn"
    assert (terima["host"], terima["port"], terima["database"], terima["user"]) == (
        "db-kol.example", "6543", "postgres", "u")
    assert terima["connect_timeout"] == 15


def test_script_tidak_lagi_membaca_pg_host_langsung():
    import inspect
    src = inspect.getsource(E)
    assert 'os.environ["PG_HOST"]' not in src and "load_dotenv" not in src
    assert "load_config().postgres.as_connect_kwargs()" in inspect.getsource(E._conn)


# =====================================================================
# 2. Pengaturan: default OFF, nilai ragu selalu jatuh ke off
# =====================================================================
def test_default_off():
    p = M.baca_pengaturan({})
    assert p.mode == M.MODE_OFF and p.cap_usd == E.CAP_TOTAL_DEFAULT


@pytest.mark.parametrize("env", [
    {"FOLLOWER_ENRICHMENT_MODE": "on"},                                   # tidak dikenal
    {"FOLLOWER_ENRICHMENT_MODE": "allowlist"},                            # tanpa id
    {"FOLLOWER_ENRICHMENT_MODE": "allowlist", "FOLLOWER_ENRICHMENT_KOL_IDS": "bukan-uuid"},
    {"FOLLOWER_ENRICHMENT_MODE": "auto"},                                 # tanpa since
    {"FOLLOWER_ENRICHMENT_MODE": "auto", "FOLLOWER_ENRICHMENT_SINCE": "kemarin"},
])
def test_pengaturan_tidak_lengkap_jatuh_ke_off(env):
    p = M.baca_pengaturan(env)
    assert p.mode == M.MODE_OFF and p.masalah


def test_allowlist_dan_auto_yang_sah():
    p = M.baca_pengaturan({"FOLLOWER_ENRICHMENT_MODE": "allowlist",
                           "FOLLOWER_ENRICHMENT_KOL_IDS": f"{K1}, {K2.upper()}"})
    assert p.mode == M.MODE_ALLOWLIST and p.kol_ids == {K1, K2}
    p = M.baca_pengaturan({"FOLLOWER_ENRICHMENT_MODE": "auto",
                           "FOLLOWER_ENRICHMENT_SINCE": "2026-10-03T00:00:00Z"})
    assert p.mode == M.MODE_AUTO and p.sejak == T1


def test_cap_hanya_bisa_diturunkan():
    assert M.baca_pengaturan({"FOLLOWER_ENRICHMENT_CAP_USD": "0.5"}).cap_usd == 0.5
    naik = M.baca_pengaturan({"FOLLOWER_ENRICHMENT_CAP_USD": "100"})
    assert naik.cap_usd == E.CAP_TOTAL_DEFAULT and naik.masalah
    assert M.baca_pengaturan({"FOLLOWER_ENRICHMENT_CAP_USD": "-1"}).cap_usd == E.CAP_TOTAL_DEFAULT
    assert E.CAP_TOTAL_DEFAULT == 4.49                       # plafon bawaan tidak dinaikkan
    assert E.parse_args([]).cap_total == E.CAP_TOTAL_DEFAULT


# =====================================================================
# 3. Pemilihan akun: idempotensi + batas percobaan + scope mode
# =====================================================================
def test_akun_yang_sudah_sukses_tidak_pernah_dipilih_lagi():
    p = M.Pengaturan(mode=M.MODE_ALLOWLIST, kol_ids=frozenset({K1}))
    boleh, lewati = M.pilih_akun([akun()], {K1: (1, 0)}, p)
    assert boleh == [] and lewati == {"sudah diperkaya": ["baru"]}


def test_gagal_berulang_berhenti_dicoba():
    p = M.Pengaturan(mode=M.MODE_ALLOWLIST, kol_ids=frozenset({K1}))
    assert M.pilih_akun([akun()], {K1: (0, M.MAKS_PERCOBAAN - 1)}, p)[0] == [akun()]
    boleh, lewati = M.pilih_akun([akun()], {K1: (0, M.MAKS_PERCOBAAN)}, p)
    assert boleh == [] and "berhenti mencoba" in next(iter(lewati))


def test_allowlist_hanya_kol_yang_disebut():
    p = M.Pengaturan(mode=M.MODE_ALLOWLIST, kol_ids=frozenset({K2}))
    boleh, lewati = M.pilih_akun([akun(), akun(K2, S2, "target")], {}, p)
    assert [a.kol_id for a in boleh] == [K2] and lewati == {"di luar allowlist": ["baru"]}


def test_auto_tidak_memproses_backlog_sebelum_since():
    p = M.Pengaturan(mode=M.MODE_AUTO, sejak=T1)
    boleh, lewati = M.pilih_akun([akun(selesai=T0), akun(K2, S2, "sesudah", T1)], {}, p)
    assert [a.username for a in boleh] == ["sesudah"]
    assert lewati == {"Add KOL sebelum FOLLOWER_ENRICHMENT_SINCE": ["baru"]}


def test_follower_yang_sudah_diperkaya_dilewati():
    baris = [("a", S1, "p1", date(2026, 10, 3)), ("b", S1, "p2", date(2026, 10, 3))]
    peta = M.susun_peta(baris, sudah={"a"}, asli={(S1, "p2", date(2026, 10, 3)): T1})
    assert peta == {"b": [(S1, "p2", date(2026, 10, 3), T1)]}


# =====================================================================
# 4. Biaya: plafon atas target akun itu, bukan seluruh database
# =====================================================================
def test_batas_tagihan_mengikuti_target_bukan_plafon_penuh():
    estimasi, batas = M.plafon_run(49, E.CAP_TOTAL_DEFAULT)
    assert round(estimasi, 4) == 0.1274 and batas == 0.1911       # 1,5 x estimasi
    assert batas < E.CAP_TOTAL_DEFAULT


def test_di_atas_plafon_ditolak():
    assert M.plafon_run(5000, E.CAP_TOTAL_DEFAULT)[1] is None
    assert M.plafon_run(49, 0.05)[1] is None


def test_scraper_asset_tanpa_retry_dan_dengan_batas_tagihan(monkeypatch):
    """Satu eksekusi asset = satu kesempatan memanggil actor per batch."""
    terima = {}

    class ScraperTiruan:
        def __init__(self, cfg, **kw):
            terima.update(kw, cfg=cfg)

    monkeypatch.setattr(M.E, "InstagramProfileScraper", ScraperTiruan)
    M._buat_scraper(SimpleNamespace(apify="cfg-apify"), 0.1911)
    assert terima == {"cfg": "cfg-apify", "actor_id": E.ACTOR_IG, "max_charge_usd": 0.1911,
                      "max_retries": 0}
    assert M.SCRAPER_MAX_RETRIES == 0


def test_tanpa_retry_berarti_satu_panggilan_actor_per_batch(monkeypatch):
    """Dengan `max_retries=0`, loop percobaan `ProfileScraper.scrape_batch` berjalan satu
    kali walau run actor gagal -- actor asli diganti tiruan, tidak ada jaringan."""
    import apify_runner

    panggilan = []

    class KlienTiruan:
        def __init__(self, _token):
            pass

        def actor(self, _actor_id):
            return self

        def call(self, **kw):
            panggilan.append(kw)
            raise RuntimeError("run gagal")

    monkeypatch.setattr(apify_runner, "ApifyClient", KlienTiruan)
    from config import ApifyConfig
    cfg = SimpleNamespace(apify=ApifyConfig(token="dummy", actor_id="x", include_about_section=False))
    scraper = M._buat_scraper(cfg, 0.1911)
    try:
        scraper.scrape_batch(["a", "b"], batch_index=1)
    except Exception:  # noqa: BLE001 - gagal total boleh melempar; yang diuji jumlah panggilan
        pass
    assert len(panggilan) == 1
    assert str(panggilan[0]["max_total_charge_usd"]) == "0.1911"


def test_cli_manual_tetap_memakai_retry_bawaan():
    import inspect
    import apify_runner
    assert inspect.signature(apify_runner.ProfileScraper.__init__).parameters["max_retries"].default == 2
    assert "max_retries" not in inspect.getsource(E.main)


# =====================================================================
# 5. Scope SQL: Instagram + Add KOL + run Add KOL itu sendiri
# =====================================================================
def _rapat(sql):
    return " ".join(sql.split())


def test_sql_akun_hanya_add_kol_instagram_yang_followernya_sukses():
    q = _rapat(M.SQL_AKUN_ADD_KOL)
    for frag in ("FROM public.add_kol_scrape_log", "l.platform = 'instagram'", "l.step = 'followers'",
                 "l.status = 'success'", "k.directory_status = 'active'"):
        assert frag in q, frag


def test_sql_follower_terikat_ke_run_add_kol():
    q = _rapat(M.SQL_FOLLOWER_ADD_KOL)
    for frag in ("pl.key = 'instagram'", "f.social_account_id = %(sa)s::uuid",
                 "l.run_id = r.scrape_run_id", "l.step = 'followers'", "l.status = 'success'",
                 "r.source_actor IS DISTINCT FROM %(actor)s",
                 "r.followers_ig_id = f.follower_platform_id"):
        assert frag in q, frag


def test_modul_tidak_punya_sql_tiktok_delete_atau_seluruh_l1():
    sqls = " ".join(v for k, v in vars(M).items() if k.startswith("SQL_"))
    for terlarang in ("tiktok", "tt_followers", "DELETE", "UPDATE ", "INSERT", "TRUNCATE"):
        assert terlarang not in sqls, terlarang
    # query follower SELALU dibatasi satu akun; tidak ada jalur "seluruh unified_follower"
    assert "%(sa)s" in M.SQL_FOLLOWER_ADD_KOL
    assert "E.SQL_TARGET" not in Path(M.__file__).read_text(encoding="utf-8")


# =====================================================================
# 6. Tanpa DELETE di flow baru; CLI lama tidak berubah
# =====================================================================
class CurCatat:
    def __init__(self):
        self.sql, self.rowcount = [], 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=None):
        self.sql.append(_rapat(sql))


class ConnCatat:
    def __init__(self):
        self.cur, self.commits = CurCatat(), 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1


def item(u):
    return {"username": u, "biography": "pecinta kopi | jakarta", "followersCount": 5,
            "followsCount": 3, "id": "x"}


def test_tulis_batch_tanpa_ganti_tidak_pernah_delete():
    conn, hasil = ConnCatat(), E._hasil_kosong()
    peta = {"a": [(S1, "p1", date(2026, 10, 3), None)]}
    E._tulis_batch(conn, "run", {"a": item("a")}, peta, T1, hasil, ganti=False)
    assert not any(s.startswith("DELETE") for s in conn.cur.sql)
    assert sum(s.startswith("INSERT INTO l0_raw.ig_followers_apify") for s in conn.cur.sql) == 1
    assert hasil["ditulis"] == 1 and hasil["dihapus"] == 0 and conn.commits == 1


def test_cli_lama_tetap_mengganti():
    conn, hasil = ConnCatat(), E._hasil_kosong()
    E._tulis_batch(conn, "run", {"a": item("a")}, {"a": [(S1, "p1", date(2026, 10, 3), None)]}, T1, hasil)
    assert any(s.startswith("DELETE FROM l0_raw.ig_followers_apify WHERE source_actor = %s")
               for s in conn.cur.sql)


# =====================================================================
# 7. Asset end-to-end dengan tiruan
# =====================================================================
class DbPalsu:
    """Satu 'database' untuk semua koneksi: hasil SELECT ditentukan dari SQL-nya."""

    def __init__(self, akun_rows, riwayat=None, follower=None, sudah=()):
        self.akun_rows, self.riwayat = akun_rows, dict(riwayat or {})
        self.follower, self.sudah = follower or {}, set(sudah)
        self.sql, self.proc = [], []

    def rows(self, sql, args):
        if sql is M.SQL_AKUN_ADD_KOL:
            return list(self.akun_rows)
        if sql is M.SQL_RIWAYAT:
            return [(k, s, g) for k, (s, g) in self.riwayat.items()]
        if sql is M.SQL_FOLLOWER_ADD_KOL:
            return list(self.follower.get(args["sa"], []))
        if sql is E.SQL_SUDAH_DIPERKAYA:
            return [(u,) for u in sorted(self.sudah)]
        return []


class CurPalsu:
    def __init__(self, db):
        self.db, self._rows, self.rowcount = db, [], 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=None):
        self.db.sql.append(_rapat(sql))
        self._rows = self.db.rows(sql, args)
        if "INSERT INTO l0_raw.ig_followers_apify" in sql:
            self.db.sudah.add(args[3])                      # username kini tercatat enriched

    def fetchall(self):
        return self._rows


class ConnPalsu:
    def __init__(self, db):
        self.db = db

    def cursor(self):
        return CurPalsu(self.db)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class PgPalsu:
    def __init__(self, db):
        self.db = db

    def get_conn(self):
        return ConnPalsu(self.db)

    def call_procedure(self, s):
        self.db.proc.append(s)

    def call_function(self, s):
        self.db.proc.append(s)


class ScraperPalsu:
    def __init__(self, gagal=False):
        self.panggilan, self.gagal = [], gagal

    def scrape_batch(self, usernames, batch_index=0):
        self.panggilan.append(list(usernames))
        if self.gagal:
            raise RuntimeError("actor timeout token=RAHASIA-TOKEN")
        return SimpleNamespace(items=[item(u) for u in usernames], cost_usd=0.01 * len(usernames))


def followers(sa, n, awalan="f"):
    return [(f"{awalan}{i}", sa, f"pid{i}", date(2026, 10, 3)) for i in range(n)]


@pytest.fixture
def rig(monkeypatch, tmp_path):
    """Asset dengan scraper, config, kunci, dan logger tiruan. Tanpa jaringan."""
    cfg = SimpleNamespace(apify=SimpleNamespace(token="RAHASIA-TOKEN"),
                          postgres=SimpleNamespace(password="RAHASIA-PW"))
    r = SimpleNamespace(scraper=ScraperPalsu(), batas=[], catatan=[], db=None)

    def buat(_cfg, batas):
        r.batas.append(batas)
        return r.scraper

    def catat(_cfg, run_id, a, status, ditulis, pesan, _mulai):
        r.catatan.append((a.kol_id, status, ditulis, pesan))
        s, g = r.db.riwayat.get(a.kol_id, (0, 0))          # log = riwayat run berikutnya
        r.db.riwayat[a.kol_id] = (s + (status == M.STATUS_SUKSES), g + (status != M.STATUS_SUKSES))
        return True

    monkeypatch.setattr(M, "load_config", lambda: cfg)
    monkeypatch.setattr(M, "_buat_scraper", buat)
    monkeypatch.setattr(M, "_catat", catat)
    monkeypatch.setattr(M, "RunLock", functools.partial(M.RunLock, lock_dir=tmp_path))
    for k in (M.ENV_MODE, M.ENV_KOL_IDS, M.ENV_SINCE, M.ENV_CAP):
        monkeypatch.delenv(k, raising=False)

    def jalankan(db):
        r.db = db
        return M._jalankan(PgPalsu(db))

    r.jalankan = jalankan
    return r


def dua_akun():
    return DbPalsu([(K1, S1, "lama", T0), (K2, S2, "baru", T1)],
                   follower={S1: followers(S1, 3, "a"), S2: followers(S2, 4, "b")})


def test_mode_off_tidak_memanggil_actor_dan_tidak_menulis(rig):
    out = rig.jalankan(dua_akun())
    assert out.value == 0 and rig.scraper.panggilan == [] and rig.catatan == []
    assert out.metadata["mode"].value == "off"
    assert not any(s.startswith(("INSERT", "DELETE", "UPDATE")) for s in rig.db.sql)
    assert rig.db.proc == []


def test_allowlist_hanya_akun_target_dan_satu_akun_per_run(rig, monkeypatch):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, f"{K1},{K2}")
    out = rig.jalankan(dua_akun())
    assert rig.scraper.panggilan == [["a0", "a1", "a2"]]            # hanya akun pertama
    assert out.value == 3 and out.metadata["akun_menunggu"].value == 1
    assert [(k, s, n) for k, s, n, _p in rig.catatan] == [(K1, M.STATUS_SUKSES, 3)]
    assert not any(s.startswith("DELETE") for s in rig.db.sql)
    assert rig.db.proc == ["CALL l0_harmonization.sp_sync_instagram_follower()",
                           "SELECT l1_silver.sp_build_unified_follower()"]
    assert rig.batas == [round(3 * M.PRICE_PER_PROFILE_USD * M.FAKTOR_PLAFON_RUN, 4)]


def test_di_luar_allowlist_tidak_tersentuh(rig, monkeypatch):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    rig.jalankan(dua_akun())
    assert rig.scraper.panggilan == [["b0", "b1", "b2", "b3"]]
    assert [k for k, *_ in rig.catatan] == [K2]


def test_run_susulan_tidak_memanggil_actor_lagi(rig, monkeypatch):
    """Sensor memicu run susulan setelah enrichment menulis L0: tidak boleh ada putaran."""
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    db = dua_akun()
    rig.jalankan(db)
    assert len(rig.scraper.panggilan) == 1
    n_insert = sum("INSERT INTO l0_raw" in s for s in db.sql)
    for _ in range(3):                                             # run susulan berulang
        out = rig.jalankan(db)
        assert out.value == 0
    assert len(rig.scraper.panggilan) == 1                          # actor tidak dipanggil lagi
    assert sum("INSERT INTO l0_raw" in s for s in db.sql) == n_insert   # L0 tidak berubah -> sensor diam


def test_follower_yang_sudah_enriched_tidak_dikirim(rig, monkeypatch):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    db = dua_akun()
    db.sudah = {"b0", "b3"}
    rig.jalankan(db)
    assert rig.scraper.panggilan == [["b1", "b2"]]


def test_semua_follower_sudah_enriched_tidak_ada_panggilan(rig, monkeypatch):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    db = dua_akun()
    db.sudah = {"b0", "b1", "b2", "b3"}
    out = rig.jalankan(db)
    assert out.value == 0 and rig.scraper.panggilan == [] and rig.catatan == []


def test_di_atas_plafon_tidak_memanggil_actor(rig, monkeypatch):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    monkeypatch.setenv(M.ENV_CAP, "0.005")                          # 4 profil = $0.0104
    out = rig.jalankan(dua_akun())
    assert rig.scraper.panggilan == [] and rig.catatan == []
    assert "ditolak" in out.metadata["status"].value


def test_apify_gagal_tidak_menjatuhkan_rantai_dan_tidak_menghapus(rig, monkeypatch):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    rig.scraper = ScraperPalsu(gagal=True)
    db = dua_akun()
    out = rig.jalankan(db)                                          # tidak melempar
    assert out.value == 0
    assert [(k, s) for k, s, *_ in rig.catatan] == [(K2, M.STATUS_GAGAL)]
    assert not any(s.startswith(("DELETE", "INSERT")) for s in db.sql)
    assert db.proc == []                                            # tidak ada yang perlu disinkronkan


def test_gagal_dicoba_ulang_terbatas(rig, monkeypatch):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    rig.scraper = ScraperPalsu(gagal=True)
    db = dua_akun()
    for _ in range(M.MAKS_PERCOBAAN + 3):
        rig.jalankan(db)
    assert len(rig.scraper.panggilan) == M.MAKS_PERCOBAAN            # lalu berhenti


def test_error_db_tidak_menjatuhkan_rantai(rig):
    class PgRusak:
        def get_conn(self):
            raise RuntimeError("could not connect: password=RAHASIA-PW")

    out = M._jalankan(PgRusak())
    assert out.value == 0 and "error" in out.metadata["status"].value


def test_kunci_dipegang_proses_lain_dilewati(rig, monkeypatch, tmp_path):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    with M.RunLock(M.LOCK_NAME):                                    # lock_dir = tmp_path (fixture)
        out = rig.jalankan(dua_akun())
    assert rig.scraper.panggilan == [] and "dilewati" in out.metadata["status"].value


def test_rahasia_tidak_pernah_masuk_pesan():
    assert M._aman("gagal token=ABC pw=XYZ", "ABC", "XYZ", None) == "gagal token=*** pw=***"
    assert len(M._aman("x" * 1000)) == 300


def test_pesan_gagal_di_log_tanpa_token(rig, monkeypatch):
    monkeypatch.setenv(M.ENV_MODE, "allowlist")
    monkeypatch.setenv(M.ENV_KOL_IDS, K2)
    galat = {}
    monkeypatch.setattr(M.E, "_jalankan_batch",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("401 token=RAHASIA-TOKEN")))
    out = rig.jalankan(dua_akun())
    galat = out.metadata["galat"].value
    assert "RAHASIA-TOKEN" not in galat and "***" in galat
    assert "RAHASIA-TOKEN" not in rig.catatan[0][3]


# =====================================================================
# 8. Dagster: registrasi, urutan, dan rantai lama tidak berubah
# =====================================================================
@pytest.fixture(scope="module")
def defs():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from kol_orchestration.repository import defs as d
    return d


def _induk(job):
    return {simpul.name: set(dep) for simpul, dep in job.dependencies.items()}


def test_urutan_di_transform_chain_job(defs):
    from kol_orchestration import one_shot
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        induk = _induk(defs.resolve_job_def(one_shot.TRANSFORM_JOB_NAME))
    assert set(induk) == set(one_shot.CHAIN_JOB_ASSETS)
    assert induk["follower_profile_enrichment"] == {"unified_follower"}
    assert induk["audience_feature"] == {"unified_follower", "follower_profile_enrichment"}
    assert induk["audience_gold"] == {"audience_feature"}


def test_classification_tidak_bergantung_pada_enrichment(defs):
    from kol_orchestration import one_shot
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        induk = _induk(defs.resolve_job_def(one_shot.TRANSFORM_JOB_NAME))
    assert induk["creator_classification"] == {"unified_profile", "unified_post", "kol_profile_card"}
    assert induk["creator_category_bridge"] == {"creator_classification"}


def test_rantai_transform_lama_tidak_memuat_enrichment():
    """`jalankan_transform_chain` (one-shot scrape, e2e, one-pass) tidak pernah bisa
    memanggil Apify lewat asset ini, dan audience_feature di sana tidak menunggunya."""
    from dagster import AssetKey, AssetSelection, Definitions, define_asset_job
    from kol_orchestration import one_shot
    from kol_orchestration.resources import PostgresResource
    assert "follower_profile_enrichment" not in one_shot.TRANSFORM_ASSETS
    assert "follower_profile_enrichment" not in {a.key.to_user_string() for a in one_shot._semua_asset()}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = Definitions(
            assets=one_shot._semua_asset(),
            jobs=[define_asset_job("rantai_lama", selection=AssetSelection.assets(
                *[AssetKey(n) for n in one_shot.TRANSFORM_ASSETS]))],
            resources={"postgres": PostgresResource(connection_string="postgresql://u:p@127.0.0.1:1/x")})
        induk = _induk(d.resolve_job_def("rantai_lama"))
    assert set(induk) == set(one_shot.TRANSFORM_ASSETS)
    assert induk["audience_feature"] == {"unified_follower"}


def test_tidak_ada_sensor_baru_dan_sensor_l0_tidak_berubah(defs):
    from kol_orchestration import one_shot, sensors
    assert {s.name for s in defs.sensors} == {
        "l0_raw_new_data_sensor", "brand_profile_changed_sensor", "brand_match_after_transform"}
    assert [t.job_name for t in sensors.l0_raw_new_data_sensor.targets] == [one_shot.TRANSFORM_JOB_NAME]
