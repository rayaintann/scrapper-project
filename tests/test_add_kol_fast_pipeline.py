"""Add KOL -> Audience Insight tanpa menunggu belasan menit.

Audit 5 Oktober (`sibungbung`): Category terisi 2m43s setelah Add, tetapi baris
audiens baru muncul ~8 menit (feature) dan ~16 menit (L2) kemudian, dan kartu
profilnya menyimpan kolom audiens NULL. Tiga penyebab, tiga penjaga di sini:

1. `_cocok_kata` mengompilasi ulang regex hampir di setiap panggilan (cache
   internal `re` lebih kecil dari kamus). Polanya kini dikompilasi sekali per
   kata -- hasilnya harus SAMA PERSIS dengan rumus lama.
2. `_tulis_gold` mengirim satu INSERT per dimensi. Barisnya kini dikirim per
   tabel -- baris, SQL, dan penjaganya tidak boleh berubah.
3. `kol_profile_card` terbentuk sebelum `audience_feature`. Kartu kini disegarkan
   setelahnya, TANPA membuat kartu / Category menunggu rantai follower.

Seluruhnya offline: tidak ada koneksi database, tidak ada Apify.
"""

from __future__ import annotations

import re
import sys
import warnings
from datetime import date
from pathlib import Path

import pytest

import audience_inference as AI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestration"))

from kol_orchestration.assets import audience, gold_profile  # noqa: E402

TAHUN = 2026


# =====================================================================
# 1. Pencocokan kata: cepat, dan hasilnya tidak berubah
# =====================================================================
def _cocok_kata_lama(haystack: str, kata: str) -> bool:
    """Rumus sebelum perbaikan, disalin apa adanya sebagai pembanding."""
    if " " in kata:
        return kata in haystack
    return re.search(rf"\b{re.escape(kata)}\b", haystack) is not None


def _semua_kata_kamus() -> set[str]:
    kata: set[str] = set()
    for nilai in vars(AI).values():
        if isinstance(nilai, dict):
            nilai = list(nilai.keys()) + [v for v in nilai.values()
                                          if isinstance(v, (set, frozenset, tuple, list))]
        if isinstance(nilai, (set, frozenset, tuple, list)):
            for v in nilai:
                if isinstance(v, str):
                    kata.add(v)
                elif isinstance(v, (set, frozenset, tuple, list)):
                    kata.update(x for x in v if isinstance(x, str))
    return kata


TEKS = (
    "mom of two | jakarta selatan | owner @tokokue.id | open order wa 0812",
    "mahasiswa ui 2022 • bandung • suka kopi, traveling & fotografi",
    "💄 beauty enthusiast - skincare review - surabaya, jawa timur",
    "football fan. gamer. lahir 1999. medan",
    "ibu rumah tangga, hobi masak dan berkebun di bali",
    "c++ dev (a.k.a. kang ngoding) | 50% kopi | [yogyakarta]",
    "",
)


def test_cocok_kata_sama_persis_dengan_rumus_lama():
    kamus = _semua_kata_kamus()
    assert len(kamus) > 600, "kamus harus lebih besar dari cache internal `re`"
    beda = [(t, k) for t in TEKS for k in kamus
            if AI._cocok_kata(t, k) != _cocok_kata_lama(t, k)]
    assert beda == []


def test_karakter_khusus_regex_tetap_di_escape():
    assert AI._cocok_kata("belajar c++ tiap hari", "c++") == _cocok_kata_lama("belajar c++ tiap hari", "c++")
    assert AI._cocok_kata("a.k.a", "a.k.a") is True
    assert AI._cocok_kata("akka", "a.k.a") is False        # titik bukan wildcard
    assert AI._cocok_kata("jakartans", "jakarta") is False  # kata utuh, bukan substring
    assert AI._cocok_kata("jakarta selatan", "jakarta selatan") is True


def test_pola_dikompilasi_sekali_per_kata():
    AI._pola_kata.cache_clear()
    for _ in range(3):
        for t in TEKS:
            AI._cocok_kata(t, "jakarta")
            AI._cocok_kata(t, "bandung")
    info = AI._pola_kata.cache_info()
    assert info.misses == 2 and info.currsize == 2
    assert info.maxsize is None, "kamus lebih besar dari cache berbatas mana pun yang wajar"


def test_analisis_follower_tidak_mengompilasi_ulang_di_putaran_kedua():
    def putaran():
        for i, t in enumerate(TEKS):
            AI.analisis_follower(full_name=f"Siti Rahma {i}", bio=t, username=f"siti.rahma{i}")

    putaran()
    sebelum = AI._pola_kata.cache_info().misses
    putaran()
    assert AI._pola_kata.cache_info().misses == sebelum


# =====================================================================
# 2. L2 audiens: satu UPSERT per tabel, baris yang sama
# =====================================================================
def _follower(sid, plat, tgl, nama, bio, username):
    # Urutan kolom `SQL_FOLLOWER`.
    return (sid, plat, tgl, nama, bio, username, False, False, 150, 200, "https://x/p.jpg", None)


FOLLOWER = [
    _follower("akun-1", "tiktok", date(2026, 10, 5), "Siti Rahma", "mom of two | jakarta | suka masak", "siti.rahma"),
    _follower("akun-1", "tiktok", date(2026, 10, 5), "Budi Santoso", "football fan, bandung. lahir 2001", "budi_s"),
    _follower("akun-1", "tiktok", date(2026, 10, 5), "toko kue", "open order wa", "tokokue.id"),
    _follower("akun-1", "tiktok", date(2026, 9, 1), "Dewi Lestari", "skincare review surabaya", "dewi.les"),
    _follower("akun-2", "instagram", date(2026, 10, 5), "Andi Wijaya", "gamer medan", "andiw"),
]


class _Cur:
    def __init__(self, log):
        self.log = log
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))

    def fetchall(self):
        return list(FOLLOWER)

    def fetchone(self):
        return (0, 0, 0)


class _Conn:
    def __init__(self, log):
        self.log = log
        self.committed = False

    def cursor(self):
        return _Cur(self.log)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class _Postgres:
    def __init__(self):
        self.log: list = []
        self.conn = _Conn(self.log)

    def get_conn(self):
        return self.conn


@pytest.fixture()
def gold(monkeypatch):
    kiriman: list = []

    def rekam(cur, sql, baris, template=None, page_size=100):
        cur.log.append(("<execute_values>", None))
        kiriman.append((sql, template, list(baris), page_size))

    monkeypatch.setattr(audience, "execute_values", rekam)
    pg = _Postgres()
    audience._tulis_gold(pg, TAHUN)
    return pg, kiriman


def _harapan():
    """Baris yang HARUS ditulis, dihitung langsung dari `_hitung_per_akun`."""
    per = {}
    for r in FOLLOWER:
        per.setdefault((r[0], r[1], r[2]), []).append(r)
    gender, umur, geo, minat = [], [], [], []
    conf = lambda sumber, k: audience._kunci_confidence(audience._modus_confidence(sumber.get(k, [])))
    for (sid, plat, tgl), baris in per.items():
        agg = audience._hitung_per_akun(baris, TAHUN)
        gender += [(sid, plat, tgl, k, v, conf(agg["gender_conf"], k)) for k, v in agg["gender"].items()]
        umur += [(sid, plat, tgl, k, v, conf(agg["umur_conf"], k)) for k, v in agg["umur"].items() if v]
        geo += [(sid, plat, tgl, "country", k, v, conf(agg["negara_conf"], k)) for k, v in agg["negara"].items()]
        geo += [(sid, plat, tgl, audience.tingkat_geo(k), k, v, conf(agg["kota_conf"], k))
                for k, v in agg["kota"].items()]
        minat += [(sid, plat, tgl, k, v, conf(agg["minat_conf"], k)) for k, v in agg["minat"].items()]
    return gender, umur, geo, minat


def test_tidak_ada_insert_per_baris(gold):
    pg, kiriman = gold
    assert [q for q, _ in pg.log if q.startswith("INSERT")] == []
    assert [k[0] for k in kiriman] == [
        audience.SQL_UPSERT_DEMOGRAFI_GENDER, audience.SQL_UPSERT_DEMOGRAFI_UMUR,
        audience.SQL_UPSERT_GEO, audience.SQL_UPSERT_INTEREST]
    assert pg.conn.committed


def test_baris_yang_ditulis_sama_dengan_hasil_inferensi(gold):
    _, kiriman = gold
    gender, umur, geo, minat = _harapan()
    assert [k[2] for k in kiriman] == [gender, umur, geo, minat]
    assert gender and umur and geo and minat, "data uji harus mengisi keempat tabel"


def test_kunci_konflik_unik_dalam_satu_pernyataan(gold):
    # ON CONFLICT DO UPDATE menolak baris yang sama disentuh dua kali.
    for _, _, baris, _ in gold[1]:
        kunci = [b[:-2] for b in baris]
        assert len(kunci) == len(set(kunci))


def test_delete_baris_basi_tetap_per_akun_tanggal_dan_mendahului_upsert(gold):
    pg, _ = gold
    urutan = [q.split(" ", 1)[0] if q != "<execute_values>" else q for q, _ in pg.log]
    hapus = [i for i, q in enumerate(urutan) if q == "DELETE"]
    kirim = [i for i, q in enumerate(urutan) if q == "<execute_values>"]
    assert len(kirim) == 4 and max(hapus) < min(kirim)
    per_akun_tanggal = {(r[0], r[1], r[2]) for r in FOLLOWER}
    hapus_gender = [p for q, p in pg.log if q.startswith("DELETE") and "audience_type='gender'" in q]
    assert {tuple(p[:3]) for p in hapus_gender} == per_akun_tanggal


@pytest.mark.parametrize("sql,templat,kolom", [
    (audience.SQL_UPSERT_DEMOGRAFI_GENDER, audience._BARIS_GENDER, 6),
    (audience.SQL_UPSERT_DEMOGRAFI_UMUR, audience._BARIS_UMUR, 6),
    (audience.SQL_UPSERT_GEO, audience._BARIS_GEO, 7),
    (audience.SQL_UPSERT_INTEREST, audience._BARIS_INTEREST, 6),
])
def test_sql_upsert_utuh(sql, templat, kolom):
    assert sql.count("%s") == 1 and "VALUES %s" in sql     # satu-satunya placeholder: daftar baris
    assert templat.count("%s") == kolom
    assert "ON CONFLICT" in sql and "IS DISTINCT FROM EXCLUDED.audience_count" in sql


def test_umur_terukur_tidak_pernah_ditimpa():
    sql = " ".join(audience.SQL_UPSERT_DEMOGRAFI_UMUR.split())
    assert f"audience_demographics_daily.confidence IS DISTINCT FROM '{audience.CONF_TERUKUR}' AND (" in sql
    assert "'age'" in audience._BARIS_UMUR and "'gender'" in audience._BARIS_GENDER


def test_follower_kosong_tidak_menulis_apa_pun(monkeypatch):
    monkeypatch.setattr(_Cur, "fetchall", lambda self: [])
    monkeypatch.setattr(audience, "execute_values",
                        lambda *a, **k: pytest.fail("tidak boleh ada UPSERT"))
    pg = _Postgres()
    assert audience._tulis_gold(pg, TAHUN).value == 0
    assert not pg.conn.committed


# =====================================================================
# 3. Kartu profil disegarkan setelah audiens, Category tidak ikut menunggu
# =====================================================================
@pytest.fixture(scope="module")
def induk():
    from kol_orchestration import one_shot
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from kol_orchestration.repository import defs
        job = defs.resolve_job_def(one_shot.TRANSFORM_JOB_NAME)
    return {simpul.name: set(dep) for simpul, dep in job.dependencies.items()}


def _leluhur(induk: dict, nama: str) -> set[str]:
    hasil: set[str] = set()
    antre = list(induk[nama])
    while antre:
        n = antre.pop()
        if n not in hasil:
            hasil.add(n)
            antre.extend(induk.get(n, ()))
    return hasil


def test_kartu_disegarkan_setelah_audience_feature(induk):
    assert induk["kol_profile_card_audience"] == {
        "kol_profile_card", "audience_feature", "creator_age", "creator_gender"}


def test_penyegaran_memakai_upsert_kartu_yang_sama(monkeypatch):
    dipanggil = []
    monkeypatch.setattr(gold_profile, "_jalankan", lambda pg: dipanggil.append(pg) or "hasil")
    assert gold_profile.kol_profile_card_audience.op.compute_fn.decorated_fn("pg") == "hasil"
    assert gold_profile.kol_profile_card.op.compute_fn.decorated_fn("pg") == "hasil"
    assert dipanggil == ["pg", "pg"]


def test_kartu_dan_category_tidak_menunggu_rantai_follower(induk):
    rantai_follower = {"instagram_follower", "tiktok_follower", "unified_follower",
                       "follower_profile_enrichment", "audience_feature", "audience_gold",
                       "kol_profile_card_audience"}
    assert induk["kol_profile_card"] == {
        "unified_profile", "ig_engagement_analysis", "tt_engagement_analysis"}
    for nama in ("kol_profile_card", "creator_classification", "creator_category_bridge"):
        assert not _leluhur(induk, nama) & rantai_follower, nama


def test_audience_gold_tidak_menunggu_penyegaran_kartu(induk):
    assert induk["audience_gold"] == {"audience_feature"}
    assert "kol_profile_card_audience" not in _leluhur(induk, "audience_gold")


def test_penyegaran_ikut_semua_rantai():
    from kol_orchestration import one_shot
    assert "kol_profile_card_audience" in one_shot.TRANSFORM_ASSETS
    assert "kol_profile_card_audience" in one_shot.CHAIN_JOB_ASSETS


def test_kolom_audiens_kartu_dijaga_is_distinct():
    # Penyegaran menjalankan UPSERT yang sama dua kali per run; penjaga inilah yang
    # membuat putaran kedua hanya menyentuh kartu yang kolom audiensnya berubah.
    for kolom in ("female_pct", "audience_quality_score", "audience_quality_tier",
                  "audience_interest_top", "audience_interest_source"):
        assert re.search(rf"kol_profile_card\.{kolom}\s+IS DISTINCT FROM EXCLUDED\.{kolom}",
                         gold_profile.SQL_UPSERT), kolom
    assert "creator_age" not in gold_profile.SQL_UPSERT
    assert "creator_gender" not in gold_profile.SQL_UPSERT


# =====================================================================
# 4. Sensor
# =====================================================================
def test_sensor_l0_raw_dicek_paling_lama_tiap_30_detik():
    from kol_orchestration import sensors
    assert sensors.MINIMUM_INTERVAL_SECONDS <= 30
    assert sensors.l0_raw_new_data_sensor.minimum_interval_seconds == sensors.MINIMUM_INTERVAL_SECONDS
