"""Add KOL -> auto Category + Subcategory.

Bagian 1 (offline): asset `creator_classification` / `creator_category_bridge`
terdaftar di Dagster, ikut `transform_chain_job`, dan urutannya benar.

Bagian 2 (needs_db): KOL baru SIMULASI di DB `kol`, di SATU transaksi yang SELALU
di-ROLLBACK -- tidak ada baris yang tersimpan. Evidence-nya (bio + post L1) disalin
dari satu KOL existing; KOL simulasi itu sendiri tidak punya roster maupun category.
Yang dibuktikan: KOL baru -> classifier -> Category -> Subcategory -> category_ids
terisi -> ROLLBACK, dan tidak satu pun baris KOL existing berubah.
"""

from __future__ import annotations

import dataclasses
import sys
import uuid
from pathlib import Path

import pytest

import creator_category_bridge as B
import creator_classification as C
import creator_classification_dryrun as D
import creator_classification_writer as W

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestration"))

MODE = "l1"                       # simulasi hanya menyalin L1: bukti production-eligible
TAHUN = 2026


# =====================================================================
# 1. Registrasi Dagster (offline)
# =====================================================================
@pytest.fixture(scope="module")
def defs():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from kol_orchestration.repository import defs as d
    return d


def test_asset_terdaftar_di_definitions(defs):
    from dagster import AssetKey
    graph = defs.resolve_asset_graph()
    assert graph.has(AssetKey("creator_classification")) and graph.has(AssetKey("creator_category_bridge"))
    parents = {k.to_user_string() for k in graph.get(AssetKey("creator_classification")).parent_keys}
    assert parents == {"unified_profile", "unified_post", "kol_profile_card"}
    assert {k.to_user_string() for k in graph.get(AssetKey("creator_category_bridge")).parent_keys} == {
        "creator_classification"}


def test_transform_chain_job_menjalankan_classification_lalu_bridge(defs):
    import warnings
    from kol_orchestration import one_shot
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        job = defs.resolve_job_def(one_shot.TRANSFORM_JOB_NAME)
    induk = {simpul.name: set(dep) for simpul, dep in job.dependencies.items()}
    assert set(induk) == set(one_shot.CHAIN_JOB_ASSETS)
    assert induk["creator_classification"] == {"unified_profile", "unified_post", "kol_profile_card"}
    assert induk["creator_category_bridge"] == {"creator_classification"}


def test_sensor_l0_raw_memicu_job_yang_berisi_classification(defs):
    from kol_orchestration import one_shot, sensors
    assert [t.job_name for t in sensors.l0_raw_new_data_sensor.targets] == [one_shot.TRANSFORM_JOB_NAME]
    assert sensors.SENSOR_NAME in {s.name for s in defs.sensors}


def test_rantai_transform_lama_tidak_berubah():
    """`jalankan_transform_chain` (one-shot scrape, e2e, one-pass enrichment) tetap murni
    L0 -> L2: classification/bridge hanya ada di `transform_chain_job`."""
    from kol_orchestration import one_shot
    assert not set(one_shot.CLASSIFICATION_ASSETS) & set(one_shot.TRANSFORM_ASSETS)
    assert one_shot.CHAIN_JOB_ASSETS == (one_shot.TRANSFORM_ASSETS + one_shot.ENRICHMENT_ASSETS
                                         + one_shot.CLASSIFICATION_ASSETS)
    assert {a.key.to_user_string() for a in one_shot._semua_asset()} == set(one_shot.TRANSFORM_ASSETS)


def test_asset_tanpa_target_berhenti_tanpa_write(monkeypatch):
    from kol_orchestration.assets import creator_classification as M

    class Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            conn.sql.append(" ".join(sql.split()))

        def fetchall(self):
            return []

    class Conn:
        sql: list = []
        committed = rolled_back = closed = 0
        isolation = None

        def set_session(self, isolation_level=None, **_kw):
            self.isolation = isolation_level

        def cursor(self):
            return Cur()

        def commit(self):
            self.committed += 1

        def rollback(self):
            self.rolled_back += 1

        def close(self):
            self.closed += 1

    class Pg:
        def get_conn(self):
            return conn

    for jalankan in (M._jalankan_klasifikasi, M._jalankan_bridge):
        conn = Conn()
        conn.sql = []
        out = jalankan(Pg())
        assert out.value == 0 and conn.committed == 0 and conn.closed == 1
        assert conn.isolation == "REPEATABLE READ"
        assert not any(s.startswith(("UPDATE", "INSERT", "DELETE")) for s in conn.sql)


# =====================================================================
# 2. KOL baru simulasi di DB `kol` -- transaksi + ROLLBACK
# =====================================================================
def _connect():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        from config import load_config
        return psycopg2.connect(connect_timeout=10, **load_config().postgres.as_connect_kwargs())
    except Exception as exc:                                   # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")


SQL_DB_FP = {
    "kol_directory": "SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t.id), '')) "
                     "FROM public.kol_directory t",
    "kol_attribute_map": "SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t.id), '')) "
                         "FROM public.kol_attribute_map t",
    "social_account": "SELECT count(*) FROM public.social_account",
    "kol_social_account": "SELECT count(*) FROM public.kol_social_account",
    "unified_profile": "SELECT count(*) FROM l1_silver.unified_profile",
    "unified_post": "SELECT count(*) FROM l1_silver.unified_post",
    "kol_categories": "SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t.id), '')) "
                      "FROM public.kol_categories t",
}


def db_fingerprint() -> dict:
    """Sidik jari dari koneksi TERPISAH (read-only): hanya melihat data yang ter-commit."""
    cn = _connect()
    try:
        cn.set_session(readonly=True)
        out = {}
        with cn.cursor() as cur:
            for k, q in SQL_DB_FP.items():
                cur.execute(q)
                out[k] = tuple(cur.fetchone())
        return out
    finally:
        cn.close()


SQL_DONOR_CANDIDATES = """
    SELECT id::text FROM public.kol_directory
     WHERE directory_status = 'active' AND inferred_subcategory_id IS NOT NULL
       AND inferred_category_source = 'creator_classification' ORDER BY id"""


def _pick_donor(conn):
    """KOL existing yang bio + post L1-nya SAJA (tanpa roster/declared) sudah cukup untuk
    category + subcategory. Mengembalikan (kol, hasil classifier atas bukti itu)."""
    with conn.cursor() as cur:
        cur.execute(SQL_DONOR_CANDIDATES)
        ids = [r[0] for r in cur.fetchall()]
    tax, kols, *rest = D.load(conn, kol_ids=ids)
    for kol in kols:
        inp, _card = D.build_input(kol, *rest, False)
        bare = dataclasses.replace(inp, roster_categories=(), sibling_roster_categories=(), roster_gender=None,
                                   nik=None, roster_name=None, manual_gender=None, manual_age=None)
        res = C.classify(bare, tax, TAHUN)
        if res["category"].known and res["subcategory"].known and \
                res["category"].confidence in B.BRIDGE_CONFIDENCE:
            return kol, res
    pytest.skip("tidak ada KOL donor yang terklasifikasi dari L1 saja")


def _insert_sim(cur, donor_sa: str) -> tuple[str, str, str]:
    kid, sa = str(uuid.uuid4()), str(uuid.uuid4())
    username = "zz_sim_newkol_" + uuid.uuid4().hex[:10]
    cur.execute("SELECT platform_id FROM public.social_account WHERE id = %s", (donor_sa,))
    platform_id, = cur.fetchone()
    cur.execute("INSERT INTO public.social_account (id, platform_id, username) VALUES (%s, %s, %s)",
                (sa, platform_id, username))
    cur.execute("""INSERT INTO public.kol_directory (id, platform_id, username, username_normalized,
                                                     source, directory_status, scrape_status)
                   VALUES (%s, %s, %s, %s, 'manual_add', 'active', 'success')""",
                (kid, platform_id, username, username))
    cur.execute("INSERT INTO public.kol_social_account (kol_id, social_account_id, platform_id) VALUES (%s, %s, %s)",
                (kid, sa, platform_id))
    cur.execute("""INSERT INTO l1_silver.unified_profile (social_account_id, platform_id, date, username, display_name, bio)
                   SELECT %s, platform_id, date, %s, display_name, bio FROM l1_silver.unified_profile
                    WHERE social_account_id = %s ORDER BY date DESC LIMIT 1""", (sa, username, donor_sa))
    cur.execute("""INSERT INTO l1_silver.unified_post (social_account_id, platform_id, content_id, caption,
                                                       hashtags, media_type, video_duration)
                   SELECT %s, platform_id, content_id, caption, hashtags, media_type, video_duration
                     FROM l1_silver.unified_post WHERE social_account_id = %s""", (sa, donor_sa))
    return kid, sa, username


SQL_SIM_ROW = """
    SELECT k.category_id::text, k.category_ids::text[], k.inferred_category_id::text,
           k.inferred_subcategory_id::text, k.inferred_category_source, k.inferred_category_confidence,
           c.level, c.parent_id, s.level, s.parent_id::text
      FROM public.kol_directory k
      LEFT JOIN public.kol_categories c ON c.id = k.category_id
      LEFT JOIN public.kol_categories s ON s.id = k.inferred_subcategory_id
     WHERE k.id = %s"""
SQL_REST_FP = """SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t.id), ''))
                   FROM public.kol_directory t WHERE t.id <> %s"""


@pytest.mark.needs_db
def test_db_kol_baru_simulasi_dapat_category_subcategory_lalu_rollback():
    fp_before = db_fingerprint()
    conn = _connect()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '15s'")
            cur.execute("SET LOCAL statement_timeout = '120s'")
        donor, expected = _pick_donor(conn)
        with conn.cursor() as cur:
            kid, _sa, username = _insert_sim(cur, donor[3])
            cur.execute(SQL_REST_FP, (kid,))
            rest_before = cur.fetchone()

            # --- KOL baru -> classifier (hanya yang unclassified) -----------------
            target = W.unclassified_ids(cur)
            assert kid in target
        tax, _rows, results, attr_ids = W.load_inputs(conn, W.EVIDENCE_MODES[MODE], TAHUN,
                                                      audience_in={}, kol_ids=target)
        assert {r[0] for r in results} == set(target)
        with conn.cursor() as cur:
            p = W.plan(tax, results, W.read_state(cur), attr_ids, MODE, additive=True)
            assert p.invalid == [] and p.map_deletes == [] and p.map_updates == []
            assert {k for k, _w in p.kd_updates} <= set(target)
            want = dict(p.kd_updates)[kid]
            assert want["inferred_category_id"] == expected["category"].ref.id
            assert want["inferred_subcategory_id"] == expected["subcategory"].ref.id

            # --- writer: WRITE -> GUARD ----------------------------------------
            before = W.snapshot_directory(cur)
            done = W.execute_plan(cur, p)
            after = W.snapshot_directory(cur)
            left = W.plan(tax, results, W.read_state(cur), attr_ids, MODE, additive=True).n_changes
            assert W.guards(before, after, p.n_changes, done, left) == []

            # --- bridge: WRITE -> GUARD ----------------------------------------
            bp = B.plan(B.read_candidates(cur))
            assert kid in bp.target_ids
            b_before = B.snapshot(cur, bp.target_ids)
            b_done = B.execute_plan(cur, bp)
            b_after = B.snapshot(cur, bp.target_ids)
            b_left = len(B.plan(B.read_candidates(cur)).updates)
            assert B.guards(b_before, b_after, len(bp.updates), b_done, b_left) == []

            # --- hasil akhir di field yang dibaca aplikasi ----------------------
            cur.execute(SQL_SIM_ROW, (kid,))
            (cat_id, cat_ids, inf_cat, inf_sub, source, conf,
             cat_level, cat_parent, sub_level, sub_parent) = cur.fetchone()
            assert cat_id == inf_cat == expected["category"].ref.id          # Category terpilih
            assert cat_ids == [cat_id]                                       # category_ids terisi
            assert inf_sub == expected["subcategory"].ref.id                 # Subcategory terpilih
            assert (cat_level, cat_parent) == ("category", None)
            assert (sub_level, sub_parent) == ("sub_category", cat_id)       # anak dari category-nya
            assert source == W.CREATOR_SOURCE and conf in B.BRIDGE_CONFIDENCE

            # --- KOL existing: tidak satu baris pun berubah ---------------------
            cur.execute(SQL_REST_FP, (kid,))
            rest_after = cur.fetchone()
            others = set(bp.target_ids) | {k for k, _w in p.kd_updates}
            if others == {kid}:
                assert rest_after == rest_before
            print(f"\nSIMULASI @{username}: donor @{donor[1]} -> category "
                  f"{expected['category'].value!r} [{conf}], subcategory {expected['subcategory'].value!r}; "
                  f"writer {done} baris, bridge {b_done} baris; KOL lain ditulis: {sorted(others - {kid})}")
    finally:
        conn.rollback()
        conn.close()

    # Tidak ada yang tersimpan: KOL simulasi hilang, sidik jari DB identik.
    assert db_fingerprint() == fp_before
    cn = _connect()
    try:
        with cn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.kol_directory WHERE username LIKE 'zz_sim_newkol_%'")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT count(*) FROM public.social_account WHERE username LIKE 'zz_sim_newkol_%'")
            assert cur.fetchone()[0] == 0
    finally:
        cn.close()


@pytest.mark.needs_db
def test_db_dry_run_only_unclassified_tidak_menulis():
    """Plan additive atas DB nyata: target hanya KOL tanpa category, 0 delete/update,
    KOL existing tidak masuk plan, dan sidik jari DB sebelum == sesudah."""
    fp_before = db_fingerprint()
    conn = _connect()
    try:
        conn.set_session(readonly=True)
        with conn.cursor() as cur:
            target = W.unclassified_ids(cur)
            cur.execute("""SELECT count(*) FROM public.kol_directory WHERE id = ANY(%s::uuid[])
                            AND (category_id IS NOT NULL OR coalesce(cardinality(category_ids), 0) > 0
                                 OR inferred_category_id IS NOT NULL OR directory_status <> 'active')""", (target,))
            assert cur.fetchone()[0] == 0
        if target:
            tax, _rows, results, attr_ids = W.load_inputs(conn, True, TAHUN, audience_in={}, kol_ids=target)
            with conn.cursor() as cur:
                p = W.plan(tax, results, W.read_state(cur), attr_ids, "l1+l0raw", additive=True)
            assert p.map_deletes == [] and p.map_updates == [] and not p.cleared
            assert {k for k, _w in p.kd_updates} <= set(target)
            assert all(w["inferred_category_id"] for _k, w in p.kd_updates)
        with conn.cursor() as cur:
            bp = B.plan(B.read_candidates(cur))
        assert all(c.category_id is None and not c.category_ids for c in bp.updates)
    finally:
        conn.rollback()
        conn.close()
    assert db_fingerprint() == fp_before
