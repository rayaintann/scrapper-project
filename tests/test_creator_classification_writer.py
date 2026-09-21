"""Test writer Creator Classification (+ verifikasi audiens read-only) -- tanpa DB."""

from __future__ import annotations

import re

import pytest

import audience_classification as A
import creator_classification as C
import creator_classification_writer as W
from tests.test_creator_classification import ATTRS, taxonomy_rows

KOL = "11111111-1111-1111-1111-111111111111"
SA = "22222222-2222-2222-2222-222222222222"
STYLE = "content_style.review"
PERS = "creator_personality.reviewer"
MODE = "l1+l0raw"


@pytest.fixture(scope="module")
def tax():
    return C.Taxonomy.from_rows(taxonomy_rows(), ATTRS)


@pytest.fixture(scope="module")
def attr_ids():
    return {(kind, key): f"attr-{kind}-{key}" for kind, key in ATTRS}


def res(tax, *, cat=None, sub=None, style=None, pers=None, gender=None, age=None):
    def ref(code):
        r = tax.by_code[code]
        return C.Attribute(r.name, "inference", "medium", [C.Evidence("bio", code, 2.0, "kuliner")],
                           "skor 2.00", ref=r)
    return {"gender": C.Attribute(gender, "roster" if gender else None, "medium" if gender else None),
            "age": C.Attribute(age, "roster_ktp" if age else None, "high" if age else None),
            "role": C.Attribute(),
            "category": ref(cat) if cat else C.Attribute(),
            "subcategory": ref(sub) if sub else C.Attribute(),
            "style": C.Attribute(style, "caption_pattern" if style else None, "medium" if style else None),
            "personality": C.Attribute(pers, "caption_pattern" if pers else None, "medium" if pers else None)}


AUD_IN = A.AudienceInput(platform="instagram", has_data=True, female_pct=71.79, male_pct=28.21,
                         gender_known_pct=39.0, gender_counts={"female": 28, "male": 11},
                         gender_reliability="Low", country={"ID": (12, "inferred_high")},
                         interest_top="religion", interest_source="audience")


def run_plan(tax, attr_ids, r, state=None, card=None, ainp=AUD_IN):
    state = state or W.State({}, {})
    return W.plan(tax, [(KOL, SA, r, card or {"gender": None, "age": None}, ainp, A.classify(ainp))],
                  state, attr_ids, MODE)


def converge(tax, attr_ids, r, ainp=AUD_IN):
    """Terapkan plan ke State palsu -> state setelah write."""
    p = run_plan(tax, attr_ids, r, ainp=ainp)
    kd = {kid: want for kid, want in p.kd_updates}
    mp = {KOL: [{"id": f"m{i}", "kind": w["kind"], "key": w["key"], "source": W.CREATOR_SOURCE,
                 "confidence": w["confidence"], "evidence": w["evidence"]} for i, w in enumerate(p.map_inserts)]}
    return W.State(kd, mp)


# --- creator category / subcategory -------------------------------------------------
def test_category_subcategory_ditulis_sebagai_id_terpisah_dengan_parent(tax, attr_ids):
    p = run_plan(tax, attr_ids, res(tax, cat="FOD", sub="FOD.CUL"))
    (kid, want), = p.kd_updates
    food, cul = tax.by_code["FOD"], tax.by_code["FOD.CUL"]
    assert kid == KOL
    assert want["inferred_category_id"] == food.id and want["inferred_subcategory_id"] == cul.id
    assert cul.parent_id == food.id
    assert want["inferred_category_source"] == "creator_classification"
    ev = want["inferred_category_evidence"]
    assert (ev["category"]["name"], ev["subcategory"]["name"]) == ("Food", "Culinary Review")
    assert ev["subcategory"]["code"] == "FOD.CUL" and ev["subcategory"]["name"] != "FOD.CUL"


def test_category_unknown_tidak_dipaksa(tax, attr_ids):
    p = run_plan(tax, attr_ids, res(tax))
    (_kid, want), = p.kd_updates or [(None, dict.fromkeys(W.KD_COLS))]
    assert all(v is None for v in want.values())
    assert p.unknown["creator_category"] == 1


def test_subkategori_parent_salah_invalid_tidak_ada_write(tax, attr_ids):
    p = run_plan(tax, attr_ids, res(tax, cat="BEA", sub="FIT.RUN", style=STYLE))
    assert p.n_changes == 0 and any("parent" in x for _k, x in p.invalid)


def test_nama_kode_invalid(tax, attr_ids):
    r = res(tax, cat="FOD")
    cul = tax.by_code["FOD.CUL"]
    r["subcategory"] = C.Attribute("FOD.CUL", "inference", "medium", ref=cul)
    p = run_plan(tax, attr_ids, r)
    assert p.n_changes == 0 and p.invalid


def test_kategori_legacy_invalid(tax, attr_ids):
    r = res(tax)
    foodies = tax.category_by_name["Foodies"]
    r["category"] = C.Attribute(foodies.name, "roster", "high", ref=foodies)
    assert run_plan(tax, attr_ids, r).invalid


def test_role_tidak_pernah_jadi_output_writer(tax, attr_ids):
    r = res(tax, cat="FOD")
    r["role"] = C.Attribute("Creator", "inference", "high")
    p = run_plan(tax, attr_ids, r)
    assert not any("role" in k for k in list(p.classified) + list(p.unknown))


# --- style / personality ------------------------------------------------------------
def test_style_personality_ditulis_dengan_source_confidence_evidence(tax, attr_ids):
    p = run_plan(tax, attr_ids, res(tax, style=STYLE, pers=PERS))
    assert [(w["kind"], w["key"], w["attribute_id"], w["confidence"]) for w in p.map_inserts] == [
        ("style", STYLE, attr_ids[("style", STYLE)], "medium"),
        ("personality", PERS, attr_ids[("personality", PERS)], "medium")]
    assert all(w["evidence"]["basis"] == "caption_pattern" for w in p.map_inserts)


def test_curated_existing_tidak_ditimpa_dan_classifier_mundur(tax, attr_ids):
    state = W.State({}, {KOL: [
        {"id": "c1", "kind": "style", "key": "content_style.tutorial", "source": "curated",
         "confidence": None, "evidence": None},
        {"id": "o1", "kind": "style", "key": STYLE, "source": W.CREATOR_SOURCE,
         "confidence": "medium", "evidence": {}}]})
    p = run_plan(tax, attr_ids, res(tax, style=STYLE), state)
    assert p.map_inserts == [] and p.map_updates == []
    assert p.map_deletes == ["o1"]                      # hanya baris classifier
    assert p.skipped_curated["creator_style"] == 1


def test_baris_classifier_basi_diganti(tax, attr_ids):
    state = W.State({}, {KOL: [{"id": "o1", "kind": "style", "key": "content_style.tutorial",
                                    "source": W.CREATOR_SOURCE, "confidence": "low", "evidence": {}}]})
    p = run_plan(tax, attr_ids, res(tax, style=STYLE), state)
    assert p.map_deletes == ["o1"] and [w["key"] for w in p.map_inserts] == [STYLE]


def test_unknown_membersihkan_baris_classifier_saja(tax, attr_ids):
    state = W.State({}, {KOL: [{"id": "o1", "kind": "personality", "key": PERS,
                                    "source": W.CREATOR_SOURCE, "confidence": "low", "evidence": {}}]})
    p = run_plan(tax, attr_ids, res(tax), state)
    assert p.map_deletes == ["o1"] and p.map_inserts == []


# --- audience: dibaca dari Audience Analysis existing, tidak ditulis ------------------
def test_audience_hanya_dibaca_tidak_ada_write(tax, attr_ids):
    p = run_plan(tax, attr_ids, res(tax))
    assert p.n_changes == 0                           # tanpa hasil kreator -> tidak ada write sama sekali
    assert p.verified["audience_gender"] == p.verified["audience_country"] == 1
    assert p.verified["audience_interest"] == 1
    assert not hasattr(p, "card_updates")


def test_audience_tidak_masuk_category_kreator(tax, attr_ids):
    p = run_plan(tax, attr_ids, res(tax, cat="FOD"))
    (_k, kd), = p.kd_updates
    assert kd["inferred_category_evidence"]["category"]["name"] == "Food"
    assert "religion" not in str(kd)                  # interest audiens tidak bocor ke kreator


def test_akun_tanpa_data_follower_audience_unknown(tax, attr_ids):
    p = run_plan(tax, attr_ids, res(tax), ainp=A.AudienceInput())
    assert p.unknown["audience_country"] == 1 and p.verified["audience_country"] == 0


def test_writer_tidak_punya_sql_audiens():
    src = " ".join(v for k, v in vars(W).items() if k.startswith("SQL_") and k not in (
        "SQL_VERIFY", "SQL_VERIFY_AUDIENCE", "SQL_VERIFY_TAX", "SQL_COUNTS"))
    for t in ("kol_profile_card", "audience_demographics_daily", "audience_geo_daily",
              "audience_interest_daily", "_audience_analysis"):
        assert t not in src, t
    assert "l2_gold.kol_profile_card" in W.FULL_FP and "l2_gold.audience_geo_daily" in W.FULL_FP


# --- creator gender/age -------------------------------------------------------------
def test_creator_gender_age_hanya_diverifikasi(tax, attr_ids):
    ok = run_plan(tax, attr_ids, res(tax, gender="female", age="27"), card={"gender": "female", "age": 27})
    assert ok.verified["creator_gender"] == ok.verified["creator_age"] == 1 and ok.card_mismatch == []
    beda = run_plan(tax, attr_ids, res(tax, gender="female"), card={"gender": "male", "age": None})
    assert beda.card_mismatch == [(KOL, "gender", "male", "female")]


# --- idempotency --------------------------------------------------------------------
def test_idempoten_run_kedua_nol_perubahan(tax, attr_ids):
    r = res(tax, cat="FOD", sub="FOD.CUL", style=STYLE, pers=PERS)
    state = converge(tax, attr_ids, r)
    again = run_plan(tax, attr_ids, r, state)
    assert again.n_changes == 0
    assert again.unchanged["creator_category"] == 1


# --- guard --------------------------------------------------------------------------
def snap(**over):
    s = {"public.kol_categories": [76, "a"], "public.kol_directory (non-classifier columns)": [1980, "b"],
         "l2_gold.kol_profile_card (non-classifier columns)": [1980, "c"],
         "public.kol_attribute_map (curated rows)": [0, "d"], "public.agency_kol_accounts": [1980, "e"]}
    s.update(active=1980, map_dupes=0, map_orphans=0, map_ours_multi=0, map_mixed=0, kd_invalid=0,
             category_orphans=0)
    s.update(over)
    return s


def test_guard_lolos():
    assert W.guards(snap(), snap(), 5, 5, 0) == []


@pytest.mark.parametrize("after,planned,done,left,frag", [
    (snap(active=1979), 5, 5, 0, "active"),
    (snap(**{"public.kol_categories": [77, "x"]}), 5, 5, 0, "kol_categories"),
    (snap(**{"public.kol_directory (non-classifier columns)": [1980, "x"]}), 5, 5, 0, "kol_directory"),
    (snap(**{"public.kol_attribute_map (curated rows)": [0, "x"]}), 5, 5, 0, "curated"),
    (snap(**{"public.agency_kol_accounts": [1980, "x"]}), 5, 5, 0, "agency_kol_accounts"),
    (snap(), 5, 4, 0, "written 4 != candidate 5"),
    (snap(), 5, 5, 2, "konvergen"),
    (snap(map_dupes=1), 5, 5, 0, "map_dupes"),
    (snap(map_orphans=1), 5, 5, 0, "map_orphans"),
    (snap(map_ours_multi=1), 5, 5, 0, "map_ours_multi"),
    (snap(map_mixed=1), 5, 5, 0, "map_mixed"),
    (snap(kd_invalid=1), 5, 5, 0, "kd_invalid"),
    (snap(category_orphans=1), 5, 5, 0, "orphan category"),
])
def test_guard_gagal(after, planned, done, left, frag):
    assert any(frag in x for x in W.guards(snap(), after, planned, done, left))


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
        self.rowcount = 0 if self.conn.noop_after and len(self.conn.statements) > self.conn.noop_after else 1


class FakeConn:
    def __init__(self, fail=False, noop_after=None):
        self.statements, self.fail, self.noop_after = [], fail, noop_after
        self.committed = self.rolled_back = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


def _plan(tax, attr_ids):
    return run_plan(tax, attr_ids, res(tax, cat="FOD", sub="FOD.CUL", style=STYLE, pers=PERS))


def _empty_replan(_cur):
    return W.Plan()


def test_commit_kalau_guard_lolos(tax, attr_ids):
    conn, p = FakeConn(), _plan(tax, attr_ids)
    done, problems, committed = W.apply(conn, _empty_replan, p, commit=True, snap=lambda _c: snap())
    assert (done, problems, committed) == (p.n_changes, [], True)
    assert conn.committed == 1 and conn.rolled_back == 0


def test_rehearse_selalu_rollback(tax, attr_ids):
    conn = FakeConn()
    _d, problems, committed = W.apply(conn, _empty_replan, _plan(tax, attr_ids), commit=False,
                                      snap=lambda _c: snap())
    assert problems == [] and not committed and (conn.committed, conn.rolled_back) == (0, 1)


def test_write_parsial_rollback_tanpa_commit(tax, attr_ids):
    conn = FakeConn(noop_after=1)            # hanya statement pertama yang mengenai baris
    done, problems, committed = W.apply(conn, _empty_replan, _plan(tax, attr_ids), commit=True,
                                        snap=lambda _c: snap())
    assert done == 1 and problems and not committed
    assert (conn.committed, conn.rolled_back) == (0, 1)


def test_tidak_konvergen_rollback(tax, attr_ids):
    conn, p = FakeConn(), _plan(tax, attr_ids)
    _d, problems, committed = W.apply(conn, lambda _c: p, p, commit=True, snap=lambda _c: snap())
    assert any("konvergen" in x for x in problems) and not committed and conn.committed == 0


def test_error_saat_write_rollback_dan_dilempar(tax, attr_ids):
    conn = FakeConn(fail=True)
    with pytest.raises(RuntimeError):
        W.apply(conn, _empty_replan, _plan(tax, attr_ids), commit=True, snap=lambda _c: snap())
    assert (conn.committed, conn.rolled_back) == (0, 1)


def test_sql_writer_tidak_menyentuh_kolom_kurasi_atau_taxonomy():
    sqls = " ".join([W.SQL_KD_UPDATE, W.SQL_MAP_INSERT, W.SQL_MAP_UPDATE, W.SQL_MAP_DELETE])
    for forbidden in ("category_ids", "agency_kol_accounts", "INSERT INTO public.kol_categories",
                      "UPDATE public.kol_categories", "creator_gender", "creator_age", "female_pct"):
        assert forbidden not in sqls, forbidden
    assert not re.search(r"(?<![\w])category_id\s*=", sqls)     # hanya inferred_category_id
    assert "source = 'creator_classification'" in W.SQL_MAP_DELETE
