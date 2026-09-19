"""Test Gender KREATOR: aturan konservatif, prioritas sumber, paritas DDL.

INI BUKAN TEST GENDER AUDIENCE. `audience_inference.tebak_gender()` tetap
dipakai untuk follower dan tidak diubah; kelas `TestBukanAudiens` menjaga
supaya modul/asset kreator tidak pernah membaca data audiens.

Contoh nama di sini adalah nama umum dari kamus, bukan akun tertentu.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestration"))

import audience_inference  # noqa: E402
from creator_gender_inference import (  # noqa: E402
    SUMBER_MANUAL, SUMBER_NAMA, SUMBER_ROSTER, gender_roster, pilih_gender,
    tebak_gender_kreator,
)

MIGRATION = ROOT / "migrations" / "051_creator_gender_columns.sql"
ASSET = ROOT / "orchestration" / "kol_orchestration" / "assets" / "creator_gender.py"
MODUL = ROOT / "creator_gender_inference.py"


class TestFemale:
    def test_nama_depan_wanita(self):
        h = tebak_gender_kreator("Rina Putri", "rinaputri")
        assert (h.nilai, h.source) == ("female", SUMBER_NAMA)

    def test_sufiks_wanita(self):
        assert tebak_gender_kreator(None, "sriwahyuningsih").nilai == "female"

    def test_simbol_wanita(self):
        h = tebak_gender_kreator("Kiki ♀", None)
        assert (h.nilai, h.confidence) == ("female", "high")


class TestMaleHanyaSinyalKuat:
    def test_nama_depan_pria_persis(self):
        h = tebak_gender_kreator("Andi Pratama", "andipratama")
        assert (h.nilai, h.confidence) == ("male", "medium")

    def test_awalan_pria(self):
        assert tebak_gender_kreator("Muhammad Rizki", None).nilai == "male"

    @pytest.mark.parametrize("display_name,username", [
        (None, "kurniawan"),          # sufiks pria saja: 47,6% benar di roster
        ("Kiki Hartono", None),       # sufiks pria = nama keluarga
        ("Kiki Budi", None),          # token pria bukan kata pertama
        (None, "kiki_budi"),          # token pria di username
        ("Mas Kiki", None),           # sapaan pria: 1 dari 5 benar
    ])
    def test_sinyal_pria_lemah_tidak_menghasilkan_male(self, display_name, username):
        assert tebak_gender_kreator(display_name, username).nilai is None


class TestUnknown:
    def test_konflik(self):
        # nama depan pria + nama wanita -> dua arah -> unknown
        assert tebak_gender_kreator("Andi Rina", None).nilai is None

    @pytest.mark.parametrize("display_name,username", [
        ("Rina & Andi", None),
        ("Rina dan Andi", None),
        ("Rina Family", None),
        (None, "rina_twins"),
    ])
    def test_grup_pasangan(self, display_name, username):
        assert tebak_gender_kreator(display_name, username).nilai is None

    def test_bisnis(self):
        assert tebak_gender_kreator("Rina Shop", "rinashop").nilai is None

    def test_tanpa_nama(self):
        assert tebak_gender_kreator(None, None).nilai is None
        assert tebak_gender_kreator("", "").nilai is None

    def test_tidak_menebak_dari_handle_acak(self):
        assert tebak_gender_kreator("xyz", "qwerty123").nilai is None


class TestRosterDanPrioritas:
    @pytest.mark.parametrize("kode,harap", [
        ("1", "female"), ("0", "male"), (" 1 ", "female"),
        (None, None), ("", None), ("bca", None), ("2", None),
    ])
    def test_mapping_roster(self, kode, harap):
        assert gender_roster(kode) == harap

    def test_roster_menang_atas_inference(self):
        # nama jelas wanita, roster bilang 0 -> roster yang dipakai
        h = pilih_gender("0", "Rina Putri", "rinaputri")
        assert (h.nilai, h.source) == ("male", SUMBER_ROSTER)

    def test_inference_hanya_kalau_roster_kosong(self):
        h = pilih_gender(None, "Rina Putri", "rinaputri")
        assert (h.nilai, h.source) == ("female", SUMBER_NAMA)
        h = pilih_gender("bca", "Rina Putri", "rinaputri")   # nilai roster rusak
        assert h.source == SUMBER_NAMA

    def test_unknown_tidak_punya_source(self):
        h = pilih_gender(None, "xyz", "qwerty")
        assert (h.nilai, h.source, h.confidence) == (None, None, None)

    def test_asset_tidak_menimpa_manual(self):
        teks = ASSET.read_text(encoding="utf-8")
        # baca dan tulis sama-sama menyaring baris manual
        assert teks.count("creator_gender_source IS DISTINCT FROM %(manual)s") == 2
        assert SUMBER_MANUAL == "manual"


class TestParitasDDL:
    def test_nilai_source_sama(self):
        ddl = MIGRATION.read_text(encoding="utf-8")
        m = re.search(r"creator_gender_source IN\s*\(([^)]*)\)", ddl)
        di_ddl = set(re.findall(r"'([a-z_]+)'", m.group(1)))
        assert di_ddl == {SUMBER_MANUAL, SUMBER_ROSTER, SUMBER_NAMA}

    def test_nilai_gender_sama(self):
        ddl = MIGRATION.read_text(encoding="utf-8")
        m = re.search(r"creator_gender IN \(([^)]*)\)", ddl)
        assert set(re.findall(r"'([a-z]+)'", m.group(1))) == {"female", "male"}


class TestBukanAudiens:
    DILARANG = ("female_pct", "male_pct", "gender_breakdown", "gender_known_pct",
                "audience_analysis", "audience_demographics", "unified_follower",
                "followers_apify", "tebak_gender(", "analisis_follower")

    @pytest.mark.parametrize("path", [MODUL, ASSET])
    def test_tidak_membaca_data_audiens(self, path):
        # abaikan docstring/komentar: yang dicek adalah kode yang berjalan
        kode = "\n".join(b for b in path.read_text(encoding="utf-8").splitlines()
                         if not b.lstrip().startswith("#"))
        kode = re.sub(r'"""[\s\S]*?"""', "", kode)
        for kata in self.DILARANG:
            assert kata not in kode, f"{path.name} memuat {kata!r}"

    def test_audience_inference_tidak_diubah_perilakunya(self):
        # Fungsi follower tetap memakai aturan lamanya: sufiks pria masih
        # menghasilkan male di SANA (dan sengaja tidak di modul kreator).
        assert audience_inference.tebak_gender(None, "kurniawan").nilai == "male"
        assert tebak_gender_kreator(None, "kurniawan").nilai is None


class TestTerdaftarDiRantai:
    def test_ikut_transform_chain_job(self):
        from kol_orchestration import one_shot
        assert "creator_gender" in one_shot.TRANSFORM_ASSETS
        assert one_shot.TRANSFORM_ASSETS.index("creator_gender") > \
            one_shot.TRANSFORM_ASSETS.index("kol_profile_card")
