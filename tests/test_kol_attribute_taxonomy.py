"""Taxonomy Style & Personality — modul, migration, Excel, dan prototype.

Empat hal dijaga:

    1. Modul konsisten sendiri: kunci unik, label boleh berulang antar-grup.
    2. Migration 045 memuat persis apa yang ada di modul.
    3. Seluruh nilai Excel sisi KOL ter-cover.
    4. Seluruh nilai prototype (dna/comm/vis) ter-cover.

Test yang menyentuh Excel dan prototype akan `skip` kalau filenya tidak ada,
supaya suite tetap jalan di lingkungan tanpa `docs/` dan `app/`.
"""

import re
from pathlib import Path

import pytest

import kol_attribute_taxonomy as t

AKAR = Path(__file__).resolve().parents[1]
MIGRATION = AKAR / "migrations" / "045_kol_attribute_taxonomy.sql"
EXCEL = AKAR / "docs" / "brand_style_personality.xlsx"
PROTOTYPE = AKAR / "app" / "AUTOME_2.html"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# ===========================================================================
# 1. KONSISTENSI MODUL
# ===========================================================================

def test_jumlah_per_grup():
    assert t.ringkasan() == {
        "content_style": 11,
        "communication_style": 9,
        "creator_personality": 13,
        "visual_style": 7,
        "TOTAL": 40,
    }


def test_kunci_unik_tidak_ada_duplikat():
    kunci = [(r["kind"], r["attribute_group"], r["attribute_key"])
             for r in t.TAXONOMY]
    assert len(kunci) == len(set(kunci))


def test_label_sama_boleh_hidup_di_beberapa_grup():
    """`Educational` punya arti berbeda di tiap sumbu; melebur ketiganya
    akan menghilangkan perbedaan itu."""
    grup = sorted(r["attribute_group"] for r in t.TAXONOMY
                  if r["label"] == "Educational")
    assert grup == ["communication_style", "content_style",
                    "creator_personality"]


@pytest.mark.parametrize("label,jumlah", [
    ("Educational", 3), ("Storytelling", 2), ("Entertaining", 2),
    ("Humorous", 2), ("Aesthetic", 2), ("Casual", 2), ("Professional", 2),
])
def test_label_lintas_grup_jumlahnya_benar(label, jumlah):
    assert sum(1 for r in t.TAXONOMY if r["label"] == label) == jumlah


def test_attribute_key_selalu_diawali_nama_grup():
    for r in t.TAXONOMY:
        assert r["attribute_key"].startswith(r["attribute_group"] + ".")


def test_kind_hanya_style_atau_personality():
    assert {r["kind"] for r in t.TAXONOMY} == {"style", "personality"}


def test_source_origin_hanya_tiga_nilai_sah():
    assert {r["source_origin"] for r in t.TAXONOMY} <= {
        "excel", "ui", "excel+ui"}


def test_brand_personality_dan_brand_tone_tidak_ikut():
    """Keduanya atribut brand, bukan KOL."""
    grup = {r["attribute_group"] for r in t.TAXONOMY}
    assert "brand_personality" not in grup
    assert "brand_tone" not in grup
    # nilai yang khas brand-side juga tidak boleh menyelinap
    label = {r["label"] for r in t.TAXONOMY}
    for khas_brand in ("Innovative", "Friendly", "Authentic", "Bold",
                       "Caring", "Modern", "Formal", "Informative", "Warm",
                       "Aspirational", "Inspiring", "Straightforward"):
        assert khas_brand not in label


def test_alias_demonstration_dicatat_bukan_digabung():
    """Demonstration (UI) / Demonstrative (Excel) / Demo (Excel) tetap
    terpisah sampai Product memutuskan."""
    label = {(r["attribute_group"], r["label"]) for r in t.TAXONOMY}
    assert ("communication_style", "Demonstration") in label
    assert ("communication_style", "Demonstrative") in label
    assert ("content_style", "Demo") in label
    assert "communication_style.demonstration" in t.ALIAS_BELUM_DIPUTUSKAN


# ===========================================================================
# 2. MIGRATION 045 SEPADAN DENGAN MODUL
# ===========================================================================

def test_migration_ada():
    assert MIGRATION.exists()


def test_migration_memuat_semua_baris_taxonomy():
    sql = MIGRATION.read_text(encoding="utf-8")
    for r in t.TAXONOMY:
        potongan = (f"('{r['kind']}', '{r['attribute_group']}', "
                    f"'{r['attribute_key']}', '{r['label']}', "
                    f"'{r['source_origin']}', {r['sort_order']})")
        assert potongan in sql, f"hilang dari migration: {potongan}"


def test_migration_verifikasi_jumlah_sesuai_ringkasan():
    sql = MIGRATION.read_text(encoding="utf-8")
    ring = t.ringkasan()
    assert f"n <> {ring['TOTAL']} THEN" in sql
    for grup in ("content_style", "communication_style",
                 "creator_personality", "visual_style"):
        assert f"attribute_group = '{grup}'" in sql
        assert f"n <> {ring[grup]} THEN" in sql


def test_migration_punya_unique_dan_fk_yang_diperlukan():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "UNIQUE (kind, attribute_group, attribute_key)" in sql
    assert "UNIQUE (kol_directory_id, kol_attribute_id)" in sql
    assert "REFERENCES public.kol_directory(id)" in sql
    assert "REFERENCES public.kol_attribute(id)" in sql
    assert "CREATE INDEX IF NOT EXISTS ix_kol_attribute_map_directory" in sql


def test_migration_tidak_destruktif():
    sql = MIGRATION.read_text(encoding="utf-8").upper()
    for terlarang in ("DROP TABLE", "DROP COLUMN", "TRUNCATE",
                      "DELETE FROM", "ALTER TABLE L2_GOLD"):
        assert terlarang not in sql


def test_migration_tidak_menyentuh_kol_profile_card():
    """Larangan calculated metric di kartu L2 tetap berlaku."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ALTER TABLE l2_gold.kol_profile_card" not in sql
    # yang ada hanya blok verifikasi yang MEMASTIKAN kolomnya tidak muncul
    assert "Kolom terlarang muncul di kol_profile_card" in sql


def test_migration_seed_idempoten():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ON CONFLICT (kind, attribute_group, attribute_key) DO NOTHING" in sql


# ===========================================================================
# 3. CAKUPAN EXCEL
# ===========================================================================

def _excel_kol_side():
    openpyxl = pytest.importorskip("openpyxl")
    if not EXCEL.exists():
        pytest.skip("docs/brand_style_personality.xlsx tidak ada")
    wb = openpyxl.load_workbook(EXCEL, data_only=True, read_only=True)
    nilai = {"style": set(), "personality": set()}
    for sheet, kind in (("Style List", "style"),
                        ("Personality List", "personality")):
        for row in wb[sheet].iter_rows(min_row=2, values_only=True):
            grup, label = row[0], row[1]
            if not grup:
                continue
            if grup in ("Brand Personality", "Brand Tone"):
                continue          # sisi brand, sengaja tidak dipakai
            nilai[kind].add(_norm(label))
    wb.close()
    return nilai


def test_semua_nilai_excel_sisi_kol_tercover():
    excel = _excel_kol_side()
    punya = {_norm(r["label"]) for r in t.TAXONOMY}
    hilang = (excel["style"] | excel["personality"]) - punya
    assert not hilang, f"nilai Excel tidak ter-cover: {sorted(hilang)}"


def test_jumlah_nilai_excel_sisi_kol_ada_30_baris():
    """Content Style 10 + Communication Style 8 + Creator Personality 12."""
    openpyxl = pytest.importorskip("openpyxl")
    if not EXCEL.exists():
        pytest.skip("Excel tidak ada")
    wb = openpyxl.load_workbook(EXCEL, data_only=True, read_only=True)
    n = 0
    for sheet in ("Style List", "Personality List"):
        for row in wb[sheet].iter_rows(min_row=2, values_only=True):
            if row[0] and row[0] not in ("Brand Personality", "Brand Tone"):
                n += 1
    wb.close()
    assert n == 30


# ===========================================================================
# 4. CAKUPAN PROTOTYPE UI
# ===========================================================================

def _prototype_values():
    if not PROTOTYPE.exists():
        pytest.skip("app/AUTOME_2.html tidak ada")
    txt = PROTOTYPE.read_text(encoding="utf-8", errors="replace")
    hasil = {}
    for axis in ("dna", "comm", "vis"):
        vals = set()
        for m in re.finditer(axis + r":\[([^\]]*)\]", txt):
            for v in re.findall(r"'([^']+)'", m.group(1)):
                if re.match(r"^[a-z][a-z ]*$", v):   # buang token filter
                    vals.add(_norm(v))
        hasil[axis] = vals
    return hasil


def test_semua_nilai_prototype_tercover():
    proto = _prototype_values()
    punya = {_norm(r["label"]) for r in t.TAXONOMY}
    semua = proto["dna"] | proto["comm"] | proto["vis"]
    hilang = semua - punya
    assert not hilang, f"nilai prototype tidak ter-cover: {sorted(hilang)}"


def test_nilai_yang_hanya_dari_ui_ditandai_ui():
    """Commentary, Demonstration, Expert, dan 4 nilai visual_style tidak ada
    di Excel — asalnya harus terekam."""
    hanya_ui = {"Commentary", "Demonstration", "Expert",
                "Cinematic", "Colorful", "Lifestyle", "Minimalist"}
    for r in t.TAXONOMY:
        if r["label"] in hanya_ui and r["attribute_group"] != "visual_style":
            assert r["source_origin"] == "ui", r


def test_visual_style_seluruhnya_dari_ui():
    """Sumbu keempat ini tidak punya padanan di Excel."""
    vis = [r for r in t.TAXONOMY if r["attribute_group"] == "visual_style"]
    assert len(vis) == 7
    assert all(r["source_origin"] == "ui" for r in vis)


# ===========================================================================
# 5. BENTUK MANY-TO-MANY  (diuji atas struktur, bukan data)
# ===========================================================================

def test_satu_kol_bisa_banyak_attribute():
    """Tidak ada unique pada kol_directory_id saja — kalau ada, satu KOL
    cuma bisa punya satu atribut."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "UNIQUE (kol_directory_id)" not in sql
    assert "UNIQUE (kol_directory_id, kol_attribute_id)" in sql


def test_satu_attribute_bisa_banyak_kol():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "UNIQUE (kol_attribute_id)" not in sql


def test_duplicate_mapping_dicegah_unique():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CONSTRAINT uq_kol_attribute_map" in sql


def _ddl_saja(sql: str) -> str:
    """Buang baris komentar `--`, sisakan DDL-nya saja.

    Migration ini SENGAJA menjelaskan kenapa `influencer_id` ditolak, jadi
    kata itu memang muncul di komentar. Yang harus dijaga adalah ia tidak
    dipakai sebagai kolom atau FK.
    """
    return "\n".join(baris for baris in sql.splitlines()
                     if not baris.lstrip().startswith("--"))


def test_tidak_ada_person_table():
    """Audit menolak influencer_id sebagai kunci person."""
    ddl = _ddl_saja(MIGRATION.read_text(encoding="utf-8"))
    assert "CREATE TABLE IF NOT EXISTS public.person" not in ddl
    assert "influencer_id" not in ddl
    assert "person_id" not in ddl
