"""42 Sub Category di public.kol_categories — modul, migration, Excel, dan DB.

Yang dijaga:

    1. Modul konsisten sendiri: 42 baris, 0 duplicate, tiap induk 3 anak.
    2. Modul == sheet `Taxonomy` bagian C (bentuk kanonik, membawa kode).
    3. Modul == sheet `Lookup_Lists` bagian 2 (label -> label induk).
    4. Migration 047 memuat PERSIS apa yang ada di modul, aditif, idempoten,
       tidak menyentuh data existing, dan tidak mengisi mapping KOL.
    5. Keadaan nyata di DB `kol` (koneksi READ-ONLY).

Test yang menyentuh Excel `skip` kalau filenya tidak ada; test DB `skip` kalau
DB tidak terjangkau.
"""

import re
from pathlib import Path

import pytest

import kol_sub_category_taxonomy as t

AKAR = Path(__file__).resolve().parents[1]
MIGRATION = AKAR / "migrations" / "047_kol_sub_category.sql"
EXCEL = AKAR / "docs" / "brand_match_master.xlsx"

#: 28 kategori existing di DB `kol` sebelum migration 047 (audit 16 Sep 2026).
KATEGORI_EXISTING = (
    "Animal Lovers", "Automotive and motorsports", "Beauty",
    "Business and entrepreneurship", "Cooking", "Cyclist", "Dance",
    "Entertainment", "Environmentalism and sustainability", "Fashion",
    "Fitness", "Food", "Foodies", "Gaming", "Gen Z", "Gym Enthusiast",
    "Home Decor", "Humor", "Lifestyle", "Medical", "Moms", "Musicians",
    "Parenting and family", "Spirituality and religion", "Sports",
    "Story Teller", "Technology and gadgets", "Travel",
)


def _sheet(nama):
    openpyxl = pytest.importorskip("openpyxl")
    if not EXCEL.exists():
        pytest.skip(f"{EXCEL.name} tidak ada")
    wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
    return list(wb[nama].iter_rows(values_only=True))


# ===========================================================================
# 1. KONSISTENSI MODUL
# ===========================================================================

def test_tepat_42_sub_category():
    assert len(t.TAXONOMY) == 42


def test_tidak_ada_duplicate():
    kode = [r["code"] for r in t.TAXONOMY]
    label = [r["label"] for r in t.TAXONOMY]
    assert len(kode) == len(set(kode)), "ada duplicate code"
    assert len(label) == len(set(label)), "ada duplicate label"
    assert len({x.lower() for x in label}) == 42, "duplicate beda huruf besar"


def test_tidak_ada_yang_hilang_14_induk_masing_masing_3():
    assert t.ringkasan() == {
        "Beauty": 3, "Fashion": 3, "Food": 3, "Fitness": 3, "Tech": 3,
        "Finance": 3, "Education": 3, "Lifestyle": 3, "Travel": 3,
        "Parenting": 3, "Entertainment": 3, "Gaming": 3, "Automotive": 3,
        "Home & Living": 3, "TOTAL": 42,
    }
    assert len(t.PARENT_CATEGORIES) == 14


def test_semua_punya_parent_dan_kodenya_bernamespace_induk():
    for r in t.TAXONOMY:
        assert r["parent_code"] and r["parent_label"], r["code"]
        assert r["code"].startswith(r["parent_code"] + ".")


def test_tidak_ada_label_yang_dinormalisasi():
    label = {r["label"] for r in t.TAXONOMY}
    for wajib in ("Coffee & Beverage", "Gym & Strength", "PC & Console",
                  "Modification & Aftermarket"):
        assert wajib in label
    assert ("HNL", "Home & Living") in t.PARENT_CATEGORIES
    for r in t.TAXONOMY:
        assert r["label"] == r["label"].strip()
        assert " and " not in r["label"]


def test_parent_existing_hanya_yang_namanya_persis_sama():
    """8 induk memakai baris existing KARENA namanya identik; 6 sisanya baru.
    Tidak ada alias nama-mirip."""
    label_induk = dict(t.PARENT_CATEGORIES)
    existing = {c for c, l in t.PARENT_CATEGORIES if l in KATEGORI_EXISTING}
    assert existing == set(t.PARENT_BARIS_EXISTING)
    assert t.PARENT_BARIS_BARU == ("TEC", "FIN", "EDU", "PAR", "AUT", "HNL")
    for c in t.PARENT_BARIS_BARU:
        assert label_induk[c] not in KATEGORI_EXISTING


def test_nama_baru_tidak_bentrok_dengan_kategori_existing():
    existing = {n.lower() for n in KATEGORI_EXISTING}
    baru = [l for c, l in t.PARENT_CATEGORIES if c in t.PARENT_BARIS_BARU]
    baru += [r["label"] for r in t.TAXONOMY]
    for n in baru:
        assert n.lower() not in existing, n
    assert len({n.lower() for n in baru}) == len(baru)


def test_parent_lookup_dua_arah():
    assert t.parent_dari_code("BEA.SKN") == "BEA"
    assert t.parent_dari_label("Skincare") == "Beauty"
    assert t.parent_dari_code("TIDAK.ADA") is None
    assert t.parent_dari_label("Tidak Ada") is None


def test_sekode_induk():
    assert t.sekode_induk("BEA.SKN", "BEA.MKP") is True
    assert t.sekode_induk("BEA.SKN", "FAS.STR") is False
    assert t.sekode_induk("BEA.SKN", "TIDAK.ADA") is False


def test_parse_kode_membuang_yang_tak_dikenal_dan_duplikat():
    assert t.parse_sub_category_codes("BEA.SKN,FAS.HJB") == ["BEA.SKN", "FAS.HJB"]
    assert t.parse_sub_category_codes("BEA.SKN,BEA.SKN") == ["BEA.SKN"]
    assert t.parse_sub_category_codes("Skincare") == [], "label bukan kode"
    assert t.parse_sub_category_codes("BEA") == [], "kode induk bukan Sub Category"
    assert t.parse_sub_category_codes("") == []
    assert t.parse_sub_category_codes(None) == []


# ===========================================================================
# 2-3. MODUL == EXCEL
# ===========================================================================

def test_modul_sama_dengan_sheet_taxonomy():
    rows = _sheet("Taxonomy")
    l1 = {r[0]: r[3] for r in rows if r[1] == "L1 Category"}
    excel = [(r[0], r[2], r[3], l1[r[2]], r[4])
             for r in rows if r[1] == "L2 Sub Category"]
    modul = [(r["code"], r["parent_code"], r["label"],
              r["parent_label"], r["label_id"]) for r in t.TAXONOMY]
    assert len(excel) == 42
    assert modul == excel, "modul bergeser dari sheet Taxonomy"
    assert list(l1.items()) == list(t.PARENT_CATEGORIES)


def test_modul_sama_dengan_lookup_lists_parent_mapping():
    rows = _sheet("Lookup_Lists")
    assert rows[48][0].startswith("2. SUB CATEGORY"), "bagian 2 bergeser barisnya"
    excel = [(r[0], r[1]) for r in rows[50:92]]
    modul = [(r["label"], r["parent_label"]) for r in t.TAXONOMY]
    assert len(excel) == 42
    assert modul == excel, "modul bergeser dari Lookup_Lists bagian 2"


def test_dua_sheet_excel_saling_sepakat():
    tax = _sheet("Taxonomy")
    l1 = {r[0]: r[3] for r in tax if r[1] == "L1 Category"}
    dari_taxonomy = [(r[3], l1[r[2]]) for r in tax if r[1] == "L2 Sub Category"]
    dari_lookup = [(r[0], r[1]) for r in _sheet("Lookup_Lists")[50:92]]
    assert dari_taxonomy == dari_lookup


def test_bobot_20_persen_dari_excel():
    rows = _sheet("Lookup_Lists")
    baris = [r for r in rows if r and "W_CC_SUBCATEGORY" in
             [str(c) for c in r if c is not None]]
    assert baris, "konstanta W_CC_SUBCATEGORY tidak ditemukan di Excel"
    nilai = [c for c in baris[0] if isinstance(c, (int, float))]
    assert t.SUB_CATEGORY_MATCH_BOBOT == 20 == nilai[0]


# ===========================================================================
# 4. MIGRATION
# ===========================================================================

def _migration() -> str:
    if not MIGRATION.exists():
        pytest.skip(f"{MIGRATION.name} tidak ada")
    return MIGRATION.read_text(encoding="utf-8")


def _eksekusi() -> str:
    """SQL yang benar-benar dijalankan: komentar `--` dan isi string literal
    dibuang, supaya kata di dalam dokumentasi tidak dianggap perintah."""
    tanpa_komentar = "\n".join(
        b for b in _migration().splitlines() if not b.strip().startswith("--"))
    return re.sub(r"'(?:[^']|'')*'", "''", tanpa_komentar)


def test_migration_memuat_seed_yang_digenerate_modul():
    """Seed di migration BYTE-IDENTIK dengan keluaran modul."""
    sql = _migration()
    assert t.baris_seed_sql() in sql
    assert t.baris_parent_sql() in sql


def test_migration_memakai_kol_categories_bukan_tabel_baru():
    eksekusi = _eksekusi().upper()
    assert "CREATE TABLE PUBLIC." not in eksekusi
    assert "ALTER TABLE PUBLIC.KOL_CATEGORIES" in eksekusi
    assert "INSERT INTO PUBLIC.KOL_CATEGORIES" in eksekusi


def test_migration_aditif():
    """Tidak ada DELETE/TRUNCATE/RENAME/DROP COLUMN, dan tidak menulis ke
    tabel yang memegang relasi KOL -> kategori."""
    eksekusi = _eksekusi().upper()
    for terlarang in ("DELETE FROM", "TRUNCATE", "RENAME", "DROP COLUMN",
                      "ALTER COLUMN", "DROP CONSTRAINT",
                      "UPDATE PUBLIC.KOL_DIRECTORY",
                      "UPDATE PUBLIC.AGENCY_KOL_ACCOUNTS",
                      "INSERT INTO PUBLIC.KOL_DIRECTORY",
                      "CASCADE"):
        assert terlarang not in eksekusi, f"{terlarang} muncul di migration"


def test_migration_hanya_drop_dua_tabel_lama():
    eksekusi = _eksekusi()
    drop = re.findall(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([\w.]+)", eksekusi, re.I)
    assert sorted(drop) == ["public.kol_sub_category",
                            "public.kol_sub_category_map"]
    # dan DROP itu dijaga: map harus kosong, isi lama identik
    assert "kol_sub_category_map berisi" in _migration()
    assert "tidak identik" in _migration()


def test_migration_update_kategori_existing_hanya_mengisi_code_yang_null():
    eksekusi = _eksekusi()
    update = re.findall(r"UPDATE\s+public\.kol_categories.*?;", eksekusi,
                        re.I | re.S)
    assert len(update) == 1
    assert re.search(r"SET\s+code\s*=\s*p\.code\s+FROM", update[0])
    assert "c.code IS NULL" in update[0]
    assert "c.name = p.name" in update[0], "induk existing dicocokkan nama persis"


def test_migration_idempoten():
    eksekusi = _eksekusi()
    assert eksekusi.count("ADD COLUMN IF NOT EXISTS") == 3
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in eksekusi
    assert "DROP TABLE IF EXISTS" in eksekusi
    # setiap constraint baru dibuat hanya bila belum ada
    add = re.findall(r"ADD CONSTRAINT (\w+)", eksekusi)
    assert len(add) == 3
    for nama in add:
        assert f"conname = ''" in eksekusi  # literal nama dibuang _eksekusi()
        assert f"'{nama}'" in _migration()
    # setiap INSERT ke kol_categories dijaga NOT EXISTS pada code
    insert = re.findall(r"INSERT INTO public\.kol_categories.*?;", eksekusi, re.S)
    assert len(insert) == 2
    for i in insert:
        assert "NOT EXISTS" in i and "x.code" in i


def test_migration_memverifikasi_data_existing_dan_relasi_kol():
    sql = _migration()
    for wajib in ("checksum_existing", "checksum_kategori_kol",
                  "checksum_kategori_agency",
                  "KOL menunjuk Sub Category",
                  "baris baru ber-taxonomy_key",
                  "Nama kategori duplikat"):
        assert wajib in sql, wajib


def test_migration_tidak_mengisi_mapping_kol():
    eksekusi = _eksekusi()
    assert "category_ids =" not in eksekusi
    assert "category_id =" not in eksekusi.replace("c.category_id", "")
    assert "content_topic" not in eksekusi


def test_migration_tidak_menyentuh_tsdb_atau_db_lain():
    eksekusi = "\n".join(b for b in _migration().splitlines()
                         if not b.strip().startswith("--")).lower()
    for asing in ("timescale", "tsdb", "hypertable", "database_url",
                  "dblink", "postgres_fdw"):
        assert asing not in eksekusi


def test_migration_parent_verifikasi_sesuai_modul():
    sql = _migration()
    existing = re.search(r"c\.code IN \(([^)]*)\)\)\s*<> EXISTS", sql)
    assert existing
    assert re.findall(r"'(\w+)'", existing.group(1)) == list(t.PARENT_BARIS_EXISTING)
    baru = re.search(r"c\.code NOT IN \(([^)]*)\)", sql)
    assert re.findall(r"'(\w+)'", baru.group(1)) == list(t.PARENT_BARIS_BARU)


# ===========================================================================
# 5. KETERSEDIAAN INPUT CREATOR + FILTER
# ===========================================================================

def test_input_creator_sub_category_ditandai_belum_tersedia():
    assert t.SUB_CATEGORY_INPUT_TERSEDIA is False
    assert t.SUB_CATEGORY_ALASAN_UNAVAILABLE


def test_belum_ada_filter_atau_field_mapping_sub_category():
    """Field mapping KOL -> Sub Category belum ditetapkan. `category_ids`
    adalah daftar Category, jadi modul tidak boleh membacanya sebagai
    Sub Category — dan tidak boleh menawarkan filter apa pun dulu."""
    assert not hasattr(t, "sql_filter_sub_category")
    kode = "\n".join(
        b for b in (AKAR / "kol_sub_category_taxonomy.py")
        .read_text(encoding="utf-8").split('"""\n\nfrom __future__', 1)[1]
        .splitlines() if not b.lstrip().startswith("#"))
    for dilarang in ("category_ids", "sub_category_ids", "kol_directory",
                     "_map"):
        assert dilarang not in kode, dilarang


def test_tidak_ada_sub_category_ids_atau_tabel_map_baru_di_migration():
    eksekusi = _eksekusi().lower()
    assert "sub_category_ids" not in eksekusi
    assert "create table" not in eksekusi
    assert "alter table public.kol_directory" not in eksekusi


def test_tidak_ada_lagi_rujukan_ke_tabel_lama():
    for f in list(AKAR.glob("*.py")) + list((AKAR / "orchestration").rglob("*.py")):
        assert "kol_sub_category_map" not in f.read_text(encoding="utf-8"), f


# ===========================================================================
# 6. KEADAAN NYATA DI DB `kol`  --  koneksi READ-ONLY
# ===========================================================================

@pytest.fixture(scope="module")
def conn():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        from config import load_config
        cfg = load_config()
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"konfigurasi DB tidak tersedia: {exc}")
    try:
        cn = psycopg2.connect(connect_timeout=5, **cfg.postgres.as_connect_kwargs())
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    cn.set_session(readonly=True, autocommit=True)
    yield cn
    cn.close()


def _satu(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


@pytest.mark.needs_db
def test_db_42_sub_category_tanpa_duplicate(conn):
    assert _satu(conn, """SELECT count(*) FROM public.kol_categories
                           WHERE level = 'sub_category'""") == 42
    assert _satu(conn, """SELECT count(DISTINCT code) FROM public.kol_categories
                           WHERE level = 'sub_category'""") == 42
    assert _satu(conn, """SELECT count(*) FROM (
                            SELECT lower(name) FROM public.kol_categories
                             GROUP BY 1 HAVING count(*) > 1) d""") == 0


@pytest.mark.needs_db
def test_db_isi_dan_parent_mapping_persis_modul(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT c.code, p.code, c.name, p.name, p.level
                         FROM public.kol_categories c
                         JOIN public.kol_categories p ON p.id = c.parent_id
                        WHERE c.level = 'sub_category'""")
        db = sorted(cur.fetchall())
    modul = sorted((r["code"], r["parent_code"], r["label"], r["parent_label"],
                    "category") for r in t.TAXONOMY)
    assert db == modul


@pytest.mark.needs_db
def test_db_14_induk_3_anak_8_existing_6_baru(conn):
    with conn.cursor() as cur:
        cur.execute("""SELECT p.code, p.name, count(c.id),
                              p.created_at < '2026-09-16'
                         FROM public.kol_categories p
                         LEFT JOIN public.kol_categories c ON c.parent_id = p.id
                        WHERE p.level = 'category' AND p.code IS NOT NULL
                        GROUP BY p.id""")
        hasil = {r[0]: r[1:] for r in cur.fetchall()}
    assert {c: v[0] for c, v in hasil.items()} == dict(t.PARENT_CATEGORIES)
    assert all(v[1] == 3 for v in hasil.values())
    assert {c for c, v in hasil.items() if v[2]} == set(t.PARENT_BARIS_EXISTING)


@pytest.mark.needs_db
def test_db_kategori_existing_utuh(conn):
    """28 kategori existing masih ada, tetap level category, dan mapping
    taxonomy_key migration 029 masih 22 mapped / 9 Discovery Category."""
    with conn.cursor() as cur:
        cur.execute("""SELECT name FROM public.kol_categories
                        WHERE level = 'category' AND parent_id IS NULL
                          AND (code IS NULL OR code NOT IN
                               ('TEC','FIN','EDU','PAR','AUT','HNL'))""")
        assert sorted(r[0] for r in cur.fetchall()) == sorted(KATEGORI_EXISTING)
    assert _satu(conn, """SELECT count(*) FROM public.kol_categories
                           WHERE taxonomy_key IS NOT NULL""") == 22
    assert _satu(conn, """SELECT count(DISTINCT taxonomy_key)
                            FROM public.kol_categories
                           WHERE taxonomy_key IS NOT NULL""") == 9
    assert _satu(conn, "SELECT count(*) FROM public.kol_categories") == 28 + 6 + 42


@pytest.mark.needs_db
def test_db_category_ids_hanya_berisi_category(conn):
    """Dasar keputusan bahwa `category_ids` BUKAN mapping Sub Category:
    setiap elemennya Category, dan `category_id` selalu ada di dalamnya."""
    assert _satu(conn, """SELECT count(*) FROM public.kol_directory k,
                                 unnest(k.category_ids) u(id)
                           WHERE NOT EXISTS (
                                 SELECT 1 FROM public.kol_categories c
                                  WHERE c.id = u.id
                                    AND c.level = 'category')""") == 0
    assert _satu(conn, """SELECT count(*) FROM public.kol_directory
                           WHERE category_id IS NOT NULL
                             AND NOT (category_id = ANY(
                                      COALESCE(category_ids, '{}')))""") == 0


@pytest.mark.needs_db
def test_db_tidak_ada_field_mapping_sub_category_baru(conn):
    assert _satu(conn, """SELECT count(*) FROM information_schema.columns
                           WHERE table_schema = 'public'
                             AND table_name = 'kol_directory'
                             AND column_name ILIKE '%sub_categ%'""") == 0


@pytest.mark.needs_db
def test_db_belum_ada_kol_yang_menunjuk_sub_category(conn):
    assert _satu(conn, """SELECT count(*) FROM public.kol_directory k
                           WHERE EXISTS (SELECT 1 FROM public.kol_categories c
                                          WHERE c.level = 'sub_category'
                                            AND (c.id = ANY(k.category_ids)
                                                 OR c.id = k.category_id))""") == 0
    assert _satu(conn, """SELECT count(*) FROM public.agency_kol_accounts a
                            JOIN public.kol_categories c ON c.id = a.category_id
                           WHERE c.level = 'sub_category'""") == 0


@pytest.mark.needs_db
def test_db_tabel_lama_sudah_tidak_ada(conn):
    assert _satu(conn, "SELECT to_regclass('public.kol_sub_category')") is None
    assert _satu(conn, "SELECT to_regclass('public.kol_sub_category_map')") is None


@pytest.mark.needs_db
def test_db_constraint_terpasang(conn):
    assert _satu(conn, """SELECT count(*) FROM pg_constraint
                           WHERE conrelid = 'public.kol_categories'::regclass
                             AND conname IN ('fk_kol_categories_parent',
                                             'ck_kol_categories_level',
                                             'ck_kol_categories_level_parent')""") == 3

