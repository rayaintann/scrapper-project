"""Lifecycle master KOL: active = serving, inactive = non-serving (histori tetap ada).

Bagian 1 (tanpa DB): SQL dan jalur kode.
Bagian 2 (needs_db): skenario nyata lewat `raw_store.insert_profiles` /
`tt_raw_store.insert_profiles` di SATU transaksi yang SELALU di-ROLLBACK --
tidak ada yang tersimpan di production.
"""

from __future__ import annotations

import csv
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import raw_store  # noqa: E402
import scheduler_engine  # noqa: E402
import scrape_followers  # noqa: E402
import tt_raw_store  # noqa: E402

COHORT = ROOT / "orchestration" / "kol_orchestration" / "data" / "one_pass_cohort.csv"


class _Cur:
    def __init__(self, rows=()):
        self.sql, self.params, self.rows = [], [], list(rows)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.sql.append(sql); self.params.append(params)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return None


class _Conn:
    def __init__(self, rows=()):
        self.cur = _Cur(rows)

    def cursor(self):
        return self.cur


# --------------------------------------------------------------------- tanpa DB
def test_pemilihan_massal_hanya_kol_active():
    c = _Conn()
    db.fetch_usernames(c, "instagram", limit=5)
    assert "k.directory_status = 'active'" in c.cur.sql[-1]
    c2 = _Conn()
    db.fetch_usernames(c2, "instagram", limit=5, include_inactive=True)
    assert "directory_status" not in c2.cur.sql[-1]


def test_update_profiles_mengaktifkan_hanya_bila_scrape_sukses():
    sql = db.update_profiles.__code__.co_consts
    teks = " ".join(s for s in sql if isinstance(s, str))
    assert "directory_status     = CASE WHEN v.scrape_status = 'success'" in teks
    assert "ELSE k.directory_status END" in teks


def test_sql_reaktivasi_tanpa_insert_delete_dan_idempoten():
    s = db.SQL_REACTIVATE.upper()
    assert "UPDATE PUBLIC.KOL_DIRECTORY" in s and "DELETE" not in s and "INSERT" not in s
    assert "IS DISTINCT FROM 'ACTIVE'" in s and "KOL_SOCIAL_ACCOUNT" in s
    assert db.reactivate_kols(_Conn(), []) == 0


def test_raw_ig_mereaktivasi_hanya_profil_sukses_yang_tertaut(monkeypatch):
    got = {}
    monkeypatch.setattr(raw_store, "reactivate_kols", lambda conn, ids: got.setdefault("ids", list(ids)) and len(ids))
    monkeypatch.setattr(raw_store.psycopg2.extras, "execute_values", lambda *a, **k: [(1,), (2,)])
    items = [{"username": "ok_user", "followersCount": 10},
             {"username": "err_user", "error": "not_found", "errorDescription": "x"},
             {"username": "unlinked_user", "followersCount": 5}]
    st = raw_store.insert_profiles(_Conn(), items, "a", datetime.now(timezone.utc), commit=False,
                                   include_failed=True, account_ids={"ok_user": "sa-1", "err_user": "sa-2"})
    assert got["ids"] == ["sa-1"] and st.reactivated == 1


def test_raw_tiktok_mereaktivasi_profil_yang_tertaut(monkeypatch):
    got = {}
    monkeypatch.setattr(tt_raw_store, "reactivate_kols", lambda conn, ids: got.setdefault("ids", list(ids)) and len(ids))
    monkeypatch.setattr(tt_raw_store.psycopg2.extras, "execute_values", lambda *a, **k: [(1,)])
    items = [{"authorMeta": {"name": "tt_user", "fans": 9}}, {"authorMeta": {"name": "tt_other", "fans": 1}}]
    st = tt_raw_store.insert_profiles(_Conn(), items, "a", datetime.now(timezone.utc), commit=False,
                                      account_ids={"tt_user": "sa-9"})
    assert got["ids"] == ["sa-9"] and st.reactivated == 1


def test_scheduler_otomatis_hanya_active_tapi_username_eksplisit_boleh_inactive():
    c = _Conn()
    scheduler_engine.select_profile_target(c, platform="instagram")
    assert "k.directory_status = 'active'" in c.cur.sql[-1]
    c2 = _Conn()
    scheduler_engine.select_profile_target(c2, platform="instagram", username="someone")
    assert "directory_status" not in c2.cur.sql[-1]


def test_follower_otomatis_hanya_akun_kol_active():
    rows = [("sa-a", "instagram", "a", None), ("sa-b", "instagram", "b", None)]

    class Cur(_Cur):
        def fetchall(self):
            return [("sa-a",)] if self.sql[-1] is scrape_followers.SQL_AKUN_AKTIF else rows

    class Conn(_Conn):
        def __init__(self):
            self.cur = Cur()

    args = SimpleNamespace(tanggal_profil=None, order="username", platform="semua", usernames=None,
                           usernames_file=None, limit_akun=None)
    assert [r[0] for r in scrape_followers.pilih_akun(Conn(), args)] == ["sa-a"]


# ------------------------------------------------------------------- dengan DB
@pytest.fixture(scope="module")
def wconn():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        from config import load_config
        cfg = load_config()
        cn = psycopg2.connect(connect_timeout=10, **cfg.postgres.as_connect_kwargs())
    except Exception as exc:                                   # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    cn.autocommit = False
    yield cn
    cn.rollback()
    cn.close()


def _cohort():
    with open(COHORT, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _one(cn, sql, a=None):
    with cn.cursor() as cur:
        cur.execute(sql, a)
        return cur.fetchone()[0]


def _pick(cn, active: bool, platform: str):
    kid = [r["kol_id"] for r in _cohort()]
    with cn.cursor() as cur:
        cur.execute(f"""SELECT kd.id::text, ksa.social_account_id::text, kd.username
                          FROM public.kol_directory kd
                          JOIN public.kol_social_account ksa ON ksa.kol_id = kd.id
                          JOIN public.platforms p ON p.id = kd.platform_id
                         WHERE p.key = %s AND {'' if active else 'NOT'} (kd.id = ANY(%s::uuid[]))
                         ORDER BY kd.username LIMIT 1""", (platform, kid))
        return cur.fetchone()


@pytest.mark.needs_db
def test_db_cohort_100_active_noncohort_inactive(wconn):
    kid = [r["kol_id"] for r in _cohort()]
    assert _one(wconn, "SELECT count(*) FROM public.kol_directory WHERE id = ANY(%s::uuid[]) "
                       "AND directory_status = 'active'", (kid,)) == 100
    assert _one(wconn, "SELECT count(*) FROM public.kol_directory WHERE directory_status = 'active'") == 100
    wconn.rollback()


@pytest.mark.needs_db
def test_db_inactive_tidak_muncul_di_discovery_tapi_historinya_ada(wconn):
    kid, sa, user = _pick(wconn, active=False, platform="instagram")
    assert _one(wconn, "SELECT directory_status FROM public.kol_directory WHERE id = %s", (kid,)) == "inactive"
    # Discovery (search) mencari persis username-nya dan tetap tidak mengembalikannya
    assert all(str(r.id) != kid for r in db.search_kol_directory(wconn, q=user, limit=50))
    # seluruh hasil Discovery tanpa filter = hanya KOL active (maks 100)
    semua = db.search_kol_directory(wconn, limit=500)
    assert 0 < len(semua) <= 100
    assert _one(wconn, "SELECT count(*) FROM public.kol_directory WHERE id = ANY(%s::uuid[]) "
                       "AND directory_status <> 'active'", ([str(r.id) for r in semua],)) == 0
    # histori tetap ada: baris L1 milik KOL inactive tidak dihapus
    assert _one(wconn, "SELECT count(*) FROM l1_silver.unified_profile up JOIN public.kol_social_account k "
                       "ON k.social_account_id = up.social_account_id JOIN public.kol_directory d ON d.id = k.kol_id "
                       "WHERE d.directory_status = 'inactive'") > 0
    wconn.rollback()


@pytest.mark.needs_db
@pytest.mark.parametrize("platform", ["instagram", "tiktok"])
def test_db_scrape_ulang_inactive_jadi_active_tanpa_duplikat(wconn, platform):
    kid, sa, user = _pick(wconn, active=False, platform=platform)
    n_kd, n_sa, n_ksa = (_one(wconn, f"SELECT count(*) FROM public.{t}")
                         for t in ("kol_directory", "social_account", "kol_social_account"))
    now = datetime.now(timezone.utc)
    if platform == "instagram":
        st = raw_store.insert_profiles(wconn, [{"username": user, "followersCount": 123}], "test/lifecycle", now,
                                       scrape_run_id=str(uuid.uuid4()), commit=False, account_ids={user: sa})
    else:
        st = tt_raw_store.insert_profiles(wconn, [{"authorMeta": {"name": user, "fans": 123}}], "test/lifecycle", now,
                                          scrape_run_id=str(uuid.uuid4()), commit=False, account_ids={user: sa})
    try:
        assert st.inserted == 1 and st.reactivated == 1
        assert _one(wconn, "SELECT directory_status FROM public.kol_directory WHERE id = %s", (kid,)) == "active"
        assert (_one(wconn, "SELECT count(*) FROM public.kol_directory"),
                _one(wconn, "SELECT count(*) FROM public.social_account"),
                _one(wconn, "SELECT count(*) FROM public.kol_social_account")) == (n_kd, n_sa, n_ksa)
    finally:
        wconn.rollback()                                        # tidak ada yang tersimpan
    assert _one(wconn, "SELECT directory_status FROM public.kol_directory WHERE id = %s", (kid,)) == "inactive"
    wconn.rollback()


@pytest.mark.needs_db
def test_db_scrape_ulang_active_tetap_active(wconn):
    kid, sa, user = _pick(wconn, active=True, platform="instagram")
    st = raw_store.insert_profiles(wconn, [{"username": user, "followersCount": 1}], "test/lifecycle",
                                   datetime.now(timezone.utc), commit=False, account_ids={user: sa})
    try:
        assert st.reactivated == 0
        assert _one(wconn, "SELECT directory_status FROM public.kol_directory WHERE id = %s", (kid,)) == "active"
    finally:
        wconn.rollback()


@pytest.mark.needs_db
def test_db_profil_gagal_tidak_mereaktivasi(wconn):
    kid, sa, user = _pick(wconn, active=False, platform="instagram")
    st = raw_store.insert_profiles(wconn, [{"username": user, "error": "not_found", "errorDescription": "gone"}],
                                   "test/lifecycle", datetime.now(timezone.utc), commit=False,
                                   include_failed=True, account_ids={user: sa})
    try:
        assert st.reactivated == 0
        assert _one(wconn, "SELECT directory_status FROM public.kol_directory WHERE id = %s", (kid,)) == "inactive"
    finally:
        wconn.rollback()
