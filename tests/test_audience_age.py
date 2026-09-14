"""Test Age AUDIENS: mapping bucket platform -> Discovery, agregasi, predikat filter.

INI BUKAN TEST AGE KREATOR. Umur kreator diuji di `test_creator_age.py`.
Dua fitur, dua file, sengaja -- lihat header `migrations/042`.

APA YANG BISA DIUJI HARI INI
============================
Sumbernya (`l1_silver.unified_audience` audience_type='age') masih 0 baris
sampai Instagram Insights API tersedia, jadi TIDAK ADA data nyata yang bisa
dijalankan lewat pipeline ini. Yang diuji karena itu adalah bagian yang tidak
bergantung pada data:

    * pemetaan bucket platform (7) -> bucket Discovery (5)
    * penjumlahan 45-54 + 55-64 + 65+ jadi 45+
    * bucket asing dilewati, bukan dipetakan ke yang terdekat
    * predikat filter Discovery sah secara SQL (butuh DB; skip kalau tidak ada)

Itu cukup untuk menjamin bahwa saat sumbernya menyala, angkanya benar tanpa
development tambahan -- yang memang tujuan asset ini dibangun sekarang.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestration"))

import metrics_thresholds as mt  # noqa: E402
from kol_orchestration.assets.audience import (  # noqa: E402
    CONF_TERUKUR, UMUR_UNKNOWN, _hitung_per_akun, age_gender_breakdown,
    agregasi_bucket_age, bucket_umur_follower,
)

AKUN = "11111111-1111-1111-1111-111111111111"
TGL = date(2026, 9, 1)


# ===========================================================================
# Mapping bucket
# ===========================================================================
class TestMappingBucket:
    @pytest.mark.parametrize("mentah,harap", [
        ("13-17", "13-17"),
        ("18-24", "18-24"),
        ("25-34", "25-34"),
        ("35-44", "35-44"),
        ("45-54", "45+"),
        ("55-64", "45+"),
        ("65+", "45+"),
    ])
    def test_tujuh_bucket_instagram(self, mentah, harap):
        assert mt.normalisasi_bucket_platform(mentah) == harap

    def test_toleran_spasi_dan_huruf_besar(self):
        assert mt.normalisasi_bucket_platform(" 18-24 ") == "18-24"
        assert mt.normalisasi_bucket_platform("65+") == "45+"

    @pytest.mark.parametrize("asing", ["0-12", "70-79", "unknown", "", None, "abc"])
    def test_bucket_asing_jadi_none(self, asing):
        """None, BUKAN bucket terdekat -- lihat docstring fungsinya."""
        assert mt.normalisasi_bucket_platform(asing) is None

    def test_semua_hasil_ada_di_bucket_discovery(self):
        for mentah in mt.PETA_BUCKET_PLATFORM:
            assert mt.normalisasi_bucket_platform(mentah) in mt.BUCKET_AGE

    def test_lima_bucket_discovery_semuanya_terjangkau(self):
        """Tiap chip di UI harus bisa dihasilkan; chip yang mustahil terisi
        adalah chip yang menyesatkan."""
        hasil = {mt.normalisasi_bucket_platform(k)
                 for k in mt.PETA_BUCKET_PLATFORM}
        assert hasil == set(mt.BUCKET_AGE)


# ===========================================================================
# Agregasi -- bagian yang mengubah angka
# ===========================================================================
class TestAgregasi:
    def test_45plus_dijumlahkan_bukan_ditimpa(self):
        """Bug yang paling mahal kalau terlewat: audiens tua hilang diam-diam.

        TIGA bucket mentah runtuh jadi satu sekarang (dulu dua), jadi ada dua
        kesempatan untuk saling menimpa, bukan satu."""
        mentah = [
            (AKUN, "instagram", TGL, "45-54", 200),
            (AKUN, "instagram", TGL, "55-64", 300),
            (AKUN, "instagram", TGL, "65+", 120),
        ]
        hasil, _ = agregasi_bucket_age(mentah)
        assert hasil == {(AKUN, "instagram", TGL, "45+"): 620.0}

    def test_total_terjaga(self):
        """Jumlah seluruh bucket sesudah pemetaan harus sama dengan sebelumnya."""
        mentah = [
            (AKUN, "instagram", TGL, "13-17", 10),
            (AKUN, "instagram", TGL, "18-24", 500),
            (AKUN, "instagram", TGL, "25-34", 300),
            (AKUN, "instagram", TGL, "35-44", 120),
            (AKUN, "instagram", TGL, "45-54", 50),
            (AKUN, "instagram", TGL, "55-64", 15),
            (AKUN, "instagram", TGL, "65+", 5),
        ]
        hasil, _ = agregasi_bucket_age(mentah)
        assert sum(hasil.values()) == sum(m[4] for m in mentah)
        assert len(hasil) == 5

    def test_bucket_asing_dilewati_dan_dihitung(self):
        mentah = [
            (AKUN, "instagram", TGL, "18-24", 100),
            (AKUN, "instagram", TGL, "0-12", 7),
            (AKUN, "instagram", TGL, "0-12", 3),
        ]
        hasil, tak_dikenal = agregasi_bucket_age(mentah)
        assert hasil == {(AKUN, "instagram", TGL, "18-24"): 100.0}
        assert dict(tak_dikenal) == {"0-12": 2}

    def test_nilai_null_dilewati(self):
        """NULL berarti tidak diukur; menulisnya sebagai 0 adalah klaim berbeda."""
        mentah = [(AKUN, "instagram", TGL, "18-24", None)]
        hasil, _ = agregasi_bucket_age(mentah)
        assert hasil == {}

    def test_akun_platform_tanggal_tidak_tercampur(self):
        lain = "22222222-2222-2222-2222-222222222222"
        mentah = [
            (AKUN, "instagram", TGL, "18-24", 100),
            (lain, "instagram", TGL, "18-24", 200),
            (AKUN, "tiktok", TGL, "18-24", 300),
            (AKUN, "instagram", date(2026, 9, 2), "18-24", 400),
        ]
        hasil, _ = agregasi_bucket_age(mentah)
        assert len(hasil) == 4
        assert hasil[(AKUN, "instagram", TGL, "18-24")] == 100.0

    def test_kosong_menghasilkan_kosong(self):
        """Sumber kosong -> tidak ada baris. Tidak ada placeholder, tidak ada nol."""
        hasil, tak_dikenal = agregasi_bucket_age([])
        assert hasil == {}
        assert dict(tak_dikenal) == {}


class TestPenandaTerukur:
    def test_confidence_tanpa_awalan_inferred(self):
        """Jalur A terukur; jalur B inferensi. Kalau penanda ini ikut berawalan
        `inferred_`, hilir tidak lagi bisa membedakan angka Insights dari
        angka turunan -- kesalahan yang tidak bisa diperbaiki di hilir."""
        assert CONF_TERUKUR == "measured"
        assert not CONF_TERUKUR.startswith("inferred_")


# ===========================================================================
# Predikat filter Discovery
# ===========================================================================
class TestPredikatFilter:
    def test_mode_tidak_sah_ditolak(self):
        with pytest.raises(ValueError):
            mt.sql_filter_audience_age_band(mode="terserah")

    def test_param_null_berarti_tidak_menyaring(self):
        for sql in (mt.sql_filter_audience_age_band(),
                    mt.sql_filter_audience_age_band(mode="any"),
                    mt.sql_filter_creator_age_band()):
            assert "IS NULL OR" in sql

    def test_dua_filter_umur_menyentuh_tabel_yang_berbeda(self):
        """Age Kreator dan Age Audiens tidak boleh tertukar sumbernya."""
        kreator = mt.sql_filter_creator_age_band()
        audiens = mt.sql_filter_audience_age_band()
        assert "creator_age_band" in kreator
        assert "audience_demographics_daily" not in kreator
        assert "audience_demographics_daily" in audiens
        assert "creator_age_band" not in audiens

    def test_filter_audiens_hanya_baris_age(self):
        """Tabelnya juga berisi baris gender dari jalur B; filter tidak boleh
        ikut membacanya."""
        for mode in ("dominant", "any"):
            assert "audience_type = 'age'" in mt.sql_filter_audience_age_band(mode=mode)

    def test_dominan_memakai_tanggal_terbaru(self):
        sql = mt.sql_filter_audience_age_band(mode="dominant")
        assert "max(ad2.audience_date)" in sql
        assert "LIMIT 1" in sql


# ===========================================================================
# JALUR B -- umur audiens dari BIO FOLLOWER
# ===========================================================================
# Ini bagian yang benar-benar menghasilkan angka hari ini. Jalur A (Insights)
# masih 0 baris; jalur inilah yang mengisi `age_gender_breakdown` dan baris
# `audience_type='age'` di L2.
#
# Yang dijaga di sini ADA DUA, dan yang kedua lebih penting daripada yang
# pertama:
#
#   1. umur yang eksplisit memang tertangkap
#   2. umur yang TIDAK eksplisit tidak pernah dikarang -- termasuk saat
#      godaannya paling besar, yaitu ketika liputan datanya nyaris nol
TAHUN = 2026


def _follower(nama, bio, username="x"):
    """Satu baris `SQL_FOLLOWER`, dalam urutan kolom yang sama persis."""
    return ("sid", "instagram", TGL, nama, bio, username,
            False, False, 100, 50, None, None)


class TestUmurDariBioFollower:
    @pytest.mark.parametrize("bio,band", [
        ("mahasiswa | umur 21 | bandung", "18-24"),
        ("usia 30 tahun, ibu satu anak", "25-34"),
        ("lahir 1990 di solo", "35-44"),
        ("foodie, 52 years old", "45+"),
        # SENGAJA tanpa kata 'anak': bio seperti "anak SMA 16 y.o" DIVETO,
        # dan itu benar -- pola yang sama menahan "anak usia 5 tahun" milik
        # orang tua yang menulis umur ANAKNYA. Harganya nyata (pelajar yang
        # menyebut dirinya 'anak SMA' ikut tertolak) dan dibayar dengan sadar.
        ("pelajar | 16 y.o | jakarta", "13-17"),
    ])
    def test_pernyataan_eksplisit_tertangkap(self, bio, band):
        assert bucket_umur_follower(bio, TAHUN)[0] == band

    @pytest.mark.parametrize("bio", [
        None, "", "   ",
        "jualan baju sejak 2016",              # tahun BERDIRI usaha
        "juara 1 lomba 2019",                  # tahun PENGHARGAAN
        "wa 0815-1986-4471",                   # potongan NOMOR TELEPON
        "20 thn bantu ribuan klien",           # tahun PENGALAMAN
        "anak usia 5 tahun",                   # umur ORANG LAIN
        "trip ke korea mei 2026",              # jadwal PERJALANAN
    ])
    def test_tidak_pernah_mengarang(self, bio):
        """Bio follower memuat kebisingan yang persis sama dengan bio kreator.

        Kalau salah satu baris di sini mulai menghasilkan umur, artinya
        extractor-nya dilonggarkan -- dan sebaran umur audiens seluruh
        database jadi karangan.
        """
        assert bucket_umur_follower(bio, TAHUN) == (UMUR_UNKNOWN, None)

    def test_username_tidak_pernah_dibaca(self):
        """Angka di belakang username adalah nomor punggung, tanggal
        pernikahan, dan angka hoki -- bukan tahun lahir."""
        agg = _hitung_per_akun([_follower("Bepe", "halo", "bepe20")], TAHUN)
        assert agg["umur"][UMUR_UNKNOWN] == 1

    def test_hasil_selalu_bucket_sah_atau_unknown(self):
        for bio in ("umur 13", "umur 80", "umur 12", "umur 81", "halo"):
            band, _ = bucket_umur_follower(bio, TAHUN)
            assert band in set(mt.BUCKET_AGE) | {UMUR_UNKNOWN}

    def test_tahun_acuan_dihormati(self):
        """Umur dari tahun lahir bergeser; band-nya harus ikut bergeser."""
        assert bucket_umur_follower("lahir 1999", 2026)[0] == "25-34"
        assert bucket_umur_follower("lahir 1999", 2020)[0] == "18-24"


class TestAgregasiPerAkun:
    def test_semua_bucket_hadir_walau_nol(self):
        """Bucket yang ABSEN terbaca 'belum dihitung'; bucket bernilai 0
        terbaca 'dihitung, tidak ada satu pun'. Yang kedua yang benar."""
        agg = _hitung_per_akun([_follower("A", "umur 21")], TAHUN)
        for b in mt.BUCKET_AGE:
            assert b in agg["umur"]

    def test_penyebut_utuh(self):
        """Jumlah seluruh bucket + unknown harus sama dengan jumlah follower.
        Kalau tidak, ada follower yang hilang dari sebaran."""
        baris = [_follower("A", "umur 21"), _follower("B", "sejak 2016"),
                 _follower("C", None), _follower("D", "lahir 1990")]
        agg = _hitung_per_akun(baris, TAHUN)
        assert sum(agg["umur"].values()) == len(baris)
        assert agg["umur"][UMUR_UNKNOWN] == 2

    def test_unknown_tidak_ikut_disilang_dengan_gender(self):
        """'umur tidak diketahui, gender perempuan' bukan kelompok umur."""
        agg = _hitung_per_akun([_follower("Siti", "halo")], TAHUN)
        assert UMUR_UNKNOWN not in agg["umur_gender"]


class TestBentukAgeGenderBreakdown:
    @staticmethod
    def _agg(*bios):
        return _hitung_per_akun([_follower("A", b) for b in bios], TAHUN)

    def test_penyebut_ikut_diterbitkan(self):
        """Tanpa ini, {'18-24': 1} terbaca sebagai 'audiensnya 100% 18-24'."""
        j = age_gender_breakdown(self._agg("umur 21", "halo", "halo", "halo"))
        assert j["followers_analyzed"] == 4
        assert j["age_known"] == 1
        assert j["age_unknown"] == 3
        assert j["coverage_pct"] == 25.0

    def test_kelima_bucket_selalu_ada(self):
        j = age_gender_breakdown(self._agg("halo"))
        for b in mt.BUCKET_AGE:
            assert b in j["age"]
        assert j["age"][UMUR_UNKNOWN] == 1

    def test_age_top_tidak_pernah_unknown(self):
        """`unknown` mayoritas mutlak di data nyata. Kalau ia boleh jadi
        `age_top`, tiap akun akan melaporkan umur audiens 'unknown' seolah itu
        jawaban."""
        j = age_gender_breakdown(self._agg("umur 21", "halo", "halo", "halo"))
        assert j["age_top"] == "18-24"

    def test_age_top_none_kalau_tidak_ada_yang_diketahui(self):
        j = age_gender_breakdown(self._agg("halo", "halo"))
        assert j["age_top"] is None
        assert j["coverage_pct"] == 0.0

    def test_tidak_ada_follower_sama_sekali(self):
        j = age_gender_breakdown({"n": 0, "umur": {}, "umur_conf": {},
                                  "umur_gender": {}})
        assert j["coverage_pct"] is None
        assert j["age_top"] is None

    def test_confidence_berawalan_inferred(self):
        """Turunan tidak boleh menyamar jadi angka Insights."""
        j = age_gender_breakdown(self._agg("umur 21"))
        for v in j["confidence"].values():
            assert v.startswith("inferred_")
            assert v != CONF_TERUKUR

    def test_age_top_deterministik_saat_seri(self):
        """Dua bucket berjumlah sama harus selalu menghasilkan pemenang yang
        sama, kalau tidak hasil filter berubah antar pemanggilan."""
        agg = self._agg("umur 21", "lahir 1990")
        assert {age_gender_breakdown(agg)["age_top"] for _ in range(20)} == {"18-24"}


class TestUmurKreatorBukanProxyUmurAudiens:
    def test_bio_kreator_tidak_bocor_ke_sebaran_audiens(self):
        """Agregasi audiens hanya boleh melihat bio FOLLOWER.

        "Kreatornya 24, jadi audiensnya 18-24" adalah asumsi bisnis, bukan
        pengukuran. Tidak ada jalur di `_hitung_per_akun` yang menerima bio
        kreator, dan test ini yang menahannya supaya tetap begitu.
        """
        agg = _hitung_per_akun([_follower("Follower", None)], TAHUN)
        assert agg["umur"][UMUR_UNKNOWN] == 1
        assert all(v == 0 for k, v in agg["umur"].items() if k != UMUR_UNKNOWN)


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


class TestSQLSah:
    """Predikatnya dijalankan APA ADANYA supaya salah ketik SQL ketahuan di
    sini, bukan saat sumbernya akhirnya menyala berbulan-bulan lagi."""

    @pytest.mark.parametrize("mode", ["dominant", "any"])
    def test_predikat_audiens_dijalankan(self, conn, mode):
        sql = mt.sql_filter_audience_age_band(
            param="%(band)s", kolom_akun="x.social_account_id", mode=mode)
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT count(*) FROM (SELECT NULL::uuid AS social_account_id) x "
                f"WHERE {sql}", {"band": "18-24"})
            assert cur.fetchone()[0] == 0

    def test_predikat_audiens_null_meloloskan_semua(self, conn):
        sql = mt.sql_filter_audience_age_band(
            param="%(band)s", kolom_akun="x.social_account_id")
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT count(*) FROM (SELECT NULL::uuid AS social_account_id) x "
                f"WHERE {sql}", {"band": None})
            assert cur.fetchone()[0] == 1

    def test_query_kesiapan_dijalankan(self, conn):
        """Kesiapan filter ditentukan DATA, bukan flag yang harus diingat
        seseorang untuk dimatikan lagi nanti."""
        with conn.cursor() as cur:
            cur.execute(mt.sql_audience_age_siap())
            assert cur.fetchone()[0] in (True, False)

    def test_kesiapan_tidak_dihitung_dari_baris_unknown(self, conn):
        """Baris `unknown` ada untuk hampir setiap akun dan tidak bisa
        dicocokkan dengan chip mana pun. Kalau ia ikut dihitung, kontrol UI
        menyala di atas tabel yang -- dari sudut pandang filter -- kosong,
        dan tiap band yang dipilih mengembalikan nol KOL."""
        assert mt.AGE_UNKNOWN in mt.sql_audience_age_siap()
        with conn.cursor() as cur:
            cur.execute(mt.sql_audience_age_siap())
            siap = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM l2_gold.audience_demographics_daily "
                        "WHERE audience_type='age' AND dimension_key <> %s "
                        "AND audience_count > 0", (mt.AGE_UNKNOWN,))
            assert siap == (cur.fetchone()[0] > 0)

    def test_sumber_terukur_masih_kosong(self, conn):
        """Mengunci fakta yang jadi alasan jalur A masih menunggu.

        Dulu test ini menuntut `audience_type='age'` NOL baris seluruhnya.
        Itu tidak lagi benar dan tidak lagi berguna: jalur bio-follower
        sekarang menulis baris `age` berawalan `inferred_`, jadi tabelnya
        memang berisi. Yang masih harus nol adalah baris `measured` --
        itulah penanda Instagram Insights, dan itulah yang menentukan apakah
        jalur A sudah menyala.

        Kalau test ini GAGAL, itu kabar baik: Insights sudah masuk.
        """
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM l2_gold.audience_demographics_daily "
                        "WHERE audience_type = 'age' AND confidence = %s",
                        (CONF_TERUKUR,))
            n = cur.fetchone()[0]
        if n > 0:
            pytest.fail(
                f"audience_type='age' confidence='{CONF_TERUKUR}' sekarang {n} "
                "baris — Insights API sudah menyala. Perbarui test ini dan "
                "tinjau prioritas measured vs inferred di assets/audience.py.")

    def test_baris_age_hanya_memakai_lima_bucket_yang_sah(self, conn):
        """Apa pun yang menulisnya, dimension_key harus salah satu dari lima
        bucket atau `unknown`. Nilai di luar itu tidak akan pernah cocok
        dengan chip Discovery dan akan hilang dari hasil filter tanpa error."""
        sah = set(mt.BUCKET_AGE) | {mt.AGE_UNKNOWN}
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT dimension_key "
                        "FROM l2_gold.audience_demographics_daily "
                        "WHERE audience_type = 'age'")
            ada = {r[0] for r in cur.fetchall()}
        assert ada <= sah, f"dimension_key di luar bucket sah: {sorted(ada - sah)}"
