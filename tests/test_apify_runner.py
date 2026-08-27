"""Logika biaya & retry runner Apify, dengan client palsu.

Tidak ada koneksi keluar dan tidak ada kredit yang terpakai: ApifyClient
diganti objek palsu, jadi semua jalur yang menentukan biaya bisa diuji.
"""

import unittest
from unittest import mock

from apify_client.errors import UnauthorizedError

import apify_runner
from apify_runner import BatchResult, FatalApifyError, chunked
from apify_tiktok import TikTokProfileScraper
from config import TikTokConfig

CFG = TikTokConfig(
    token="token-palsu",
    actor_id="clockworks/tiktok-scraper",
    proxy_country="ID",
    results_per_page=1,
)


def hasil(username: str) -> dict:
    return {"authorMeta": {"id": "1", "name": username, "fans": 10}}


class FakeResponse:
    """Response HTTP 401 secukupnya untuk membentuk error asli dari pustaka."""

    status_code = 401
    text = "unauthorized"

    def json(self):
        return {"error": {"message": "token salah", "type": "token-not-provided"}}


def fatal() -> UnauthorizedError:
    """Error fatal yang dibentuk persis seperti yang dilempar apify-client."""
    return UnauthorizedError(FakeResponse(), 1)


class FakeRun:
    def __init__(self, run_id, status, dataset_id, usage):
        self.id = run_id
        self.status = status
        self.default_dataset_id = dataset_id
        self.usage_total_usd = usage


class FakeDataset:
    def __init__(self, items):
        self._items = items

    def iterate_items(self):
        return iter(self._items)


class FakeActor:
    def __init__(self, client):
        self._client = client

    def call(self, **kwargs):
        return self._client.jalankan(kwargs)


class FakeClient:
    """Membalas panggilan actor sesuai skenario: (status, items) atau Exception."""

    def __init__(self, skenario, usage=0.05):
        self.skenario = list(skenario)
        self.usage = usage
        self.panggilan: list[dict] = []
        self._datasets: dict[str, list] = {}

    def actor(self, actor_id):
        self.actor_id = actor_id
        return FakeActor(self)

    def dataset(self, dataset_id):
        return FakeDataset(self._datasets.get(dataset_id, []))

    def jalankan(self, kwargs):
        self.panggilan.append(kwargs)
        langkah = self.skenario.pop(0) if self.skenario else ("SUCCEEDED", [])
        if isinstance(langkah, Exception):
            raise langkah
        status, items = langkah
        dataset_id = f"ds{len(self.panggilan)}"
        self._datasets[dataset_id] = items
        return FakeRun(f"run{len(self.panggilan)}", status, dataset_id, self.usage)

    @property
    def profil_dikirim(self) -> list[list[str]]:
        return [k["run_input"]["profiles"] for k in self.panggilan]


def jalankan(skenario, usernames, **kwargs) -> tuple[BatchResult, FakeClient]:
    fake = FakeClient(skenario)
    with mock.patch.object(apify_runner, "ApifyClient", lambda token: fake), \
         mock.patch.object(apify_runner.time, "sleep", lambda detik: None):
        scraper = TikTokProfileScraper(CFG, **kwargs)
        return scraper.scrape_batch(usernames, batch_index=1), fake


class Chunked(unittest.TestCase):
    def test_membagi_rata(self):
        self.assertEqual(chunked(["a", "b", "c"], 2), [["a", "b"], ["c"]])

    def test_ukuran_nol_ditolak(self):
        with self.assertRaises(ValueError):
            chunked(["a"], 0)


class Missing(unittest.TestCase):
    def test_username_yang_tidak_kembali(self):
        b = BatchResult(batch_index=1, usernames=["a", "b"],
                        items=[hasil("a")],
                        _username_of=lambda i: i["authorMeta"]["name"])
        self.assertEqual(b.missing, ["b"])


class ScrapeBatch(unittest.TestCase):
    def test_sukses_penuh(self):
        r, fake = jalankan([("SUCCEEDED", [hasil("a"), hasil("b")])], ["a", "b"])
        self.assertEqual(len(r.items), 2)
        self.assertIsNone(r.error)
        self.assertFalse(r.partial)
        self.assertEqual(r.missing, [])
        self.assertAlmostEqual(r.cost_usd, 0.05)
        self.assertEqual(len(fake.panggilan), 1)

    def test_dataset_kosong_dianggap_gagal_dan_diulang(self):
        # TikTok melaporkan SUCCEEDED walau semua request diblokir.
        r, fake = jalankan(
            [("SUCCEEDED", []), ("SUCCEEDED", [hasil("a"), hasil("b")])], ["a", "b"]
        )
        self.assertEqual(len(fake.panggilan), 2)
        self.assertEqual(len(r.items), 2)
        self.assertIsNone(r.error)

    def test_retry_hanya_mengirim_yang_belum_kembali(self):
        # Inti pengaman biaya: profil yang sudah dibayar tidak dikirim ulang.
        r, fake = jalankan(
            [("SUCCEEDED", [hasil("a")]), ("SUCCEEDED", [hasil("b")])], ["a", "b"]
        )
        self.assertEqual(fake.profil_dikirim, [["a", "b"], ["b"]])
        self.assertEqual(len(r.items), 2)
        self.assertTrue(r.partial)
        self.assertAlmostEqual(r.cost_usd, 0.10)

    def test_item_dari_run_gagal_tetap_diselamatkan(self):
        r, _ = jalankan(
            [("TIMED-OUT", [hasil("a")]), RuntimeError("gagal lagi"), RuntimeError("gagal lagi")],
            ["a", "b"],
        )
        self.assertEqual([i["authorMeta"]["name"] for i in r.items], ["a"])
        self.assertTrue(r.partial)
        self.assertIsNone(r.error)      # sebagian berhasil, bukan gagal total
        self.assertEqual(r.missing, ["b"])

    def test_gagal_total_menyimpan_pesan_error(self):
        r, fake = jalankan([RuntimeError("boom")] * 3, ["a"])
        self.assertEqual(r.items, [])
        self.assertIn("boom", r.error)
        self.assertEqual(len(fake.panggilan), 3)   # 1 + max_retries

    def test_error_fatal_menghentikan_pipeline(self):
        with self.assertRaises(FatalApifyError):
            jalankan([fatal()], ["a"])

    def test_error_fatal_tidak_diulang(self):
        fake = FakeClient([fatal(), ("SUCCEEDED", [hasil("a")])])
        with mock.patch.object(apify_runner, "ApifyClient", lambda token: fake), \
             mock.patch.object(apify_runner.time, "sleep", lambda d: None):
            scraper = TikTokProfileScraper(CFG)
            with self.assertRaises(FatalApifyError):
                scraper.scrape_batch(["a"], batch_index=1)
        self.assertEqual(len(fake.panggilan), 1)


class Plafon(unittest.TestCase):
    def test_plafon_dinaikkan_ke_minimum_actor(self):
        # Actor menolak max_total_charge_usd di bawah $0.50.
        _, fake = jalankan([("SUCCEEDED", [hasil("a")])], ["a"], max_charge_usd=0.1875)
        self.assertEqual(float(fake.panggilan[0]["max_total_charge_usd"]), 0.50)

    def test_tanpa_plafon_tidak_mengirim_parameternya(self):
        _, fake = jalankan([("SUCCEEDED", [hasil("a")])], ["a"])
        self.assertNotIn("max_total_charge_usd", fake.panggilan[0])

    def test_batas_waktu_mengikuti_ukuran_batch(self):
        usernames = [f"u{i}" for i in range(50)]
        _, fake = jalankan([("SUCCEEDED", [hasil(u) for u in usernames])], usernames)
        # 50 username x 30 detik = 1500 detik, di atas batas tetap 900.
        self.assertEqual(fake.panggilan[0]["run_timeout"].total_seconds(), 1500)


class InputActor(unittest.TestCase):
    def test_opsi_unduhan_semuanya_mati(self):
        # Setiap opsi unduhan menambah biaya per hasil; harus tetap mati.
        with mock.patch.object(apify_runner, "ApifyClient", lambda token: FakeClient([])):
            scraper = TikTokProfileScraper(CFG)
        run_input = scraper.build_input(["a", "b"])
        for kunci, nilai in run_input.items():
            if kunci.startswith("shouldDownload"):
                self.assertFalse(nilai, f"{kunci} harus False supaya tidak menambah biaya")
        self.assertEqual(run_input["profiles"], ["a", "b"])
        self.assertEqual(run_input["resultsPerPage"], 1)
        self.assertEqual(run_input["proxyCountryCode"], "ID")

    def test_proxy_none_tidak_dikirim(self):
        cfg = TikTokConfig(token="t", actor_id="x", proxy_country="None", results_per_page=1)
        with mock.patch.object(apify_runner, "ApifyClient", lambda token: FakeClient([])):
            scraper = TikTokProfileScraper(cfg)
        self.assertNotIn("proxyCountryCode", scraper.build_input(["a"]))


if __name__ == "__main__":
    unittest.main()
