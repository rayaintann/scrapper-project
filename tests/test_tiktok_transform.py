"""Parsing + cleaning item TikTok. Offline: tidak menyentuh Apify maupun DB."""

import unittest

from tiktok_transform import (
    extract_username,
    flatten_for_csv,
    is_error_item,
    to_raw_row,
)


def item(**meta) -> dict:
    """Item actor minimal dengan authorMeta yang bisa dipakai."""
    dasar = {"id": "708", "name": "someone", "fans": 100}
    dasar.update(meta)
    return {"authorMeta": dasar}


class ExtractUsername(unittest.TestCase):
    def test_dari_author_meta(self):
        self.assertEqual(extract_username(item(name="Ibnu_Wardani")), "ibnu_wardani")

    def test_membuang_at_dan_url(self):
        self.assertEqual(extract_username(item(name="@Foo")), "foo")
        self.assertEqual(
            extract_username({"authorMeta": {"profileUrl": "https://www.tiktok.com/@bar/"}}),
            "bar",
        )

    def test_jatuh_ke_input_kalau_author_meta_kosong(self):
        # Item gagal sering hanya membawa kembali nilai yang kita kirim.
        self.assertEqual(extract_username({"input": "https://www.tiktok.com/@zed"}), "zed")

    def test_tidak_ada_yang_bisa_dibaca(self):
        self.assertIsNone(extract_username({}))
        self.assertIsNone(extract_username({"authorMeta": {}}))

    def test_username_bertitik_tidak_terpotong(self):
        self.assertEqual(extract_username(item(name="ravie.pie")), "ravie.pie")


class IsErrorItem(unittest.TestCase):
    def test_error_eksplisit(self):
        rusak = item()
        rusak["error"] = "not_found"
        self.assertTrue(is_error_item(rusak))

    def test_tanpa_author_meta(self):
        self.assertTrue(is_error_item({"input": "foo"}))

    def test_tanpa_id_dan_tanpa_fans(self):
        self.assertTrue(is_error_item({"authorMeta": {"name": "foo"}}))

    def test_punya_fans_saja_masih_dipakai(self):
        self.assertFalse(is_error_item({"authorMeta": {"name": "foo", "fans": 5}}))


class ToRawRow(unittest.TestCase):
    def test_kolom_utama(self):
        row = to_raw_row(item(
            name="foo", nickName="Foo Bar", signature="halo", fans=10,
            following=2, heart=99, video=7, verified=True,
            originalAvatarUrl="https://x/a.jpg",
        ))
        self.assertEqual(row["username"], "foo")
        self.assertEqual(row["display_name"], "Foo Bar")
        self.assertEqual(row["bio_description"], "halo")
        self.assertEqual(row["follower_count"], 10)
        self.assertEqual(row["following_count"], 2)
        self.assertEqual(row["likes_count"], 99)
        self.assertEqual(row["video_count"], 7)
        self.assertIs(row["is_verified"], True)
        self.assertEqual(row["avatar_url"], "https://x/a.jpg")

    def test_display_name_diratakan_jadi_satu_baris(self):
        row = to_raw_row(item(nickName="Foo\nBar   Baz"))
        self.assertEqual(row["display_name"], "Foo Bar Baz")

    def test_bio_mempertahankan_baris_tapi_dirapikan(self):
        row = to_raw_row(item(signature="baris satu\n\n\n\nbaris dua   \n"))
        self.assertEqual(row["bio_description"], "baris satu\n\nbaris dua")

    def test_teks_kosong_jadi_none(self):
        row = to_raw_row(item(nickName="   ", signature=""))
        self.assertIsNone(row["display_name"])
        self.assertIsNone(row["bio_description"])

    def test_angka_berbentuk_string_tetap_jadi_int(self):
        row = to_raw_row(item(fans="1234"))
        self.assertEqual(row["follower_count"], 1234)

    def test_angka_tidak_masuk_akal_jadi_none(self):
        row = to_raw_row(item(fans=100, following="banyak", heart=None))
        self.assertIsNone(row["following_count"])
        self.assertIsNone(row["likes_count"])

    def test_verified_non_boolean_jadi_none(self):
        # 'true' sebagai string tidak boleh diam-diam dianggap True.
        self.assertIsNone(to_raw_row(item(verified="true"))["is_verified"])

    def test_avatar_kosong_jadi_none(self):
        self.assertIsNone(to_raw_row(item(originalAvatarUrl="   ", avatar=""))["avatar_url"])

    def test_avatar_cadangan(self):
        row = to_raw_row(item(avatar="https://x/kecil.jpg"))
        self.assertEqual(row["avatar_url"], "https://x/kecil.jpg")

    def test_item_error_ditolak(self):
        self.assertIsNone(to_raw_row({"input": "foo", "error": "blocked"}))
        self.assertIsNone(to_raw_row({}))


class FlattenForCsv(unittest.TestCase):
    def test_kolom_lengkap_walau_item_rusak(self):
        row = flatten_for_csv({"input": "foo", "error": "blocked"})
        self.assertEqual(row["username"], "foo")
        self.assertEqual(row["error"], "blocked")
        self.assertIsNone(row["follower_count"])

    def test_newline_di_bio_dibuang_untuk_csv(self):
        row = flatten_for_csv(item(signature="a\nb"))
        self.assertNotIn("\n", row["bio_description"])


if __name__ == "__main__":
    unittest.main()
