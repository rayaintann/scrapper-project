"""Creator Classification -- offline, tanpa database, tanpa jaringan.

Taxonomy di sini meniru baris `public.kol_categories` apa adanya: id UUID,
nama DB, kode, level, dan `parent_id` (relasi induk-anak dari parent_id, BUKAN
dari prefix kode). Juga beberapa label legacy dan segmen audiens yang ada di DB.
"""

import uuid

import pytest

import creator_classification as C
import creator_classification_lexicon as L
from creator_classification import CreatorInput, Post

TAHUN = 2026

#: 14 kategori canonical, nama persis seperti di DB `kol`.
CATEGORIES = {"BEA": "Beauty", "ENT": "Entertainment", "FAS": "Fashion", "FIT": "Fitness",
              "FOD": "Food", "LIF": "Lifestyle", "TRV": "Travel", "GAM": "Gaming",
              "AUT": "Automotive", "EDU": "Education", "FIN": "Finance", "HNL": "Home & Living",
              "PAR": "Parenting", "TEC": "Tech"}
#: 42 subkategori: kode -> (nama DB, kode induk).
SUBCATEGORIES = {
    "BEA.HAR": ("Haircare", "BEA"), "BEA.MKP": ("Makeup", "BEA"), "BEA.SKN": ("Skincare", "BEA"),
    "ENT.COM": ("Comedy", "ENT"), "ENT.FLM": ("Film & Series", "ENT"), "ENT.MUS": ("Music", "ENT"),
    "FAS.HJB": ("Hijab Fashion", "FAS"), "FAS.LOC": ("Local Brand", "FAS"), "FAS.STR": ("Streetwear", "FAS"),
    "FIT.GYM": ("Gym & Strength", "FIT"), "FIT.HOM": ("Home Workout", "FIT"), "FIT.RUN": ("Running", "FIT"),
    "FOD.BEV": ("Coffee & Beverage", "FOD"), "FOD.CUL": ("Culinary Review", "FOD"),
    "FOD.HCK": ("Home Cooking", "FOD"),
    "GAM.ESP": ("Esports", "GAM"), "GAM.MOB": ("Mobile Gaming", "GAM"), "GAM.PCC": ("PC & Console", "GAM"),
    "LIF.MIN": ("Minimalism", "LIF"), "LIF.SLF": ("Self Improvement", "LIF"), "LIF.VLG": ("Daily Vlog", "LIF"),
    "TRV.BGT": ("Budget Travel", "TRV"), "TRV.DOM": ("Domestic Travel", "TRV"),
    "TRV.STY": ("Staycation & Hotel", "TRV"),
    "AUT.CAR": ("Car Review", "AUT"), "AUT.MOD": ("Modification & Aftermarket", "AUT"),
    "AUT.MTR": ("Motorcycle", "AUT"),
    "EDU.CAR": ("Career", "EDU"), "EDU.LNG": ("Language", "EDU"), "EDU.STU": ("Study Tips", "EDU"),
    "FIN.BIZ": ("Business", "FIN"), "FIN.INV": ("Investing", "FIN"), "FIN.PFN": ("Personal Finance", "FIN"),
    "HNL.IMP": ("Home Improvement", "HNL"), "HNL.INT": ("Interior", "HNL"),
    "HNL.ORG": ("Home Organization", "HNL"),
    "PAR.KID": ("Kids & Family", "PAR"), "PAR.MOM": ("Momlife", "PAR"),
    "PAR.PRG": ("Pregnancy & Newborn", "PAR"),
    "TEC.AIP": ("AI & Productivity", "TEC"), "TEC.GDG": ("Gadget Review", "TEC"),
    "TEC.SAAS": ("Software & SaaS", "TEC"),
}
#: Baris legacy / segmen audiens (level='category', tanpa kode) yang ada di DB.
LEGACY = ("Foodies", "Cooking", "Dance", "Sports", "Home Decor", "Medical", "Animal Lovers",
          "Gen Z", "Moms")
STYLES = [
    "communication_style.educational", "communication_style.storytelling",
    "communication_style.demonstrative", "communication_style.conversational",
    "communication_style.data_driven", "communication_style.visual_first",
    "communication_style.humorous", "communication_style.testimonial",
    "communication_style.demonstration", "content_style.educational", "content_style.tutorial",
    "content_style.review", "content_style.storytelling", "content_style.aesthetic",
    "content_style.entertaining", "content_style.vlog", "content_style.talking_head",
    "content_style.demo", "content_style.comedy", "content_style.commentary",
    "visual_style.aesthetic", "visual_style.casual", "visual_style.professional",
    "visual_style.cinematic", "visual_style.colorful", "visual_style.lifestyle",
    "visual_style.minimalist"]
PERSONALITIES = [f"creator_personality.{k}" for k in (
    "professional", "educational", "relatable", "casual", "entertaining", "humorous",
    "inspirational", "creative", "tech_savvy", "reviewer", "premium", "luxury", "expert")]


def uid(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"kol_categories/{key}"))


def taxonomy_rows():
    rows = [(uid(code), name, code, "category", None) for code, name in CATEGORIES.items()]
    rows += [(uid(code), name, code, "sub_category", uid(parent))
             for code, (name, parent) in SUBCATEGORIES.items()]
    rows += [(uid(name), name, None, "category", None) for name in LEGACY]
    return rows


ATTRS = [("style", k) for k in STYLES] + [("personality", k) for k in PERSONALITIES]


@pytest.fixture(scope="module")
def tax():
    return C.Taxonomy.from_rows(taxonomy_rows(), ATTRS)


def posts(*captions, tags=()):
    return tuple(Post(caption=c, hashtags=tuple(tags)) for c in captions)


def cat_of(inp, tax):
    return C.classify_category(inp, tax)


# --------------------------------------------------------------------------- taxonomy
def test_taxonomy_menolak_leksikon_yang_menunjuk_baris_tidak_ada():
    with pytest.raises(ValueError, match="tidak ada di taxonomy"):
        C.Taxonomy.from_rows([(uid("BEA"), "Beauty", "BEA", "category", None)], [])


def test_taxonomy_menolak_subkategori_yang_induknya_bukan_canonical():
    rows = [r for r in taxonomy_rows() if r[2] != "FOD.CUL"]
    rows.append((uid("FOD.CUL"), "Culinary Review", "FOD.CUL", "sub_category", uid("Foodies")))
    with pytest.raises(ValueError, match="subcategory-parent:FOD.CUL"):
        C.Taxonomy.from_rows(rows, ATTRS)


def test_taxonomy_hanya_14_canonical_dan_label_legacy_bukan_target(tax):
    assert set(L.CATEGORY_TARGETS) == set(CATEGORIES)
    for name in ("Medical", "Animal Lovers", "Foodies", "Gen Z", "Moms"):
        assert tax.category_by_name[name].code not in L.CATEGORY_TARGETS


def test_children_dari_parent_id_bukan_prefix_kode(tax):
    food = tax.category("FOD")
    assert [c.name for c in tax.children(food.id)] == ["Coffee & Beverage", "Culinary Review",
                                                       "Home Cooking"]
    assert all(c.parent_id == food.id for c in tax.children(food.id))


def test_taxonomy_27_style_13_personality(tax):
    assert len(tax.styles) == 27 and len(tax.personalities) == 13
    assert set(L.STYLE_CUES) <= tax.styles
    assert not set(L.STYLE_CUES) & L.STYLE_NOT_INFERABLE


# --------------------------------------------------------------------------- gender
def test_gender_roster_menang_atas_inference():
    g = C.classify_gender(CreatorInput("k", roster_gender="1", display_name="Andi Pratama"))
    assert (g.value, g.source, g.confidence) == ("female", "roster", "medium")


def test_gender_manual_tidak_pernah_ditimpa():
    g = C.classify_gender(CreatorInput("k", manual_gender="male", roster_gender="1"))
    assert (g.value, g.source) == ("male", "manual")


def test_gender_inference_hanya_mengisi_yang_kosong():
    g = C.classify_gender(CreatorInput("k", display_name="Rina Putri", username="rinaputri"))
    assert g.value == "female" and g.source == "name_inference"


def test_gender_tanpa_sinyal_unknown():
    g = C.classify_gender(CreatorInput("k", username="xyz_123"))
    assert not g.known and g.reason


# --------------------------------------------------------------------------- age
def test_age_bio_self_declared():
    a = C.classify_age(CreatorInput("k", bio="umur 24"), TAHUN)
    assert a.value == "24" and a.source == "bio_self_declared"


def test_age_nik_hanya_kalau_bio_diam_dan_nomornya_tidak_bocor():
    nik = "3201011505900001"
    a = C.classify_age(CreatorInput("k", bio="beauty creator", nik=nik), TAHUN)
    assert a.known and a.source == "roster_ktp"
    assert all(nik not in (e.detail + e.label) for e in a.evidence) and nik not in a.reason


def test_age_tanpa_bukti_unknown():
    assert not C.classify_age(CreatorInput("k", bio="mahasiswa, suka jalan jalan"), TAHUN).known


# --------------------------------------------------------------------------- category
def test_category_objek_kol_categories(tax):
    c = cat_of(CreatorInput("k", bio="Beauty enthusiast | skincare & makeup"), tax)
    assert c.ref.as_dict() == {"id": uid("BEA"), "name": "Beauty", "code": "BEA"}
    assert c.value == "Beauty" and c.source == "inference" and c.confidence == "medium"


def test_category_declared_plus_bio_high(tax):
    c = cat_of(CreatorInput("k", declared_category="Beauty, cosmetic & personal care",
                            bio="skincare review"), tax)
    assert c.ref.code == "BEA" and c.confidence == "high"


def test_category_username_saja_unknown(tax):
    c = cat_of(CreatorInput("k", username="skincare_makeup_beauty", display_name="Beauty Skincare"), tax)
    assert not c.known and c.ref is None


def test_category_bukti_bertentangan_unknown_dengan_nama_db(tax):
    c = cat_of(CreatorInput("k", bio="skincare lover dan food vlogger"), tax)
    assert not c.known and "bertentangan" in c.reason
    assert "Beauty" in c.reason and "Food" in c.reason and "BEA" not in c.reason


def test_category_roster_legacy_dipetakan_ke_canonical(tax):
    c = cat_of(CreatorInput("k", roster_categories=("Foodies",), bio="skincare & makeup artist"), tax)
    assert c.ref.code == "FOD" and c.value == "Food" and c.source == "roster" and "konflik" in c.reason


def test_category_roster_canonical_dikenali_dari_kode_db(tax):
    c = cat_of(CreatorInput("k", roster_categories=("Beauty",)), tax)
    assert c.ref.id == uid("BEA") and c.source == "roster"


def test_category_segmen_audiens_dan_unmapped_tidak_jadi_kategori(tax):
    c = cat_of(CreatorInput("k", roster_categories=("Moms", "Gen Z")), tax)
    assert not c.known and "segmen audiens" in c.reason
    m = cat_of(CreatorInput("k", roster_categories=("Medical",), bio="dokter kulit"), tax)
    assert not m.known and "tidak ada padanan canonical" in m.reason
    p = cat_of(CreatorInput("k", roster_categories=("Moms",), bio="momlife | parenting tips"), tax)
    assert p.ref.code == "PAR" and p.value == "Parenting" and p.source == "inference"


def test_category_roster_ganda_dipilih_bukti(tax):
    c = cat_of(CreatorInput("k", roster_categories=("Beauty", "Fashion"),
                            bio="makeup artist & skincare"), tax)
    assert c.ref.code == "BEA" and c.source.startswith("roster")


def test_category_hashtag_saja_tidak_cukup(tax):
    assert not cat_of(CreatorInput("k", posts=posts("", "", tags=("#skincareroutine",))), tax).known


def test_category_post_berulang(tax):
    assert cat_of(CreatorInput("k", posts=posts("resep ayam bakar", "resep kue coklat")), tax).ref.code == "FOD"


# --------------------------------------------------------------------------- subcategory
def test_category_dan_subcategory_field_berbeda(tax):
    inp = CreatorInput("k", bio="beauty creator, skincare routine & sunscreen review, running pagi")
    res = C.classify(inp, tax, TAHUN)
    cat, sub = res["category"], res["subcategory"]
    assert cat is not sub and cat.ref.id != sub.ref.id
    assert cat.ref.as_dict() == {"id": uid("BEA"), "name": "Beauty", "code": "BEA"}
    assert sub.ref.as_dict() == {"id": uid("BEA.SKN"), "name": "Skincare", "code": "BEA.SKN"}


def test_subcategory_nama_db_bukan_kode_dan_parent_id(tax):
    inp = CreatorInput("k", roster_categories=("Food",), bio="food vlogger | review kuliner jakarta",
                       posts=posts("review kuliner bakso", "kulineran di blok m"))
    cat = cat_of(inp, tax)
    sub = C.classify_subcategory(inp, cat, tax)
    assert sub.ref.code == "FOD.CUL" and sub.value == "Culinary Review" and sub.ref.name == "Culinary Review"
    assert sub.value != sub.ref.code and sub.ref.id is not None
    assert sub.ref.parent_id == cat.ref.id and tax.rows[sub.ref.id] == sub.ref


def test_subcategory_hanya_dari_anak_kategori_terpilih(tax):
    inp = CreatorInput("k", roster_categories=("Beauty",), bio="marathon runner, half marathon, fun run")
    cat = cat_of(inp, tax)
    sub = C.classify_subcategory(inp, cat, tax)
    assert cat.ref.code == "BEA"
    assert sub.ref is None or sub.ref.parent_id == cat.ref.id


def test_subcategory_none_valid_kalau_bukti_kurang(tax):
    # "foodie" dan "chef" menunjuk kategori Food, tapi tidak ada di leksikon
    # subkategori Food mana pun -> subcategory None.
    inp = CreatorInput("k", bio="foodie sejati | chef rumahan")
    res = C.classify(inp, tax, TAHUN)
    assert res["category"].ref.code == "FOD"
    assert res["subcategory"].ref is None and not res["subcategory"].known
    assert C.validate(res, tax) == []


def test_subcategory_unknown_kalau_kategori_unknown(tax):
    assert not C.classify_subcategory(CreatorInput("k"), C.Attribute(), tax).known


# --------------------------------------------------------------------------- style
def test_style_dari_pola_caption():
    s = C.classify_style(CreatorInput("k", posts=posts(
        "honest review serum baru", "review sunscreen", "review cushion lokal", "OOTD hari ini",
        "weekend santai")))
    assert s.value == "content_style.review"


def test_style_data_sedikit_unknown():
    assert not C.classify_style(CreatorInput("k", posts=posts("review serum", "review toner"))).known


def test_style_seri_unknown():
    s = C.classify_style(CreatorInput("k", posts=posts(
        "tutorial makeup", "tutorial hijab", "review serum", "review toner")))
    assert not s.known and "seri" in s.reason


def test_style_tidak_pernah_label_visual():
    assert not C.classify_style(CreatorInput("k", posts=posts("aesthetic", "cinematic", "aesthetic vibes"))).known


# --------------------------------------------------------------------------- personality
def test_personality_dari_pola_konsisten():
    p = C.classify_personality(CreatorInput("k", posts=posts(
        "tips skincare pagi", "tips memilih sunscreen", "fakta tentang retinol",
        "tips double cleansing", "OOTD", "weekend")), C.Attribute(), C.Attribute())
    assert p.value == "creator_personality.educational" and p.confidence == "medium"


def test_personality_expert_butuh_peran_professional():
    inp = CreatorInput("k", posts=posts("tips kesehatan kulit", "fakta tentang jerawat",
                                        "tips memilih sunscreen", "edukasi skincare", "OOTD", "weekend"))
    prof = C.Attribute(L.ROLE_PROFESSIONAL, "inference", "medium")
    assert C.classify_personality(inp, prof, C.Attribute()).value == "creator_personality.expert"
    assert C.classify_personality(inp, C.Attribute(), C.Attribute()).value == "creator_personality.educational"


def test_personality_tech_savvy_dari_kode_kategori(tax):
    inp = CreatorInput("k", posts=posts(*["review gadget smartphone baru"] * 3,
                                        *["update fitur aplikasi terbaru"] * 3))
    tech = cat_of(CreatorInput("k", roster_categories=("Tech",)), tax)
    p = C.classify_personality(inp, C.Attribute(), tech)
    assert any(e.label == "creator_personality.tech_savvy" for e in p.evidence)


def test_personality_satu_caption_atau_nama_tidak_cukup():
    p = C.classify_personality(CreatorInput("k", username="the_reviewer", posts=posts("review serum")),
                               C.Attribute(), C.Attribute())
    assert not p.known


def test_personality_tidak_pernah_premium_atau_luxury():
    p = C.classify_personality(CreatorInput("k", posts=posts(*["premium luxury lifestyle"] * 6)),
                               C.Attribute(), C.Attribute())
    assert p.value not in ("creator_personality.premium", "creator_personality.luxury")


# --------------------------------------------------------------------------- role
def test_role_media_dari_declared_category():
    assert C.classify_role(CreatorInput("k", declared_category="Media/news company")).value == L.ROLE_MEDIA


def test_role_pejabat_publik_hanya_peran_yang_terlihat():
    r = C.classify_role(CreatorInput("k", bio="Anggota DPR RI periode 2024-2029"))
    assert r.value == L.ROLE_PUBLIC_OFFICIAL and r.ref is None


def test_role_public_figure_bukan_politisi():
    assert C.classify_role(CreatorInput("k", declared_category="Public figure")).value == L.ROLE_CREATOR


def test_role_profesional_lebih_spesifik_dari_creator():
    assert C.classify_role(CreatorInput("k", bio="dokter | content creator kesehatan")).value == L.ROLE_PROFESSIONAL


def test_role_bertentangan_unknown():
    r = C.classify_role(CreatorInput("k", declared_category="Digital creator",
                                     bio="official store | order via wa", is_business=True))
    assert not r.known and "bertentangan" in r.reason


def test_role_username_saja_unknown():
    assert not C.classify_role(CreatorInput("k", username="official_store_id", display_name="Official Store")).known


# --------------------------------------------------------------------------- validate
def test_validate_hasil_lengkap_valid(tax):
    inp = CreatorInput("k", declared_category="Beauty, cosmetic & personal care",
                       bio="beauty creator | skincare | for endorsement dm",
                       roster_gender="1", posts=posts(
                           "review serum", "review toner", "review sunscreen",
                           "tips skincare", "review moisturizer", "review masker"))
    res = C.classify(inp, tax, TAHUN)
    assert C.validate(res, tax) == []
    assert res["category"].ref.code == "BEA" and res["subcategory"].ref.code == "BEA.SKN"
    assert res["subcategory"].value == "Skincare"
    assert res["style"].value == "content_style.review"


def _res(cat=None, sub=None, **kw):
    base = {k: C.Attribute() for k in ("style", "personality", "role")}
    base.update(kw)
    return {"category": cat or C.Attribute(), "subcategory": sub or C.Attribute(), **base}


def test_validate_menolak_subkategori_dengan_parent_lain(tax):
    beauty, run = tax.category("BEA"), tax.by_code["FIT.RUN"]
    v = C.validate(_res(C.Attribute(beauty.name, ref=beauty), C.Attribute(run.name, ref=run)), tax)
    assert any("bukan anak (parent_id)" in x for x in v)


def test_validate_menolak_kategori_legacy_dan_segmen(tax):
    for name in ("Foodies", "Moms"):
        r = tax.category_by_name[name]
        assert any("bukan kategori canonical" in x for x in C.validate(_res(C.Attribute(r.name, ref=r)), tax))


def test_validate_menolak_nama_berbentuk_kode_dan_id_asing(tax):
    cul = tax.by_code["FOD.CUL"]
    food = tax.category("FOD")
    v = C.validate(_res(C.Attribute(food.name, ref=food), C.Attribute("FOD.CUL", ref=cul)), tax)
    assert any("nama berbentuk kode" in x for x in v) and any("bukan nama DB" in x for x in v)
    fake = C.TaxRef("00000000-0000-0000-0000-000000000000", "Food", "FOD", "category", None)
    assert any("tidak ter-resolve" in x for x in C.validate(_res(C.Attribute("Food", ref=fake)), tax))


def test_validate_menolak_style_personality_role_di_luar_taxonomy(tax):
    v = C.validate(_res(style=C.Attribute("visual_style.cinematic"),
                        personality=C.Attribute("creator_personality.luxury"),
                        role=C.Attribute("Voter")), tax)
    assert len(v) == 3


def test_deterministik(tax):
    inp = CreatorInput("k", bio="food vlogger | kuliner jakarta", posts=posts("review bakso", "review mie"))
    assert C.classify(inp, tax, TAHUN) == C.classify(inp, tax, TAHUN)
