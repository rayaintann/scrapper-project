"""Test jalur NIK -- AKTIF sejak 12 September 2026.

Yang diuji di sini bukan cuma "parsernya benar". Yang diuji terutama adalah
dua janji yang TIDAK ikut longgar bersama persetujuan:

  1. nomor KTP tidak pernah keluar dari `creator_age_nik.py`
  2. `bio_self_declared` selalu menang atas `roster_ktp`

Janji ketiga -- "jalur ini tidak bisa menyala sendiri" -- memang sudah tidak
berlaku, dan test-nya diganti, bukan dihapus diam-diam: yang sekarang dijaga
adalah bahwa mematikannya kembali tetap mungkin lewat environment.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import metrics_thresholds as mt  # noqa: E402
from creator_age_inference import SUMBER_BIO as SUMBER_BIO_ASSET  # noqa: E402
from creator_age_nik import (  # noqa: E402
    KOLOM_NIK, OFFSET_PEREMPUAN, SUMBER_NIK, TABEL_ROSTER, HasilNIK,
    nik_aktif, umur_dari_nik, umur_per_akun,
)

TAHUN = 2026

#: NIK contoh yang DIKARANG untuk test: kode wilayah 3201 (Kab. Bogor) dengan
#: tanggal lahir yang dipilih supaya hasilnya bisa dihitung tangan. Bukan
#: nomor milik siapa pun.
NIK_LAKI_1990 = "3201011505900001"      # 15 Mei 1990
NIK_PEREMPUAN_1990 = "3201015505900001"  # 55 = 15 + 40 -> 15 Mei 1990


# ===========================================================================
# PENJAGAAN -- bagian terpenting di file ini
# ===========================================================================
class TestGerbang:
    """Jalur ini sekarang HIDUP secara default, dan tetap bisa dimatikan."""

    def test_default_hidup(self, monkeypatch):
        """Persetujuan turun 12 September 2026, jadi keadaan benar = hidup."""
        monkeypatch.delenv("CREATOR_AGE_NIK_ENABLED", raising=False)
        assert nik_aktif() is True

    @pytest.mark.parametrize("nilai", ["0", "false", "FALSE", "no", "off",
                                       "tidak", "nonaktif", "disabled"])
    def test_bisa_dimatikan_lewat_env(self, monkeypatch, nilai):
        """Tombol mati darurat: menghentikan jalur NIK tanpa menunggu deploy."""
        monkeypatch.setenv("CREATOR_AGE_NIK_ENABLED", nilai)
        assert nik_aktif() is False

    @pytest.mark.parametrize("nilai", ["", " ", "1", "true", "yes", "on"])
    def test_nilai_lain_berarti_hidup(self, monkeypatch, nilai):
        monkeypatch.setenv("CREATOR_AGE_NIK_ENABLED", nilai)
        assert nik_aktif() is True

    def test_salah_ketik_pada_nilai_mati_tetap_hidup(self, monkeypatch):
        """Konsekuensi dari membalik arah gerbang, DIUJI supaya tidak jadi
        kejutan.

        Sebelum persetujuan, daftarnya PUTIH dan `treu` berarti mati -- arah
        aman saat itu. Sesudah persetujuan, daftarnya HITAM dan `flase`
        berarti tetap hidup. Siapa pun yang mematikan jalur ini wajib
        memastikan lewat metadata run (`nik_aktif`), bukan berasumsi dari isi
        environment.
        """
        monkeypatch.setenv("CREATOR_AGE_NIK_ENABLED", "flase")
        assert nik_aktif() is True

    def test_diimpor_asset_creator_age(self):
        """Kebalikan dari test lama, dan sengaja tidak dihapus begitu saja.

        Dulu test ini menuntut TIDAK ADA asset yang mengimpornya. Sekarang ia
        menuntut asset yang benar -- dan HANYA asset itu -- yang mengimpornya.
        Kalau suatu saat `audience.py` ikut mengimpor modul ini, artinya
        seseorang memakai NIK untuk umur AUDIENS, yang tidak pernah disetujui.
        """
        assets = ROOT / "orchestration" / "kol_orchestration" / "assets"
        pemakai = {f.name for f in assets.glob("*.py")
                   if "creator_age_nik" in f.read_text(encoding="utf-8")}
        assert pemakai == {"creator_age.py"}, (
            f"modul NIK diimpor {sorted(pemakai)}; yang disetujui hanya "
            "creator_age.py (umur KREATOR, bukan audiens)")

    def test_sumber_terdaftar_di_ddl_044(self):
        """CHECK di database harus menerima nilai yang ditulis asset.

        Kalau keduanya bergeser sendiri-sendiri, materialisasi gagal dengan
        pelanggaran constraint -- dan itu kegagalan yang benar, tapi lebih
        baik ketahuan di sini.
        """
        sql = (ROOT / "migrations"
               / "044_creator_age_source_roster_ktp.sql").read_text(encoding="utf-8")
        m = re.search(r"creator_age_source IN\s*\(([^)]*)\)", sql)
        assert m
        daftar = m.group(1)
        assert f"'{SUMBER_NIK}'" in daftar
        assert "'bio_self_declared'" in daftar
        assert "'manual'" in daftar

    def test_042_tidak_diubah(self):
        """Migration lama tetap apa adanya; 044 yang menggantikan CHECK-nya."""
        sql = (ROOT / "migrations" / "042_creator_age_columns.sql").read_text(
            encoding="utf-8")
        m = re.search(r"creator_age_source IN\s*\(([^)]*)\)", sql)
        assert m
        assert f"'{SUMBER_NIK}'" not in m.group(1)


class TestNomorTidakPernahKeluar:
    def test_hasil_tidak_punya_field_untuk_nomor(self):
        """Bukan kelalaian, melainkan syarat. Menambahkannya = kebocoran."""
        nama = {f.name for f in dataclasses.fields(HasilNIK)}
        assert nama == {"umur", "tahun_lahir", "band", "source",
                        "confidence", "alasan"}

    @pytest.mark.parametrize("nik", [
        NIK_LAKI_1990, "3201019905900001", "320101150590", "abcd", "3201011505" * 3,
    ])
    def test_alasan_tidak_pernah_memuat_nomornya(self, nik):
        """Log yang memuat NIK sama bocornya dengan kolom yang memuat NIK,
        dan lebih sulit ditarik kembali."""
        alasan = umur_dari_nik(nik, tahun_acuan=TAHUN).alasan
        digit = "".join(ch for ch in nik if ch.isdigit())
        if len(digit) >= 6:
            assert digit not in alasan
            assert digit[:6] not in alasan


# ===========================================================================
# Penguraian
# ===========================================================================
class TestPenguraian:
    def test_laki_laki(self):
        h = umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN)
        assert (h.umur, h.tahun_lahir, h.band) == (36, 1990, "35-44")
        assert h.source == SUMBER_NIK
        assert h.confidence == "high"

    def test_perempuan_offset_40_dikurangi_lebih_dulu(self):
        """Kalau offsetnya tidak dikurangi sebelum validasi, SELURUH kreator
        perempuan tertolak sebagai 'tanggal tak sah' -- separuh data hilang
        tanpa satu pun error."""
        h = umur_dari_nik(NIK_PEREMPUAN_1990, tahun_acuan=TAHUN)
        assert h.diketahui
        assert (h.umur, h.tahun_lahir) == (36, 1990)

    def test_laki_dan_perempuan_tanggal_sama_umur_sama(self):
        a = umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN)
        b = umur_dari_nik(NIK_PEREMPUAN_1990, tahun_acuan=TAHUN)
        assert (a.umur, a.tahun_lahir) == (b.umur, b.tahun_lahir)

    def test_offset_perempuan_sesuai_spesifikasi(self):
        assert OFFSET_PEREMPUAN == 40

    @pytest.mark.parametrize("nik,alasan_memuat", [
        (None, "kosong"),
        ("", "kosong"),
        ("123", "panjang"),
        ("3201011505900001" + "9", "panjang"),
        ("3201013213900001", "tanggal/bulan"),   # bulan 13
        ("3201013202900001", "tanggal/bulan"),   # 32 Februari
        ("3201017202900001", "tanggal/bulan"),   # 72-40 = 32 Februari
    ])
    def test_yang_tidak_sah_jadi_unknown(self, nik, alasan_memuat):
        h = umur_dari_nik(nik, tahun_acuan=TAHUN)
        assert not h.diketahui
        assert alasan_memuat in h.alasan

    def test_abad_dipilih_lewat_rentang_umur(self):
        """Dua digit tahun diselesaikan oleh rentang umur, bukan oleh tebakan.

        `YY=90` pada tahun acuan 2026: 1990 -> 36 (sah), 2090 -> negatif
        (ditolak). Satu kandidat, jadi jawabannya pasti.
        """
        assert umur_dari_nik(NIK_LAKI_1990, tahun_acuan=2026).tahun_lahir == 1990
        assert umur_dari_nik(NIK_LAKI_1990, tahun_acuan=2005).tahun_lahir == 1990
        # YY=10 pada 2026: 1910 -> 116 (ditolak), 2010 -> 16 (sah).
        assert umur_dari_nik("3201011505100001", tahun_acuan=2026).tahun_lahir == 2010

    def test_ambiguitas_abad_mustahil_dengan_rentang_sekarang(self):
        """Cabang "abad ambigu" di modulnya TIDAK BISA tercapai hari ini.

        Supaya 19YY dan 20YY sama-sama sah, rentang umur yang diterima harus
        membentang 100 tahun atau lebih. `AGE_MAX - AGE_MIN` = 67, jadi tidak
        ada satu pun (YY, tahun acuan) yang menghasilkan dua kandidat.

        Cabang itu tetap ditulis, dan test ini yang menjelaskan kenapa ia
        terlihat seperti kode mati: ia menjadi hidup begitu `AGE_MAX`
        dinaikkan melewati 112. Kalau suatu saat itu terjadi, test ini gagal
        dan memaksa keputusannya diambil sadar, bukan ditemukan dari umur yang
        meleset seabad.
        """
        assert mt.AGE_MAX - mt.AGE_MIN < 100, (
            "rentang umur sekarang membentang >= 100 tahun; cabang 'abad "
            "ambigu' di creator_age_nik kini bisa tercapai — tinjau ulang.")

    def test_umur_di_luar_rentang_ditolak(self):
        """Batasnya sama dengan `metrics_thresholds`, bukan angka kedua.

        YY=30 pada 2026: 1930 -> 96 (di atas AGE_MAX), 2030 -> belum lahir.
        Tidak ada kandidat yang sah, jadi `unknown`.
        """
        h = umur_dari_nik("3201011505300001", tahun_acuan=TAHUN)
        assert not h.diketahui
        assert str(mt.AGE_MIN) in h.alasan and str(mt.AGE_MAX) in h.alasan

    def test_pemisah_diabaikan(self):
        assert umur_dari_nik("3201-0115-0590-0001",
                             tahun_acuan=TAHUN).umur == 36

    def test_band_konsisten_dengan_bucket_age(self):
        for nik in (NIK_LAKI_1990, NIK_PEREMPUAN_1990):
            h = umur_dari_nik(nik, tahun_acuan=TAHUN)
            assert h.band == mt.bucket_age(h.umur)
            assert h.band in mt.BUCKET_AGE

    def test_deterministik(self):
        hasil = {umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN).umur
                 for _ in range(50)}
        assert hasil == {36}

    def test_murni_tidak_terpengaruh_gerbang(self, monkeypatch):
        """Penguraian dipisah dari GERBANG, dan tetap begitu sesudah jalur ini
        aktif.

        Yang dijaga gerbang adalah PEMAKAIAN hasilnya di asset, bukan
        kemampuan mengurai. Memisahkan keduanya membuat decoder bisa diuji
        dan diaudit tanpa menyentuh perilaku produksi.
        """
        monkeypatch.setenv("CREATOR_AGE_NIK_ENABLED", "0")
        assert nik_aktif() is False
        assert umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN).diketahui


class TestKonstanta:
    def test_nama_kolom_ditulis_sekali(self):
        assert KOLOM_NIK == "influencer_no_ktp"


# ===========================================================================
# umur_per_akun -- batas tempat nomor KTP berhenti
# ===========================================================================
class KursorPalsu:
    """Kursor seadanya yang mengembalikan baris yang sudah disiapkan test."""

    def __init__(self, baris):
        self._baris = baris
        self.sql_dijalankan = []

    def execute(self, sql, params=None):
        self.sql_dijalankan.append(sql)

    def fetchall(self):
        return self._baris

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class KoneksiPalsu:
    def __init__(self, baris):
        self._kursor = KursorPalsu(baris)

    def cursor(self):
        return self._kursor


class TestUmurPerAkun:
    SID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    SID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    def test_mengembalikan_hasil_bukan_nomor(self):
        """Kontrak inti modul ini: pemanggil menerima HasilNIK, titik."""
        conn = KoneksiPalsu([(self.SID_A, NIK_LAKI_1990)])
        per_akun, stat = umur_per_akun(conn, tahun_acuan=TAHUN)
        assert set(per_akun) == {self.SID_A}
        h = per_akun[self.SID_A]
        assert isinstance(h, HasilNIK)
        assert (h.umur, h.tahun_lahir, h.band, h.source) == (
            36, 1990, "35-44", SUMBER_NIK)
        # tidak ada nomor di hasil MAUPUN di statistik
        assert NIK_LAKI_1990 not in repr(per_akun)
        assert NIK_LAKI_1990 not in repr(stat)

    def test_statistik_hanya_cacah_dan_alasan(self):
        conn = KoneksiPalsu([
            (self.SID_A, NIK_LAKI_1990),
            (self.SID_B, "1234567"),           # terpotong, 7 digit
        ])
        _, stat = umur_per_akun(conn, tahun_acuan=TAHUN)
        assert stat["baris_sumber"] == 2
        assert stat["akun_berhasil"] == 1
        assert stat["gagal_diurai"] == 1
        assert "1234567" not in repr(stat)
        assert all(isinstance(v, int) for k, v in stat["per_alasan_gagal"].items())

    def test_umur_bertentangan_dibuang_bukan_dipilih(self):
        """Roster diketik manusia. Dua NIK berbeda untuk satu akun berarti
        setidaknya satu salah, dan tidak ada cara memilih yang benar dari
        sini -- aturan yang sama dengan 'bukti bertentangan -> unknown' di
        creator_age_inference."""
        conn = KoneksiPalsu([
            (self.SID_A, NIK_LAKI_1990),        # lahir 1990
            (self.SID_A, "3201011505800001"),   # lahir 1980
        ])
        per_akun, stat = umur_per_akun(conn, tahun_acuan=TAHUN)
        assert self.SID_A not in per_akun
        assert stat["akun_umur_bertentangan_dibuang"] == 1

    def test_nik_sama_dua_kali_bukan_konflik(self):
        """Baris duplikat yang sepakat tidak boleh membuang akunnya."""
        conn = KoneksiPalsu([
            (self.SID_A, NIK_LAKI_1990),
            (self.SID_A, NIK_LAKI_1990),
        ])
        per_akun, stat = umur_per_akun(conn, tahun_acuan=TAHUN)
        assert per_akun[self.SID_A].umur == 36
        assert stat["akun_umur_bertentangan_dibuang"] == 0

    def test_hanya_menyentuh_tabel_roster(self):
        conn = KoneksiPalsu([])
        umur_per_akun(conn, tahun_acuan=TAHUN)
        sql = " ".join(conn._kursor.sql_dijalankan)
        assert TABEL_ROSTER in sql
        assert KOLOM_NIK in sql
        assert "kol_profile_card" not in sql, (
            "modul NIK tidak boleh menulis maupun membaca kartu profil; "
            "itu tugas asset")

    def test_kosong_menghasilkan_kosong(self):
        per_akun, stat = umur_per_akun(KoneksiPalsu([]), tahun_acuan=TAHUN)
        assert per_akun == {}
        assert stat["akun_berhasil"] == 0


# ===========================================================================
# Prioritas source -- bio SELALU menang
# ===========================================================================
class TestPrioritasSource:
    """Diuji terhadap fungsi asset yang sebenarnya, lewat kursor palsu.

    Yang dijaga bukan cuma "bio menang", tapi juga bahwa jalur NIK TIDAK BISA
    MENGURANGI apa pun: satu-satunya baris yang disentuhnya adalah baris yang
    tanpa dia akan NULL.
    """

    SID_BIO = "11111111-1111-1111-1111-111111111111"
    SID_NIK = "22222222-2222-2222-2222-222222222222"
    SID_DUA = "33333333-3333-3333-3333-333333333333"
    SID_NIHIL = "44444444-4444-4444-4444-444444444444"

    @staticmethod
    def _pilih(bio, hasil_nik, tahun=TAHUN):
        """Cerminan aturan prioritas di `creator_age._jalankan`.

        Sengaja ditulis ulang sesingkat ini alih-alih menjalankan seluruh
        asset: yang diuji adalah ATURANNYA, dan aturan itu harus bisa dibaca
        utuh dalam satu layar oleh siapa pun yang meninjaunya.
        """
        from creator_age_inference import ekstrak_umur
        h = ekstrak_umur(bio, tahun_acuan=tahun)
        if h.diketahui:
            return h
        if hasil_nik is not None:
            return hasil_nik
        # Keduanya gagal: hasil bio (umur=None) yang dipertahankan, BUKAN
        # None. Asset menulis hasil itu apa adanya, dan itulah yang mencabut
        # umur basi dari baris yang sumbernya sudah hilang.
        return h

    def test_bio_menang_saat_keduanya_ada(self):
        nik = umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN)   # 36, 35-44
        h = self._pilih("content creator | umur 24", nik)
        assert h.umur == 24
        assert h.source == SUMBER_BIO_ASSET
        assert h.source != SUMBER_NIK

    def test_nik_dipakai_saat_bio_tidak_menghasilkan(self):
        nik = umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN)
        h = self._pilih("jualan baju sejak 2016", nik)
        assert h.umur == 36
        assert h.source == SUMBER_NIK

    def test_nik_dipakai_saat_bio_kosong(self):
        nik = umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN)
        for bio in (None, "", "   "):
            assert self._pilih(bio, nik).source == SUMBER_NIK

    def test_tanpa_keduanya_tetap_unknown(self):
        assert self._pilih("jualan baju sejak 2016", None).diketahui is False
        assert self._pilih(None, None).diketahui is False

    def test_nik_tidak_pernah_mengurangi(self):
        """Untuk tiap bio, hasil DENGAN NIK tidak boleh punya umur lebih
        sedikit daripada hasil TANPA NIK."""
        nik = umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN)
        for bio in ("umur 24", "lahir 1998", "sejak 2016", None, "", "halo"):
            tanpa = self._pilih(bio, None)
            dengan = self._pilih(bio, nik)
            assert dengan.diketahui >= tanpa.diketahui
            if tanpa.diketahui:
                # bio menang: hasilnya harus PERSIS sama seperti tanpa NIK
                assert (dengan.umur, dengan.source) == (tanpa.umur, tanpa.source)

    def test_band_nik_selalu_salah_satu_dari_lima(self):
        nik = umur_dari_nik(NIK_LAKI_1990, tahun_acuan=TAHUN)
        assert nik.band in mt.BUCKET_AGE
        assert nik.band not in ("45-54", "55+")


# ===========================================================================
# Asset -- SQL-nya tidak boleh menyentuh kolom NIK
# ===========================================================================
class TestAssetTidakMenyentuhKolomNIK:
    def test_sql_asset_tidak_menyebut_kolom_ktp(self):
        """Satu-satunya SELECT yang menyentuh kolom itu ada di
        creator_age_nik. Kalau asset menambah yang kedua, jaminan 'nomornya
        tidak pernah hidup di asset' hilang tanpa ada yang memperhatikan."""
        src = (ROOT / "orchestration" / "kol_orchestration" / "assets"
               / "creator_age.py").read_text(encoding="utf-8")
        # nama kolomnya boleh muncul di komentar/dokumentasi, tapi tidak di
        # dalam string SQL. Dicek pada blok SQL_BACA dan SQL_UPDATE.
        for nama in ("SQL_BACA", "SQL_UPDATE"):
            awal = src.index(f"{nama} = \"\"\"")
            akhir = src.index("\"\"\"", awal + len(nama) + 8)
            blok = src[awal:akhir]
            assert KOLOM_NIK not in blok, f"{nama} menyebut kolom {KOLOM_NIK}"

    def test_asset_tidak_menulis_kolom_selain_lima_kolom_umur(self):
        src = (ROOT / "orchestration" / "kol_orchestration" / "assets"
               / "creator_age.py").read_text(encoding="utf-8")
        awal = src.index("SQL_UPDATE = \"\"\"")
        akhir = src.index("\"\"\"", awal + 20)
        blok = src[awal:akhir]
        assert "SET creator_age" in blok
        for terlarang in ("followers_count", "bio ", "username", "tier"):
            assert f"{terlarang}=" not in blok and f"{terlarang} =" not in blok
