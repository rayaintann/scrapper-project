"""Test Audience Classification -- pembaca Audience Analysis existing, tanpa DB."""

from __future__ import annotations

import audience_classification as A
from audience_classification import AudienceInput
from creator_classification import Attribute


def inp(**kw):
    return AudienceInput(platform="instagram", has_data=True, **kw)


def test_tanpa_feature_audience_semua_unknown():
    res = A.classify(AudienceInput())
    assert all(not res[a].known for a in A.AUDIENCE_ATTRS)
    assert A.validate(res) == []


def test_output_hanya_lima_atribut_audiens():
    assert set(A.classify(AudienceInput())) == {"gender", "age", "city", "country", "interest"}


def test_gender_dari_female_male_pct_existing():
    g = A.classify_gender(inp(female_pct=71.79, male_pct=28.21, gender_known_pct=39.0,
                              gender_counts={"female": 28, "male": 11}, gender_reliability="Low"))
    assert (g.value, g.confidence) == ("female", "low")
    assert g.source == A.SRC_GENDER
    assert {e.label for e in g.evidence} == {"female_pct", "male_pct", "gender_known_pct"}


def test_gender_seimbang_adalah_nilai_balanced_bukan_unknown():
    g = A.classify_gender(inp(female_pct=45.0, male_pct=55.0, gender_known_pct=20.0,
                              gender_counts={"female": 9, "male": 11}))
    assert g.known and g.value == A.BALANCED and "seimbang" in g.reason
    assert any(e.label == "female_pct" and e.detail == "45" for e in g.evidence)


def test_gender_50_50_balanced():
    g = A.classify_gender(inp(female_pct=50.0, male_pct=50.0, gender_counts={"female": 5, "male": 5}))
    assert g.value == A.BALANCED


def test_gender_ambang_tetap_60_dan_5():
    assert A.GENDER_SHARE_MIN == 60.0 and A.MIN_KNOWN == 5
    # tepat 60% = mayoritas, bukan balanced
    g = A.classify_gender(inp(female_pct=60.0, male_pct=40.0, gender_counts={"female": 6, "male": 4}))
    assert g.value == "female"
    # seimbang tapi < MIN_KNOWN diketahui: tetap Unknown (tidak ada bukti cukup)
    g = A.classify_gender(inp(female_pct=50.0, male_pct=50.0, gender_counts={"female": 2, "male": 2}))
    assert not g.known and "< 5" in g.reason


def test_gender_tanpa_pct_unknown():
    assert not A.classify_gender(inp(gender_counts={"female": 3})).known


def test_age_top_existing_dari_satu_follower_tetap_unknown():
    a = A.classify_age(inp(age_counts={"18-24": 1}, age_top="18-24"))
    assert not a.known and "< 5" in a.reason
    assert "18-24" in a.evidence[0].detail          # nilai existing tetap terlihat, tidak dibuang


def test_age_cukup_bukti():
    a = A.classify_age(inp(age_counts={"18-24": 6, "25-34": 2}, age_top="18-24",
                           age_confidence={"18-24": "inferred_high"}))
    assert (a.value, a.confidence) == ("18-24", "high")


def test_country_dari_l2_geo_dengan_confidence_l2():
    c = A.classify_country(inp(country={"ID": (12, "inferred_high"), "IT": (1, "inferred_low"),
                                        "unknown": (86, "inferred_high")}))
    assert (c.value, c.confidence, c.source) == ("ID", "high", "l2_gold.audience_geo_daily[country]")


def test_city_tersebar_tipis_unknown():
    c = A.classify_city(inp(city={"Bali": (2, "inferred_high"), "Kediri": (1, "inferred_high"),
                                  "Surabaya": (1, "inferred_medium")}))
    assert not c.known


def test_geo_seri_unknown():
    assert not A.classify_city(inp(city={"Bandung": (3, "inferred_high"), "Bogor": (3, "inferred_high")})).known


def test_interest_mengikuti_interest_top_existing_apa_adanya():
    i = A.classify_interest(inp(interest_top="religion", interest_source="audience"))
    assert (i.value, i.source) == ("religion", "feature.audience_analysis.interest_top:audience")
    fb = A.classify_interest(inp(interest_top="beauty", interest_source="content_inferred"))
    assert fb.value == "beauty" and fb.source.endswith(":content_inferred") and fb.confidence == "low"


def test_interest_kosong_unknown():
    assert not A.classify_interest(inp()).known


def test_tidak_ada_kosakata_interest_kedua():
    assert not hasattr(A, "INTEREST_SEGMENTS") and not hasattr(A, "INTEREST_TO_SEGMENT")


def test_validate_menolak_nilai_tidak_sah():
    bad = {a: Attribute() for a in A.AUDIENCE_ATTRS}
    bad["country"] = Attribute("Indonesia", A.SRC_GEO, "low")
    bad["age"] = Attribute("45-54", A.SRC_AGE, "low")
    bad["interest"] = Attribute("food", "x:llm", "low")
    assert len(A.validate(bad)) == 3


def test_tidak_ada_input_kreator_di_audience_input():
    fields = set(AudienceInput.__dataclass_fields__)
    assert not fields & {"bio", "username", "display_name", "creator_city", "category", "creator_gender",
                         "creator_age", "declared_category", "language"}


def test_modul_tidak_menulis_ke_db():
    import inspect
    src = inspect.getsource(A)
    for w in ("INSERT", "UPDATE ", "DELETE", "ALTER"):
        assert w not in src.upper().replace("UPDATED_AT", ""), w


# --- migration 054: label kurasi hanya fallback --------------------------------------
def test_label_kurasi_mengisi_unknown_saja():
    inp = A.AudienceInput(has_data=True, country={"ID": (9, "inferred_high")},
                          curated={"country": ("MY", "low"), "age": ("18-24", "low"), "city": ("Jakarta", "medium")})
    r = A.classify(inp)
    assert r["country"].value == "ID" and r["country"].source != A.SRC_CURATED       # measured/inferred menang
    assert (r["age"].value, r["age"].source, r["age"].confidence) == ("18-24", A.SRC_CURATED, "low")
    assert (r["city"].value, r["city"].confidence) == ("Jakarta", "medium")
    assert A.validate(r) == []


def test_akun_tanpa_feature_dengan_label_kurasi():
    r = A.classify(A.AudienceInput(has_data=False, curated={"gender": ("female", "low")}))
    assert r["gender"].value == "female" and not r["age"].known
