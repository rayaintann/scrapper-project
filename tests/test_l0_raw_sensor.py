"""Sensor l0_raw -> transform_chain_job: trigger, skip, idempotensi, keamanan biaya.

OFFLINE DAN GRATIS
==================
Tidak satu pun tes di sini menyentuh Apify atau Postgres sungguhan:

    * database         diganti `PostgresPalsu`, sebuah PostgresResource yang
                       koneksinya objek dalam-memori. Tidak ada TCP, tidak ada
                       kredensial, tidak ada baris yang berubah.
    * Apify            seluruh entry point actor di-patch dengan pengganti yang
                       MELEDAK kalau dipanggil, lalu dibuktikan tidak pernah
                       meledak selama sensor dievaluasi.
    * rantai transform `transform_chain_job` dijalankan SUNGGUHAN lewat Dagster,
                       tapi satu helper database per modul asset di-stub. Jadi
                       orkestrasinya (13 asset, urutan L0 -> L2) benar-benar
                       diuji, sementara SQL-nya tidak pernah menembak database
                       dan tidak diubah sebaris pun.

Jalankan:
    python -m unittest discover -s tests -t .
"""

import ast
import json
import pathlib
import re
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest import mock

import dagster

from kol_orchestration import one_shot, sensors
from kol_orchestration.resources import PostgresResource
from kol_orchestration.sensors import (
    SENSOR_NAME,
    TABEL_DIPANTAU,
    Sidik,
    ambil_sidik_jari,
    baca_cursor,
    kunci_run,
    l0_raw_new_data_sensor,
    tabel_dengan_data_baru,
    tulis_cursor,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
ORCH = PROJECT_ROOT / "orchestration" / "kol_orchestration"

T0 = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)


def _sumber(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def sidik(**baris_per_tabel) -> dict:
    """Sidik jari lengkap kedelapan tabel; yang tidak disebut dianggap kosong.

    Watermark diturunkan dari jumlah baris supaya "lebih banyak baris" selalu
    berpasangan dengan "watermark lebih baru", seperti di database sungguhan.
    """
    hasil = {}
    for t in TABEL_DIPANTAU:
        n = baris_per_tabel.get(t, 0)
        hasil[t] = Sidik(baris=n, watermark=T0 + timedelta(minutes=n) if n else None)
    return hasil


class KoneksiPalsu:
    """Koneksi psycopg2 tiruan yang mengembalikan sidik jari yang sudah disiapkan."""

    def __init__(self, sidik_jari: dict, query_tercatat: list):
        self._sidik = sidik_jari
        self._query = query_tercatat
        self.ditutup = False

    def cursor(self):
        koneksi = self

        class _Cur:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def execute(self_inner, sql, params=None):
                koneksi._query.append(sql)

            def fetchall(self_inner):
                return [
                    (nama, s.baris, s.watermark)
                    for nama, s in koneksi._sidik.items()
                ]

        return _Cur()

    def close(self):
        self.ditutup = True


#: Meja tulis untuk PostgresPalsu, di luar objek resource-nya.
#: Dagster MENYALIN ConfigurableResource saat menginisialisasinya, jadi state
#: yang ditempel ke instance akan hilang di tengah jalan. Yang ikut tersalin
#: hanya field pydantic — karena itu instance-nya cuma membawa `kunci` (str)
#: dan seluruh state hidupnya dititipkan di sini.
_MEJA: dict[str, dict] = {}


class PostgresPalsu(PostgresResource):
    """PostgresResource yang tidak pernah membuka soket.

    Subclass sungguhan, bukan Mock, supaya sensor menerima tipe resource yang
    persis sama dengan produksi dan jalur `get_conn -> cursor -> execute` tetap
    diuji apa adanya.
    """

    kunci: str

    def get_conn(self):
        meja = _MEJA[self.kunci]
        koneksi = KoneksiPalsu(meja["sidik"], meja["query"])
        meja["koneksi"].append(koneksi)
        return koneksi


def buat_postgres_palsu(sidik_jari: dict) -> PostgresPalsu:
    kunci = str(len(_MEJA))
    _MEJA[kunci] = {"sidik": sidik_jari, "query": [], "koneksi": []}
    return PostgresPalsu(connection_string="postgresql://palsu/kol", kunci=kunci)


def query_dijalankan(pg: PostgresPalsu) -> list:
    return _MEJA[pg.kunci]["query"]


def koneksi_dibuat(pg: PostgresPalsu) -> list:
    return _MEJA[pg.kunci]["koneksi"]


def evaluasi(sidik_jari: dict, cursor: str | None):
    """Jalankan satu tick sensor dengan database palsu. Mengembalikan SensorResult."""
    ctx = dagster.build_sensor_context(cursor=cursor, sensor_name=SENSOR_NAME)
    # Resource dilewatkan sebagai keyword sesuai nama parameternya: Dagster
    # membedakan argumen resource dari argumen context lewat nama, bukan posisi.
    return l0_raw_new_data_sensor(ctx, postgres=buat_postgres_palsu(sidik_jari))


# ===========================================================================
# 1. Data baru di L0 -> sensor menghasilkan trigger
# ===========================================================================


class DataBaruMemicuTrigger(unittest.TestCase):
    def test_baris_bertambah_menghasilkan_run_request(self):
        sebelum = sidik(ig_profile_apify=952)
        sesudah = sidik(ig_profile_apify=960)

        hasil = evaluasi(sesudah, tulis_cursor(sebelum))

        self.assertEqual(len(hasil.run_requests), 1, "harus ada tepat satu run")
        self.assertIsNone(hasil.skip_reason)

    def test_run_request_menunjuk_tabel_yang_berubah(self):
        sebelum = sidik(ig_profile_apify=952, tt_video_apify=291)
        sesudah = sidik(ig_profile_apify=952, tt_video_apify=300)

        hasil = evaluasi(sesudah, tulis_cursor(sebelum))

        tags = hasil.run_requests[0].tags
        self.assertEqual(tags["l0_raw/tabel_baru"], "tt_video_apify")
        self.assertEqual(tags["l0_raw/pemicu"], SENSOR_NAME)

    def test_watermark_maju_tanpa_perubahan_jumlah_baris_tetap_memicu(self):
        # Kasus langka: sebagian baris dihapus manual lalu masuk baris baru,
        # sehingga count(*) kebetulan sama. max(fetched_at) yang menangkapnya.
        lama = {"ig_profile_apify": Sidik(baris=100, watermark=T0)}
        baru = {"ig_profile_apify": Sidik(baris=100, watermark=T0 + timedelta(hours=1))}

        self.assertEqual(tabel_dengan_data_baru(lama, baru), ["ig_profile_apify"])

    def test_cursor_ikut_maju_saat_memicu(self):
        sesudah = sidik(ig_profile_apify=960)
        hasil = evaluasi(sesudah, tulis_cursor(sidik(ig_profile_apify=952)))
        self.assertEqual(baca_cursor(hasil.cursor), sesudah)


# ===========================================================================
# 2. Tidak ada data baru -> tidak trigger
# ===========================================================================


class TanpaDataBaruTidakTrigger(unittest.TestCase):
    def test_sidik_jari_identik_menghasilkan_skip(self):
        sama = sidik(ig_profile_apify=952, tt_video_apify=291)

        hasil = evaluasi(sama, tulis_cursor(sama))

        self.assertEqual(list(hasil.run_requests or []), [])
        self.assertIsNotNone(hasil.skip_reason)
        self.assertIn("Tidak ada data baru", hasil.skip_reason.skip_message)

    def test_l0_kosong_tidak_pernah_memicu(self):
        kosong = sidik()
        hasil = evaluasi(kosong, tulis_cursor(kosong))
        self.assertEqual(list(hasil.run_requests or []), [])

    def test_baris_berkurang_bukan_data_baru(self):
        # Baris hilang bukan alasan menjalankan transformasi, tapi cursor tetap
        # turun supaya sensor tidak tersangkut membandingkan dengan angka lama.
        sebelum = sidik(ig_profile_apify=952)
        sesudah = sidik(ig_profile_apify=900)

        hasil = evaluasi(sesudah, tulis_cursor(sebelum))

        self.assertEqual(list(hasil.run_requests or []), [])
        self.assertEqual(baca_cursor(hasil.cursor), sesudah)

    def test_tick_pertama_hanya_mencatat_baseline(self):
        hasil = evaluasi(sidik(ig_profile_apify=952), cursor=None)

        self.assertEqual(list(hasil.run_requests or []), [])
        self.assertIn("baseline", hasil.skip_reason.skip_message)
        self.assertIsNotNone(hasil.cursor)

    def test_cursor_rusak_diperlakukan_sebagai_baseline_bukan_trigger(self):
        for rusak in ("bukan json", "[]", '{"versi":99,"tabel":{}}',
                      '{"versi":1,"tabel":{"x":"bukan objek"}}'):
            with self.subTest(rusak=rusak):
                hasil = evaluasi(sidik(ig_profile_apify=952), cursor=rusak)
                self.assertEqual(list(hasil.run_requests or []), [], rusak)


# ===========================================================================
# 3. Data yang sama tidak ditrigger berulang
# ===========================================================================


class TidakTriggerBerulang(unittest.TestCase):
    def test_tick_kedua_atas_data_yang_sama_tidak_memicu_lagi(self):
        sebelum = sidik(ig_profile_apify=952)
        sesudah = sidik(ig_profile_apify=960)

        tick1 = evaluasi(sesudah, tulis_cursor(sebelum))
        self.assertEqual(len(tick1.run_requests), 1)

        # Data tidak berubah lagi; cursor dari tick1 dipakai apa adanya.
        tick2 = evaluasi(sesudah, tick1.cursor)
        self.assertEqual(list(tick2.run_requests or []), [])

        tick3 = evaluasi(sesudah, tick2.cursor)
        self.assertEqual(list(tick3.run_requests or []), [])

    def test_run_key_stabil_untuk_keadaan_data_yang_sama(self):
        # Lapis kedua: walau cursor hilang, Dagster menolak run_key berulang.
        a = evaluasi(sidik(ig_profile_apify=960), tulis_cursor(sidik(ig_profile_apify=952)))
        b = evaluasi(sidik(ig_profile_apify=960), tulis_cursor(sidik(ig_profile_apify=950)))

        self.assertEqual(a.run_requests[0].run_key, b.run_requests[0].run_key)

    def test_run_key_berbeda_untuk_keadaan_data_berbeda(self):
        self.assertNotEqual(
            kunci_run(sidik(ig_profile_apify=960)),
            kunci_run(sidik(ig_profile_apify=961)),
        )

    def test_run_key_tidak_mengandung_waktu_evaluasi(self):
        # Kalau run_key ikut jam dinding, dedup Dagster tidak akan pernah kena.
        k1 = kunci_run(sidik(ig_profile_apify=960))
        k2 = kunci_run(sidik(ig_profile_apify=960))
        self.assertEqual(k1, k2)

    def test_run_request_selalu_membawa_run_key(self):
        hasil = evaluasi(sidik(tt_video_apify=300), tulis_cursor(sidik(tt_video_apify=291)))
        self.assertTrue(hasil.run_requests[0].run_key)

    def test_cursor_bolak_balik_serialisasi_tanpa_kehilangan_nilai(self):
        asli = sidik(ig_profile_apify=952, tt_video_apify=291)
        self.assertEqual(baca_cursor(tulis_cursor(asli)), asli)

    def test_state_hanya_di_cursor_dagster_bukan_tabel_baru(self):
        s = _sumber(ORCH / "sensors.py")
        for terlarang in ("INSERT INTO", "CREATE TABLE", "UPDATE ", "DELETE "):
            self.assertNotIn(terlarang, s.upper().replace("DELETE)", ""),
                             "sensor tidak boleh menulis apa pun")


# ===========================================================================
# 4. Transformasi berjalan sampai L2
# ===========================================================================


class RantaiSampaiL2(unittest.TestCase):
    def test_sensor_menargetkan_transform_chain_job(self):
        nama = [t.job_name for t in l0_raw_new_data_sensor.targets]
        self.assertEqual(nama, [one_shot.TRANSFORM_JOB_NAME])

    def test_transform_chain_job_mencakup_l0_sampai_l2(self):
        wajib = {
            # L0 Harmonization
            "instagram_profile", "tiktok_profile", "instagram_post", "tiktok_post",
            # L1 Silver
            "unified_profile", "unified_post",
            # Feature
            "ig_engagement_analysis", "tt_engagement_analysis",
            "ig_post_analysis", "tt_post_analysis",
            # L2 Gold
            "kol_profile_card", "kol_metric_daily", "kol_metric_monthly",
        }
        self.assertTrue(wajib.issubset(set(one_shot.TRANSFORM_ASSETS)))

    def test_dependency_asset_berurutan_l0_ke_l2(self):
        """Urutan dijamin `deps` antar-asset, bukan urutan daftar."""
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "orchestration"))
        from dagster import AssetKey
        from kol_orchestration.repository import defs

        graph = defs.resolve_asset_graph()

        def deps(nama):
            return {k.to_user_string()
                    for k in graph.get(AssetKey(nama)).parent_keys}

        # L1 Silver membaca L0 Harmonization
        self.assertLessEqual({"instagram_profile", "tiktok_profile"},
                             deps("unified_profile"))
        self.assertLessEqual({"instagram_post", "tiktok_post", "unified_profile"},
                             deps("unified_post"))
        # Feature membaca L1 Silver. Engagement per akun butuh keduanya
        # (metrik post dibagi jumlah follower); analisis per post cukup
        # unified_post karena grain-nya memang per post.
        for fitur in ("ig_engagement_analysis", "tt_engagement_analysis"):
            self.assertLessEqual({"unified_post", "unified_profile"}, deps(fitur),
                                 fitur)
        for fitur in ("ig_post_analysis", "tt_post_analysis"):
            self.assertIn("unified_post", deps(fitur), fitur)
        # L2 Gold membaca L1 Silver, dan monthly membaca daily
        self.assertLessEqual({"unified_post", "unified_profile"},
                             deps("kol_metric_daily"))
        self.assertIn("unified_profile", deps("kol_profile_card"))
        self.assertIn("kol_metric_daily", deps("kol_metric_monthly"))

    def test_job_yang_dipicu_benar_benar_jalan_sampai_l2(self):
        """Eksekusi `transform_chain_job` sungguhan, dengan SQL-nya di-stub.

        Yang diuji ORKESTRASInya: apakah job yang dipicu sensor benar-benar
        menjalankan ke-13 asset dan berhenti di L2 Gold. Isi SQL tiap asset
        tidak disentuh dan tidak diubah -- hanya satu helper per modul yang
        diganti, supaya tes ini tetap offline dan tidak menulis ke database.
        """
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "orchestration"))
        import warnings

        from dagster import Output
        from kol_orchestration.assets import (
            feature_engagement, feature_post, gold, gold_profile,
            harmonization, silver,
        )
        from kol_orchestration.repository import defs

        dijalankan = []

        def rekam(*a, **k):
            return Output(0)

        # (modul, nama helper) -- satu titik masuk database per modul.
        TITIK_DB = (
            (harmonization, "_jalankan"), (silver, "_jalankan"),
            (feature_engagement, "_jalankan"), (feature_post, "_jalankan"),
            (gold, "_jalankan"), (gold, "_jalankan_bulanan"),
            (gold_profile, "_jalankan"),
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            job = defs.resolve_job_def(one_shot.TRANSFORM_JOB_NAME)

        with ExitStack() as tumpukan:
            for modul, helper in TITIK_DB:
                tumpukan.enter_context(
                    mock.patch.object(modul, helper, side_effect=rekam)
                )
            hasil = job.execute_in_process(
                resources={"postgres": buat_postgres_palsu(sidik())},
                raise_on_error=False,
            )

        self.assertTrue(hasil.success, "rantai harus selesai sampai L2")

        dijalankan = [
            ev.event_specific_data.materialization.asset_key.to_user_string()
            for ev in hasil.get_asset_materialization_events()
        ]
        self.assertEqual(sorted(dijalankan), sorted(one_shot.TRANSFORM_ASSETS))
        # Ujung rantai memang L2 Gold, bukan berhenti di Feature.
        for l2 in ("kol_profile_card", "kol_metric_daily", "kol_metric_monthly"):
            self.assertIn(l2, dijalankan)

    def test_urutan_eksekusi_l0_ke_l2_dijaga_dagster(self):
        """Urutan datang dari `deps` di job hasil resolve, bukan urutan daftar."""
        import sys
        import warnings
        sys.path.insert(0, str(PROJECT_ROOT / "orchestration"))
        from kol_orchestration.repository import defs

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            job = defs.resolve_job_def(one_shot.TRANSFORM_JOB_NAME)

        induk = {
            simpul.name: set(dep)
            for simpul, dep in job.dependencies.items()
        }

        # Kedalaman topologis: 0 untuk yang tidak punya induk.
        def kedalaman(nama, terlihat=frozenset()):
            self.assertNotIn(nama, terlihat, "graf tidak boleh melingkar")
            if not induk.get(nama):
                return 0
            return 1 + max(kedalaman(p, terlihat | {nama})
                           for p in induk[nama])

        d = {n: kedalaman(n) for n in induk}

        for l0 in ("instagram_profile", "tiktok_profile",
                   "instagram_post", "tiktok_post"):
            self.assertEqual(d[l0], 0, l0)
        self.assertLess(d["unified_profile"], d["unified_post"])
        for hilir in ("ig_engagement_analysis", "tt_engagement_analysis",
                      "ig_post_analysis", "tt_post_analysis",
                      "kol_metric_daily"):
            self.assertGreater(d[hilir], d["unified_post"], hilir)
        self.assertGreater(d["kol_metric_monthly"], d["kol_metric_daily"])
        self.assertGreater(d["kol_profile_card"], d["unified_profile"])


# ===========================================================================
# 5. Sensor tidak pernah memanggil actor
# ===========================================================================


class SensorTidakMemanggilActor(unittest.TestCase):
    """Requirement biaya: satu evaluasi sensor tidak boleh menagih satu kredit pun."""

    #: Entry point yang benar-benar menembak Apify.
    ENTRY_POINT_BERBIAYA = (
        ("apify_runner", "ApifyClient"),
        ("apify_posts", "InstagramDetailsScraper"),
        ("apify_posts", "TikTokVideoScraper"),
        ("scheduler_engine", "run_once"),
    )

    def test_evaluasi_sensor_tidak_menyentuh_apify(self):
        import importlib

        def meledak(*a, **k):
            raise AssertionError("sensor memanggil actor Apify")

        patcher = []
        for modul, atribut in self.ENTRY_POINT_BERBIAYA:
            m = importlib.import_module(modul)
            if hasattr(m, atribut):
                patcher.append(mock.patch.object(m, atribut, side_effect=meledak))

        self.assertTrue(patcher, "tidak ada entry point yang berhasil di-patch")
        with mock.patch.object(one_shot, "jalankan_transform_chain",
                               side_effect=meledak):
            for p in patcher:
                p.start()
            try:
                # Ketiga jalur keputusan sensor dijalankan: baseline, skip, trigger.
                evaluasi(sidik(ig_profile_apify=952), cursor=None)
                evaluasi(sidik(ig_profile_apify=952),
                         tulis_cursor(sidik(ig_profile_apify=952)))
                hasil = evaluasi(sidik(ig_profile_apify=960),
                                 tulis_cursor(sidik(ig_profile_apify=952)))
            finally:
                for p in patcher:
                    p.stop()

        # Sensor hanya MEMINTA run; ia tidak menjalankan job-nya sendiri.
        self.assertEqual(len(hasil.run_requests), 1)

    def test_sensor_hanya_menjalankan_query_read_only(self):
        pg = buat_postgres_palsu(sidik(ig_profile_apify=952))
        ctx = dagster.build_sensor_context(cursor=None, sensor_name=SENSOR_NAME)
        l0_raw_new_data_sensor(ctx, postgres=pg)

        self.assertEqual(len(query_dijalankan(pg)), 1, "cukup satu round-trip")
        sql = query_dijalankan(pg)[0].upper()
        self.assertTrue(sql.lstrip().startswith("SELECT"))
        for terlarang in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP",
                          "ALTER", "TRUNCATE"):
            self.assertNotIn(terlarang, sql)

    def test_modul_sensor_tidak_mengimpor_apify(self):
        pohon = ast.parse(_sumber(ORCH / "sensors.py"))
        diimpor = set()
        for simpul in ast.walk(pohon):
            if isinstance(simpul, ast.Import):
                diimpor.update(a.name for a in simpul.names)
            elif isinstance(simpul, ast.ImportFrom) and simpul.module:
                diimpor.add(simpul.module)

        for nama in diimpor:
            self.assertFalse(nama.startswith("apify"), nama)
            self.assertNotIn("scraper", nama.lower())
            self.assertNotEqual(nama, "scheduler_engine")

    def test_sensor_tidak_menargetkan_job_scraping(self):
        nama = {t.job_name for t in l0_raw_new_data_sensor.targets}
        self.assertNotIn(one_shot.SCRAPE_JOB_NAME, nama)

    def test_one_shot_scrape_job_tetap_ada_dan_berurutan(self):
        """Requirement 13: jalur manual scrape -> transform tidak boleh hilang."""
        job = one_shot.one_shot_scrape_job
        self.assertEqual(job.name, "one_shot_scrape_job")
        nama_op = {n.name for n in job.graph.node_defs}
        self.assertEqual(nama_op, {"scrape_once", "transform_to_gold"})
        self.assertIn(job, one_shot.one_shot_jobs)

    def test_transform_chain_job_tetap_bisa_manual_tanpa_scraping(self):
        """Requirement 14."""
        self.assertIn(one_shot.transform_chain_job, one_shot.one_shot_jobs)
        self.assertEqual(one_shot.transform_chain_job.name, "transform_chain_job")

    def test_sensor_tidak_menyentuh_scheduler_logs(self):
        """`public.scheduler_logs` tetap milik scraping, bukan milik sensor.

        Kalau sensor ikut menulis ke sana, tabel itu berhenti berarti "riwayat
        scraping" dan jadi campuran dua hal yang berbeda.
        """
        s = _sumber(ORCH / "sensors.py")
        self.assertNotIn("scheduler_logs", s)
        self.assertNotIn("scrape_log", s)

    def test_penulis_scheduler_logs_tetap_hanya_scrape_log(self):
        import scrape_log
        self.assertEqual(scrape_log.TABLE, "public.scheduler_logs")
        self.assertIn("INSERT INTO public.scheduler_logs", scrape_log._INSERT)


class ServiceWindowsTidakMemanggilScraping(unittest.TestCase):
    """Script yang menghidupkan Dagster otomatis tidak boleh jadi jalur ke Apify."""

    SERVICE = PROJECT_ROOT / "orchestration" / "service"
    SCRIPT = ("jalankan_dagster.ps1", "pasang_task_windows.ps1",
              "copot_task_windows.ps1")

    def test_script_service_ada(self):
        for n in self.SCRIPT:
            self.assertTrue((self.SERVICE / n).exists(), n)

    @staticmethod
    def _kode_saja(path: pathlib.Path) -> str:
        """Isi script tanpa komentar, huruf kecil.

        Yang dilarang adalah MENJALANKAN scraping, bukan menyebutnya di
        dokumentasi -- dan dokumentasi ketiga script ini memang menjelaskan
        panjang lebar apa yang sengaja TIDAK dipanggil. Jadi blok bantuan
        `<# ... #>` dan komentar `#` dibuang dulu sebelum diperiksa.
        """
        s = re.sub(r"<#.*?#>", "", _sumber(path), flags=re.DOTALL)
        return "\n".join(b.split("#", 1)[0] for b in s.splitlines()).lower()

    def test_tidak_ada_pemanggilan_scraping_di_script_service(self):
        """Yang dicari token PEMANGGILAN, bukan kata bebas.

        `pasang_task_windows.ps1` memang menulis kalimat "tidak memanggil Apify"
        ke dalam Description task-nya, dan kalimat itu memang harus ada di sana
        supaya orang yang membuka Task Scheduler tahu task ini bukan scraper.
        Jadi yang dilarang adalah nama modul dan entry point yang bisa
        DIEKSEKUSI, bukan kemunculan kata "apify" di mana pun.
        """
        for n in self.SCRIPT:
            kode = self._kode_saja(self.SERVICE / n)
            for terlarang in ("scheduler_engine", "apify_", "run_once",
                              "one_shot_scrape_job", "scrape_once", ".py"):
                self.assertNotIn(terlarang, kode, f"{n}: {terlarang}")

    def test_hanya_executable_dagster_yang_dijalankan(self):
        """Positif, bukan cuma negatif: yang dieksekusi memang proses Dagster."""
        kode = self._kode_saja(self.SERVICE / "jalankan_dagster.ps1")
        self.assertIn("dagster-daemon.exe", kode)
        self.assertIn("dagster-webserver.exe", kode)
        self.assertNotIn("dagster dev", kode, "dagster dev bukan solusi service")

    def test_script_service_tidak_membuat_schedule_dagster(self):
        for n in self.SCRIPT:
            kode = self._kode_saja(self.SERVICE / n)
            self.assertNotIn("scheduledefinition", kode)
            self.assertNotIn("cron_schedule", kode)

    def test_daemon_adalah_peran_default(self):
        """Sensor tidak jalan tanpa daemon, jadi itu yang harus default."""
        self.assertIn("[string]$peran = 'daemon'",
                      self._kode_saja(self.SERVICE / "jalankan_dagster.ps1"))

    def test_webserver_hanya_localhost(self):
        # Dagster tidak punya autentikasi bawaan: UI yang terikat ke 0.0.0.0
        # berarti siapa pun di jaringan bisa meluncurkan job.
        kode = self._kode_saja(self.SERVICE / "jalankan_dagster.ps1")
        self.assertIn("'-h', '127.0.0.1'", kode)
        self.assertNotIn("0.0.0.0", kode)


class CodeServerTerpisah(unittest.TestCase):
    """Code server dijalankan sendiri, bukan di-spawn ulang tiap tick sensor.

    Code server yang di-spawn daemon dijalankan dengan `--heartbeat
    --heartbeat-timeout 20`, sementara daemon hanya memegang code location
    selama satu tick. Dengan sensor tiap 60 detik, ada ~40 detik hening dan
    server itu mematikan diri tiap siklus lalu di-spawn ulang — mengimpor ulang
    modul yang berat setiap kali. `DAEMON_GRPC_SERVER_HEARTBEAT_TTL` di Dagster
    hardcoded 20 detik dan tidak ada opsi `dagster.yaml` untuk mengubahnya.
    """

    SERVICE = PROJECT_ROOT / "orchestration" / "service"
    WORKSPACE = PROJECT_ROOT / "orchestration" / "workspace.yaml"
    #: Harus sama persis dengan nama location sebelum perubahan. Status sensor
    #: (RUNNING) dan cursor-nya disimpan dengan kunci nama location; kalau
    #: berubah, sensor dianggap baru dan cursornya hilang.
    NAMA_LOCATION = "kol_orchestration.repository"

    def _kode(self):
        return ServiceWindowsTidakMemanggilScraping._kode_saja(
            self.SERVICE / "jalankan_dagster.ps1"
        )

    def test_workspace_mengarah_ke_grpc_server_bukan_python_module(self):
        w = _sumber(self.WORKSPACE)
        baris = [b.strip() for b in w.splitlines()
                 if b.strip() and not b.strip().startswith("#")]
        teks = "\n".join(baris)
        self.assertIn("grpc_server:", teks)
        self.assertNotIn("python_module:", teks,
                         "python_module membuat tiap proses spawn code server sendiri")

    def test_workspace_dan_launcher_sepakat_soal_port(self):
        w = _sumber(self.WORKSPACE)
        port_workspace = re.search(r"^\s*port:\s*(\d+)", w, re.M)
        self.assertIsNotNone(port_workspace, "workspace.yaml harus menyebut port")
        port_launcher = re.search(r"\$portcodeserver\s*=\s*(\d+)", self._kode())
        self.assertIsNotNone(port_launcher, "launcher harus punya default port")
        self.assertEqual(port_workspace.group(1), port_launcher.group(1))

    def test_nama_location_dipertahankan_di_kedua_tempat(self):
        w = _sumber(self.WORKSPACE)
        self.assertIn(f'location_name: "{self.NAMA_LOCATION}"', w)
        self.assertIn(f"'--location-name', '{self.NAMA_LOCATION}'",
                      _sumber(self.SERVICE / "jalankan_dagster.ps1"))

    def test_code_server_dijalankan_tanpa_heartbeat(self):
        """Inti perbaikannya. `--heartbeat` membuat server bunuh diri di sela tick."""
        kode = self._kode()
        self.assertIn("'api', 'grpc'", kode)
        self.assertNotIn("--heartbeat", kode)

    def test_peran_codeserver_tersedia(self):
        kode = self._kode()
        self.assertIn("'codeserver', 'daemon', 'webserver'", kode)

    def test_installer_memasang_task_code_server(self):
        s = _sumber(self.SERVICE / "pasang_task_windows.ps1")
        self.assertIn("KOL Dagster Code Server", s)
        # Code server harus didaftarkan SEBELUM daemon: daemon tidak bisa
        # me-resolve workspace.yaml tanpa server itu hidup.
        self.assertLess(s.index("KOL Dagster Code Server"),
                        s.index("'KOL Dagster Daemon'"))

    def test_uninstaller_ikut_mencopot_code_server(self):
        self.assertIn("KOL Dagster Code Server",
                      _sumber(self.SERVICE / "copot_task_windows.ps1"))


# ===========================================================================
# 6. Tidak ada ScheduleDefinition / cron
# ===========================================================================


class TanpaScheduleAtauCron(unittest.TestCase):
    FILE_ORKESTRASI = ("sensors.py", "one_shot.py", "repository.py")

    def test_definitions_tidak_punya_schedule_satu_pun(self):
        """Yang dilihat UI/GraphQL adalah repository hasil resolve, bukan daftar
        mentah — jadi keduanya diperiksa."""
        import sys
        import warnings
        sys.path.insert(0, str(PROJECT_ROOT / "orchestration"))
        from kol_orchestration.repository import defs

        self.assertEqual(list(defs.schedules or []), [], "jumlah schedule harus 0")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            repo = defs.get_repository_def()
        self.assertEqual(list(repo.schedule_defs), [], "jumlah schedule harus 0")
        self.assertEqual([s.name for s in repo.sensor_defs], [SENSOR_NAME])

    def test_daftar_schedule_masih_kosong(self):
        self.assertEqual(one_shot.one_shot_schedules, [])

    def test_tidak_ada_schedule_atau_cron_di_kode_orkestrasi(self):
        for nama in self.FILE_ORKESTRASI:
            s = _sumber(ORCH / nama)
            with self.subTest(file=nama):
                self.assertNotIn("ScheduleDefinition(", s)
                self.assertNotIn("cron_schedule=", s)
                self.assertNotIn("@schedule", s)
                self.assertNotIn("build_schedule_from", s)

    def test_sensor_memakai_dekorator_sensor_bukan_schedule(self):
        s = _sumber(ORCH / "sensors.py")
        self.assertIn("@sensor(", s)
        self.assertIsInstance(l0_raw_new_data_sensor, dagster.SensorDefinition)

    def test_interval_sensor_bukan_ekspresi_cron(self):
        # `minimum_interval_seconds` adalah jeda antar-pengecekan, bukan jadwal:
        # tanpa data baru, tidak ada run seberapa sering pun sensor dievaluasi.
        self.assertIsInstance(sensors.MINIMUM_INTERVAL_SECONDS, int)
        s = _sumber(ORCH / "sensors.py")
        self.assertNotIn("*/5", s)
        self.assertNotIn("* * * * *", s)

    def test_definitions_masih_memakai_daftar_schedule_kosong(self):
        s = _sumber(ORCH / "repository.py")
        self.assertIn("schedules=one_shot_schedules", s)
        self.assertIn("sensors=l0_raw_sensors", s)


# ===========================================================================
# Sidik jari: mekanisme deteksi memang stabil (bukan timestamp yang selalu ganti)
# ===========================================================================


class MekanismeDeteksiStabil(unittest.TestCase):
    def test_sql_hanya_agregat_atas_tabel_yang_dipantau(self):
        sql = sensors.sql_sidik_jari()
        for t in TABEL_DIPANTAU:
            self.assertIn("l0_raw." + t, sql)
        self.assertEqual(sql.count("count(*)"), len(TABEL_DIPANTAU))
        self.assertEqual(sql.count("max(fetched_at)"), len(TABEL_DIPANTAU))

    def test_tidak_memakai_now_atau_waktu_evaluasi(self):
        # Inti requirement: kalau sidik jari mengandung waktu sekarang, sensor
        # akan trigger tiap tick walau data tidak berubah sama sekali.
        sql = sensors.sql_sidik_jari().lower()
        for terlarang in ("now()", "current_timestamp", "clock_timestamp",
                          "statement_timestamp", "random()"):
            self.assertNotIn(terlarang, sql)

    def test_tidak_memakai_id_uuid_sebagai_watermark(self):
        # id l0_raw adalah gen_random_uuid(): acak, tidak monoton, tidak bisa
        # dipakai sebagai watermark.
        sql = sensors.sql_sidik_jari().lower()
        self.assertNotIn("max(id)", sql)
        self.assertNotIn("scrape_run_id", sql)

    def test_sidik_jari_dua_evaluasi_atas_data_sama_identik(self):
        pg = buat_postgres_palsu(sidik(ig_profile_apify=952, tt_video_apify=291))
        self.assertEqual(ambil_sidik_jari(pg), ambil_sidik_jari(pg))

    def test_koneksi_selalu_ditutup(self):
        pg = buat_postgres_palsu(sidik(ig_profile_apify=1))
        ambil_sidik_jari(pg)
        self.assertTrue(all(c.ditutup for c in koneksi_dibuat(pg)))

    def test_tabel_dipantau_hanya_sumber_rantai_transformasi(self):
        # Tabel l0_raw lain (comments, stories, followers, roster) sengaja tidak
        # dipantau: tidak ada asset di transform_chain_job yang membacanya.
        self.assertEqual(len(TABEL_DIPANTAU), 8)
        for t in TABEL_DIPANTAU:
            self.assertTrue(t.endswith("_apify") or t.endswith("_official"), t)
        for tidak_dipantau in ("ig_comments_apify", "ig_stories_apify",
                               "ig_followers_apify", "kol_roster_import",
                               "tt_comments_apify", "ig_tagged_posts_apify"):
            self.assertNotIn(tidak_dipantau, TABEL_DIPANTAU)

    def test_cursor_berbentuk_json_berversi(self):
        isi = json.loads(tulis_cursor(sidik(ig_profile_apify=952)))
        self.assertEqual(isi["versi"], sensors.CURSOR_VERSION)
        self.assertIn("ig_profile_apify", isi["tabel"])


if __name__ == "__main__":
    unittest.main()
