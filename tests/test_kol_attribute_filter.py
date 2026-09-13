"""Filter Style & Personality untuk KOL Discovery.

Semantik yang dijaga:

    OR  di dalam satu grup   -- pilih dua Style = "salah satunya"
    AND antar grup           -- menambah Personality MEMPERSEMPIT hasil

Semantiknya diuji dua kali, atas hal yang sama:

    Python  `cocok_atribut()`
    SQL     `sql_filter_atribut()` dijalankan ke Postgres SUNGGUHAN dengan
            sumber mapping diganti klausa VALUES

Pola sumber-yang-bisa-disubstitusi itu meniru `db._GROWTH_CTE_TEMPLATE`: yang
diuji jadi SQL yang benar-benar dipakai produksi, bukan tiruannya, dan tanpa
menulis satu baris pun ke database.
"""

import pytest

import db
import kol_attribute_taxonomy as kat

STYLE_EDU = "content_style.educational"
STYLE_TUT = "content_style.tutorial"
STYLE_REV = "content_style.review"
COMM_CONV = "communication_style.conversational"
VIS_MIN = "visual_style.minimalist"
PERS_REL = "creator_personality.relatable"
PERS_EXP = "creator_personality.expert"


# ===========================================================================
# TAXONOMY STYLE
# ===========================================================================

def test_taxonomy_style_tiga_grup():
    grup = {r["attribute_group"] for r in kat.TAXONOMY
            if r["kind"] == kat.STYLE}
    assert grup == {"content_style", "communication_style", "visual_style"}


def test_taxonomy_style_jumlahnya():
    n = sum(1 for r in kat.TAXONOMY if r["kind"] == kat.STYLE)
    assert n == 11 + 9 + 7 == 27


@pytest.mark.parametrize("kunci", [STYLE_EDU, STYLE_TUT, STYLE_REV,
                                   COMM_CONV, VIS_MIN])
def test_kunci_style_ada_di_master(kunci):
    assert kunci in {r["attribute_key"] for r in kat.TAXONOMY}


# ===========================================================================
# TAXONOMY PERSONALITY
# ===========================================================================

def test_taxonomy_personality_satu_grup_sisi_kol():
    grup = {r["attribute_group"] for r in kat.TAXONOMY
            if r["kind"] == kat.PERSONALITY}
    assert grup == {"creator_personality"}


def test_taxonomy_personality_jumlahnya():
    n = sum(1 for r in kat.TAXONOMY if r["kind"] == kat.PERSONALITY)
    assert n == 13


def test_brand_personality_dan_tone_tidak_ikut():
    grup = {r["attribute_group"] for r in kat.TAXONOMY}
    assert "brand_personality" not in grup
    assert "brand_tone" not in grup


def test_style_dan_personality_satu_taxonomy_yang_sama():
    """Keduanya hidup di satu master, dibedakan `kind` — bukan dua tabel."""
    assert {r["kind"] for r in kat.TAXONOMY} == {kat.STYLE, kat.PERSONALITY}
    assert len(kat.TAXONOMY) == 40


# ===========================================================================
# PARSING FILTER
# ===========================================================================

def test_parse_menerima_csv():
    assert kat.parse_attribute_keys(f"{STYLE_EDU},{STYLE_TUT}") == [
        STYLE_EDU, STYLE_TUT]


def test_parse_membuang_kunci_asing_dan_duplikat():
    assert kat.parse_attribute_keys(f"ngawur,{STYLE_EDU},{STYLE_EDU}") == [
        STYLE_EDU]
    assert kat.parse_attribute_keys("") == []
    assert kat.parse_attribute_keys(None) == []


def test_parse_menyaring_per_kind():
    """Kunci personality yang dikirim ke slot style harus dibuang."""
    assert kat.parse_attribute_keys(PERS_REL, kind=kat.STYLE) == []
    assert kat.parse_attribute_keys(STYLE_EDU, kind=kat.PERSONALITY) == []
    assert kat.parse_attribute_keys(PERS_REL, kind=kat.PERSONALITY) == [PERS_REL]


def test_parse_style_menerima_ketiga_grupnya():
    for kunci in (STYLE_EDU, COMM_CONV, VIS_MIN):
        assert kat.parse_attribute_keys(kunci, kind=kat.STYLE) == [kunci]


def test_filter_berbasis_key_bukan_label():
    """`Educational` hidup di 3 grup; menyaring dengan label akan menyaring
    hal yang tidak diminta."""
    assert kat.parse_attribute_keys("Educational") == []


# ===========================================================================
# SEMANTIK  --  Python
# ===========================================================================

def test_or_di_dalam_satu_grup():
    assert kat.cocok_atribut([STYLE_EDU], [STYLE_EDU, STYLE_TUT]) is True
    assert kat.cocok_atribut([STYLE_TUT], [STYLE_EDU, STYLE_TUT]) is True
    assert kat.cocok_atribut([STYLE_REV], [STYLE_EDU, STYLE_TUT]) is False


def test_filter_kosong_berarti_jangan_saring():
    assert kat.cocok_atribut([], []) is True
    assert kat.cocok_atribut([STYLE_EDU], []) is True


def test_kol_tanpa_atribut_tidak_lolos_filter():
    assert kat.cocok_atribut([], [STYLE_EDU]) is False


def test_multiple_style_dalam_satu_kol():
    punya = [STYLE_EDU, STYLE_TUT, COMM_CONV, VIS_MIN]
    for kunci in punya:
        assert kat.cocok_atribut(punya, [kunci]) is True


def test_multiple_personality_dalam_satu_kol():
    punya = [PERS_REL, PERS_EXP]
    assert kat.cocok_atribut(punya, [PERS_REL]) is True
    assert kat.cocok_atribut(punya, [PERS_EXP]) is True


def test_kombinasi_style_dan_personality_bersifat_and():
    punya = [STYLE_EDU, PERS_REL]
    assert (kat.cocok_atribut(punya, [STYLE_EDU])
            and kat.cocok_atribut(punya, [PERS_REL])) is True
    # personality yang tidak dimiliki -> gagal, meski style-nya cocok
    assert (kat.cocok_atribut(punya, [STYLE_EDU])
            and kat.cocok_atribut(punya, [PERS_EXP])) is False


# ===========================================================================
# WIRING KE JALUR BACA
# ===========================================================================

def test_search_menerima_style_dan_personality():
    import inspect
    sig = inspect.signature(db.search_kol_directory)
    assert sig.parameters["style"].default is None
    assert sig.parameters["personality"].default is None


def test_query_memakai_exists_bukan_join():
    """JOIN akan menduplikasi KOL yang punya beberapa label cocok."""
    assert "EXISTS (" in db._SEARCH_QUERY
    assert "kol_attribute_map" in db._SEARCH_QUERY


def test_query_tidak_menyentuh_kol_categories_untuk_style():
    sql = kat.sql_filter_atribut("%(style)s::text[]")
    assert "kol_categories" not in sql
    assert "category_ids" not in sql


def test_query_menghormati_is_active():
    assert "a.is_active" in kat.SUMBER_MAP_DEFAULT


# ===========================================================================
# SEMANTIK  --  SQL, dijalankan ke Postgres sungguhan
# ===========================================================================

#: Mapping tiruan. Bukan data DB: disuntikkan sebagai VALUES lewat parameter
#: `sumber`, jadi tidak ada baris yang ditulis ke mana pun.
_SUMBER_UJI = """(VALUES
        ('kol-a', 'content_style.educational'),
        ('kol-a', 'content_style.tutorial'),
        ('kol-a', 'creator_personality.relatable'),
        ('kol-b', 'content_style.review'),
        ('kol-b', 'creator_personality.relatable'),
        ('kol-c', 'content_style.educational')
    ) AS m(kol_directory_id, attribute_key)"""


def _cari(conn, style=None, personality=None):
    """Jalankan filter yang SAMA dengan produksi, atas mapping tiruan."""
    syarat = ["TRUE"]
    if style is not None:
        syarat.append(kat.sql_filter_atribut("%(style)s::text[]", "k.id",
                                             _SUMBER_UJI))
    if personality is not None:
        syarat.append(kat.sql_filter_atribut("%(personality)s::text[]", "k.id",
                                             _SUMBER_UJI))
    sql = f"""
        WITH k(id) AS (VALUES ('kol-a'), ('kol-b'), ('kol-c'), ('kol-d'))
        SELECT k.id FROM k WHERE {' AND '.join(syarat)} ORDER BY k.id
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"style": style, "personality": personality})
        return [r[0] for r in cur.fetchall()]


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


@pytest.mark.needs_db
def test_sql_filter_style_tunggal(conn):
    assert _cari(conn, style=[STYLE_EDU]) == ["kol-a", "kol-c"]


@pytest.mark.needs_db
def test_sql_filter_style_or_di_dalam_grup(conn):
    assert _cari(conn, style=[STYLE_EDU, STYLE_REV]) == [
        "kol-a", "kol-b", "kol-c"]


@pytest.mark.needs_db
def test_sql_filter_personality(conn):
    assert _cari(conn, personality=[PERS_REL]) == ["kol-a", "kol-b"]


@pytest.mark.needs_db
def test_sql_kombinasi_style_dan_personality_and(conn):
    """kol-a punya keduanya; kol-b hanya personality; kol-c hanya style."""
    assert _cari(conn, style=[STYLE_EDU], personality=[PERS_REL]) == ["kol-a"]


@pytest.mark.needs_db
def test_sql_multiple_style_tidak_menduplikasi_kol(conn):
    """kol-a punya educational DAN tutorial; ia harus muncul SEKALI."""
    hasil = _cari(conn, style=[STYLE_EDU, STYLE_TUT])
    assert hasil.count("kol-a") == 1


@pytest.mark.needs_db
def test_sql_kol_tanpa_atribut_tersaring(conn):
    assert "kol-d" not in _cari(conn, style=[STYLE_EDU])


@pytest.mark.needs_db
def test_sql_filter_kosong_tidak_menyaring(conn):
    assert _cari(conn) == ["kol-a", "kol-b", "kol-c", "kol-d"]


# ===========================================================================
# JALUR PRODUKSI  --  read-only ke tabel sungguhan
# ===========================================================================

@pytest.mark.needs_db
def test_db_master_taxonomy_utuh_40_baris(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.kol_attribute")
        assert cur.fetchone()[0] == 40


@pytest.mark.needs_db
def test_db_kol_categories_tidak_tersentuh(conn):
    """Taxonomy Category terpisah dan tidak boleh berubah."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.kol_categories")
        assert cur.fetchone()[0] == 28


@pytest.mark.needs_db
def test_db_filter_produksi_valid_sql(conn):
    """Mapping masih 0 baris, jadi hasilnya 0 — yang diuji di sini query-nya
    berjalan terhadap schema sungguhan."""
    hasil = db.search_kol_directory(conn, style=STYLE_EDU, limit=10)
    assert hasil == []


@pytest.mark.needs_db
def test_db_filter_asing_diabaikan_bukan_menyaring_habis(conn):
    tanpa = db.search_kol_directory(conn, limit=10)
    ngawur = db.search_kol_directory(conn, style="ngawur", limit=10)
    assert [r.id for r in ngawur] == [r.id for r in tanpa]


@pytest.mark.needs_db
def test_db_kunci_salah_kind_diabaikan(conn):
    """Kunci personality di slot style dibuang, bukan menyaring sembarangan."""
    tanpa = db.search_kol_directory(conn, limit=10)
    salah = db.search_kol_directory(conn, style=PERS_REL, limit=10)
    assert [r.id for r in salah] == [r.id for r in tanpa]


# ===========================================================================
# CLI  --  satu-satunya interface layer di repo ini
# ===========================================================================

def test_cli_punya_argumen_style_dan_personality():
    import search_kol
    args = search_kol.parse_args(["--style", STYLE_EDU,
                                  "--personality", PERS_REL])
    assert args.style == STYLE_EDU
    assert args.personality == PERS_REL


def test_cli_meneruskan_style_dan_personality(monkeypatch):
    import search_kol
    ditangkap = {}

    def palsu(conn, **kwargs):
        ditangkap.update(kwargs)
        return []

    monkeypatch.setattr(search_kol, "search_kol_directory", palsu)
    monkeypatch.setattr(search_kol, "load_config", lambda: _CfgPalsu())
    monkeypatch.setattr(search_kol, "connect", _ConnPalsu)

    search_kol.main(["--style", f"{STYLE_EDU},{STYLE_TUT}",
                     "--personality", PERS_REL])
    assert ditangkap["style"] == [STYLE_EDU, STYLE_TUT]
    assert ditangkap["personality"] == [PERS_REL]


def test_cli_tanpa_filter_mengirim_none(monkeypatch):
    import search_kol
    ditangkap = {}

    def palsu(conn, **kwargs):
        ditangkap.update(kwargs)
        return []

    monkeypatch.setattr(search_kol, "search_kol_directory", palsu)
    monkeypatch.setattr(search_kol, "load_config", lambda: _CfgPalsu())
    monkeypatch.setattr(search_kol, "connect", _ConnPalsu)

    search_kol.main([])
    assert ditangkap["style"] is None
    assert ditangkap["personality"] is None


def test_cli_menolak_style_salah_ketik(monkeypatch, capsys):
    import search_kol
    monkeypatch.setattr(search_kol, "load_config", lambda: _CfgPalsu())
    assert search_kol.main(["--style", "ngawur"]) == 1
    assert "tidak dikenal" in capsys.readouterr().out


def test_cli_menolak_personality_salah_kind(monkeypatch, capsys):
    """Kunci style di slot personality ditolak, bukan diabaikan diam-diam."""
    import search_kol
    monkeypatch.setattr(search_kol, "load_config", lambda: _CfgPalsu())
    assert search_kol.main(["--personality", STYLE_EDU]) == 1
    assert "tidak dikenal" in capsys.readouterr().out


class _CfgPalsu:
    postgres = None


class _ConnPalsu:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_session(self, **k):
        pass
