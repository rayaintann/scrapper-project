"""Importer workbook classification: pemetaan field -> storage label, murni (tanpa DB)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import classification_workbook_import as W  # noqa: E402

ATTR = {("style", "content_style.review"): "a1", ("personality", "creator_personality.reviewer"): "a2"}


def db(**kw):
    base = dict(kol_ids={"k1", "k2"}, attributes=ATTR, attr_map={}, card={"s1": (None, None)},
                kd={"k1": {"cat": None, "sub": None, "source": None, "cat_conf": None, "sub_conf": None, "evidence": None}},
                categories={"Beauty": "C1", "Food": "C2"}, subcats={("C1", "Makeup"): "S1", ("C2", "Culinary Review"): "S2"},
                cat_names={"C1": "Beauty", "C2": "Food", "S1": "Makeup", "S2": "Culinary Review"},
                aud_curated={}, aud_state={"s1": {"gender": None, "age": None, "country": None, "city": None,
                                                  "interest": "beauty"}},
                cities={"Jakarta", "Bandung"})
    base.update(kw)
    return W.DbState(**base)


def cell(field, final, method="INFERRED", kol="k1", conf="low", sa="s1"):
    return W.Cell(kol, "u", "instagram", field, final, method, conf, "ev", "src", "why", sa)


# --- style / personality ------------------------------------------------------
def test_style_baru_insert_curated_dengan_method():
    it = W.plan([cell("Creator Style", "content_style.review", "ESTIMATED")], db())[0]
    assert it.status == "INSERT" and it.params["confidence"] == "low"
    assert it.params["evidence"]["method"] == "ESTIMATED" and "'curated'" in W.SQL_INSERT


def test_style_existing_dan_import_ulang_skip_same():
    d = db(attr_map={("k1", "style"): {"content_style.review"}})
    assert W.plan([cell("Creator Style", "content_style.review", "EXISTING")], d)[0].status == "SKIP_SAME"
    assert W.plan([cell("Creator Style", "content_style.review", "ESTIMATED")], d)[0].status == "SKIP_SAME"


def test_style_tidak_menimpa_nilai_db():
    d = db(attr_map={("k1", "style"): {"content_style.vlog"}})
    assert W.plan([cell("Creator Style", "content_style.review")], d)[0].status == "INVALID"


# --- creator gender -----------------------------------------------------------
def test_gender_null_diisi_manual():
    it = W.plan([cell("Creator Gender", "male", conf="high")], db())[0]
    assert it.status == "UPDATE" and it.params == {"sa": "s1", "gender": "male", "confidence": "high"}


def test_gender_existing_tidak_ditimpa():
    assert W.plan([cell("Creator Gender", "male")], db(card={"s1": ("female", "roster")}))[0].status == "INVALID"
    assert W.plan([cell("Creator Gender", "male")], db(card={"s1": ("male", "manual")}))[0].status == "SKIP_SAME"


# --- category / subcategory ---------------------------------------------------
def test_category_dan_sub_kosong_jadi_satu_update_curated():
    d = db()
    items = W.plan([cell("Creator Category", "Beauty", conf="medium"), cell("Creator Subcategory", "Makeup")], d)
    assert [i.status for i in items] == ["UPDATE", "UPDATE"]
    (w,) = W.kd_writes(items, d)
    assert (w["cat"], w["sub"], w["expect_cat"], w["cat_conf"], w["sub_conf"]) == ("C1", "S1", None, "medium", "low")
    assert "'curated'" in W.SQL_KD_CURATED and "inferred_subcategory_id IS NULL" in W.SQL_KD_CURATED


def test_sub_diisi_di_bawah_category_existing_yang_dipertahankan():
    d = db(kd={"k1": {"cat": "C2", "sub": None, "source": "creator_classification", "cat_conf": "high",
                      "sub_conf": None, "evidence": {"x": 1}}})
    items = W.plan([cell("Creator Category", "Food", "EXISTING"), cell("Creator Subcategory", "Culinary Review")], d)
    assert [i.status for i in items] == ["SKIP_SAME", "UPDATE"]
    (w,) = W.kd_writes(items, d)
    assert w["cat"] == "C2" and w["cat_conf"] == "high" and w["expect_cat"] == "C2"
    assert w["evidence"]["preserved"] == {"x": 1}


def test_sub_bukan_anak_category_invalid():
    d = db(kd={"k1": {"cat": "C2", "sub": None, "source": "creator_classification", "cat_conf": "high",
                      "sub_conf": None, "evidence": None}})
    assert W.plan([cell("Creator Subcategory", "Makeup")], d)[0].status == "INVALID"


def test_category_existing_berbeda_tidak_ditimpa():
    d = db(kd={"k1": {"cat": "C2", "sub": None, "source": "creator_classification", "cat_conf": "high",
                      "sub_conf": None, "evidence": None}})
    assert W.plan([cell("Creator Category", "Beauty")], d)[0].status == "INVALID"


# --- audience -----------------------------------------------------------------
def test_audience_gap_jadi_update_kolom_curated_di_baris_feature():
    items = W.plan([cell("Audience Age", "18-24"), cell("Audience City", "Jakarta"),
                    cell("Audience Country", "ID")], db())
    assert {i.status for i in items} == {"UPDATE"}
    (w,) = W.aud_writes(items)
    assert (w["age"], w["city"], w["country"], w["gender"]) == ("18-24", "Jakarta", "ID", None)
    assert w["table"] == "feature.ig_audience_analysis" and set(w["evidence"]) == {"age", "city", "country"}
    sql = W.SQL_AUD_UPDATE.format(table=w["table"])
    assert "COALESCE(curated_city" in sql and "DELETE" not in sql.upper() and "INSERT" not in sql.upper()


def test_update_audience_tidak_menyentuh_kolom_measurement():
    sql = W.SQL_AUD_UPDATE.lower()
    for col in ("gender_breakdown", "age_gender_breakdown", "geo_distribution", "female_pct", "male_pct",
                "interest_top", "updated_at"):
        assert col not in sql
    assert W.AUD_TABLE == {"instagram": "feature.ig_audience_analysis", "tiktok": "feature.tt_audience_analysis"}


def test_audience_measured_tidak_ditimpa_label():
    d = db(aud_state={"s1": {"gender": None, "age": None, "country": "ID", "city": None, "interest": "x"}})
    assert W.plan([cell("Audience Country", "ID", "EXISTING")], d)[0].status == "SKIP_SAME"
    assert W.plan([cell("Audience Country", "MY")], d)[0].status == "INVALID"


def test_audience_taxonomy_dan_idempoten():
    assert W.plan([cell("Audience Age", "18 - 24")], db())[0].status == "INVALID"
    assert W.plan([cell("Audience Country", "Indonesia")], db())[0].status == "INVALID"
    assert W.plan([cell("Audience City", "Atlantis")], db())[0].status == "INVALID"
    d = db(aud_curated={"s1": {"gender": None, "age": "18-24", "country": None, "city": None}})
    assert W.plan([cell("Audience Age", "18-24")], d)[0].status == "SKIP_SAME"


def test_interest_existing_skip_same():
    assert W.plan([cell("Audience Interest", "beauty", "EXISTING")], db())[0].status == "SKIP_SAME"


# --- umum -----------------------------------------------------------------------
def test_only_duplikat_dan_kol_asing():
    items = W.plan([cell("Creator Gender", "male"), cell("Creator Style", "content_style.review")], db(),
                   only={"Creator Gender"})
    assert [i.status for i in items] == ["UPDATE", "NOT_SELECTED"]
    items = W.plan([cell("Creator Style", "content_style.review")] * 2 + [cell("Creator Style", "x", kol="zz")], db())
    assert [i.status for i in items] == ["INSERT", "INVALID", "INVALID"]


def test_sql_tanpa_delete():
    for sql in (W.SQL_INSERT, W.SQL_GENDER, W.SQL_KD_CURATED, W.SQL_AUD_UPDATE):
        assert "DELETE" not in sql.upper()
    assert W.BLOCKED == {}
