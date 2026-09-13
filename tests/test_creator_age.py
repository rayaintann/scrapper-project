"""Test Age KREATOR: extractor bio + bucket + paritas ambang Python vs DDL.

INI BUKAN TEST AGE AUDIENCE. Umur audiens diuji di `test_audience_age.py`.
Dua fitur, dua file, sengaja.

YANG PALING PENTING DI FILE INI ADALAH KELAS TEST NEGATIF
=========================================================
`TestFalsePositiveNyata` berisi bio ASLI dari `output/instagram_profiles_*.csv`
yang membuat parser naif salah. Tiap kasus di sana pernah benar-benar
menghasilkan umur karangan saat pola dikembangkan:

    `36th online`                      -> ordinal Inggris dibaca 36 tahun
    `20 thn bantu ribuan klien`        -> 20 tahun PENGALAMAN dibaca umur
    `+62 815-1986-4471`                -> potongan nomor HP dibaca lahir 1986
    `20 Nov 2017 / 17 Sept 2020`       -> tanggal lahir ANAK dibaca umur 8 thn

Kalau suatu saat seseorang melonggarkan `_VETO` atau menambah pola baru supaya
kolomnya "lebih terisi", test di kelas itulah yang gagal lebih dulu -- bukan
pengguna Discovery yang menemukan KOL 8 tahun di hasil filter.
"""

from __future__ import annotations

import csv
import glob
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import metrics_thresholds as mt  # noqa: E402
from creator_age_inference import (  # noqa: E402
    SUMBER_BIO, SUMBER_MANUAL, ekstrak_umur,
)

#: Dibekukan supaya umur yang diturunkan dari tahun lahir tidak berubah tiap
#: 1 Januari dan membuat test ini gagal sendiri tanpa ada yang mengubah kode.
TAHUN = 2026


# ===========================================================================
# Bucket -- dipakai bersama Age Audience, jadi batasnya diuji di sini juga
# ===========================================================================
class TestBucket:
    @pytest.mark.parametrize("umur,harap", [
        (13, "13-17"), (17, "13-17"),
        (18, "18-24"), (24, "18-24"),
        (25, "25-34"), (34, "25-34"),
        (35, "35-44"), (44, "35-44"),
        (45, "45+"), (54, "45+"),
        (55, "45+"), (65, "45+"), (80, "45+"),
    ])
    def test_batas_tiap_bucket(self, umur, harap):
        assert mt.bucket_age(umur) == harap

    @pytest.mark.parametrize("umur", [None, 0, 12, 81, 200, -5])
    def test_di_luar_rentang_jadi_none(self, umur):
        """None, BUKAN bucket terdekat. Lihat docstring `bucket_age`."""
        assert mt.bucket_age(umur) is None

    def test_tidak_ada_celah_antar_bucket(self):
        """Tiap umur sah harus masuk tepat satu bucket."""
        for umur in range(mt.AGE_MIN, mt.AGE_MAX + 1):
            assert mt.bucket_age(umur) in mt.BUCKET_AGE

    def test_urutan_bucket_monoton(self):
        """Umur naik tidak boleh membuat bucket mundur."""
        urut = [mt.BUCKET_AGE.index(mt.bucket_age(u))
                for u in range(mt.AGE_MIN, mt.AGE_MAX + 1)]
        assert urut == sorted(urut)

    def test_lima_bucket_sesuai_discovery(self):
        """Daftar FINAL. Lima, bukan enam.

        Versi pertama memisahkan `45-54` dan `55+` karena itu bentuk mentah
        Instagram Insights. Spesifikasi Discovery yang final memakai satu
        bucket teratas `45+`; migration 043 yang meruntuhkannya di database.
        """
        assert mt.BUCKET_AGE == ("13-17", "18-24", "25-34", "35-44", "45+")

    def test_bucket_lama_tidak_bisa_muncul_lagi(self):
        """Penjaga regresi: kalau seseorang mengembalikan enam bucket, umur 55
        akan kembali menghasilkan '55+' dan menabrak CHECK migration 043."""
        hasil = {mt.bucket_age(u) for u in range(mt.AGE_MIN, mt.AGE_MAX + 1)}
        assert "45-54" not in hasil
        assert "55+" not in hasil

    def test_unknown_bukan_anggota_bucket(self):
        """`unknown` adalah PENYEBUT, bukan kelompok umur. Kalau ia masuk
        daftar bucket, ia akan muncul sebagai chip di UI dan bisa terpilih
        sebagai 'bucket dominan' -- dua hal yang sama-sama salah."""
        assert mt.AGE_UNKNOWN not in mt.BUCKET_AGE


# ===========================================================================
# POSITIF -- pernyataan eksplisit yang memang harus tertangkap
# ===========================================================================
class TestPernyataanEksplisit:
    @pytest.mark.parametrize("bio,umur", [
        ("Content creator | umur 24 | Jakarta", 24),
        ("usia 31 tahun, ibu dua anak", 31),
        ("beauty enthusiast, age: 19", 19),
        ("27 y.o | Bandung", 27),
        ("skincare junkie 22yo", 22),
        ("travel blogger, 45 years old", 45),
    ])
    def test_umur_langsung(self, bio, umur):
        h = ekstrak_umur(bio, tahun_acuan=TAHUN)
        assert h.umur == umur
        assert h.source == SUMBER_BIO
        assert h.band == mt.bucket_age(umur)

    @pytest.mark.parametrize("bio,umur,tahun_lahir", [
        ("Lifestyle blogger, lahir 1998", 28, 1998),
        ("foodie | born 1995 | Surabaya", 31, 1995),
        ("traveller | born 15/08/1990 | Bali", 36, 1990),
    ])
    def test_tahun_lahir(self, bio, umur, tahun_lahir):
        h = ekstrak_umur(bio, tahun_acuan=TAHUN)
        assert h.umur == umur
        assert h.tahun_lahir == tahun_lahir

    def test_umur_langsung_tidak_menebak_tahun_lahir(self):
        """"umur 24" tidak menentukan tahun lahir -- harus None, bukan tebakan.

        Orangnya bisa sudah atau belum ulang tahun tahun ini; menuliskan
        salah satunya berarti mengarang presisi yang tidak ada di sumbernya.
        """
        h = ekstrak_umur("umur 24", tahun_acuan=TAHUN)
        assert h.umur == 24
        assert h.tahun_lahir is None

    def test_confidence_high_untuk_kata_kunci_tegas(self):
        assert ekstrak_umur("umur 24", tahun_acuan=TAHUN).confidence == "high"
        assert ekstrak_umur("lahir 1998", tahun_acuan=TAHUN).confidence == "high"

    def test_confidence_medium_untuk_satuan_tahun(self):
        """`21 tahun` lebih rawan salah baca daripada `umur 21`."""
        assert ekstrak_umur("Mahasiswa 21 tahun berbagi tips",
                            tahun_acuan=TAHUN).confidence == "medium"


# ===========================================================================
# NEGATIF -- bio ASLI yang pernah menghasilkan umur karangan
# ===========================================================================
class TestFalsePositiveNyata:
    @pytest.mark.parametrize("nama,bio", [
        ("ordinal inggris",
         "Your 36th online BUDHE SAWO MATANG COOL TONE"),
        ("tahun pengalaman",
         "20 thn bantu ribuan klien hadapi krisis hubungan & pernikahan"),
        ("tahun penghargaan",
         "2nd Winner IMAE Beauty Vlogger 2018 Inquiries : +62815"),
        ("tahun penghargaan 2",
         "Puteri Anak Indonesia Dki Little Miss Glamorous GMI 2021"),
        ("tahun berdiri brand",
         "Station For Your Mobility! Est 2018 Info/Iklan"),
        ("since brand",
         "Only serve quality since 1989, scratch resistant paint protection"),
        ("nomor telepon",
         "for business inquiries: DM or +62 815-1986-4471 (Aji)"),
        ("tanggal lahir anak",
         "Son & Daughter of Jesus 20 Nov 2017 17 Sept 2020 Gingersnaps"),
        ("jadwal perjalanan",
         "Korea Mei 2026 Thailand June 2026 Traveling Parenting is journey"),
        ("tahun telanjang",
         "1997 Business Inquiries ICA 085195911501 @bamama_universe"),
        ("angkatan sekolah",
         "Ketua Osis SMP Petra 1 Sby angkatan 2019"),
        ("tahun konten kreator",
         "Konten Kreator since 2017 Director of PT SAM"),
    ])
    def test_harus_unknown(self, nama, bio):
        h = ekstrak_umur(bio, tahun_acuan=TAHUN)
        assert h.umur is None, f"{nama}: seharusnya unknown, dapat {h.umur} ({h.alasan})"
        assert h.band is None
        assert h.source is None

    def test_umur_mustahil_ditolak(self):
        """Angka di luar 13..80 bukan umur, meski kata kuncinya benar."""
        assert ekstrak_umur("umur 5 tahun", tahun_acuan=TAHUN).umur is None
        assert ekstrak_umur("usia 99", tahun_acuan=TAHUN).umur is None

    def test_bio_kosong(self):
        for bio in (None, "", "   "):
            assert ekstrak_umur(bio, tahun_acuan=TAHUN).umur is None

    def test_username_tidak_dipakai(self):
        """Angka di username (nomor punggung, tanggal nikah) bukan umur.

        Diuji sebagai kontrak API: `ekstrak_umur` tidak menerima username sama
        sekali, jadi tidak ada jalan bagi angka itu untuk ikut terbaca.
        """
        import inspect
        params = inspect.signature(ekstrak_umur).parameters
        assert "username" not in params
        assert "full_name" not in params


class TestBuktiBertentangan:
    def test_dua_umur_berbeda_jadi_unknown(self):
        """Aturan 3: bertentangan -> unknown, bukan "yang ketemu duluan"."""
        h = ekstrak_umur("umur 24 tapi juga 41 y.o", tahun_acuan=TAHUN)
        assert h.umur is None
        assert "bertentangan" in h.alasan

    def test_selisih_satu_tahun_masih_diterima(self):
        """`umur 27` + `lahir 1998` (=28) bisa dua-duanya benar."""
        h = ekstrak_umur("umur 27, lahir 1998", tahun_acuan=TAHUN)
        assert h.umur is not None
        # Yang menang harus yang membawa tahun lahir -- nilainya tidak basi.
        assert h.tahun_lahir == 1998


class TestDeterminisme:
    def test_input_sama_output_sama(self):
        bio = "Content creator | umur 24 | Jakarta"
        hasil = {ekstrak_umur(bio, tahun_acuan=TAHUN).umur for _ in range(50)}
        assert hasil == {24}

    def test_tahun_acuan_menggeser_umur_bukan_tahun_lahir(self):
        a = ekstrak_umur("lahir 1998", tahun_acuan=2026)
        b = ekstrak_umur("lahir 1998", tahun_acuan=2030)
        assert (a.umur, b.umur) == (28, 32)
        assert a.tahun_lahir == b.tahun_lahir == 1998


# ===========================================================================
# Paritas ambang: Python vs CHECK di migration 042
# ===========================================================================
class TestParitasAmbang:
    def test_batas_ddl_sama_dengan_python(self):
        """CHECK di 042 menulis 13..80 sebagai literal; keduanya harus sama.

        DDL tidak bisa mengimpor Python, jadi angkanya memang diulang. Test
        ini yang menahan keduanya supaya tidak bergeser sendiri-sendiri.
        """
        sql = (ROOT / "migrations" / "042_creator_age_columns.sql").read_text(
            encoding="utf-8")
        assert f"BETWEEN {mt.AGE_MIN} AND {mt.AGE_MAX}" in sql

    def test_daftar_band_ddl_sama_dengan_python(self):
        """CHECK yang BERLAKU ada di 043, bukan 042.

        042 membuat kolomnya dengan daftar enam bucket; 043 menggantinya
        dengan lima. Test ini menunjuk 043 karena itulah constraint yang
        benar-benar terpasang di database sesudah kedua migration jalan.
        """
        sql = (ROOT / "migrations" / "043_age_band_five_buckets.sql").read_text(
            encoding="utf-8")
        daftar = "','".join(mt.BUCKET_AGE)
        assert f"('{daftar}')" in sql, (
            "daftar bucket di CHECK migration 043 tidak sama persis dengan "
            f"metrics_thresholds.BUCKET_AGE: {mt.BUCKET_AGE}")

    def test_ddl_043_tidak_lagi_mengizinkan_bucket_lama(self):
        """CHECK-nya saja yang diperiksa, bukan seluruh file.

        `'45-54'` dan `'55+'` memang MASIH muncul di file itu -- di komentar,
        di UPDATE backfill, dan di blok verifikasi -- dan semuanya memang
        harus. Yang tidak boleh lagi memuatnya adalah daftar nilai yang
        diizinkan constraint.
        """
        sql = (ROOT / "migrations" / "043_age_band_five_buckets.sql").read_text(
            encoding="utf-8")
        m = re.search(
            r"CHECK\s*\(creator_age_band IS NULL OR creator_age_band IN\s*\(([^)]*)\)",
            sql)
        assert m, "CHECK ck_kpc_creator_age_band tidak ditemukan di 043"
        daftar = m.group(1)
        for band in mt.BUCKET_AGE:
            assert f"'{band}'" in daftar
        assert "'45-54'" not in daftar
        assert "'55+'" not in daftar

    def test_sumber_manual_terdaftar_di_ddl(self):
        sql = (ROOT / "migrations" / "042_creator_age_columns.sql").read_text(
            encoding="utf-8")
        assert f"'{SUMBER_BIO}'" in sql
        assert f"'{SUMBER_MANUAL}'" in sql


# ===========================================================================
# Terhadap data NYATA -- menjaga janji "tidak mengarang"
# ===========================================================================
class TestDataNyata:
    @staticmethod
    def _bio_asli() -> dict[str, str]:
        bios: dict[str, str] = {}
        pola = [str(ROOT / "output" / "instagram_profiles_*.csv"),
                str(ROOT / "output" / "tiktok_profiles_*.csv")]
        for p in pola:
            for f in glob.glob(p):
                with open(f, encoding="utf-8-sig") as fh:
                    for r in csv.DictReader(fh):
                        u = (r.get("username") or "").strip().lower()
                        b = (r.get("biography") or r.get("signature") or "").strip()
                        if u and b:
                            bios[u] = b
        return bios

    def test_tidak_mengarang_umur_pada_bio_asli(self):
        """Tiap umur yang DIKELUARKAN pada data asli harus bisa dipertanggungjawabkan.

        Test ini tidak menuntut jumlah tertentu -- kalau suatu hari ada bio
        yang benar-benar menyatakan umur, ia BOLEH lolos. Yang dijaga adalah
        bentuk hasilnya: tiap hasil wajib membawa source, confidence, band
        yang konsisten, dan umur di dalam rentang sah.
        """
        bios = self._bio_asli()
        if not bios:
            pytest.skip("tidak ada CSV profil di output/")

        for user, bio in bios.items():
            h = ekstrak_umur(bio, tahun_acuan=TAHUN)
            if not h.diketahui:
                continue
            assert mt.AGE_MIN <= h.umur <= mt.AGE_MAX, f"@{user}: umur {h.umur}"
            assert h.band == mt.bucket_age(h.umur), f"@{user}: band tidak konsisten"
            assert h.source == SUMBER_BIO, f"@{user}: source kosong"
            assert h.confidence in ("high", "medium", "low"), f"@{user}"

    def test_mayoritas_unknown_pada_bio_asli(self):
        """Sinyal umur di bio memang hampir tidak ada; ini mengunci fakta itu.

        Ambangnya sengaja longgar (>=95% unknown), bukan "tepat 0 ditemukan":
        menambah SATU bio yang benar-benar menyatakan umur ke dataset tidak
        boleh membuat test ini gagal. Yang ditangkap adalah perubahan besar --
        mis. seseorang menambahkan heuristik "tahun 4-digit = tahun lahir",
        yang akan langsung menjatuhkan angka ini jauh di bawah ambang.
        """
        bios = self._bio_asli()
        if not bios:
            pytest.skip("tidak ada CSV profil di output/")

        diketahui = sum(1 for b in bios.values()
                        if ekstrak_umur(b, tahun_acuan=TAHUN).diketahui)
        rasio_unknown = (len(bios) - diketahui) / len(bios)
        assert rasio_unknown >= 0.95, (
            f"hanya {rasio_unknown:.1%} unknown dari {len(bios)} bio asli — "
            f"{diketahui} umur ditemukan. Curigai heuristik yang terlalu "
            f"longgar: tahun di bio hanya ~3% benar sebagai tahun lahir.")
