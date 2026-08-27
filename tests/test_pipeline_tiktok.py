"""Pemilihan username + ketahanan penulisan DB per batch.

Semuanya offline: koneksi Postgres dan insert diganti objek palsu, jadi tes ini
tidak menyentuh database maupun Apify.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import psycopg2

import tiktok_pipeline
from config import PostgresConfig
from tiktok_pipeline import RawWriter, dedupe_preserving_order, parse_args, read_usernames_file
from tt_raw_store import RawInsertStats

PG = PostgresConfig(host="h", port="5432", database="d", user="u", password="p")


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if not self._conn.hidup:
            raise psycopg2.OperationalError("server closed the connection unexpectedly")


class FakeConn:
    def __init__(self, hidup=True):
        self.hidup = hidup
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def stats_untuk(items, scrape_run_id):
    return RawInsertStats(
        scrape_run_id=scrape_run_id, inserted=len(items), linked=len(items), unlinked=0
    )


class DaftarUsername(unittest.TestCase):
    def test_normalisasi_dan_buang_duplikat(self):
        hasil = dedupe_preserving_order(
            ["@Foo", "foo", "https://www.tiktok.com/@bar/", "", "  ", "BAR"]
        )
        self.assertEqual(hasil, ["foo", "bar"])

    def test_urutan_pertama_dipertahankan(self):
        self.assertEqual(dedupe_preserving_order(["c", "a", "c", "b"]), ["c", "a", "b"])

    def test_baca_file_dengan_komentar(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "gagal.txt"
            path.write_text(
                "# username yang belum berhasil\n"
                "jharnabhagwani\n"
                "\n"
                "  vamells  # sempat diblokir\n"
                "ravie.pie\n",
                encoding="utf-8",
            )
            self.assertEqual(
                read_usernames_file(path), ["jharnabhagwani", "vamells", "ravie.pie"]
            )

    def test_file_tidak_ada(self):
        with self.assertRaises(FileNotFoundError):
            read_usernames_file(Path("tidak-ada-1234.txt"))

    def test_daftar_manual_tidak_menyentuh_database(self):
        args = parse_args(["--usernames", "@Foo", "foo", "bar"])
        # conn=None membuktikan kol_directory tidak diakses sama sekali.
        usernames, sumber = tiktok_pipeline.select_usernames(None, args)
        self.assertEqual(usernames, ["foo", "bar"])
        self.assertIn("manual", sumber)


class PenulisanPerBatch(unittest.TestCase):
    """RawWriter: satu commit per batch, koneksi mati dipulihkan sendiri."""

    def setUp(self):
        self.scraped_at = datetime(2026, 8, 14, 15, 59, 5, tzinfo=timezone.utc)
        self.items = [{"authorMeta": {"name": "a"}}, {"authorMeta": {"name": "b"}}]

    def buat(self, conns, insert_side_effect=None):
        writer = RawWriter(PG, "clockworks/tiktok-scraper", self.scraped_at)
        buka = mock.Mock(side_effect=conns)
        if insert_side_effect is None:
            insert = mock.Mock(side_effect=lambda conn, items, **kw: stats_untuk(
                items, kw["scrape_run_id"]))
        else:
            insert = mock.Mock(side_effect=insert_side_effect)
        patcher_buka = mock.patch.object(tiktok_pipeline, "open_connection", buka)
        patcher_insert = mock.patch.object(tiktok_pipeline, "insert_profiles", insert)
        patcher_buka.start()
        patcher_insert.start()
        self.addCleanup(patcher_buka.stop)
        self.addCleanup(patcher_insert.stop)
        return writer, buka, insert

    def test_batch_kosong_tidak_membuka_koneksi(self):
        writer, buka, insert = self.buat([FakeConn()])
        self.assertTrue(writer.write([], 1))
        buka.assert_not_called()
        insert.assert_not_called()

    def test_satu_koneksi_dipakai_ulang_antar_batch(self):
        writer, buka, insert = self.buat([FakeConn()])
        self.assertTrue(writer.write(self.items, 1))
        self.assertTrue(writer.write(self.items, 2))
        self.assertEqual(buka.call_count, 1)
        self.assertEqual(writer.total.inserted, 4)
        self.assertEqual(writer.failures, [])

    def test_semua_batch_memakai_scrape_run_id_yang_sama(self):
        writer, _, insert = self.buat([FakeConn()])
        writer.write(self.items, 1)
        writer.write(self.items, 2)
        dipakai = {c.kwargs["scrape_run_id"] for c in insert.call_args_list}
        self.assertEqual(dipakai, {writer.scrape_run_id})

    def test_koneksi_mati_dibuka_ulang(self):
        # Persis kegagalan run 100 profil: koneksi mati setelah menganggur lama.
        mati, baru = FakeConn(), FakeConn()
        writer, buka, _ = self.buat([mati, baru])
        self.assertTrue(writer.write(self.items, 1))
        mati.hidup = False
        self.assertTrue(writer.write(self.items, 2))
        self.assertEqual(buka.call_count, 2)
        self.assertTrue(mati.closed)
        self.assertEqual(writer.total.inserted, 4)

    def test_insert_gagal_sekali_dicoba_lagi_dengan_koneksi_baru(self):
        stats = RawInsertStats(scrape_run_id="x", inserted=2, linked=2)
        writer, buka, insert = self.buat(
            [FakeConn(), FakeConn()],
            insert_side_effect=[psycopg2.OperationalError("koneksi putus"), stats],
        )
        self.assertTrue(writer.write(self.items, 1))
        self.assertEqual(buka.call_count, 2)
        self.assertEqual(insert.call_count, 2)
        self.assertEqual(writer.failures, [])
        self.assertEqual(writer.total.inserted, 2)

    def test_gagal_dua_kali_dicatat_tanpa_menghentikan_run(self):
        writer, _, insert = self.buat(
            [FakeConn(), FakeConn()],
            insert_side_effect=psycopg2.OperationalError("DB tumbang"),
        )
        self.assertFalse(writer.write(self.items, 7))
        self.assertEqual(insert.call_count, 2)
        self.assertEqual(len(writer.failures), 1)
        self.assertEqual(writer.failures[0][0], 7)
        self.assertIn("DB tumbang", writer.failures[0][1])
        self.assertEqual(writer.total.inserted, 0)

    def test_batch_berikutnya_tetap_bisa_masuk_setelah_satu_gagal(self):
        stats = RawInsertStats(scrape_run_id="x", inserted=2, linked=2)
        writer, _, _ = self.buat(
            [FakeConn(), FakeConn(), FakeConn()],
            insert_side_effect=[
                psycopg2.OperationalError("putus"),
                psycopg2.OperationalError("putus"),
                stats,
            ],
        )
        self.assertFalse(writer.write(self.items, 1))
        self.assertTrue(writer.write(self.items, 2))
        self.assertEqual(writer.total.inserted, 2)
        self.assertEqual(len(writer.failures), 1)

    def test_akumulasi_statistik(self):
        def insert(conn, items, **kw):
            return RawInsertStats(scrape_run_id=kw["scrape_run_id"], inserted=1,
                                  linked=1, unlinked=0, skipped_failed=2)
        writer, _, _ = self.buat([FakeConn()], insert_side_effect=insert)
        writer.write(self.items, 1)
        writer.write(self.items, 2)
        self.assertEqual(writer.total.inserted, 2)
        self.assertEqual(writer.total.linked, 2)
        self.assertEqual(writer.total.skipped_failed, 4)


class OpsiBaris(unittest.TestCase):
    def test_default_aman(self):
        args = parse_args([])
        self.assertFalse(args.skip_existing)      # harus disengaja
        self.assertTrue(args.write_raw)
        self.assertIsNone(args.max_total_cost_usd)
        self.assertEqual(args.limit, 100)

    def test_plafon_biaya_total(self):
        args = parse_args(["--max-total-cost-usd", "2.5", "--skip-existing"])
        self.assertEqual(args.max_total_cost_usd, 2.5)
        self.assertTrue(args.skip_existing)


if __name__ == "__main__":
    unittest.main()
