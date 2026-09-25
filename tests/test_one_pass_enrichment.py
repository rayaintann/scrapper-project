"""Test master orchestrator ONE-PASS ENRICHMENT (`kol_orchestration/one_pass.py`).

Offline kecuali yang ditandai `needs_db`. Test DB hanya MEMBACA, atau menulis ke
TEMP TABLE milik sesinya sendiri (lenyap saat koneksi ditutup) -- tidak ada
baris production yang disentuh.
"""

from __future__ import annotations

import socket
import subprocess
import sys
from collections import Counter

import pytest

import audience_classification as A
import creator_classification_writer as W
from kol_orchestration import one_pass as OP
from kol_orchestration import one_pass_guard as G

BASELINE = G.load_baseline()


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def cost_guard():
    G.install_cost_guard()
    yield
    G.uninstall_cost_guard()


def _connect_kwargs():
    try:
        from config import load_config
        return load_config().postgres.as_connect_kwargs()
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"konfigurasi DB tidak tersedia: {exc}")


@pytest.fixture(scope="module")
def conn():
    import psycopg2
    try:
        cn = psycopg2.connect(connect_timeout=10, **_connect_kwargs())
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    cn.set_session(readonly=True, autocommit=True)
    yield cn
    cn.close()


@pytest.fixture
def guarded():
    """Koneksi ber-guard; hanya dipakai untuk TEMP TABLE."""
    G.RECORDER.reset()
    try:
        cn = G.guarded_connect(_connect_kwargs(), mode="write")
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    yield cn
    cn.close()


@pytest.fixture(scope="module")
def members():
    return OP.load_cohort()


# ---------------------------------------------------------------------------
# 1. paid scraper blocked
# ---------------------------------------------------------------------------
def test_paid_scraper_blocked(cost_guard):
    import apify_client
    import scheduler_engine
    from kol_orchestration import one_shot

    for fn in (scheduler_engine.run_once, scheduler_engine.run_profile_job,
               scheduler_engine.run_post_job, one_shot.run_once):
        with pytest.raises(G.PaidOperationBlocked, match="BLOCKED: paid external operation is disabled"):
            fn()
    with pytest.raises(G.PaidOperationBlocked, match="BLOCKED: paid external operation is disabled"):
        apify_client.ApifyClient("token-palsu")


def test_paid_entry_points_restored_after_uninstall():
    import scheduler_engine
    asli = scheduler_engine.run_once
    G.install_cost_guard()
    assert getattr(scheduler_engine.run_once, "__one_pass_blocked__", False)
    G.uninstall_cost_guard()
    assert scheduler_engine.run_once is asli


# ---------------------------------------------------------------------------
# 2. external paid API blocked
# ---------------------------------------------------------------------------
def test_external_paid_api_blocked(cost_guard):
    with pytest.raises(G.PaidOperationBlocked, match="BLOCKED: paid external operation is disabled"):
        socket.create_connection(("api.apify.com", 443), timeout=1)
    s = socket.socket()
    try:
        with pytest.raises(G.PaidOperationBlocked):
            s.connect(("1.1.1.1", 443))
    finally:
        s.close()
    with pytest.raises(G.PaidOperationBlocked):
        subprocess.run(["curl", "https://api.apify.com/v2/acts"], capture_output=True)


def test_subprocess_only_when_allowlisted(cost_guard):
    with G.allow_subprocess("one-pass-penanda"):
        r = subprocess.run([sys.executable, "-c", "print('one-pass-penanda')"],
                           capture_output=True, text=True)
    assert r.returncode == 0
    with pytest.raises(G.PaidOperationBlocked):
        subprocess.run([sys.executable, "-c", "print('lain')"], capture_output=True)


def test_loopback_still_allowed(cost_guard):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        c = socket.create_connection(srv.getsockname(), timeout=2)
        c.close()
    finally:
        srv.close()


def test_dagster_materialize_works_under_cost_guard(cost_guard):
    """Guard tidak boleh mematahkan Dagster in-process yang dipakai rantai transformasi."""
    from dagster import asset, materialize

    @asset
    def uji_one_pass():
        return 1

    assert materialize([uji_one_pass]).success


def test_policy_all_false_and_frozen():
    assert not any(G.POLICY.as_env().values())
    with pytest.raises(Exception):
        G.POLICY.allow_delete = True        # dataclass frozen


# ---------------------------------------------------------------------------
# 3. delete blocked
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sql", ["TRUNCATE l2_gold.kol_profile_card",
                                 "/* komentar */ DROP TABLE public.x",
                                 "-- x\nALTER TABLE public.kol_directory ADD c int",
                                 "CREATE TABLE public.x (a int)"])
def test_ddl_rejected_before_reaching_db(sql):
    with pytest.raises(G.DestructiveSqlBlocked):
        G.check_sql(sql)


@pytest.mark.parametrize("sql", ["SELECT 1", "INSERT INTO t VALUES (1)", "UPDATE t SET a=1",
                                 "CREATE TEMP TABLE t (a int)", "SET LOCAL lock_timeout = '1s'",
                                 "DELETE FROM t WHERE a = 1"])
def test_normal_sql_passes_static_check(sql):
    G.check_sql(sql)     # DELETE diperiksa saat commit, bukan di sini


@pytest.mark.needs_db
def test_delete_blocked_at_commit_and_rolled_back(guarded):
    cur = guarded.cursor()
    cur.execute("CREATE TEMP TABLE one_pass_uji (x int)")
    cur.execute("INSERT INTO one_pass_uji VALUES (1), (2)")
    guarded.commit()
    cur.execute("DELETE FROM one_pass_uji WHERE x = 1")
    with pytest.raises(G.DeleteBlocked, match="delete disabled"):
        guarded.commit()
    cur.execute("SELECT count(*) FROM one_pass_uji")
    assert cur.fetchone()[0] == 2            # delete tidak pernah tersimpan
    assert G.RECORDER.blocked and G.RECORDER.totals("committed")["deleted"] == 0


@pytest.mark.needs_db
def test_truncate_and_autocommit_blocked(guarded):
    cur = guarded.cursor()
    cur.execute("CREATE TEMP TABLE one_pass_uji2 (x int)")
    with pytest.raises(G.DestructiveSqlBlocked):
        cur.execute("TRUNCATE one_pass_uji2")
    with pytest.raises(G.DestructiveSqlBlocked):
        guarded.autocommit = True
    guarded.rollback()


@pytest.mark.needs_db
def test_rehearse_mode_counts_rows_and_persists_nothing():
    G.RECORDER.reset()
    cn = G.guarded_connect(_connect_kwargs(), mode="rehearse")
    try:
        cur = cn.cursor()
        cur.execute("CREATE TEMP TABLE one_pass_uji3 (x int)")
        cur.execute("INSERT INTO one_pass_uji3 SELECT generate_series(1, 3)")
        cn.commit()                          # rehearse: commit -> ROLLBACK
        assert G.RECORDER.totals("rehearsed")["inserted"] == 3
        assert G.RECORDER.totals("committed")["inserted"] == 0
        cur.execute("SELECT to_regclass('pg_temp.one_pass_uji3')")
        assert cur.fetchone()[0] is None     # tabelnya ikut di-rollback
    finally:
        cn.close()


@pytest.mark.needs_db
def test_guarded_resource_hands_out_guarded_connections():
    from kol_orchestration.repository import _build_connection_string
    res = G.GuardedPostgresResource(connection_string=_build_connection_string(), mode="rehearse")
    cn = res.get_conn()
    try:
        assert isinstance(cn, G.GuardedConnection) and cn.mode == "rehearse"
    finally:
        cn.close()


# ---------------------------------------------------------------------------
# 4. threshold mutation blocked
# ---------------------------------------------------------------------------
def test_baseline_pins_existing_thresholds():
    t = BASELINE["thresholds"]["audience_classification"]
    assert t == {"MIN_KNOWN": 5, "GENDER_SHARE_MIN": 60.0}
    assert A.MIN_KNOWN == 5 and A.GENDER_SHARE_MIN == 60.0
    G.check_thresholds(BASELINE)             # kode sekarang == baseline


def test_threshold_mutation_blocked(monkeypatch):
    monkeypatch.setattr(A, "MIN_KNOWN", 3)
    with pytest.raises(G.ThresholdMutation, match="MIN_KNOWN"):
        G.check_thresholds(BASELINE)


def test_creator_threshold_mutation_blocked(monkeypatch):
    import creator_classification as C
    monkeypatch.setattr(C, "MIN_SCORE", C.MIN_SCORE - 1)
    with pytest.raises(G.ThresholdMutation, match="MIN_SCORE"):
        G.check_thresholds(BASELINE)


# ---------------------------------------------------------------------------
# 5. taxonomy mutation blocked
# ---------------------------------------------------------------------------
class _FakeCursor:
    def __init__(self, rows):
        self.rows = iter(rows)

    def execute(self, *_a, **_kw):
        pass

    def fetchone(self):
        return next(self.rows)


def test_taxonomy_mutation_blocked():
    cat_n, cat_fp = BASELINE["taxonomy"]["kol_categories"]
    att_n, att_fp = BASELINE["taxonomy"]["kol_attribute"]
    G.check_taxonomy(_FakeCursor([(cat_n, cat_fp), (att_n, att_fp)]), BASELINE)
    with pytest.raises(G.TaxonomyMutation, match="kol_categories"):
        G.check_taxonomy(_FakeCursor([(cat_n + 1, "baru"), (att_n, att_fp)]), BASELINE)


@pytest.mark.needs_db
def test_live_taxonomy_matches_baseline(conn):
    with conn.cursor() as cur:
        G.check_taxonomy(cur, BASELINE)


# ---------------------------------------------------------------------------
# 6. evidence reused
# ---------------------------------------------------------------------------
@pytest.mark.needs_db
def test_evidence_loaded_once_and_reused(conn, members, monkeypatch):
    import creator_classification_dryrun as D
    calls = Counter()
    base = OP._default_loaders()

    def counting(name):
        def f(*a, **kw):
            calls[name] += 1
            return base[name](*a, **kw)
        return f

    ev = OP.EvidenceSet.build(conn, members, {k: counting(k) for k in base})
    # setelah evidence dibangun, loader asli tidak boleh dipanggil lagi oleh langkah mana pun
    monkeypatch.setattr(D, "load", lambda *_a: pytest.fail("D.load dipanggil ulang"))
    monkeypatch.setattr(A, "load", lambda *_a: pytest.fail("A.load dipanggil ulang"))

    first = ev.creator_results(members, 2026, conn)
    assert ev.creator_results(members, 2026, conn) is first          # di-cache
    state = OP.read_state(conn, members, ev.audience)
    OP.unknown_reasons(state, ev, members, 2026, conn)
    OP._creator_plan(ev, members, 2026, conn)
    assert calls == {"creator": 1, "audience": 1, "metric": 1}
    assert ev.loads == {"creator": 1, "audience": 1, "metric": 1}
    assert {str(r[0]) for r in first[2]} <= {m.kol_id for m in members}


# ---------------------------------------------------------------------------
# 7. unknown preserved
# ---------------------------------------------------------------------------
def test_unknown_preserved_below_min_known():
    inp = A.AudienceInput(has_data=True, female_pct=100.0, male_pct=0.0,
                          gender_counts={"female": 3, "male": 0},
                          country={"ID": (4.0, "inferred_low")})
    res = A.classify(inp)
    assert res["gender"].value is None and res["country"].value is None
    assert OP.audience_reason(res["gender"].reason, n_follower=40) == OP.BELOW_THRESHOLD
    assert OP.audience_reason(res["country"].reason, n_follower=40) == OP.BELOW_THRESHOLD
    assert OP.audience_reason(res["gender"].reason, n_follower=0) == OP.BLOCKED_BY_ZERO_COST
    kosong = A.classify(A.AudienceInput(has_data=True))["age"]
    assert kosong.value is None
    assert OP.audience_reason(kosong.reason, n_follower=40) == OP.NO_SOURCE


@pytest.mark.parametrize("reason,code", [
    ("tidak ada bukti kategori", OP.NO_SOURCE),
    ("umur: tidak ada pernyataan umur di bio dan tidak ada NIK", OP.NO_SOURCE),
    ("gender: tidak ada sinyal", OP.NO_SOURCE),
    ("kategori: bukti terlalu lemah (Beauty 1.00 < 2.0)", OP.INSUFFICIENT_EVIDENCE),
    ("kategori: hanya bukti lemah (hashtags)", OP.INSUFFICIENT_EVIDENCE),
    ("kategori: bukti bertentangan (A 3.00 vs B 2.50)", OP.CONFLICTING_EVIDENCE),
    ("style: seri humor vs edukasi", OP.CONFLICTING_EVIDENCE),
    ("style: hanya 2 post ber-caption (< 3)", OP.BELOW_THRESHOLD),
    ("personality: tidak ada pola yang konsisten (>= 3 post)", OP.BELOW_THRESHOLD),
    ("subkategori: kategori Unknown", OP.INSUFFICIENT_EVIDENCE),
    ("subkategori: kategori Food tidak punya subkategori di taxonomy", OP.STRUCTURALLY_UNAVAILABLE),
    ("gender: akun bisnis", OP.STRUCTURALLY_UNAVAILABLE),
    ("sesuatu yang belum dikenal", OP.UNCLASSIFIED),
])
def test_creator_reason_mapping(reason, code):
    assert OP.creator_reason(reason) == code


def test_metric_reason_never_invents_value():
    ev = dict(n_post=0, n_views=0, n_spons_known=0, n_caption=0, last_post=None,
              first_snap=None, n_follower=0, n_bio=0, has_card=True)
    assert OP.metric_reason("avg_views", ev) == OP.BLOCKED_BY_ZERO_COST
    assert OP.metric_reason("interest", ev) == OP.BLOCKED_BY_ZERO_COST
    ev.update(n_post=5, n_views=0, n_spons_known=0, n_caption=0)
    assert OP.metric_reason("avg_views", ev) == OP.STRUCTURALLY_UNAVAILABLE
    assert OP.metric_reason("paid_ratio", ev) == OP.STRUCTURALLY_UNAVAILABLE
    assert OP.metric_reason("content_topic", ev) == OP.NO_SOURCE
    from datetime import date
    ev.update(first_snap=date(2026, 9, 1), last_post=date(2026, 8, 1))
    assert OP.metric_reason("ER", ev) == OP.STRUCTURALLY_UNAVAILABLE
    assert OP.metric_reason("ER", None) == OP.NO_SOURCE


# ---------------------------------------------------------------------------
# 8. idempotent second run
# ---------------------------------------------------------------------------
def _simulate_apply(state: W.State, p: W.Plan) -> None:
    """Terapkan plan ke State di memori, sama seperti execute_plan ke DB."""
    for kid, want in p.kd_updates:
        state.kd[kid] = dict(want)
    gone = set(p.map_deletes)
    for kid in state.map:
        state.map[kid] = [r for r in state.map[kid] if r["id"] not in gone]
    for i, w in enumerate(p.map_inserts):
        state.map.setdefault(w["kol_directory_id"], []).append(
            {"id": f"baru-{i}", "kind": w["kind"], "key": w["key"], "source": W.CREATOR_SOURCE,
             "confidence": w["confidence"], "evidence": w["evidence"]})
    for w in p.map_updates:
        for rows in state.map.values():
            for r in rows:
                if r["id"] == w["id"]:
                    r.update(confidence=w["confidence"], evidence=w["evidence"])


@pytest.mark.needs_db
def test_creator_step_is_idempotent_on_cohort(conn, members):
    ev = OP.EvidenceSet.build(conn, members)
    tax, _rows, results = ev.creator_results(members, 2026, conn)
    with conn.cursor() as cur:
        cur.execute(W.SQL_ATTRIBUTE_IDS)
        attr_ids = {(k, key): aid for aid, k, key in cur.fetchall()}
        state = W.read_state(cur)
    run1 = W.plan(tax, results, state, attr_ids, OP.EVIDENCE_MODE)
    _simulate_apply(state, run1)
    run2 = W.plan(tax, results, state, attr_ids, OP.EVIDENCE_MODE)
    assert run2.n_changes == 0, "run #2 masih punya perubahan"


def test_brand_match_skipped_when_inputs_unchanged():
    fp = {"public.kol_directory": "1:a", "l2_gold.kol_profile_card": "2:b"}
    assert OP.brand_match_decision(fp, dict(fp), None) == (False, "skipped_no_input_change")
    assert OP.brand_match_decision(fp, dict(fp), {"fingerprint": dict(fp)})[0] is False
    run, why = OP.brand_match_decision(fp, {**fp, "l2_gold.kol_profile_card": "2:c"}, None)
    assert run and "kol_profile_card" in why
    assert OP.brand_match_decision(fp, dict(fp), {"fingerprint": {"x": "y"}})[0] is True


def test_brand_match_trigger_accepted_by_autometric_script():
    """scripts/brand-match-recalc.ts menolak trigger selain tiga ini (exit 1)."""
    assert OP.BRAND_MATCH_TRIGGER in ("brand_profile", "kol_data", "manual")


def test_failed_brand_match_is_retried_next_run():
    before, after = {"t": "1:a"}, {"t": "1:b"}
    gagal = {"fingerprint": before, "status": "failed"}      # yang dicatat saat gagal
    run, why = OP.brand_match_decision(after, dict(after), gagal)
    assert run and why == "input_changed_since_last_brand_match"


@pytest.mark.needs_db
def test_brand_match_fingerprint_ignores_timestamps(conn):
    with conn.cursor() as cur:
        cols = OP._value_columns(cur, "l2_gold.kol_profile_card")
        assert cols and "updated_at" not in cols and "created_at" not in cols
        assert OP.brand_match_input_fingerprint(cur) == OP.brand_match_input_fingerprint(cur)


def test_second_run_with_same_state_reports_zero_changes():
    s = {"a": {"creator": {"gender": "female"}, "audience": {"city": None}, "metric": {"ER": "1.2"}}}
    assert OP.count_changes(s, s) == {"creator": 0, "audience": 0, "metric": 0}


# ---------------------------------------------------------------------------
# 9-12. cohort, duplicate, orphan, ER invariant
# ---------------------------------------------------------------------------
def test_cohort_remains_100(members):
    assert OP.validate_cohort(members, BASELINE["cohort"]) == []
    assert len({m.social_account_id for m in members}) == 100
    assert Counter(m.platform for m in members) == {"instagram": 70, "tiktok": 30}


def test_cohort_validation_detects_problems(members):
    rusak = members[:99] + [members[0]]
    bad = OP.validate_cohort(rusak, BASELINE["cohort"])
    assert any("ganda" in b for b in bad)


@pytest.mark.needs_db
def test_cohort_matches_db(conn, members):
    with conn.cursor() as cur:
        assert OP.validate_cohort_db(cur, members) == []


@pytest.fixture(scope="module")
def integrity(conn, members):
    with conn.cursor() as cur:
        meta = OP.db_meta(cur, [m.social_account_id for m in members])
        return {c.name: c for c in OP.run_integrity(cur, members, BASELINE, meta, meta, 0)}


@pytest.mark.needs_db
def test_no_duplicate(integrity):
    dups = {k: c.got for k, c in integrity.items() if k.startswith("duplicate")}
    assert len(dups) == 6 and all(v == 0 for v in dups.values()), dups


@pytest.mark.needs_db
def test_no_orphan_and_valid_ownership(integrity):
    for k, c in integrity.items():
        if k.startswith(("orphan", "invalid ownership")):
            assert c.ok, (k, c.got)


@pytest.mark.needs_db
def test_er_invariant_preserved(integrity):
    assert integrity["ER invariant: post valid tapi ER NULL"].got == 0


@pytest.mark.needs_db
def test_integrity_all_pass_on_current_state(integrity):
    assert [k for k, c in integrity.items() if not c.ok] == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_modes():
    assert OP.parse_args(["--dry-run"]).dry_run
    assert OP.parse_args(["--report-only"]).report_only
    with pytest.raises(SystemExit):
        OP.parse_args(["--dry-run", "--report-only"])
