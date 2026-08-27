"""Ingest file JSONL ke raw table: pembacaan file, stamp waktu, dan file nyata.

Offline. Bagian yang menyentuh DB (guard duplikat, transaksi) tidak diuji di
sini karena butuh Postgres; jalur itu diperiksa lewat `--dry-run`, yang
melakukan insert sungguhan lalu me-rollback.
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ingest import load_items
from ingest_tiktok import scraped_at_from
from tiktok_transform import extract_username, to_raw_row

FIXTURE = Path(__file__).resolve().parent.parent / "output" / \
    "tiktok_profiles_20260814T155905Z.jsonl"


class StampWaktu(unittest.TestCase):
    def test_stamp_dari_nama_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tiktok_profiles_20260814T155905Z.jsonl"
            p.write_text("", encoding="utf-8")
            self.assertEqual(
                scraped_at_from([p]),
                datetime(2026, 8, 14, 15, 59, 5, tzinfo=timezone.utc),
            )

    def test_nama_tidak_standar_jatuh_ke_mtime(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tiktok_profiles_entah.jsonl"
            p.write_text("", encoding="utf-8")
            hasil = scraped_at_from([p])
            self.assertEqual(hasil.tzinfo, timezone.utc)


class BacaJsonl(unittest.TestCase):
    def test_baris_rusak_dilewati_bukan_menggagalkan(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tiktok_profiles_20260101T000000Z.jsonl"
            p.write_text(
                json.dumps({"authorMeta": {"name": "a", "id": "1", "fans": 1}}) + "\n"
                + "{rusak\n"
                + "\n"
                + json.dumps({"authorMeta": {"name": "b", "id": "2", "fans": 2}}) + "\n",
                encoding="utf-8",
            )
            items = load_items([p])
        self.assertEqual([extract_username(i) for i in items], ["a", "b"])

    def test_file_tidak_ada(self):
        with self.assertRaises(FileNotFoundError):
            load_items([Path("tidak-ada-9999.jsonl")])


@unittest.skipUnless(FIXTURE.exists(), f"fixture tidak ada: {FIXTURE}")
class FileRunNyata(unittest.TestCase):
    """Menahan regresi memakai hasil run 100 profil yang sudah dibayar."""

    @classmethod
    def setUpClass(cls):
        cls.items = load_items([FIXTURE])

    def test_jumlah_item(self):
        self.assertEqual(len(self.items), 90)

    def test_semua_baris_bisa_diparsing_tanpa_error(self):
        for i in self.items:
            to_raw_row(i)   # tidak boleh melempar

    def test_85_layak_masuk_raw_table(self):
        layak = [i for i in self.items if to_raw_row(i) is not None]
        self.assertEqual(len(layak), 85)

    def test_username_unik_tidak_ada_yang_kosong(self):
        nama = [extract_username(i) for i in self.items]
        self.assertNotIn(None, nama)
        self.assertEqual(len(set(nama)), 90)

    def test_kolom_wajib_terisi(self):
        for i in self.items:
            row = to_raw_row(i)
            if row is None:
                continue
            self.assertTrue(row["username"])
            self.assertIsInstance(row["follower_count"], int)
            self.assertIsNone(row["display_name"]) if row["display_name"] is None \
                else self.assertNotIn("\n", row["display_name"])


if __name__ == "__main__":
    unittest.main()
