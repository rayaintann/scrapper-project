"""Klasifikasi kegagalan scraping post. Offline: tidak menyentuh Apify maupun DB."""

import unittest

from apify_posts import InstagramPostScraper, TikTokVideoScraper
from post_errors import (
    ACTOR_ERROR,
    NOT_FOUND,
    PRIVATE_UNAVAILABLE,
    RATE_LIMIT,
    SUCCESS,
    TIMEOUT,
    UNKNOWN,
    classify_exception,
    classify_item,
    classify_missing,
    classify_text,
    error_text,
    is_error_item,
)

# Item error persis seperti yang dikembalikan actor untuk bbrightvc.
BBRIGHTVC = {
    "error": "not_found",
    "errorDescription": "Post does not exist",
    "url": "https://www.instagram.com/bbrightvc/",
}

POST_SAH = {
    "id": "3962865876566269926",
    "ownerUsername": "cristiano",
    "likesCount": 23952,
    "commentsCount": 167,
}


class KlasifikasiTeks(unittest.TestCase):
    def test_not_found(self):
        for teks in ("not_found", "Post does not exist", "User not exist", "404 page not found"):
            self.assertEqual(classify_text(teks), NOT_FOUND, teks)

    def test_private_unavailable(self):
        for teks in ("This account is private", "restricted", "Profile unavailable",
                     "login required", "403 Forbidden", "account suspended"):
            self.assertEqual(classify_text(teks), PRIVATE_UNAVAILABLE, teks)

    def test_rate_limit(self):
        for teks in ("rate limit exceeded", "429 Too Many Requests", "throttled", "quota exceeded"):
            self.assertEqual(classify_text(teks), RATE_LIMIT, teks)

    def test_timeout(self):
        for teks in ("run timed out", "Timeout after 900s", "deadline exceeded"):
            self.assertEqual(classify_text(teks), TIMEOUT, teks)

    def test_actor_error(self):
        for teks in ("ApifyRunError: run selesai dengan status FAILED",
                     "actor gagal memulai", "dataset tidak ditemukan di server"):
            self.assertIn(classify_text(teks), (ACTOR_ERROR, NOT_FOUND), teks)

    def test_kosong_jadi_unknown(self):
        self.assertEqual(classify_text(""), UNKNOWN)
        self.assertEqual(classify_text(None), UNKNOWN)
        self.assertEqual(classify_text("   "), UNKNOWN)

    def test_teks_asing_jadi_unknown(self):
        self.assertEqual(classify_text("sesuatu yang tidak dikenali sama sekali"), UNKNOWN)

    def test_rate_limit_menang_atas_actor(self):
        # "429" harus dibaca rate_limit walau kalimatnya menyebut actor.
        self.assertEqual(classify_text("actor returned 429 too many requests"), RATE_LIMIT)


class DeteksiItemError(unittest.TestCase):
    def test_item_error_dikenali(self):
        self.assertTrue(is_error_item(BBRIGHTVC))

    def test_post_sah_tidak_dianggap_error(self):
        self.assertFalse(is_error_item(POST_SAH))

    def test_tanpa_id_dianggap_error(self):
        self.assertTrue(is_error_item({"ownerUsername": "x", "likesCount": 5}))

    def test_bukan_dict_dianggap_error(self):
        self.assertTrue(is_error_item(None))
        self.assertTrue(is_error_item("bukan objek"))

    def test_error_kosong_bukan_error(self):
        # error: "" tidak boleh menjatuhkan post yang sebenarnya sah.
        self.assertFalse(is_error_item({"id": "1", "error": ""}))


class KlasifikasiItem(unittest.TestCase):
    def test_bbrightvc_jadi_not_found(self):
        code, pesan = classify_item(BBRIGHTVC)
        self.assertEqual(code, NOT_FOUND)
        self.assertIn("not_found", pesan)
        self.assertIn("Post does not exist", pesan)

    def test_pesan_menggabungkan_field(self):
        self.assertEqual(
            error_text({"error": "a", "errorDescription": "b"}), "a | b"
        )

    def test_tanpa_keterangan_tetap_punya_pesan(self):
        code, pesan = classify_item({"ownerUsername": "x"})
        self.assertEqual(code, UNKNOWN)
        self.assertTrue(pesan)


class KlasifikasiException(unittest.TestCase):
    def test_timeout(self):
        code, _ = classify_exception(TimeoutError("run timed out after 900s"))
        self.assertEqual(code, TIMEOUT)

    def test_exception_asing_jatuh_ke_actor_error(self):
        code, pesan = classify_exception(ValueError("entah apa ini"))
        self.assertEqual(code, ACTOR_ERROR)
        self.assertIn("ValueError", pesan)


class KlasifikasiMissing(unittest.TestCase):
    def test_default_unknown_bukan_not_found(self):
        # Actor yang diam tidak boleh ditebak sebagai not_found.
        code, pesan = classify_missing()
        self.assertEqual(code, UNKNOWN)
        self.assertIn("tidak muncul di hasil", pesan)

    def test_alasan_eksplisit_dipakai(self):
        code, _ = classify_missing("diblokir, 429 too many requests")
        self.assertEqual(code, RATE_LIMIT)


class AtribusiUsername(unittest.TestCase):
    """Item error harus tetap bisa ditelusuri pemiliknya."""

    def setUp(self):
        class CfgIG:
            token = "x"
            actor_id = "apify/instagram-scraper"
            include_about_section = False

        class CfgTT:
            token = "x"
            actor_id = "clockworks/tiktok-scraper"
            proxy_country = "ID"
            results_per_page = 10

        # ApifyClient hanya dibuat, tidak dipanggil.
        self.ig = InstagramPostScraper(CfgIG())
        self.tt = TikTokVideoScraper(CfgTT())

    def test_ig_item_error_terbaca_dari_url(self):
        self.assertEqual(self.ig.item_username(BBRIGHTVC), "bbrightvc")

    def test_ig_post_sah_dari_owner(self):
        self.assertEqual(self.ig.item_username(POST_SAH), "cristiano")

    def test_ig_url_post_bukan_username(self):
        # https://www.instagram.com/p/<kode>/ tidak boleh dibaca sebagai "p".
        self.assertIsNone(self.ig.item_username({"url": "https://www.instagram.com/p/Db-7YTBP9_m/"}))

    def test_tt_dari_author_meta(self):
        self.assertEqual(
            self.tt.item_username({"authorMeta": {"name": "Saalhaerid"}}), "saalhaerid"
        )

    def test_tt_fallback_dari_url_video(self):
        self.assertEqual(
            self.tt.item_username({"webVideoUrl": "https://www.tiktok.com/@inul.d/video/693"}),
            "inul.d",
        )


class StatusSukses(unittest.TestCase):
    def test_success_bukan_kode_error(self):
        from post_errors import ERROR_CODES

        self.assertNotIn(SUCCESS, ERROR_CODES)


if __name__ == "__main__":
    unittest.main()
