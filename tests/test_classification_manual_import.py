"""Importer keputusan manual: murni (tanpa DB)."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import classification_manual_import as M  # noqa: E402

COHORT = {"a": [{"sa": "sa-ig", "kol_id": "k-ig", "platform": "instagram"},
                {"sa": "sa-tt", "kol_id": "k-tt", "platform": "tiktok"}],
          "b": [{"sa": "sa-b", "kol_id": "k-b", "platform": "instagram"}]}
ATTR = {("style", "content_style.review"): "at-review", ("personality", "creator_personality.reviewer"): "at-rev"}
TODAY = date(2026, 9, 25)


def run(decisions, card=None, attr_map=None):
    return M.plan(decisions, COHORT, ATTR, card if card is not None else {"sa-ig": (None, None), "sa-tt": (None, None),
                                                                          "sa-b": (None, None)},
                  attr_map or set(), TODAY)


def test_gender_manual_ke_semua_akun_kreator():
    rows = run([M.Decision("a", "gender", "male")])
    assert [(r.status, r.social_account_id) for r in rows] == [("WRITE", "sa-ig"), ("WRITE", "sa-tt")]
    assert rows[0].params == {"gender": "male", "source": "manual", "confidence": "high"}


def test_gender_tidak_menimpa_nilai_yang_ada():
    rows = run([M.Decision("b", "gender", "female")], card={"sa-b": ("male", "name_inference")})
    assert rows[0].status == "INVALID"


def test_gender_idempotent():
    rows = run([M.Decision("b", "gender", "male")], card={"sa-b": ("male", "manual")})
    assert rows[0].status == "SKIP_SAME"


def test_style_curated_dan_idempotent():
    r = run([M.Decision("b", "style", "content_style.review", "9/21")])[0]
    assert r.status == "WRITE" and r.params["source"] == "curated" and r.target == "public.kol_attribute_map"
    assert run([M.Decision("b", "style", "content_style.review")], attr_map={("k-b", "at-review")})[0].status == "SKIP_SAME"


def test_attribute_di_luar_taxonomy_invalid():
    assert run([M.Decision("b", "style", "visual_style.bogus")])[0].status == "INVALID"


def test_category_dan_subcategory_ditolak_bukan_disamarkan():
    rows = run([M.Decision("b", "category", "Lifestyle"), M.Decision("b", "subcategory", "Makeup")])
    assert {r.status for r in rows} == {"BLOCKED"}
    assert all(r.params == {} and not r.target for r in rows)


def test_tidak_ada_source_creator_classification():
    rows = run([M.Decision("a", "gender", "male"), M.Decision("b", "style", "content_style.review"),
                M.Decision("b", "personality", "creator_personality.reviewer")])
    assert {r.params.get("source") for r in rows} <= {"manual", "curated"}


def test_username_di_luar_cohort_dan_duplikat():
    rows = run([M.Decision("zzz", "style", "content_style.review"),
                M.Decision("b", "style", "content_style.review"), M.Decision("b", "style", "content_style.review")])
    assert [r.status for r in rows] == ["INVALID", "WRITE", "INVALID"]


def test_sql_tanpa_delete():
    for sql in (M.SQL_WRITE_GENDER, M.SQL_WRITE_ATTR):
        assert "DELETE" not in sql.upper()
    assert "creator_gender IS NULL" in M.SQL_WRITE_GENDER
    assert "NOT EXISTS" in M.SQL_WRITE_ATTR
