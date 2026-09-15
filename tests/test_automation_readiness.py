"""Test untuk perubahan kesiapan automation (G1-G8).

Tiga kelompok, semuanya OFFLINE kecuali yang ditandai `needs_db`:

  1. `run_lock` -- kunci antar-proses.
  2. Pemilihan akun & cost guard `scrape_followers`.
  3. Kontrak orkestrasi: chain, sensor, dan pemulihan run gagal.

Tidak satu pun test di sini memanggil Apify.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from run_lock import EXIT_TERKUNCI, LockTaken, RunLock, jalankan_terkunci  # noqa: E402


# =====================================================================
# 1. run_lock -- G7
# =====================================================================

@pytest.fixture
def lock_dir(tmp_path):
    return tmp_path / "locks"


def test_kunci_pertama_berhasil(lock_dir):
    with RunLock("uji", lock_dir=lock_dir) as k:
        assert k.path.exists()
    assert not k.path.exists(), "kunci harus dilepas setelah blok selesai"


def test_kunci_kedua_ditolak_selagi_dipegang(lock_dir):
    with RunLock("uji", lock_dir=lock_dir):
        with pytest.raises(LockTaken):
            RunLock("uji", lock_dir=lock_dir).acquire()


def test_kunci_berbeda_nama_tidak_saling_menghalangi(lock_dir):
    """post-ig dan post-tt harus bisa jalan bersamaan."""
    with RunLock("post_instagram", lock_dir=lock_dir):
        with RunLock("post_tiktok", lock_dir=lock_dir):
            pass


def test_kunci_yatim_diambil_alih(lock_dir):
    """Proses mati tanpa sempat membersihkan tidak boleh memblokir selamanya."""
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "uji.lock").write_text(json.dumps({
        # PID yang hampir pasti tidak ada. 0 ditolak `_proses_hidup`.
        "pid": 999_999_998,
        "dibuat": "2020-01-01T00:00:00+00:00",
        "perintah": "proses yang sudah lama mati",
    }), encoding="utf-8")
    with RunLock("uji", lock_dir=lock_dir) as k:
        assert json.loads(k.path.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_kunci_hidup_tapi_kedaluwarsa_diambil_alih(lock_dir):
    """Jaring pengaman untuk PID yang didaur ulang OS."""
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "uji.lock").write_text(json.dumps({
        "pid": os.getpid(),           # hidup: ini proses tes sendiri
        "dibuat": "2020-01-01T00:00:00+00:00",
        "perintah": "tua sekali",
    }), encoding="utf-8")
    with RunLock("uji", lock_dir=lock_dir, max_umur_jam=1.0) as k:
        assert k.path.exists()


def test_kunci_hidup_dan_masih_muda_tetap_menolak(lock_dir):
    from datetime import datetime, timezone
    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "uji.lock").write_text(json.dumps({
        "pid": os.getpid(),
        "dibuat": datetime.now(timezone.utc).isoformat(),
        "perintah": "baru saja",
    }), encoding="utf-8")
    with pytest.raises(LockTaken):
        RunLock("uji", lock_dir=lock_dir, max_umur_jam=12.0).acquire()


def test_jalankan_terkunci_mengembalikan_kode_khusus(monkeypatch, lock_dir):
    """Bentrok BUKAN kegagalan: kodenya 75, bukan 1, supaya riwayat Task
    Scheduler bisa membedakan keduanya."""
    monkeypatch.setattr("run_lock.DEFAULT_LOCK_DIR", lock_dir)
    with RunLock("uji", lock_dir=lock_dir):
        assert jalankan_terkunci("uji", lambda: 0) == EXIT_TERKUNCI


def test_jalankan_terkunci_meneruskan_kode_asli(monkeypatch, lock_dir):
    monkeypatch.setattr("run_lock.DEFAULT_LOCK_DIR", lock_dir)
    assert jalankan_terkunci("uji", lambda: 3) == 3


def test_kunci_dilepas_walau_fungsi_melempar(monkeypatch, lock_dir):
    monkeypatch.setattr("run_lock.DEFAULT_LOCK_DIR", lock_dir)

    def meledak():
        raise RuntimeError("gagal di tengah")

    with pytest.raises(RuntimeError):
        jalankan_terkunci("uji", meledak)
    # Kalau kunci tidak dilepas, run berikutnya akan tertolak selamanya.
    assert not (lock_dir / "uji.lock").exists()


def test_dua_proses_sungguhan_hanya_satu_yang_menang(tmp_path):
    """Bukan simulasi: dua interpreter Python terpisah berebut kunci yang sama.

    Ini yang membedakan `O_CREAT|O_EXCL` dari "cek lalu tulis" -- yang kedua
    lolos pada tes satu-proses tapi bocor di sini.
    """
    lock_dir = tmp_path / "locks"
    skrip = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from run_lock import RunLock, LockTaken
        try:
            with RunLock("balapan", lock_dir={str(lock_dir)!r}):
                print("MENANG")
                time.sleep(2.0)
        except LockTaken:
            print("KALAH")
    """)
    a = subprocess.Popen([sys.executable, "-c", skrip],
                         stdout=subprocess.PIPE, text=True)
    # Beri jeda cukup supaya A benar-benar sudah memegang kunci saat B mencoba.
    import time
    time.sleep(0.8)
    b = subprocess.run([sys.executable, "-c", skrip],
                       capture_output=True, text=True, timeout=30)
    keluaran_a = a.communicate(timeout=30)[0]

    assert "MENANG" in keluaran_a
    assert "KALAH" in b.stdout, f"proses kedua seharusnya ditolak, dapat: {b.stdout!r}"


# =====================================================================
# 2. scrape_followers -- G1 & G2
# =====================================================================

import scrape_followers as sf  # noqa: E402


def test_tanggal_profil_tidak_lagi_hardcode():
    """Inti G1: default tanggal harfiah membuat prosedur ini tak bisa dijadwalkan.

    Yang diperiksa adalah NILAI DEFAULT-nya, bukan ada tidaknya string tanggal
    di file -- komentar yang menjelaskan kenapa default itu dibuang justru
    memang menyebutkannya, dan melarang itu akan menghukum dokumentasinya.
    """
    args = sf.parse_args([])
    assert args.tanggal_profil is None

    # Tidak ada baris KODE (bukan komentar) yang memasang tanggal sebagai default.
    for baris in Path(sf.__file__).read_text(encoding="utf-8").splitlines():
        bersih = baris.strip()
        if bersih.startswith("#") or bersih.startswith('"'):
            continue
        assert not ("default=" in bersih and "2026-" in bersih), bersih


def test_default_memakai_snapshot_terbaru():
    """Tanpa --tanggal-profil, query yang dipakai adalah DISTINCT ON terbaru."""
    assert "DISTINCT ON" in sf.SQL_AKUN_TERBARU
    assert "p.date DESC" in sf.SQL_AKUN_TERBARU
    # Tie-break eksplisit supaya hasilnya deterministik antar-run.
    assert "p.updated_at DESC" in sf.SQL_AKUN_TERBARU


def test_limit_akun_terpisah_dari_limit_follower():
    """G2: keduanya beda sumbu dan keduanya perlu."""
    args = sf.parse_args(["--limit", "50", "--limit-akun", "3"])
    assert args.limit == 50 and args.limit_akun == 3


def test_cost_guard_ada_dan_configurable():
    args = sf.parse_args([])
    assert args.max_cost_usd is None, "default harus dari environment, bukan flag"
    assert sf._FALLBACK_MAX_COST > 0


def test_harga_follower_dari_config_bukan_angka_karangan():
    """Angkanya berasal dari biaya nyata yang tercatat, dan bisa ditimpa .env."""
    from config import PRICE_PER_FOLLOWER_USD
    assert PRICE_PER_FOLLOWER_USD == pytest.approx(0.0013)


def test_plafon_dari_environment(monkeypatch):
    from config import default_max_cost_usd
    monkeypatch.setenv("SCRAPE_MAX_COST_FOLLOWERS_USD", "2.50")
    assert default_max_cost_usd("SCRAPE_MAX_COST_FOLLOWERS_USD", 1.0) == 2.50
    monkeypatch.delenv("SCRAPE_MAX_COST_FOLLOWERS_USD")
    assert default_max_cost_usd("SCRAPE_MAX_COST_FOLLOWERS_USD", 1.0) == 1.0


def test_plafon_salah_ketik_ditolak(monkeypatch):
    """'satu dolar' tidak boleh diam-diam jadi plafon tak terbatas."""
    from config import ConfigError, default_max_cost_usd
    monkeypatch.setenv("SCRAPE_MAX_COST_FOLLOWERS_USD", "satu dolar")
    with pytest.raises(ConfigError):
        default_max_cost_usd("SCRAPE_MAX_COST_FOLLOWERS_USD", 1.0)


class _CursorPalsu:
    def __init__(self, akun, terakhir):
        self._akun, self._terakhir, self._hasil = akun, terakhir, []

    def execute(self, sql, params=None):
        self._hasil = self._terakhir if "max(scraped_at)" in sql else self._akun

    def fetchall(self):
        return self._hasil

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _ConnPalsu:
    def __init__(self, akun, terakhir=()):
        self._akun, self._terakhir = akun, terakhir

    def cursor(self):
        return _CursorPalsu(self._akun, self._terakhir)


def test_pilih_akun_menghormati_limit_akun():
    conn = _ConnPalsu([(f"id{i}", "instagram", f"u{i}") for i in range(10)])
    args = sf.parse_args(["--limit-akun", "3", "--order", "username"])
    assert len(sf.pilih_akun(conn, args)) == 3


def test_pilih_akun_menyaring_platform():
    conn = _ConnPalsu([("a", "instagram", "x"), ("b", "tiktok", "y")])
    args = sf.parse_args(["--platform", "tiktok", "--order", "username"])
    hasil = sf.pilih_akun(conn, args)
    assert [r[1] for r in hasil] == ["tiktok"]


def test_urutan_stale_mendahulukan_yang_belum_pernah():
    from datetime import datetime, timezone
    lama = datetime(2026, 1, 1, tzinfo=timezone.utc)
    conn = _ConnPalsu(
        [("sudah", "instagram", "a"), ("belum", "instagram", "b")],
        terakhir=[("sudah", lama)],
    )
    args = sf.parse_args(["--order", "stale"])
    assert [r[0] for r in sf.pilih_akun(conn, args)] == ["belum", "sudah"]


def test_usernames_mengabaikan_limit_akun():
    """Pilihan eksplisit tidak boleh dipotong diam-diam."""
    conn = _ConnPalsu([("a", "instagram", "satu"), ("b", "instagram", "dua"),
                       ("c", "instagram", "tiga")])
    args = sf.parse_args(["--usernames", "satu", "dua", "--limit-akun", "1"])
    assert len(sf.pilih_akun(conn, args)) == 2


# =====================================================================
# 3. Orkestrasi -- G6 & retry sensor
# =====================================================================

sys.path.insert(0, str(ROOT / "orchestration"))
from kol_orchestration import one_shot  # noqa: E402
from kol_orchestration import sensors  # noqa: E402


@pytest.mark.parametrize("asset", [
    "instagram_follower", "tiktok_follower", "unified_follower",
    "audience_feature", "audience_gold",
])
def test_asset_follower_audiens_masuk_chain(asset):
    """Sebelum ini kelimanya terdaftar di Definitions tapi tidak di job mana pun,
    sehingga tidak ada jalur otomatis apa pun menuju tabel audiens."""
    assert asset in one_shot.TRANSFORM_ASSETS


def test_chain_mencakup_seluruh_asset_terdaftar():
    from kol_orchestration.one_shot import _semua_asset
    terdaftar = {a.key.to_user_string() for a in _semua_asset()}
    assert terdaftar - set(one_shot.TRANSFORM_ASSETS) == set(), \
        "ada asset terdaftar yang tidak pernah dijalankan job mana pun"


@pytest.mark.parametrize("tabel", ["ig_followers_apify", "tt_followers_apify"])
def test_sensor_memantau_tabel_follower(tabel):
    assert tabel in sensors.TABEL_DIPANTAU


def test_sensor_tidak_memantau_tabel_tanpa_pembaca():
    """Aturannya tidak berubah: dipantau hanya kalau ada asset yang membacanya."""
    for t in ("ig_comments_apify", "ig_stories_apify", "kol_roster_import"):
        assert t not in sensors.TABEL_DIPANTAU


def test_cursor_lama_tetap_terbaca():
    """Format cursor tidak boleh pecah -- kalau pecah, tick berikutnya jadi
    baseline dan satu putaran data terlewat."""
    sidik = {"ig_profile_apify": sensors.Sidik(baris=10, watermark=None)}
    lama = sensors.tulis_cursor(sidik)
    assert sensors.baca_cursor(lama) == sidik
    assert sensors.baca_menunggu(lama) is None


def test_cursor_dengan_menunggu_masih_terbaca_bagian_sidiknya():
    """`menunggu` adalah tambahan; ia tidak boleh mengganggu pembacaan sidik jari."""
    sidik = {"ig_profile_apify": sensors.Sidik(baris=10, watermark=None)}
    baru = sensors._cursor_dengan_menunggu(sensors.tulis_cursor(sidik), "k1", 2)
    assert sensors.baca_cursor(baru) == sidik
    assert sensors.baca_menunggu(baru) == {"run_key": "k1", "percobaan": 2}


def test_baca_menunggu_tahan_cursor_rusak():
    for rusak in (None, "", "bukan json", "{}", '{"menunggu": 5}'):
        assert sensors.baca_menunggu(rusak) is None


def test_batas_percobaan_ulang_ada():
    """Retry tanpa batas akan menyamarkan kegagalan yang butuh perbaikan."""
    assert 1 <= sensors.MAX_PERCOBAAN <= 5


def test_kolom_watermark_dipetakan_untuk_tabel_follower():
    """Regresi untuk bug nyata: kedua tabel follower TIDAK punya `fetched_at`.

    Menambahkannya ke `TABEL_DIPANTAU` tanpa memetakan kolomnya membuat sensor
    gagal di SETIAP tick dengan `UndefinedColumn` -- terjadi 9 September dan
    baru ketahuan dari tick_body, bukan dari tes.
    """
    for t in ("ig_followers_apify", "tt_followers_apify"):
        assert sensors.kolom_watermark(t) == "insert_at"
    assert sensors.kolom_watermark("ig_profile_apify") == "fetched_at"


def test_sql_sidik_jari_memakai_kolom_per_tabel():
    sql = sensors.sql_sidik_jari(sensors.TABEL_DIPANTAU)
    assert "max(insert_at)" in sql, "tabel follower harus memakai insert_at"
    assert "max(fetched_at)" in sql, "tabel lama harus tetap memakai fetched_at"


@pytest.mark.needs_db
def test_db_setiap_tabel_dipantau_punya_kolom_watermarknya():
    """Dijalankan terhadap database sungguhan: satu-satunya cara memastikan
    peta kolom tidak berbohong. READ-ONLY."""
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        from config import load_config
        cfg = load_config()
    except Exception as exc:                       # pragma: no cover
        pytest.skip(f"konfigurasi DB tidak tersedia: {exc}")
    try:
        cn = psycopg2.connect(connect_timeout=5, **cfg.postgres.as_connect_kwargs())
    except Exception as exc:                       # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    cn.set_session(readonly=True, autocommit=True)
    try:
        with cn.cursor() as cur:
            for t in sensors.TABEL_DIPANTAU:
                kolom = sensors.kolom_watermark(t)
                cur.execute(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema=%s AND table_name=%s AND column_name=%s",
                    (sensors.SCHEMA, t, kolom),
                )
                assert cur.fetchone()[0] == 1, \
                    f"l0_raw.{t} tidak punya kolom watermark '{kolom}'"
    finally:
        cn.close()
