"""Bridge inferred category -> category_id/category_ids -- offline, tanpa DB."""

from __future__ import annotations

import pytest

import creator_category_bridge as B

K1 = "11111111-1111-1111-1111-111111111111"
CAT, SUB = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def cand(kid=K1, **over):
    d = dict(kol_id=kid, username="baru", category_id=None, category_ids=(), inferred_category_id=CAT,
             inferred_subcategory_id=SUB, source=B.CLASSIFIER_SOURCE, confidence="medium",
             category_name="Food", subcategory_name="Culinary Review")
    d.update(over)
    return B.Candidate(**d)


# --- plan ---------------------------------------------------------------------------
@pytest.mark.parametrize("conf", ["high", "medium"])
def test_kol_baru_high_medium_dibridge(conf):
    p = B.plan([cand(confidence=conf)])
    assert p.target_ids == [K1] and p.skipped == {}


def test_low_confidence_tidak_dipaksakan():
    p = B.plan([cand(confidence="low")])
    assert p.updates == [] and any("low" in k for k in p.skipped)


@pytest.mark.parametrize("over", [{"category_id": CAT}, {"category_ids": (CAT,)},
                                  {"category_id": CAT, "category_ids": (CAT, SUB)}])
def test_category_existing_tidak_pernah_ditimpa(over):
    p = B.plan([cand(**over)])
    assert p.updates == [] and p.skipped == {"category sudah terisi": [K1]}


def test_tanpa_hasil_classifier_tidak_ada_write():
    p = B.plan([cand(inferred_category_id=None, inferred_subcategory_id=None, source=None, confidence=None)])
    assert p.updates == [] and "belum ada hasil classifier" in p.skipped


def test_inferred_curated_bukan_urusan_bridge():
    p = B.plan([cand(source="curated", confidence="high")])
    assert p.updates == []


# --- SQL: aturan dijaga di WHERE, bukan hanya di plan ---------------------------------
def test_sql_update_hanya_mengisi_yang_kosong():
    q = " ".join(B.SQL_BRIDGE_UPDATE.split())
    assert "SET category_id = inferred_category_id, category_ids = ARRAY[inferred_category_id]" in q
    for frag in ("category_id IS NULL", "coalesce(cardinality(category_ids), 0) = 0",
                 "directory_status = 'active'", "inferred_category_source = 'creator_classification'",
                 "inferred_category_confidence IN ('high', 'medium')", "inferred_category_id IS NOT NULL"):
        assert frag in q, frag


def test_sql_tidak_menyentuh_yang_dilarang():
    sqls = " ".join(v for k, v in vars(B).items() if k.startswith("SQL_"))
    for forbidden in ("DELETE", "INSERT", "creator_city", "ALTER", "TRUNCATE", "DROP"):
        assert forbidden not in sqls, forbidden
    assert sqls.count("UPDATE") == 1                       # satu-satunya write
    # subcategory tidak pernah masuk category_ids (pembacanya menganggap elemen = Category L1)
    assert "inferred_subcategory_id" not in B.SQL_BRIDGE_UPDATE
    assert "= NULL" not in B.SQL_BRIDGE_UPDATE


# --- guard --------------------------------------------------------------------------
def snap(**over):
    s = {"rest": [1984, "a"], "target_other": [1, "b"], "active": 105, "total": 1985, "bad_category": 0}
    s.update(over)
    return s


def test_guard_lolos():
    assert B.guards(snap(), snap(), 1, 1, 0) == []
    assert B.guards(snap(), snap(), 1, 1, 0, expect_active=105) == []


@pytest.mark.parametrize("after,planned,done,left,exp,frag", [
    (snap(active=104), 1, 1, 0, None, "active KOL berubah"),
    (snap(), 1, 1, 0, 1980, "expected 1980"),
    (snap(total=1984), 1, 1, 0, None, "jumlah baris"),
    (snap(rest=[1984, "x"]), 1, 1, 0, None, "di luar target"),
    (snap(target_other=[1, "x"]), 1, 1, 0, None, "kolom selain"),
    (snap(), 2, 1, 0, None, "written 1 != candidate 2"),
    (snap(), 1, 1, 1, None, "konvergen"),
    (snap(bad_category=1), 1, 1, 0, None, "bad_category"),
])
def test_guard_gagal(after, planned, done, left, exp, frag):
    assert any(frag in x for x in B.guards(snap(), after, planned, done, left, exp))


# --- transaksi ----------------------------------------------------------------------
class FakeCursor:
    def __init__(self, conn):
        self.conn, self.rowcount = conn, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        if self.conn.fail:
            raise RuntimeError("boom")
        self.conn.statements.append(sql)
        self.rowcount = self.conn.rowcount

    def fetchall(self):
        return []                       # setelah write: tidak ada kandidat tersisa


class FakeConn:
    def __init__(self, fail=False, rowcount=1):
        self.statements, self.fail, self.rowcount = [], fail, rowcount
        self.committed = self.rolled_back = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


def _snap(_cur, _ids):
    return snap()


def test_commit_kalau_guard_lolos():
    conn = FakeConn()
    done, problems, committed = B.apply(conn, B.plan([cand()]), commit=True, snap=_snap)
    assert (done, problems, committed) == (1, [], True) and (conn.committed, conn.rolled_back) == (1, 0)
    assert conn.statements.count(B.SQL_BRIDGE_UPDATE) == 1


def test_rehearse_selalu_rollback():
    conn = FakeConn()
    _d, problems, committed = B.apply(conn, B.plan([cand()]), commit=False, snap=_snap)
    assert problems == [] and not committed and (conn.committed, conn.rolled_back) == (0, 1)


def test_baris_tidak_kena_where_rollback():
    """Baris berubah di antara plan dan write (mis. category diisi manual) -> 0 rowcount -> ROLLBACK."""
    conn = FakeConn(rowcount=0)
    _d, problems, committed = B.apply(conn, B.plan([cand()]), commit=True, snap=_snap)
    assert problems and not committed and conn.committed == 0


def test_error_saat_write_rollback_dan_dilempar():
    conn = FakeConn(fail=True)
    with pytest.raises(RuntimeError):
        B.apply(conn, B.plan([cand()]), commit=True, snap=_snap)
    assert (conn.committed, conn.rolled_back) == (0, 1)
