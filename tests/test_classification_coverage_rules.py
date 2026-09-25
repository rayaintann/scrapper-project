"""Aturan coverage classifier (Sep 2026): Rule 2 (gender), Rule 3/3b (kategori),
detektor style per post, personality relatable. Tanpa DB.

Ground truth per post (dev 200 / held-out 97 / test 96) dan hasil evaluasinya ada di
laporan research audit, bukan di repo -- caption kreator tidak disalin ke test.
"""

from __future__ import annotations

import pytest

import creator_classification as C
import creator_classification_lexicon as L
import creator_gender_inference as G
from creator_classification import CreatorInput, Post
from tests.test_creator_classification import ATTRS, posts, taxonomy_rows


@pytest.fixture(scope="module")
def tax():
    return C.Taxonomy.from_rows(taxonomy_rows(), ATTRS)


def p(caption, *tags):
    return Post(caption=caption, hashtags=tuple(tags))


# --------------------------------------------------------------------------- Rule 3
def test_rule3_subkategori_terklasifikasi_menentukan_induk_canonical(tax):
    # 'lari pagi' / 'trail run' hanya ada di leksikon SUBKATEGORI Running, bukan leksikon kategori
    inp = CreatorInput("k", posts=posts("lari pagi keliling komplek", "trail run perdana di bogor",
                                        "OOTD", "weekend"))
    cat = C.classify_category(inp, tax)
    assert cat.value == "Fitness" and cat.source == C.SOURCE_SUBCATEGORY_TERMS
    assert cat.confidence == "medium"
    assert C.classify_subcategory(inp, cat, tax).value == "Running"


def test_rule3_subtopik_berbeda_tidak_dijumlahkan(tax):
    # 1 post kopi + 1 post masak = dua subkategori berbeda, masing-masing 1 post -> Unknown
    inp = CreatorInput("k", posts=posts("ngopi sore di cafe", "hari ini masak sayur", "weekend"))
    assert not C.classify_category(inp, tax).known


def test_rule3_tidak_memutus_konflik_bukti_langsung(tax):
    # Bukti langsung: Travel & Finance sama kuat (seri); subkategori unik menunjuk Food (Culinary Review).
    inp = CreatorInput("k", posts=posts("liburan seru", "liburan lagi", "keuangan keluarga",
                                        "finansial sehat", "review makanan enak", "tempat makan hits"))
    assert C.subcategory_parent(inp, tax).value == "FOD"
    cat = C.classify_category(inp, tax)
    assert not cat.known and "tetap Unknown" in cat.reason


def test_rule3_nama_tempat_tidak_menentukan_induk(tax):
    inp = CreatorInput("k", posts=posts("pulang ke jogja", "jogja selalu istimewa", "weekend"))
    assert not C.classify_category(inp, tax).known
    assert "jogja" in L.SUBCATEGORY_TERMS_NOT_FOR_PARENT


def test_rule3_dibatasi_pilihan_roster_bila_roster_multi(tax):
    inp = CreatorInput("k", roster_categories=("Beauty", "Lifestyle"),
                       posts=posts("moisturizer favorit", "jerawat mulai hilang", "OOTD"))
    cat = C.classify_category(inp, tax)
    assert cat.value == "Beauty" and cat.source == f"{C.SOURCE_ROSTER}+{C.SOURCE_SUBCATEGORY_TERMS}"


def test_istilah_ambigu_lintas_induk_dibuang(tax):
    amb = C._ambiguous_subcategory_terms(tax)
    for code, terms in L.SUBCATEGORY_LEXICON.items():
        parent = tax.rows[tax.by_code[code].parent_id].code
        for t in terms:
            others = {tax.rows[tax.by_code[c].parent_id].code for c, ts in L.SUBCATEGORY_LEXICON.items()
                      if t in ts} - {parent}
            assert (C._norm(t) in amb) == bool(others)


# --------------------------------------------------------------------------- Rule 3b
def test_rule3b_roster_saudara_mengisi_roster_kosong(tax):
    cat = C.classify_category(CreatorInput("k", sibling_roster_categories=("Entertainment",)), tax)
    assert cat.value == "Entertainment" and cat.source == C.SOURCE_ROSTER_SIBLING
    assert cat.confidence == "medium"


def test_rule3b_saudara_mempersempit_roster_multi_hanya_bila_termasuk(tax):
    ok = C.classify_category(CreatorInput("k", roster_categories=("Fashion", "Food", "Lifestyle"),
                                          sibling_roster_categories=("Fashion",)), tax)
    assert ok.value == "Fashion"
    no = C.classify_category(CreatorInput("k", roster_categories=("Fashion", "Food"),
                                          sibling_roster_categories=("Travel",)), tax)
    assert not no.known


def test_rule3b_saudara_multi_tidak_dipakai(tax):
    assert not C.classify_category(CreatorInput("k", sibling_roster_categories=("Beauty", "Lifestyle")), tax).known


def test_roster_sendiri_tetap_menang_atas_saudara(tax):
    cat = C.classify_category(CreatorInput("k", roster_categories=("Beauty",),
                                           sibling_roster_categories=("Fashion",)), tax)
    assert cat.value == "Beauty" and cat.source == C.SOURCE_ROSTER


# --------------------------------------------------------------------------- Rule 2
def test_rule2a_influencer_name_hanya_bila_nama_akun_tidak_menjawab():
    h = G.pilih_gender(None, "@@", "xx123", nama_roster="Siti Aminah")
    assert (h.nilai, h.source) == ("female", G.SUMBER_NAMA_ROSTER)
    # nama akun sudah menjawab -> influencer_name tidak dipakai
    h = G.pilih_gender(None, "Rina Putri", "rina", nama_roster="Muhammad Rizki")
    assert (h.nilai, h.source) == ("female", G.SUMBER_NAMA)


def test_rule2_tidak_menimpa_roster_gender():
    h = G.pilih_gender("0", None, None, nama_roster="Siti Aminah", bio="mom of 2")
    assert (h.nilai, h.source) == ("male", G.SUMBER_ROSTER)


def test_rule2_akun_bisnis_atau_grup_tetap_unknown():
    assert not G.pilih_gender(None, "Toko Kue Official", "tokokue", nama_roster="Siti Aminah").diketahui
    assert not G.pilih_gender(None, "Rina & Budi", "rinabudi", nama_roster="Siti Aminah").diketahui


def test_rule2b_bio_hanya_peran_eksplisit_bukan_kata_ganti():
    assert G.gender_dari_bio("Mom of 2 | beauty").nilai == "female"
    assert G.gender_dari_bio("proud dad & runner").nilai == "male"
    assert G.gender_dari_bio("love my wife").nilai == "male"        # pasangan -> arah sebaliknya
    assert G.gender_dari_bio("wifey vibes").nilai is None           # bukan frasa peran utuh
    assert not G.gender_dari_bio("he/him").diketahui
    assert not G.gender_dari_bio("she/her").diketahui
    assert not G.gender_dari_bio("mom of 2, husband of @x").diketahui   # bertentangan


def test_rule2_nama_roster_dan_bio_bertentangan_unknown():
    h = G.pilih_gender(None, "@@", "xx", nama_roster="Siti Aminah", bio="proud dad")
    assert not h.diketahui and "bertentangan" in h.alasan


# --------------------------------------------------------------------------- style per post
@pytest.mark.parametrize("caption,tags,expected", [
    ("Tutorial makeup natural: 1. primer\n2. foundation", (), "content_style.tutorial"),
    ("Honest review serum X, teksturnya ringan 8/10", (), "content_style.review"),
    ("a day in my life di Bandung", (), "content_style.vlog"),
    ("Kalian tim bibir matte atau juicy?", (), "communication_style.conversational"),
    ("rambut lagi kusut, pake ini jadi gampang diatur @dove.indonesia", (), "communication_style.testimonial"),
    ("Selamat hari kemerdekaan", (), None),
    ("", (), None),
])
def test_post_style_per_label(caption, tags, expected):
    assert C.post_style(p(caption, *tags)) == expected


def test_post_style_kredit_kru_bukan_brand():
    assert C.post_style(p("Our wedding day\nMUA @makeupbyx\nPhotographer: @fotoy")) is None


def test_post_style_bentuk_konten_di_atas_testimonial():
    cap = "Resep ayam kecap\nBahan: 300gr ayam\nMasaknya pake wajan dari @brand.id"
    assert C.post_style(p(cap)) == "content_style.tutorial"


def test_post_style_satu_kata_lepas_tidak_cukup():
    # 'cara' dalam arti umum dan 'lucu' bukan tutorial/comedy
    assert C.post_style(p("dengan cara ini aku bahagia")) is None
    assert C.post_style(p("koleksinya lucu lucu")) is None


def test_style_kreator_memakai_ambang_existing():
    tst = "my current fav serum @brand.id"
    inp = CreatorInput("k", posts=posts(tst, tst, "OOTD", "weekend", "hai", "sore"))
    s = C.classify_style(inp)
    assert s.value == "communication_style.testimonial" and "2/6" in s.reason
    inp = CreatorInput("k", posts=posts(tst, "OOTD", "weekend", "hai", "sore", "pagi", "malam"))
    assert not C.classify_style(inp).known           # 1 post < STYLE_MIN_HITS


def test_style_validate_menerima_conversational_dan_testimonial(tax):
    for key in ("communication_style.conversational", "communication_style.testimonial"):
        assert key not in L.STYLE_NOT_INFERABLE and key in tax.styles


# --------------------------------------------------------------------------- personality
def test_personality_relatable_dari_pola_percakapan_dan_keseharian():
    inp = CreatorInput("k", posts=posts("kalian tim mana nih?", "siapa yang pernah gini?",
                                        "a day in my life", "OOTD", "weekend"))
    pe = C.classify_personality(inp, C.Attribute(), C.Attribute())
    assert pe.value == "creator_personality.relatable" and "bukan fakta psikologis" in pe.reason


def test_personality_testimonial_bukan_kepribadian():
    tst = "my current fav serum @brand.id"
    inp = CreatorInput("k", posts=posts(*[tst] * 5))
    assert not C.classify_personality(inp, C.Attribute(), C.Attribute()).known


def test_ambang_style_personality_tidak_berubah():
    assert (C.STYLE_MIN_POSTS, C.STYLE_MIN_HITS, C.STYLE_MIN_RATIO) == (3, 2, 0.3)
    assert (C.PERSONALITY_MIN_POSTS, C.PERSONALITY_MIN_HITS, C.PERSONALITY_MIN_RATIO) == (5, 3, 0.4)
    assert (C.MIN_SCORE, C.MIN_MARGIN) == (2.0, 1.0)


def test_style_seri_bentuk_konten_vs_testimonial_pilih_bentuk_konten():
    tut = "Resep ayam kecap\nBahan: ayam"
    tst = "my current fav serum @brand.id"
    s = C.classify_style(CreatorInput("k", posts=posts(tut, tut, tst, tst, "hai")))
    assert s.value == "content_style.tutorial" and "seri dengan testimonial" in s.reason


def test_style_seri_dua_bentuk_konten_tetap_unknown():
    tut = "Resep ayam kecap\nBahan: ayam"
    rev = "honest review serum 8/10"
    assert not C.classify_style(CreatorInput("k", posts=posts(tut, tut, rev, rev, "hai"))).known


def test_sumber_gender_produksi_sesuai_constraint_db():
    # ck_kpc_creator_gender_source: manual / roster / name_inference
    allowed = {"manual", "roster", "name_inference"}
    assert {G.SUMBER_MANUAL, G.SUMBER_ROSTER, G.SUMBER_NAMA, G.SUMBER_NAMA_ROSTER} <= allowed
    h = G.pilih_gender(None, "@@", "xx123", nama_roster="Siti Aminah")
    assert h.source in allowed and "influencer_name" in h.alasan


# ------------------------------------------------------ kredit kru bukan bukti kategori
def test_kredit_mua_bukan_bukti_beauty(tax):
    # "make up by @x" = kredit kru di foto acara, bukan konten beauty (rayanurfitrird, riaricis1795)
    inp = CreatorInput("k", posts=posts("kondangan season ✨ make up by @nakku.mua",
                                        "wisuda hari ini! makeup by @mua.jkt", "weekend di rumah"))
    assert not C.classify_category(inp, tax).known


def test_konten_makeup_tetap_bukti_beauty(tax):
    inp = CreatorInput("k", posts=posts("tutorial makeup natural buat wisuda",
                                        "makeup look sehari-hari pake cushion", "weekend"))
    cat = C.classify_category(inp, tax)
    assert cat.value == "Beauty"
    assert C.classify_subcategory(inp, cat, tax).value == "Makeup"


def test_kredit_mua_dengan_nama_sebelum_handle(tax):
    inp = CreatorInput("k", posts=posts("kondangan ✨ Make up by nakku @cipampaa___",
                                        "wisuda! makeup by kak rina @rina.mua", "weekend"))
    assert not C.classify_category(inp, tax).known
