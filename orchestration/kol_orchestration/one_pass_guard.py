"""Penjaga runtime untuk ONE-PASS ENRICHMENT (`one_pass.py`).

Semua aturan "nol biaya, nol delete, nol mutasi" di sini adalah KODE yang
berjalan, bukan dokumentasi. Tidak ada flag CLI yang bisa melonggarkannya:
`POLICY` dibekukan, dan mengubahnya berarti mengubah kode ini lewat review.

    ALLOW_PAID_SCRAPING        False   actor Apify / scraper berbayar
    ALLOW_EXTERNAL_PAID_API    False   koneksi jaringan keluar dari proses ini
    ALLOW_DELETE               False   transaksi yang menghapus baris
    ALLOW_TAXONOMY_MUTATION    False   kol_categories / kol_attribute berubah
    ALLOW_THRESHOLD_MUTATION   False   konstanta ambang classifier/metric berubah

LAPISAN PENJAGA
===============
1. Biaya (`install_cost_guard`)
   * audit hook Python (`sys.addaudithook`): setiap `socket.connect` /
     `socket.getaddrinfo` ke host non-loopback dan setiap subprocess yang tidak
     di-allowlist -> `PaidOperationBlocked("BLOCKED: paid external operation is
     disabled")`. Koneksi Postgres lewat libpq (kode C), jadi tidak terkena.
   * entry point berbayar yang dikenal (`ApifyClient`, `scheduler_engine.run_once`
     dan kawan-kawan) diganti fungsi yang langsung melempar error yang sama.

2. Delete / DDL (`GuardedConnection`, `GuardedPostgresResource`)
   * TRUNCATE/DROP/ALTER/CREATE non-TEMP/... ditolak sebelum dikirim ke DB.
   * Saat `commit()`, jumlah baris yang dihapus transaksi itu dibaca dari
     `pg_stat_xact_user_tables` -- menangkap DELETE langsung, di dalam
     procedure, maupun lewat trigger. Kalau > 0: ROLLBACK + `DeleteBlocked`.
   * mode "rehearse": semua commit menjadi ROLLBACK, jumlah insert/update/delete
     per tabel dicatat. Itulah dry-run yang menghitung affected rows tanpa
     menyimpan apa pun.

3. Threshold & taxonomy (`check_thresholds`, `check_taxonomy`)
   Dibandingkan dengan `one_pass_baseline.json` yang ikut di-commit. Perubahan
   ambang/taxonomy yang sah dilakukan lewat perubahan kode + baseline yang
   direview, bukan lewat command ini.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import psycopg2.extensions

from kol_orchestration.resources import PostgresResource

PAID_BLOCKED_MSG = "BLOCKED: paid external operation is disabled"
BASELINE_PATH = Path(__file__).with_name("one_pass_baseline.json")


@dataclass(frozen=True)
class SafetyPolicy:
    allow_paid_scraping: bool = False
    allow_external_paid_api: bool = False
    allow_delete: bool = False
    allow_taxonomy_mutation: bool = False
    allow_threshold_mutation: bool = False

    def as_env(self) -> dict[str, bool]:
        return {
            "ALLOW_PAID_SCRAPING": self.allow_paid_scraping,
            "ALLOW_EXTERNAL_PAID_API": self.allow_external_paid_api,
            "ALLOW_DELETE": self.allow_delete,
            "ALLOW_TAXONOMY_MUTATION": self.allow_taxonomy_mutation,
            "ALLOW_THRESHOLD_MUTATION": self.allow_threshold_mutation,
        }


#: Satu-satunya policy. Sengaja tidak bisa diubah dari CLI atau environment.
POLICY = SafetyPolicy()


class BlockedOperation(RuntimeError):
    """Operasi yang dilarang policy one-pass."""


class PaidOperationBlocked(BlockedOperation):
    pass


class DeleteBlocked(BlockedOperation):
    pass


class DestructiveSqlBlocked(BlockedOperation):
    pass


class ThresholdMutation(BlockedOperation):
    pass


class TaxonomyMutation(BlockedOperation):
    pass


# ---------------------------------------------------------------------------
# 1. Biaya
# ---------------------------------------------------------------------------
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0"})
_SUBPROCESS_EVENTS = frozenset({"subprocess.Popen", "os.system", "os.exec", "os.spawn",
                                "os.posix_spawn", "os.startfile"})

#: (modul, atribut) yang memanggil actor/API berbayar. Diganti saat guard aktif.
PAID_ENTRY_POINTS = (
    ("scheduler_engine", "run_once"),
    ("scheduler_engine", "run_profile_job"),
    ("scheduler_engine", "run_post_job"),
    ("scheduler_engine", "scrape_target"),
    ("kol_orchestration.one_shot", "run_once"),
)
#: Kelas klien berbayar: konstruktornya diganti, jadi semua modul yang sudah
#: mengimpor kelas yang sama ikut terblokir.
PAID_CLIENT_CLASSES = (("apify_client", "ApifyClient"), ("apify_client", "ApifyClientAsync"))

_state = {"hook": False, "active": False, "allowed_cmd": None, "patched": []}


def _blocked(detail: str):
    return PaidOperationBlocked(f"{PAID_BLOCKED_MSG} ({detail})")


def _cmd_text(cmd) -> str:
    if isinstance(cmd, (list, tuple)):
        return " ".join(str(c) for c in cmd)
    return str(cmd)


def _audit_hook(event: str, args) -> None:
    if not _state["active"]:
        return
    if event == "socket.connect":
        addr = args[1]
        host = str(addr[0]) if isinstance(addr, tuple) and addr else str(addr)
        if host not in _LOOPBACK:
            raise _blocked(f"network connect {host}")
    elif event == "socket.getaddrinfo":
        host = args[0]
        if isinstance(host, bytes):
            host = host.decode(errors="replace")
        if host and str(host) not in _LOOPBACK:
            raise _blocked(f"network lookup {host}")
    elif event in _SUBPROCESS_EVENTS:
        text = _cmd_text(args[1] if event == "subprocess.Popen" and len(args) > 1 else args)
        allowed = _state["allowed_cmd"]
        if not allowed or allowed not in text:
            raise _blocked(f"subprocess {text[:120]}")


def _make_blocker(name: str):
    def blocker(*_a, **_kw):
        raise _blocked(name)
    blocker.__name__ = f"blocked_{name.replace('.', '_')}"
    blocker.__one_pass_blocked__ = True
    return blocker


def install_cost_guard() -> None:
    """Aktifkan penjaga biaya. Aman dipanggil berkali-kali."""
    if not _state["hook"]:
        sys.addaudithook(_audit_hook)   # tidak bisa dilepas; di-nonaktifkan lewat flag
        _state["hook"] = True
    if _state["active"]:
        return
    for mod_name, attr in PAID_ENTRY_POINTS:
        mod = sys.modules.get(mod_name)
        if mod is None:
            with contextlib.suppress(Exception):
                mod = importlib.import_module(mod_name)
        if mod is not None and hasattr(mod, attr):
            _state["patched"].append((mod, attr, getattr(mod, attr)))
            setattr(mod, attr, _make_blocker(f"{mod_name}.{attr}"))
    for mod_name, cls_name in PAID_CLIENT_CLASSES:
        try:
            cls = getattr(importlib.import_module(mod_name), cls_name)
        except Exception:   # paket tidak terpasang -> tidak ada yang perlu diblokir
            continue
        _state["patched"].append((cls, "__init__", cls.__dict__.get("__init__")))
        cls.__init__ = _make_blocker(f"{mod_name}.{cls_name}")
    _state["active"] = True


def uninstall_cost_guard() -> None:
    """Untuk test: kembalikan entry point asli dan matikan hook."""
    for obj, attr, orig in reversed(_state["patched"]):
        if orig is None:
            with contextlib.suppress(AttributeError):
                delattr(obj, attr)
        else:
            setattr(obj, attr, orig)
    _state["patched"].clear()
    _state["active"] = False
    _state["allowed_cmd"] = None


def cost_guard_active() -> bool:
    return _state["active"]


@contextlib.contextmanager
def allow_subprocess(token: str):
    """Izinkan SATU jenis subprocess (dicocokkan lewat substring perintah).

    Dipakai untuk Brand Match (`npm run brand-match:recalc`, perhitungan DB milik
    Autometric) dan pytest. Jaringan tetap terblokir untuk proses Python ini."""
    prev = _state["allowed_cmd"]
    _state["allowed_cmd"] = token
    try:
        yield
    finally:
        _state["allowed_cmd"] = prev


# ---------------------------------------------------------------------------
# 2. Delete / DDL
# ---------------------------------------------------------------------------
_COMMENTS = re.compile(r"(--[^\n]*\n)|(/\*.*?\*/)", re.S)
_DDL = re.compile(r"^(TRUNCATE|DROP|ALTER|GRANT|REVOKE|VACUUM|REINDEX|CLUSTER|COPY|COMMENT|"
                  r"REFRESH|IMPORT|SECURITY|LOCK)\b", re.I)
_CREATE_NON_TEMP = re.compile(r"^CREATE\s+(?!(?:LOCAL\s+|GLOBAL\s+)?TEMP(?:ORARY)?\s)", re.I)

SQL_XACT_STATS = """
    SELECT schemaname || '.' || relname, n_tup_ins, n_tup_upd, n_tup_del
      FROM pg_stat_xact_user_tables
     WHERE n_tup_ins + n_tup_upd + n_tup_del > 0"""


def _sql_text(query, conn) -> str:
    if hasattr(query, "as_string"):
        query = query.as_string(conn)
    if isinstance(query, bytes):
        query = query.decode("utf-8", errors="replace")
    return str(query)


def check_sql(sql: str) -> None:
    """Tolak DDL / TRUNCATE sebelum sampai ke database."""
    head = _COMMENTS.sub(" ", sql).strip()
    if _DDL.match(head) or _CREATE_NON_TEMP.match(head):
        raise DestructiveSqlBlocked(f"BLOCKED: destructive SQL disabled: {head[:80]!r}")


class WriteRecorder:
    """Jumlah insert/update/delete per tabel, dipisah committed vs rehearsed."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.tables = {"committed": defaultdict(lambda: [0, 0, 0]),
                       "rehearsed": defaultdict(lambda: [0, 0, 0])}
        self.blocked: list[str] = []

    def add(self, kind: str, rows) -> None:
        for table, ins, upd, dele in rows:
            t = self.tables[kind][table]
            t[0] += ins
            t[1] += upd
            t[2] += dele

    def totals(self, kind: str) -> dict[str, int]:
        ins = sum(v[0] for v in self.tables[kind].values())
        upd = sum(v[1] for v in self.tables[kind].values())
        dele = sum(v[2] for v in self.tables[kind].values())
        return {"inserted": ins, "updated": upd, "deleted": dele}

    def per_table(self, kind: str) -> dict[str, dict[str, int]]:
        return {t: {"inserted": v[0], "updated": v[1], "deleted": v[2]}
                for t, v in sorted(self.tables[kind].items())}


RECORDER = WriteRecorder()


class GuardedCursor(psycopg2.extensions.cursor):
    def execute(self, query, vars=None):
        check_sql(_sql_text(query, self.connection))
        return super().execute(query, vars)

    def executemany(self, query, vars_list):
        check_sql(_sql_text(query, self.connection))
        return super().executemany(query, vars_list)


class GuardedConnection(psycopg2.extensions.connection):
    """Koneksi psycopg2 dengan penjaga delete di commit.

    mode = "write"     commit sungguhan, kecuali transaksinya menghapus baris
    mode = "rehearse"  setiap commit/rollback -> ROLLBACK, statistik dicatat
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cursor_factory = GuardedCursor
        self.mode = "write"

    def _xact_stats(self) -> list[tuple]:
        cur = psycopg2.extensions.cursor(self)
        try:
            cur.execute(SQL_XACT_STATS)
            return [(t, int(i), int(u), int(d)) for t, i, u, d in cur.fetchall()]
        finally:
            cur.close()

    def commit(self):
        if self.status == psycopg2.extensions.STATUS_READY:   # tidak ada transaksi terbuka
            return super().commit()
        if self.info.transaction_status == psycopg2.extensions.TRANSACTION_STATUS_INERROR:
            return super().rollback()   # COMMIT atas transaksi gagal = ROLLBACK di server
        rows = self._xact_stats()
        if self.mode == "rehearse":
            RECORDER.add("rehearsed", rows)
            return super().rollback()
        deleted = {t: d for t, _i, _u, d in rows if d}
        if deleted and not POLICY.allow_delete:
            super().rollback()
            msg = ("BLOCKED: delete disabled -- transaksi akan menghapus "
                   + ", ".join(f"{t}={n}" for t, n in sorted(deleted.items()))
                   + " baris; di-ROLLBACK")
            RECORDER.blocked.append(msg)
            raise DeleteBlocked(msg)
        super().commit()
        RECORDER.add("committed", rows)

    def rollback(self):
        if self.mode == "rehearse" and self.status != psycopg2.extensions.STATUS_READY:
            with contextlib.suppress(psycopg2.Error):
                RECORDER.add("rehearsed", self._xact_stats())
        return super().rollback()

    @property
    def autocommit(self):
        return psycopg2.extensions.connection.autocommit.__get__(self)

    @autocommit.setter
    def autocommit(self, value):
        if value:
            raise DestructiveSqlBlocked("BLOCKED: autocommit disabled under one-pass guard")
        psycopg2.extensions.connection.autocommit.__set__(self, value)

    def set_session(self, *args, **kwargs):
        if kwargs.get("autocommit") or (len(args) >= 4 and args[3]):
            raise DestructiveSqlBlocked("BLOCKED: autocommit disabled under one-pass guard")
        return super().set_session(*args, **kwargs)


def guarded_connect(connect_kwargs: dict | None = None, dsn: str | None = None,
                    mode: str = "write", connect_timeout: int = 15):
    if mode not in ("write", "rehearse"):
        raise ValueError(f"mode tidak dikenal: {mode}")
    conn = psycopg2.connect(dsn, connection_factory=GuardedConnection,
                            connect_timeout=connect_timeout, **(connect_kwargs or {}))
    conn.mode = mode
    return conn


class GuardedPostgresResource(PostgresResource):
    """`PostgresResource` yang setiap koneksinya `GuardedConnection`.

    Semua asset membuka koneksi lewat `get_conn()` (juga `call_procedure`,
    `call_function`, `scalar`), jadi satu override ini menutup seluruh rantai."""

    mode: str = "write"

    def get_conn(self):
        return guarded_connect(dsn=self.connection_string, mode=self.mode,
                               connect_timeout=self.connect_timeout)


# ---------------------------------------------------------------------------
# 3. Threshold & taxonomy
# ---------------------------------------------------------------------------
#: Modul yang memuat ambang business rule classifier/metric/audiens.
THRESHOLD_MODULES = (
    "audience_classification",
    "creator_classification",
    "metrics_thresholds",
    "creator_age_inference",
    "kol_orchestration.assets.feature_engagement",
)

SQL_TAXONOMY_FP = {
    "kol_categories": """SELECT count(*), md5(coalesce(string_agg(id::text || name
                             || coalesce(taxonomy_key, '') || level, '|' ORDER BY id::text), ''))
                           FROM public.kol_categories""",
    "kol_attribute": """SELECT count(*), md5(coalesce(string_agg(id::text || kind || attribute_key
                            || is_active::text, '|' ORDER BY id::text), ''))
                          FROM public.kol_attribute""",
}


def threshold_values(modules=THRESHOLD_MODULES) -> dict[str, dict[str, float]]:
    """Konstanta numerik UPPERCASE tiap modul ambang, apa adanya saat ini."""
    out = {}
    for name in modules:
        mod = importlib.import_module(name)
        out[name] = {k: v for k, v in sorted(vars(mod).items())
                     if k.isupper() and not k.startswith("_")
                     and isinstance(v, (int, float)) and not isinstance(v, bool)}
    return out


def diff_thresholds(expected: dict, actual: dict) -> list[str]:
    bad = []
    for mod in sorted(set(expected) | set(actual)):
        e, a = expected.get(mod, {}), actual.get(mod, {})
        for k in sorted(set(e) | set(a)):
            if e.get(k) != a.get(k):
                bad.append(f"{mod}.{k}: baseline={e.get(k)!r} sekarang={a.get(k)!r}")
    return bad


def check_thresholds(baseline: dict) -> dict:
    actual = threshold_values(tuple(baseline["thresholds"]))
    bad = diff_thresholds(baseline["thresholds"], actual)
    if bad and not POLICY.allow_threshold_mutation:
        raise ThresholdMutation("BLOCKED: threshold mutation detected: " + "; ".join(bad[:10]))
    return actual


def taxonomy_fingerprint(cur) -> dict[str, list]:
    out = {}
    for name, sql in SQL_TAXONOMY_FP.items():
        cur.execute(sql)
        n, fp = cur.fetchone()
        out[name] = [int(n), fp]
    return out


def diff_taxonomy(expected: dict, actual: dict) -> list[str]:
    return [f"{k}: baseline={expected.get(k)} sekarang={actual.get(k)}"
            for k in sorted(set(expected) | set(actual)) if expected.get(k) != actual.get(k)]


def check_taxonomy(cur, baseline: dict) -> dict:
    actual = taxonomy_fingerprint(cur)
    bad = diff_taxonomy(baseline["taxonomy"], actual)
    if bad and not POLICY.allow_taxonomy_mutation:
        raise TaxonomyMutation("BLOCKED: taxonomy mutation detected: " + "; ".join(bad))
    return actual


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
