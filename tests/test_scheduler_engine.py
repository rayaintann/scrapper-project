"""Scheduler Engine: identity, platform, batas, actor, dedup, log, keamanan biaya.

Offline: tidak menyentuh Apify maupun database. Koneksi dan pemanggilan actor
digantikan objek palsu, jadi tes ini aman dijalankan tanpa kredensial.
"""

import pathlib
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import scheduler_engine as se
from apify_posts import (
    DEFAULT_IG_POST_ACTOR,
    DEFAULT_TT_VIDEO_ACTOR,
    InstagramDetailsScraper,
    TikTokVideoScraper,
)
from config import ApifyConfig, PostgresConfig, TikTokConfig
from post_raw_store import IG_TABLE, TT_TABLE, split_new_and_duplicate

APIFY = ApifyConfig(token="token-palsu", actor_id="x", include_about_section=False)
TIKTOK = TikTokConfig(
    token="token-palsu", actor_id=DEFAULT_TT_VIDEO_ACTOR,
    proxy_country="ID", results_per_page=1,
)
PG = PostgresConfig(host="h", port="5432", database="kol", user="u", password="p")
CFG = mock.Mock(postgres=PG, apify=APIFY, tiktok=TIKTOK)

PROJECT_ROOT = pathlib.Path(se.__file__).resolve().parent
ORCH = PROJECT_ROOT / "orchestration" / "kol_orchestration"

IG_TARGET = se.KolTarget(
    kol_directory_id="kd-1", social_account_id="sa-1",
    platform="instagram", username="kol_ig",
)
TT_TARGET = se.KolTarget(
    kol_directory_id="kd-2", social_account_id="sa-2",
    platform="tiktok", username="kol_tt",
)


class KursorPalsu:
    """Kursor yang mengembalikan baris siap-pakai dan merekam query."""

    def __init__(self, rows, sink):
        self._rows = list(rows)
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, query, params=None):
        self._sink.append((query, params))

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class KoneksiPalsu:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.queries = []

    def cursor(self):
        return KursorPalsu(self.rows, self.queries)


def _teks_query(conn):
    return " ".join(q for q, _ in conn.queries)


def _sumber(modul_atau_path):
    p = getattr(modul_atau_path, "__file__", modul_atau_path)
    return pathlib.Path(p).read_text(encoding="utf-8")


# --- batas eksekusi ---------------------------------------------------------


class BatasEksekusi(unittest.TestCase):
    def test_hanya_satu_profil(self):
        self.assertEqual(se.PROFILE_TARGET_LIMIT, 1)

    def test_sepuluh_post_per_target(self):
        self.assertEqual(se.POSTS_PER_TARGET, 10)

    def test_aamandazahra_dikecualikan(self):
        self.assertIn("aamandazahra", se.EXCLUDED_USERNAMES)


# --- keamanan biaya: tanpa cron, tanpa retry --------------------------------


class KeamananBiaya(unittest.TestCase):
    def test_retry_otomatis_dimatikan(self):
        self.assertEqual(se.MAX_RETRIES, 0)

    def test_scraper_dibuat_tanpa_retry(self):
        for plat in ("instagram", "tiktok"):
            scraper = se._build_scraper(plat, CFG)
            self.assertEqual(scraper._max_retries, 0, plat)
            self.assertFalse(scraper.retry_missing, plat)

    def test_tidak_ada_cron_di_scheduler_engine(self):
        s = _sumber(se)
        self.assertNotIn("*/5", s)
        self.assertNotRegex(s, r"cron_schedule|ScheduleDefinition")

    def test_tidak_ada_loop_berulang(self):
        self.assertFalse(hasattr(se, "run_forever"))
        s = _sumber(se)
        self.assertNotIn("while True", s)
        self.assertNotIn("time.sleep", s)

    def test_satu_run_actor_melayani_dua_kategori(self):
        plan = se.ExecutionPlan(
            run_id="r", profile_target=IG_TARGET, post_targets=[IG_TARGET, TT_TARGET]
        )
        self.assertEqual(plan.actor_runs, 2)


# --- identity: jembatan, bukan username -------------------------------------


class IdentityLewatJembatan(unittest.TestCase):
    def test_query_kandidat_memakai_kol_social_account(self):
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        se.select_profile_target(conn, "instagram")
        q = _teks_query(conn)
        for tabel in ("public.kol_directory", "public.kol_social_account",
                      "public.social_account", "public.platforms"):
            self.assertIn(tabel, q)

    def test_query_kandidat_tidak_menjodohkan_username(self):
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        se.select_profile_target(conn, "instagram")
        q = _teks_query(conn)
        self.assertNotRegex(q, r"k\.username\s*=\s*s\.username")
        self.assertNotRegex(q, r"ltrim\(lower\([^)]*\)\)\s*=\s*ltrim\(lower")

    def test_social_account_id_diteruskan_ke_penulis_profil(self):
        with mock.patch.object(se, "insert_ig_profiles") as ins:
            se._simpan_profil(KoneksiPalsu(), IG_TARGET, [{"username": "kol_ig"}],
                              "run-1", se._now())
        self.assertEqual(ins.call_args.kwargs["account_ids"], {"kol_ig": "sa-1"})

    def test_social_account_id_diteruskan_ke_penulis_post(self):
        with mock.patch.object(se, "insert_ig_posts") as ins:
            se._simpan_post(KoneksiPalsu(), IG_TARGET, [{"id": "p1"}],
                            lambda i: "kol_ig", "run-1", se._now())
        self.assertEqual(ins.call_args.kwargs["account_ids"], {"kol_ig": "sa-1"})

    def test_penulis_tiktok_dapat_id_tiktok(self):
        with mock.patch.object(se, "insert_tt_videos") as ins:
            se._simpan_post(KoneksiPalsu(), TT_TARGET, [{"id": "v1"}],
                            lambda i: "kol_tt", "run-1", se._now())
        self.assertEqual(ins.call_args.kwargs["account_ids"], {"kol_tt": "sa-2"})


# --- pemilihan kandidat profil ----------------------------------------------


class PemilihanProfil(unittest.TestCase):
    def test_menuntut_belum_punya_profil_dan_belum_punya_post(self):
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        se.select_profile_target(conn, "instagram")
        q = _teks_query(conn)
        self.assertEqual(q.count("NOT EXISTS"), 2)
        self.assertIn("ig_profile_apify", q)
        self.assertIn("ig_media_snapshots_apify", q)

    def test_scrape_status_TIDAK_dipakai_sebagai_kriteria(self):
        # Kriteria yang benar: belum punya baris di L0 RAW profile.
        # scrape_status menandai percobaan, bukan keberhasilan menulis ke L0.
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        se.select_profile_target(conn, "instagram")
        self.assertNotIn("scrape_status", _teks_query(conn))

    def test_urutan_default_followers_terbesar(self):
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        se.select_profile_target(conn, "instagram")
        self.assertIn("k.followers_count DESC NULLS LAST", _teks_query(conn))

    def test_urutan_username_bisa_dipilih(self):
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        se.select_profile_target(conn, "instagram", order="username")
        q = _teks_query(conn)
        self.assertIn("ORDER BY k.username ASC", q)
        self.assertNotIn("followers_count DESC", q)

    def test_username_terkunci_tetap_diverifikasi(self):
        # Mengunci kandidat TIDAK melewati syarat "belum ada di L0".
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        se.select_profile_target(conn, "instagram", username="Kol_X")
        q, params = conn.queries[0]
        self.assertEqual(params["username"], "kol_x")
        self.assertEqual(q.count("NOT EXISTS"), 2)

    def test_username_terkunci_tanpa_hasil_mengembalikan_none(self):
        conn = KoneksiPalsu(rows=[])
        self.assertIsNone(
            se.select_profile_target(conn, "instagram", username="tidak_ada")
        )

    def test_username_kosong_ditolak(self):
        with self.assertRaises(ValueError):
            se.select_profile_target(KoneksiPalsu(), "instagram", username="@@@")

    def test_urutan_asing_ditolak(self):
        with self.assertRaises(ValueError):
            se.select_profile_target(KoneksiPalsu(), "instagram", order="acak")

    def test_aamandazahra_dikirim_sebagai_pengecualian(self):
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        se.select_profile_target(conn, "instagram")
        self.assertIn("aamandazahra", conn.queries[0][1]["dikecualikan"])

    def test_platform_diambil_dari_baris_bukan_diasumsikan(self):
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "tiktok", "kol_tt")])
        t = se.select_profile_target(conn, "tiktok")
        self.assertEqual((t.platform, t.social_account_id, t.kol_directory_id),
                         ("tiktok", "sa-9", "kd-9"))

    def test_tabel_tiktok_dipakai_untuk_platform_tiktok(self):
        conn = KoneksiPalsu(rows=[])
        se.select_profile_target(conn, "tiktok")
        q = _teks_query(conn)
        self.assertIn("tt_profile_apify", q)
        self.assertIn("tt_video_apify", q)
        self.assertNotIn("ig_profile_apify", q)

    def test_tanpa_platform_mencari_di_kedua_platform(self):
        conn = KoneksiPalsu(rows=[])
        se.select_profile_target(conn)
        self.assertEqual(len(conn.queries), 2)

    def test_tanpa_kandidat_mengembalikan_none(self):
        self.assertIsNone(se.select_profile_target(KoneksiPalsu(rows=[]), "instagram"))

    def test_platform_asing_ditolak(self):
        with self.assertRaises(ValueError):
            se.select_profile_target(KoneksiPalsu(), "youtube")


# --- target post ------------------------------------------------------------


class TargetPostAdalahProfilYangSama(unittest.TestCase):
    """Uji ini hanya butuh 1 profil: post-nya dari profil itu juga."""

    def _plan(self, rows):
        conn = KoneksiPalsu(rows=rows)
        with mock.patch.object(se, "count_rows", return_value=0):
            return se.build_plan(conn, "instagram")

    def test_target_post_adalah_profil_yang_sama(self):
        plan = self._plan([("kd-9", "sa-9", "instagram", "kol_x")])
        self.assertEqual(len(plan.post_targets), 1)
        self.assertIs(plan.post_targets[0], plan.profile_target)

    def test_hanya_satu_run_actor(self):
        plan = self._plan([("kd-9", "sa-9", "instagram", "kol_x")])
        self.assertEqual(plan.actor_runs, 1)

    def test_tanpa_kandidat_tidak_ada_target_post(self):
        plan = self._plan([])
        self.assertIsNone(plan.profile_target)
        self.assertEqual(plan.post_targets, [])

    def test_no_posts_menghasilkan_nol_target(self):
        conn = KoneksiPalsu(rows=[("kd-9", "sa-9", "instagram", "kol_x")])
        with mock.patch.object(se, "count_rows", return_value=0):
            plan = se.build_plan(conn, "instagram", with_posts=False)
        self.assertEqual(plan.post_targets, [])
        self.assertIsNotNone(plan.profile_target)

    def test_daftar_23_target_tidak_dipakai_lagi(self):
        self.assertFalse(hasattr(se, "fetch_post_targets"))


# --- actor & platform -------------------------------------------------------


class ActorPerPlatform(unittest.TestCase):
    def test_instagram_memakai_instagram_scraper(self):
        self.assertEqual(se.actor_for("instagram"), "apify/instagram-scraper")
        self.assertEqual(se.actor_for("instagram"), DEFAULT_IG_POST_ACTOR)

    def test_tiktok_memakai_clockworks(self):
        self.assertEqual(se.actor_for("tiktok"), "clockworks/tiktok-scraper")
        self.assertEqual(se.actor_for("tiktok"), DEFAULT_TT_VIDEO_ACTOR)

    def test_profile_scraper_lama_tidak_dipakai(self):
        # Yang dilarang adalah MEMAKAI actor lama, bukan menyebutnya di dokumentasi.
        # Karena itu yang dicari literal string berkutip, bukan teks bebas.
        s = _sumber(se)
        for literal in ('"apify/instagram-profile-scraper"',
                        "'apify/instagram-profile-scraper'"):
            self.assertNotIn(literal, s, "actor lama tidak boleh dipakai scheduler")
        # Dan actor yang benar-benar terdaftar hanya dua.
        terdaftar = {v["actor"] for v in se.PLATFORM_TABLES.values()}
        self.assertEqual(
            terdaftar, {"apify/instagram-scraper", "clockworks/tiktok-scraper"}
        )

    def test_actor_tidak_bisa_dioverride_lewat_env(self):
        with mock.patch.dict(
            "os.environ", {"APIFY_ACTOR_ID": "lain/x", "TIKTOK_ACTOR_ID": "lain/y"}
        ):
            self.assertEqual(se.actor_for("instagram"), "apify/instagram-scraper")
            self.assertEqual(se.actor_for("tiktok"), "clockworks/tiktok-scraper")

    def test_platform_asing_ditolak(self):
        with self.assertRaises(ValueError):
            se.actor_for("youtube")

    def test_tabel_per_platform_tidak_tertukar(self):
        self.assertEqual(se.table_for("instagram", "profile_table"), "l0_raw.ig_profile_apify")
        self.assertEqual(se.table_for("instagram", "post_table"), IG_TABLE)
        self.assertEqual(se.table_for("tiktok", "profile_table"), "l0_raw.tt_profile_apify")
        self.assertEqual(se.table_for("tiktok", "post_table"), TT_TABLE)

    def test_input_instagram_profil_dan_post_sekaligus(self):
        run_input = InstagramDetailsScraper(
            APIFY, results_limit=se.POSTS_PER_TARGET
        ).build_input(["contoh"])
        self.assertEqual(run_input["resultsType"], "details")
        self.assertEqual(run_input["resultsLimit"], 10)

    def test_input_tiktok_sepuluh_video(self):
        run_input = TikTokVideoScraper(
            TIKTOK, results_per_page=se.POSTS_PER_TARGET
        ).build_input(["contoh"])
        self.assertEqual(run_input["resultsPerPage"], 10)
        self.assertEqual(run_input["proxyCountryCode"], "ID")


# --- 10 post terbaru --------------------------------------------------------


class SepuluhPostTerbaru(unittest.TestCase):
    def _items(self, n, key="timestamp"):
        return [{"id": str(i), key: f"2026-08-{i:02d}T00:00:00Z"} for i in range(1, n + 1)]

    def test_dipotong_ke_sepuluh(self):
        self.assertEqual(len(se.latest_posts(self._items(20), "timestamp")), 10)

    def test_yang_diambil_yang_terbaru(self):
        hasil = se.latest_posts(self._items(20), "timestamp")
        self.assertEqual([h["id"] for h in hasil], [str(i) for i in range(20, 10, -1)])

    def test_kunci_tiktok_berbeda(self):
        items = [
            {"id": "lama", "createTimeISO": "2026-01-01T00:00:00Z"},
            {"id": "baru", "createTimeISO": "2026-08-01T00:00:00Z"},
        ]
        self.assertEqual(se.latest_posts(items, "createTimeISO", 1)[0]["id"], "baru")

    def test_post_tanpa_timestamp_kalah(self):
        items = [{"id": "tanpa"}, {"id": "punya", "timestamp": "2020-01-01T00:00:00Z"}]
        self.assertEqual(se.latest_posts(items, "timestamp", 1)[0]["id"], "punya")


# --- deduplication ----------------------------------------------------------


class Deduplication(unittest.TestCase):
    def test_post_yang_sudah_ada_dipisahkan(self):
        conn = KoneksiPalsu(rows=[("sudah-1",)])
        baru, dup = split_new_and_duplicate(
            conn, IG_TABLE, [{"id": "sudah-1"}, {"id": "baru"}], "sa-1"
        )
        self.assertEqual([i["id"] for i in baru], ["baru"])
        self.assertEqual([i["id"] for i in dup], ["sudah-1"])

    def test_dibatasi_ke_akun_yang_sama(self):
        conn = KoneksiPalsu(rows=[])
        split_new_and_duplicate(conn, IG_TABLE, [{"id": "a"}], "sa-1")
        q, params = conn.queries[0]
        self.assertIn("social_account_id = %s", q)
        self.assertEqual(params[1], "sa-1")

    def test_tidak_membuat_unique_constraint(self):
        import post_raw_store
        s = _sumber(post_raw_store)
        self.assertNotRegex(s, r"CREATE\s+UNIQUE|ADD\s+CONSTRAINT|ON\s+CONFLICT")


# --- logging ----------------------------------------------------------------


class LoggingKeSchedulerLogs(unittest.TestCase):
    def test_tabel_tujuan_hanya_scheduler_logs(self):
        import scrape_log
        self.assertEqual(scrape_log.TABLE, "public.scheduler_logs")
        self.assertIn("INSERT INTO public.scheduler_logs", scrape_log._INSERT)

    def test_tidak_ada_schema_schedule_di_kode(self):
        import scrape_log
        for mod in (se, scrape_log):
            s = _sumber(mod)
            self.assertNotIn("schedule.logs", s, mod.__name__)
            self.assertNotRegex(s, r"CREATE\s+SCHEMA|CREATE\s+(OR REPLACE )?VIEW", mod.__name__)

    def test_kategori_profile_dan_post_terpisah(self):
        import scrape_log
        self.assertEqual(scrape_log.SCHEDULER_CATEGORY_PROFILE, "profile")
        self.assertEqual(scrape_log.SCHEDULER_CATEGORY_POST, "post")
        self.assertFalse(hasattr(scrape_log, "SCHEDULER_CATEGORY"))

    def _tangkap_log(self, hasil):
        palsu = mock.MagicMock()
        palsu.__enter__.return_value = palsu
        palsu.log_cycle.return_value = True
        with mock.patch.object(se, "ScrapeLogger", return_value=palsu):
            se.write_log(CFG, hasil)
        return palsu.log_cycle.call_args.kwargs

    def _hasil(self, category, **kw):
        return se.JobResult(
            run_id="run-abc", category=category, platform="instagram",
            actor="apify/instagram-scraper",
            started_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
            finished_at=datetime(2026, 8, 27, tzinfo=timezone.utc), **kw,
        )

    def test_baris_profile_membawa_kategori_profile(self):
        kw = self._tangkap_log(
            self._hasil("profile", status="success", profiles_processed=1, username="kol_x")
        )
        self.assertEqual(kw["category"], "profile")
        self.assertEqual(kw["profiles_processed"], 1)
        self.assertEqual(kw["username"], "kol_x")

    def test_baris_post_membawa_kategori_post(self):
        kw = self._tangkap_log(
            self._hasil("post", status="success", posts_fetched=10,
                        posts_saved=10, duplicates_skipped=0)
        )
        self.assertEqual(kw["category"], "post")
        self.assertEqual((kw["posts_fetched"], kw["posts_saved"]), (10, 10))

    def test_run_id_sama_menghubungkan_kedua_baris(self):
        self.assertEqual(self._hasil("profile").run_id, self._hasil("post").run_id)

    def test_catatan_pada_sukses_diberi_awalan(self):
        kw = self._tangkap_log(self._hasil("post", status="success", notes=["semua duplikat"]))
        self.assertEqual(kw["message"], "catatan: semua duplikat")

    def test_gagal_menulis_log_tidak_melempar(self):
        with mock.patch.object(se, "ScrapeLogger", side_effect=OSError("log mati")):
            self.assertFalse(se.write_log(CFG, self._hasil("profile")))


# --- ketahanan --------------------------------------------------------------


class KegagalanDicatatTanpaRetry(unittest.TestCase):
    def test_profil_gagal_jadi_status_failed(self):
        with mock.patch.object(se, "scrape_target", side_effect=RuntimeError("actor mati")):
            hasil, _, _ = se.run_profile_job(CFG, KoneksiPalsu(), IG_TARGET, "r")
        self.assertEqual(hasil.status, "failed")
        self.assertIn("actor mati", hasil.error_message)
        self.assertEqual(hasil.failed_targets, 1)

    def test_actor_hanya_dipanggil_sekali_saat_gagal(self):
        with mock.patch.object(se, "scrape_target", side_effect=RuntimeError("x")) as sc:
            se.run_profile_job(CFG, KoneksiPalsu(), IG_TARGET, "r")
        sc.assert_called_once()

    def test_satu_target_post_gagal_tidak_menghentikan_sisanya(self):
        panggilan = []

        def palsu(cfg, target):
            panggilan.append(target.username)
            if target.username == "kol_ig":
                raise RuntimeError("diblokir")
            return [], [], (lambda i: target.username)

        with mock.patch.object(se, "scrape_target", side_effect=palsu):
            hasil = se.run_post_job(CFG, KoneksiPalsu(), [IG_TARGET, TT_TARGET], "r",
                                    write=False)
        self.assertEqual(panggilan, ["kol_ig", "kol_tt"])
        self.assertEqual(hasil.failed_targets, 1)
        self.assertEqual(hasil.status, "success")

    def test_semua_target_gagal_jadi_failed(self):
        with mock.patch.object(se, "scrape_target", side_effect=RuntimeError("x")):
            hasil = se.run_post_job(CFG, KoneksiPalsu(), [IG_TARGET], "r", write=False)
        self.assertEqual(hasil.status, "failed")

    def test_target_prescraped_tidak_memanggil_actor_lagi(self):
        with mock.patch.object(se, "scrape_target") as sc:
            se.run_post_job(
                CFG, KoneksiPalsu(), [IG_TARGET], "r", write=False,
                prescraped={"sa-1": ([{"id": "p1"}], lambda i: "kol_ig")},
            )
        sc.assert_not_called()


# --- orkestrasi Dagster -----------------------------------------------------


class OrkestrasiTanpaSchedule(unittest.TestCase):
    def test_file_schedules_lama_sudah_hilang(self):
        self.assertFalse((ORCH / "schedules.py").exists())

    def test_one_shot_tidak_mendefinisikan_schedule(self):
        s = _sumber(ORCH / "one_shot.py")
        self.assertNotIn("ScheduleDefinition(", s)
        self.assertNotIn("cron_schedule", s)
        self.assertNotIn("*/5", s)

    def test_repository_mendaftarkan_schedule_kosong(self):
        s = _sumber(ORCH / "repository.py")
        self.assertIn("schedules=one_shot_schedules", s)

    def test_rantai_transformasi_menutup_semua_layer(self):
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "orchestration"))
        from kol_orchestration.one_shot import TRANSFORM_ASSETS
        for wajib in ("instagram_profile", "instagram_post", "tiktok_profile", "tiktok_post",
                      "unified_profile", "unified_post",
                      "ig_post_analysis", "ig_engagement_analysis",
                      "tt_post_analysis", "tt_engagement_analysis",
                      "kol_profile_card", "kol_metric_daily", "kol_metric_monthly"):
            self.assertIn(wajib, TRANSFORM_ASSETS)



class ActorTepatSekaliPerAkun(unittest.TestCase):
    """Kegagalan menyimpan profil tidak boleh memicu panggilan actor kedua."""

    def _jalankan(self, scrape_side_effect, insert_return=None):
        conn = KoneksiPalsu(rows=[])
        plan = se.ExecutionPlan(
            run_id="r", profile_target=IG_TARGET, post_targets=[IG_TARGET]
        )
        with mock.patch.object(se, "connect") as conn_ctx, \
             mock.patch.object(se, "scrape_target", side_effect=scrape_side_effect) as sc, \
             mock.patch.object(se, "_simpan_profil", return_value=insert_return), \
             mock.patch.object(se, "_simpan_post", return_value=(None, 0)), \
             mock.patch.object(se, "write_log", return_value=True):
            conn_ctx.return_value.__enter__.return_value = conn
            hasil = se.run_once(CFG, plan=plan)
        return sc, hasil

    def test_actor_sekali_walau_simpan_profil_gagal(self):
        stats = mock.Mock(inserted=0, unlinked=0, skipped_failed=1, skipped_no_username=0)
        sc, hasil = self._jalankan(
            lambda cfg, t: ([{"username": "kol_ig"}], [], lambda i: "kol_ig"),
            insert_return=stats,
        )
        sc.assert_called_once()
        self.assertEqual(hasil[0].status, "failed")
        self.assertIn("item error", hasil[0].error_message)

    def test_actor_sekali_walau_run_actor_gagal(self):
        sc, hasil = self._jalankan(RuntimeError("diblokir"))
        sc.assert_called_once()
        self.assertEqual(hasil[0].status, "failed")
        self.assertEqual(hasil[1].status, "failed")
        self.assertIn("TIDAK dipanggil ulang", hasil[1].error_message)

    def test_alasan_kegagalan_menyebut_penyebabnya(self):
        stats = mock.Mock(inserted=0, unlinked=0, skipped_failed=2, skipped_no_username=0)
        pesan = se._alasan_profil_kosong(stats, IG_TARGET)
        self.assertIn("2 item error", pesan)
        self.assertIn("kol_ig", pesan)

    def test_alasan_tanpa_username_dibedakan(self):
        stats = mock.Mock(inserted=0, unlinked=0, skipped_failed=0, skipped_no_username=3)
        self.assertIn("tidak membawa username", se._alasan_profil_kosong(stats, IG_TARGET))


class DurasiMencakupRunActor(unittest.TestCase):
    """duration_seconds harus mengukur actor + penyimpanan, bukan insert saja."""

    def test_profile_memakai_started_at_dari_pemanggil(self):
        # 30 detik lalu: mewakili run actor yang sudah berjalan sebelum
        # pekerjaan ini dipanggil. Durasi tercatat harus mencakupnya.
        awal = datetime.now(timezone.utc) - timedelta(seconds=30)
        with mock.patch.object(se, "_simpan_profil",
                               return_value=mock.Mock(inserted=1, unlinked=0)):
            hasil, _, _ = se.run_profile_job(
                CFG, KoneksiPalsu(), IG_TARGET, "r",
                scraped=([{"username": "kol_ig"}], [], lambda i: "kol_ig"),
                started_at=awal, actor_seconds=12.5,
            )
        self.assertEqual(hasil.started_at, awal)
        self.assertGreaterEqual(hasil.duration_seconds, 30)
        self.assertIn("termasuk 12.50s run actor", "; ".join(hasil.notes))

    def test_post_memakai_started_at_dari_pemanggil(self):
        awal = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)
        hasil = se.run_post_job(
            CFG, KoneksiPalsu(), [IG_TARGET], "r", write=False,
            prescraped={"sa-1": ([{"id": "p1"}], lambda i: "kol_ig")},
            started_at=awal, actor_seconds=12.5,
        )
        self.assertEqual(hasil.started_at, awal)
        self.assertIn("dipakai bersama", "; ".join(hasil.notes))

    def test_run_once_mengukur_dari_sebelum_actor(self):
        """Kedua baris log harus mulai dari saat actor dipanggil."""
        plan = se.ExecutionPlan(
            run_id="r", profile_target=IG_TARGET, post_targets=[IG_TARGET]
        )
        dicatat = []

        def scrape_lambat(cfg, target):
            return ([{"username": "kol_ig"}], [{"id": "p1"}], lambda i: "kol_ig")

        with mock.patch.object(se, "connect") as conn_ctx, \
             mock.patch.object(se, "scrape_target", side_effect=scrape_lambat), \
             mock.patch.object(se, "_simpan_profil",
                               return_value=mock.Mock(inserted=1, unlinked=0)), \
             mock.patch.object(se, "_simpan_post", return_value=(None, 0)), \
             mock.patch.object(se, "write_log", side_effect=lambda c, h: dicatat.append(h)):
            conn_ctx.return_value.__enter__.return_value = KoneksiPalsu()
            se.run_once(CFG, plan=plan)

        self.assertEqual(len(dicatat), 2)
        # Kedua pekerjaan berbagi titik mulai yang sama: saat run actor dimulai.
        self.assertEqual(dicatat[0].started_at, dicatat[1].started_at)
        for h in dicatat:
            self.assertIn("run actor", "; ".join(h.notes))

    def test_tanpa_actor_seconds_tidak_ada_catatan_palsu(self):
        hasil = se.run_post_job(CFG, KoneksiPalsu(), [IG_TARGET], "r", write=False,
                                prescraped={"sa-1": ([], lambda i: "kol_ig")})
        self.assertNotIn("run actor", "; ".join(hasil.notes))


if __name__ == "__main__":
    unittest.main()


# --- orkestrasi: scraping otomatis meneruskan ke L2 -------------------------


class OneShotJobMeneruskanKeGold(unittest.TestCase):
    """one_shot_scrape_job: scraping -> L0 -> Harmonization -> L1 -> Feature -> L2."""

    @classmethod
    def setUpClass(cls):
        import sys
        jalur = str(PROJECT_ROOT / "orchestration")
        if jalur not in sys.path:
            sys.path.insert(0, jalur)
        from kol_orchestration import one_shot
        cls.one_shot = one_shot

    def test_job_punya_dua_op(self):
        # Urutan `graph.nodes` tidak dijamin topologis, jadi yang dibandingkan
        # himpunannya; urutannya diuji lewat peta dependency di bawah.
        graph = self.one_shot.one_shot_scrape_job.graph
        self.assertEqual(set(graph.node_dict), {"scrape_once", "transform_to_gold"})

    def test_transform_bergantung_pada_scrape(self):
        """Inilah yang membuat Dagster menjalankannya berurutan, bukan paralel."""
        graph = self.one_shot.one_shot_scrape_job.graph
        peta = {inv.name: dep for inv, dep in graph.dependencies.items()}

        self.assertEqual(peta["scrape_once"], {}, "scraping tidak boleh punya hulu")

        hulu = peta["transform_to_gold"]
        self.assertEqual(set(hulu), {"hasil_scrape"})
        self.assertEqual(hulu["hasil_scrape"].node, "scrape_once")

    def test_transform_dijalankan_setelah_scrape_sukses(self):
        urutan = []

        def scrape_palsu(**kw):
            urutan.append("scrape")
            return [
                se.JobResult(run_id="r", category="profile", platform="instagram",
                             actor="apify/instagram-scraper", started_at=se._now(),
                             finished_at=se._now(), status="success",
                             username="kol_x", profiles_processed=1),
                se.JobResult(run_id="r", category="post", platform="instagram",
                             actor="apify/instagram-scraper", started_at=se._now(),
                             finished_at=se._now(), status="success",
                             username="kol_x", posts_fetched=10, posts_saved=10),
            ]

        def transform_palsu(logger=None):
            urutan.append("transform")
            return True, [f"{n}: ok" for n in self.one_shot.TRANSFORM_ASSETS]

        with mock.patch.object(self.one_shot, "run_once", side_effect=scrape_palsu), \
             mock.patch.object(self.one_shot, "jalankan_transform_chain",
                               side_effect=transform_palsu):
            hasil = self.one_shot.one_shot_scrape_job.execute_in_process()

        self.assertTrue(hasil.success)
        self.assertEqual(urutan, ["scrape", "transform"])
        keluaran = hasil.output_for_node("transform_to_gold")
        self.assertEqual(keluaran["asset_dimaterialisasi"], 13)

    def test_transform_TIDAK_jalan_kalau_scrape_gagal(self):
        urutan = []

        def scrape_gagal(**kw):
            urutan.append("scrape")
            return [se.JobResult(run_id="r", category="profile", platform="instagram",
                                 actor="apify/instagram-scraper", started_at=se._now(),
                                 finished_at=se._now(), status="failed",
                                 error_message="actor diblokir")]

        def transform_palsu(logger=None):
            urutan.append("transform")
            return True, []

        with mock.patch.object(self.one_shot, "run_once", side_effect=scrape_gagal), \
             mock.patch.object(self.one_shot, "jalankan_transform_chain",
                               side_effect=transform_palsu):
            hasil = self.one_shot.one_shot_scrape_job.execute_in_process(
                raise_on_error=False
            )

        self.assertFalse(hasil.success)
        self.assertEqual(urutan, ["scrape"], "transform tidak boleh jalan")

    def test_transform_gagal_membuat_job_gagal(self):
        def scrape_ok(**kw):
            return [se.JobResult(run_id="r", category="profile", platform="instagram",
                                 actor="apify/instagram-scraper", started_at=se._now(),
                                 finished_at=se._now(), status="success",
                                 username="kol_x", profiles_processed=1)]

        with mock.patch.object(self.one_shot, "run_once", side_effect=scrape_ok), \
             mock.patch.object(self.one_shot, "jalankan_transform_chain",
                               return_value=(False, [])):
            hasil = self.one_shot.one_shot_scrape_job.execute_in_process(
                raise_on_error=False
            )
        self.assertFalse(hasil.success)

    def test_transform_chain_job_tetap_berdiri_sendiri(self):
        job = self.one_shot.transform_chain_job
        self.assertEqual(job.name, "transform_chain_job")
        self.assertIn(job, self.one_shot.one_shot_jobs)
        self.assertIn(self.one_shot.one_shot_scrape_job, self.one_shot.one_shot_jobs)

    def test_rantai_menutup_semua_layer(self):
        for wajib in ("instagram_profile", "instagram_post", "tiktok_profile",
                      "tiktok_post", "unified_profile", "unified_post",
                      "ig_post_analysis", "ig_engagement_analysis",
                      "tt_post_analysis", "tt_engagement_analysis",
                      "kol_profile_card", "kol_metric_daily", "kol_metric_monthly"):
            self.assertIn(wajib, self.one_shot.TRANSFORM_ASSETS)

    def test_tidak_ada_schedule_atau_cron(self):
        # Yang dilarang MEMBUAT schedule, bukan menyebutnya di dokumentasi.
        # Jadi yang dicari pemanggilan dan impor, bukan teks bebas.
        self.assertEqual(self.one_shot.one_shot_schedules, [])
        s = _sumber(ORCH / "one_shot.py")
        self.assertNotIn("ScheduleDefinition(", s)
        self.assertNotIn("cron_schedule=", s)
        self.assertNotIn("*/5", s)
        baris_impor = [b for b in s.splitlines() if "ScheduleDefinition" in b
                       and ("import" in b or b.strip().startswith("Schedule"))]
        self.assertEqual(baris_impor, [], "ScheduleDefinition tidak boleh diimpor")

    def test_repository_tidak_mendaftarkan_schedule(self):
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "orchestration"))
        from kol_orchestration.repository import defs
        with self.assertRaises(Exception):
            defs.get_schedule_def("scheduled_scrape_every_5_min")

    def test_cli_dan_dagster_memakai_fungsi_transform_yang_sama(self):
        s = _sumber(PROJECT_ROOT / "run_e2e_once.py")
        self.assertIn("from kol_orchestration.one_shot import", s)
        self.assertIn("jalankan_transform_chain", s)
