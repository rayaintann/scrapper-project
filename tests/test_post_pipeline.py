"""Penyusunan status per akun dan penyaringan item error.

Offline: tidak menyentuh Apify maupun database.
"""

import unittest
from datetime import datetime, timezone

from post_errors import NOT_FOUND, RATE_LIMIT, SUCCESS, UNKNOWN
from post_pipeline import build_outcomes
from post_raw_store import PostInsertStats, _partition


class Row:
    """Pengganti db.DirectoryRow secukupnya."""

    def __init__(self, id_, username):
        self.id = id_
        self.username = username


T0 = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 8, 21, 3, 5, tzinfo=timezone.utc)


def outcomes(requested, per_account=None, item_errors=None, batch_errors=None):
    return build_outcomes(
        requested=requested,
        platform="instagram",
        per_account=per_account or {},
        item_errors=item_errors or [],
        batch_errors=batch_errors or {},
        started_at=T0,
        finished_at=T1,
    )


class SetiapAkunDapatBaris(unittest.TestCase):
    def test_sukses_dan_gagal_sama_sama_tercatat(self):
        requested = {
            "cristiano": [Row("kd-1", "cristiano")],
            "bbrightvc": [Row("kd-2", "bbrightvc")],
        }
        hasil = outcomes(
            requested,
            per_account={"cristiano": 10},
            item_errors=[("bbrightvc", NOT_FOUND, "not_found | Post does not exist")],
        )
        self.assertEqual(len(hasil), 2)
        peta = {o.username: o for o in hasil}

        self.assertEqual(peta["cristiano"].status, SUCCESS)
        self.assertEqual(peta["cristiano"].records, 10)
        self.assertEqual(peta["cristiano"].kol_directory_id, "kd-1")
        self.assertTrue(peta["cristiano"].ok)

        self.assertEqual(peta["bbrightvc"].status, NOT_FOUND)
        self.assertEqual(peta["bbrightvc"].records, 0)
        self.assertEqual(peta["bbrightvc"].kol_directory_id, "kd-2")
        self.assertFalse(peta["bbrightvc"].ok)
        self.assertIn("Post does not exist", peta["bbrightvc"].message)

    def test_semua_akun_punya_timestamp(self):
        hasil = outcomes({"a": [Row("kd-a", "a")]})
        self.assertEqual(hasil[0].started_at, T0)
        self.assertEqual(hasil[0].finished_at, T1)


class UrutanPenentuanStatus(unittest.TestCase):
    def test_baris_masuk_mengalahkan_item_error(self):
        # Akun yang sebagian post-nya masuk tidak boleh ditandai gagal.
        hasil = outcomes(
            {"a": [Row("kd-a", "a")]},
            per_account={"a": 3},
            item_errors=[("a", NOT_FOUND, "satu post hilang")],
        )
        self.assertEqual(hasil[0].status, SUCCESS)

    def test_item_error_mengalahkan_batch_error(self):
        hasil = outcomes(
            {"a": [Row("kd-a", "a")]},
            item_errors=[("a", NOT_FOUND, "not_found")],
            batch_errors={"a": (RATE_LIMIT, "429")},
        )
        self.assertEqual(hasil[0].status, NOT_FOUND)

    def test_batch_error_dipakai_kalau_tidak_ada_item_error(self):
        hasil = outcomes({"a": [Row("kd-a", "a")]}, batch_errors={"a": (RATE_LIMIT, "429")})
        self.assertEqual(hasil[0].status, RATE_LIMIT)

    def test_tanpa_jejak_jadi_unknown(self):
        hasil = outcomes({"a": [Row("kd-a", "a")]})
        self.assertEqual(hasil[0].status, UNKNOWN)


class ErrorTidakMenghentikanAkunLain(unittest.TestCase):
    def test_satu_gagal_sisanya_tetap_sukses(self):
        requested = {f"u{i}": [Row(f"kd-{i}", f"u{i}")] for i in range(5)}
        hasil = outcomes(
            requested,
            per_account={f"u{i}": 10 for i in range(5) if i != 2},
            item_errors=[("u2", NOT_FOUND, "not_found")],
        )
        status = {o.username: o.status for o in hasil}
        self.assertEqual(status["u2"], NOT_FOUND)
        self.assertEqual([status[f"u{i}"] for i in (0, 1, 3, 4)], [SUCCESS] * 4)

    def test_batch_gagal_tidak_menjatuhkan_batch_lain(self):
        requested = {f"u{i}": [Row(f"kd-{i}", f"u{i}")] for i in range(4)}
        hasil = outcomes(
            requested,
            per_account={"u0": 10, "u1": 10},
            batch_errors={"u2": (RATE_LIMIT, "429"), "u3": (RATE_LIMIT, "429")},
        )
        status = {o.username: o.status for o in hasil}
        self.assertEqual(status["u0"], SUCCESS)
        self.assertEqual(status["u1"], SUCCESS)
        self.assertEqual(status["u2"], RATE_LIMIT)
        self.assertEqual(status["u3"], RATE_LIMIT)


class ItemErrorTanpaUsername(unittest.TestCase):
    def test_tetap_dicatat_tanpa_kol_directory_id(self):
        hasil = outcomes({}, item_errors=[(None, NOT_FOUND, "tidak jelas milik siapa")])
        self.assertEqual(len(hasil), 1)
        self.assertIsNone(hasil[0].kol_directory_id)
        self.assertEqual(hasil[0].status, NOT_FOUND)


class PenyaringanSebelumL0(unittest.TestCase):
    """Item error tidak boleh lolos ke daftar yang akan di-INSERT."""

    def setUp(self):
        self.stats = PostInsertStats(scrape_run_id="run-1", table="l0_raw.dummy")

    def test_item_error_disaring_dan_dicatat(self):
        items = [
            {"id": "1", "ownerUsername": "a"},
            {"error": "not_found", "errorDescription": "Post does not exist",
             "url": "https://www.instagram.com/bbrightvc/"},
            {"id": "2", "ownerUsername": "a"},
        ]
        usable = _partition(items, lambda i: i.get("ownerUsername") or "bbrightvc", self.stats)

        self.assertEqual(len(usable), 2)
        self.assertEqual([i["id"] for _, i in usable], ["1", "2"])
        self.assertEqual(self.stats.skipped_error, 1)
        self.assertEqual(self.stats.errors[0][1], NOT_FOUND)

    def test_item_tanpa_content_id_tidak_masuk(self):
        items = [{"ownerUsername": "a", "likesCount": 1}]
        usable = _partition(items, lambda i: "a", self.stats)
        self.assertEqual(usable, [])
        # Tanpa id, is_error_item sudah menangkapnya lebih dulu.
        self.assertEqual(self.stats.skipped_error, 1)

    def test_item_tanpa_username_tidak_masuk(self):
        items = [{"id": "9"}]
        usable = _partition(items, lambda i: None, self.stats)
        self.assertEqual(usable, [])
        self.assertEqual(self.stats.skipped_no_username, 1)


if __name__ == "__main__":
    unittest.main()
