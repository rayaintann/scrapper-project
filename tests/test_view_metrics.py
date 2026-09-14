"""Test untuk empat metrik views: Avg Views, Median Views, V2F, L2V.

Ditambahkan bersama migration 036 dan perubahan pada
`orchestration/kol_orchestration/assets/feature_engagement.py`.

============================================================================
KENAPA TEST KALKULASINYA MENJALANKAN SQL, BUKAN MENIRUNYA DI PYTHON
============================================================================

Rumus keempat metrik ini hidup sebagai SQL, bukan sebagai fungsi Python.
Menulis ulang rumusnya di Python lalu mengujinya berarti menguji tiruan --
tiruannya bisa lulus semua test sementara SQL yang sebenarnya jalan di
produksi tetap salah, dan itu justru kegagalan yang paling mahal.

Karena itu test di kelompok 2 MENGIMPOR string ekspresi yang sama persis
dengan yang dipakai asset (`_AVG_VIEWS`, `_MEDIAN_VIEWS`, `_V2F`, `_L2V`),
menempelkannya di atas CTE `post` berisi baris buatan lewat `VALUES`, lalu
menjalankannya di Postgres. Yang diuji adalah ekspresi produksinya sendiri.

Tidak ada satu pun test di file ini yang menulis ke database: seluruhnya
`SELECT` di atas `VALUES`, tanpa menyentuh tabel proyek mana pun. Aman
dijalankan terhadap database produksi dalam sesi read-only.

Database yang dipakai:
    1. `KOL_TEST_PG_DSN` kalau diset -- Postgres mana pun bisa, termasuk
       cluster sekali pakai, karena query-nya tidak menyentuh tabel proyek.
    2. kalau tidak, konfigurasi `.env` proyek (read-only).
    3. kalau keduanya tidak terjangkau, di-skip.

Kelompok 1 (isi migration & sambungan SQL) tidak butuh database sama sekali.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"
M036 = MIGRATIONS / "036_view_metrics_avg_median_v2f_l2v.sql"
ASSETS = ROOT / "orchestration" / "kol_orchestration" / "assets"

#: Lima kolom yang ditambah migration 036, dipakai berulang di bawah.
KOLOM_BARU = (
    "views_analyzed_count",
    "avg_views",
    "median_views",
    "view_to_follower_ratio",
    "like_to_view_ratio",
)


def baca(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sql_saja(path: Path) -> str:
    """Isi file tanpa baris komentar, supaya assertion tidak ikut menghitung
    teks penjelasan di header -- pola yang sama dipakai
    tests/test_discovery_tier_growth.py."""
    return "\n".join(
        b for b in baca(path).splitlines() if not b.lstrip().startswith("--")
    )


# =====================================================================
# 1. Isi migration dan sambungan asset -- tanpa database
# =====================================================================

def test_migration_036_ada():
    assert M036.exists(), "migration 036 hilang"


def test_036_hanya_menambah_kolom():
    """Migrasi ini harus aman untuk data yang sudah ada.

    Tidak boleh ada DROP, DELETE, TRUNCATE, UPDATE, maupun perubahan tipe
    kolom. Kalau salah satu muncul, migrasi berhenti bersifat aditif dan
    persetujuan yang diberikan untuknya tidak lagi berlaku.
    """
    s = sql_saja(M036).upper()
    for terlarang in ("DROP TABLE", "DROP COLUMN", "DELETE FROM", "TRUNCATE",
                      "ALTER COLUMN", "UPDATE "):
        assert terlarang not in s, f"036 mengandung {terlarang!r}"


def test_036_tidak_menyentuh_source_of_truth_followers():
    """`public.kol_directory.followers_count` tidak boleh disentuh sama sekali."""
    assert "kol_directory" not in sql_saja(M036), \
        "036 menyebut kol_directory; source of truth followers harus tidak tersentuh"


def test_036_tidak_menyentuh_tabel_l2_lain():
    """Hanya tiga tabel tujuan. kol_metric_daily/monthly/post_metric di luar scope."""
    s = sql_saja(M036)
    for lain in ("kol_metric_daily", "kol_metric_monthly", "post_metric",
                 "content_format_daily"):
        assert lain not in s, f"036 menyentuh {lain}, di luar scope 4 metrik"


@pytest.mark.parametrize("tabel", [
    "feature.ig_engagement_analysis",
    "feature.tt_engagement_analysis",
    "l2_gold.kol_profile_card",
])
def test_036_menambah_lima_kolom_ke_tiap_tabel(tabel):
    s = sql_saja(M036)
    assert f"ALTER TABLE {tabel}" in s, f"tidak ada ALTER TABLE untuk {tabel}"


@pytest.mark.parametrize("kolom", KOLOM_BARU)
def test_036_tiap_kolom_ditambah_tiga_kali(kolom):
    """Lima kolom x tiga tabel. Nama harus identik di ketiganya supaya nilai
    bisa ditelusuri Feature -> L2 tanpa tabel pemetaan nama."""
    s = sql_saja(M036)
    assert s.count(f"ADD COLUMN {kolom}") == 3, \
        f"{kolom} tidak ditambahkan ke tepat 3 tabel"


def test_036_tidak_ada_default():
    """DEFAULT 0 akan membuat baris lama tampak sudah diukur dan hasilnya nol."""
    s = sql_saja(M036)
    for kolom in KOLOM_BARU:
        for baris in s.splitlines():
            if f"ADD COLUMN {kolom}" in baris:
                assert "DEFAULT" not in baris.upper(), \
                    f"{kolom} punya DEFAULT; harus NULL sampai dihitung"


def test_036_tidak_ada_not_null():
    """NULL adalah jawaban yang sah ('data tidak cukup'), jadi tidak boleh
    ada kolom baru yang NOT NULL."""
    s = sql_saja(M036)
    for kolom in KOLOM_BARU:
        for baris in s.splitlines():
            if f"ADD COLUMN {kolom}" in baris:
                assert "NOT NULL" not in baris.upper(), \
                    f"{kolom} NOT NULL; NULL harus boleh"


def test_036_rasio_tidak_memakai_numeric_5_2():
    """V2F rutin melewati 100%, jadi numeric(5,2) (maks 999,99) akan overflow.

    Tipe yang lebih lebar juga menghapus kebutuhan clamp `LEAST`, sumber bug
    yang sudah dua kali muncul di project ini.
    """
    s = sql_saja(M036)
    for kolom in ("view_to_follower_ratio", "like_to_view_ratio"):
        for baris in s.splitlines():
            if f"ADD COLUMN {kolom}" in baris:
                assert "numeric(12,4)" in baris, \
                    f"{kolom} harus numeric(12,4), bukan {baris.strip()}"


def _fe_module():
    """Muat feature_engagement.py tanpa perlu Dagster terpasang.

    Yang diuji hanyalah string SQL-nya, jadi import Dagster diganti stub.
    Ini bukan tiruan rumus -- string yang diambil tetap string yang sama
    persis yang dikirim ke Postgres di produksi.
    """
    src = (ASSETS / "feature_engagement.py").read_text(encoding="utf-8")
    src = src.replace(
        "from dagster import AssetKey, MetadataValue, Output, asset",
        "AssetKey = lambda *a, **k: None\n"
        "MetadataValue = None\n"
        "Output = None\n"
        "def asset(*a, **k):\n"
        "    return lambda f: f",
    )
    src = src.replace(
        "from kol_orchestration.resources import PostgresResource",
        "PostgresResource = object",
    )
    # `__file__` WAJIB disediakan: modulnya menghitung root project dari
    # lokasi filenya sendiri untuk mengimpor `metrics_thresholds`. Tanpa ini
    # exec() gagal dengan NameError yang tidak ada hubungannya dengan metrik
    # views yang sedang diuji.
    ns: dict = {"__file__": str(ASSETS / "feature_engagement.py")}
    exec(compile(src, str(ASSETS / "feature_engagement.py"), "exec"), ns)
    return ns


FE = _fe_module()


@pytest.mark.parametrize("sql_name", ["SQL_IG", "SQL_TT"])
@pytest.mark.parametrize("kolom", KOLOM_BARU)
def test_asset_menulis_kolom_baru(sql_name, kolom):
    """Kolom harus ada di daftar INSERT DAN di ON CONFLICT DO UPDATE.

    Hanya di INSERT berarti nilainya tidak pernah diperbarui pada rerun --
    akun yang sudah punya baris akan memajang angka pertama selamanya.
    """
    sql = FE[sql_name]
    kepala, _, ekor = sql.partition("ON CONFLICT")
    assert kolom in kepala, f"{kolom} tidak ada di INSERT {sql_name}"
    assert f"{kolom} " in ekor or f"{kolom}=" in ekor, \
        f"{kolom} tidak diperbarui di ON CONFLICT {sql_name}"


@pytest.mark.parametrize("sql_name", ["SQL_IG", "SQL_TT"])
@pytest.mark.parametrize("kolom", KOLOM_BARU)
def test_asset_memakai_penugasan_langsung_bukan_coalesce(sql_name, kolom):
    """`COALESCE(EXCLUDED.x, x)` akan membuat hasil NULL gagal menimpa nilai
    lama, sehingga metrik yang seharusnya hilang justru jadi basi.
    Butir 5 di docstring asset."""
    ekor = FE[sql_name].partition("ON CONFLICT")[2]
    for baris in ekor.splitlines():
        if kolom in baris:
            assert "COALESCE" not in baris.upper(), \
                f"{kolom} memakai COALESCE di ON CONFLICT {sql_name}"


@pytest.mark.parametrize("sql_name", ["SQL_IG", "SQL_TT"])
def test_asset_tidak_meng_clamp_kolom_baru(sql_name):
    """Keempat kolom baru tipenya sudah muat, jadi tidak boleh ada LEAST --
    `LEAST(NULL, x)` mengabaikan NULL dan mengembalikan x, bug yang sudah
    tercatat dua kali di project ini."""
    # Baris komentar dibuang dulu: salah satunya memang MENYEBUT kata LEAST
    # untuk menjelaskan kenapa clamp tidak dipakai di sini.
    for baris in FE[sql_name].splitlines():
        if baris.lstrip().startswith("--"):
            continue
        if "LEAST" in baris:
            assert "er_mentah" in baris, \
                f"LEAST dipakai di luar engagement_rate: {baris.strip()}"


def test_v2f_dan_l2v_menyaring_simetris():
    """Syarat sampel harus dipakai di pembilang DAN penyebut.

    Kalau hanya penyebut yang disaring, pembilangnya tetap menumpuk dan
    rasionya meledak; kalau hanya pembilang, rasionya mengecil.
    """
    for nama, ekspr in (("V2F", FE["_V2F"]), ("L2V", FE["_L2V"])):
        syarat = FE["_S_V2F"] if nama == "V2F" else FE["_S_L2V"]
        assert ekspr.count(f"FILTER (WHERE {syarat})") == 2, \
            f"{nama} tidak menyaring simetris pembilang & penyebut"


def test_penyebut_dibungkus_nullif():
    """Satu-satunya penjaga pembagian-dengan-nol. Tanpa NULLIF, Postgres
    melempar division_by_zero dan seluruh asset gagal."""
    for nama, ekspr in (("V2F", FE["_V2F"]), ("L2V", FE["_L2V"])):
        assert "NULLIF(" in ekspr, f"{nama} tidak memakai NULLIF pada penyebut"


def test_avg_dan_median_memakai_sampel_yang_sama():
    """Median harus dihitung atas himpunan yang persis sama dengan rata-rata,
    kalau tidak keduanya tidak bisa dibandingkan."""
    assert FE["_S_VIEWS"] in FE["_AVG_VIEWS"]
    assert FE["_S_VIEWS"] in FE["_MEDIAN_VIEWS"]


def test_median_memakai_percentile_cont():
    """percentile_disc akan mengembalikan salah satu nilai tengah pada jumlah
    post GENAP, bukan rata-ratanya -- diam-diam membuang separuh jawaban."""
    assert "percentile_cont" in FE["_MEDIAN_VIEWS"]
    assert "percentile_disc" not in FE["_MEDIAN_VIEWS"]


def test_definisi_views_valid_hanya_satu_tempat():
    """Keempat metrik harus membaca definisi yang sama dari `_VIEWS_VALID`.

    Kalau salah satu menuliskan syaratnya sendiri, mengubah definisinya nanti
    akan mengubah sebagian metrik saja dan angkanya berhenti bisa
    direkonsiliasi satu sama lain.
    """
    assert FE["_VIEWS_VALID"] in FE["_S_VIEWS"]
    assert FE["_VIEWS_VALID"] in FE["_S_V2F"]
    assert FE["_VIEWS_VALID"] in FE["_S_L2V"]


def test_semua_metrik_berangkat_dari_aturan_sampel_yang_sama():
    """`lolos` = bukan likes_hidden, bukan kolaborasi. Aturan yang sudah
    disepakati dan dipakai ER; keempat metrik baru tidak boleh menyimpang."""
    for nama in ("_S_VIEWS", "_S_V2F", "_S_L2V"):
        assert FE[nama].startswith("lolos AND"), \
            f"{nama} tidak berangkat dari aturan sampel `lolos`"


def test_gold_profile_membawa_kolom_ke_l2():
    """L2 harus menyalin dari feature, bukan menghitung ulang."""
    s = (ASSETS / "gold_profile.py").read_text(encoding="utf-8")
    assert "feature.ig_engagement_analysis" in s
    assert "feature.tt_engagement_analysis" in s
    for kolom in KOLOM_BARU:
        assert f"EXCLUDED.{kolom}" in s, f"{kolom} tidak di-upsert ke L2"
        assert f"IS DISTINCT FROM EXCLUDED.{kolom}" in s, \
            (f"{kolom} tidak ikut penjaga IS DISTINCT FROM; kartu yang hanya "
             f"berubah kolom ini tidak akan pernah ditulis ulang")


def test_gold_profile_tidak_menghitung_ulang_rumusnya():
    """Kalau rumusnya muncul lagi di L2, ada dua definisi yang cepat atau
    lambat berbeda."""
    s = (ASSETS / "gold_profile.py").read_text(encoding="utf-8")
    for jejak_rumus in ("percentile_cont", "avg(views)", "sum(views)"):
        assert jejak_rumus not in s, \
            f"gold_profile.py menghitung ulang ({jejak_rumus}); harus menyalin saja"


def test_gold_profile_bergantung_pada_asset_feature():
    """Tanpa dep, Dagster boleh menjalankan kartu lebih dulu dan kartu akan
    menyalin nilai feature dari run sebelumnya -- angka basi yang tidak
    terlihat salah."""
    s = (ASSETS / "gold_profile.py").read_text(encoding="utf-8")
    assert '_IG_ENGAGEMENT = AssetKey("ig_engagement_analysis")' in s
    assert '_TT_ENGAGEMENT = AssetKey("tt_engagement_analysis")' in s
    assert "deps=[_PROFILE, _IG_ENGAGEMENT, _TT_ENGAGEMENT]" in s


# =====================================================================
# 2. Kalkulasi -- menjalankan ekspresi SQL produksi di Postgres
# =====================================================================

@pytest.fixture(scope="module")
def conn():
    psycopg2 = pytest.importorskip("psycopg2")

    dsn = os.getenv("KOL_TEST_PG_DSN")
    if dsn:
        try:
            c = psycopg2.connect(dsn, connect_timeout=5)
        except Exception as exc:                     # pragma: no cover
            pytest.skip(f"KOL_TEST_PG_DSN tidak bisa dijangkau: {exc}")
    else:
        sys.path.insert(0, str(ROOT))
        try:
            from config import load_config

            cfg = load_config()
        except Exception as exc:                     # pragma: no cover
            pytest.skip(f"konfigurasi DB tidak tersedia: {exc}")
        try:
            c = psycopg2.connect(connect_timeout=5, **cfg.postgres.as_connect_kwargs())
        except Exception as exc:                     # pragma: no cover
            pytest.skip(f"database tidak bisa dijangkau: {exc}")

    # READ-ONLY: seluruh test di bawah hanya SELECT di atas VALUES.
    c.set_session(readonly=True, autocommit=True)
    yield c
    c.close()


#: Kolom CTE `post` yang dipakai ekspresi produksi. Namanya harus sama persis
#: seperti yang dihasilkan `_cte_dasar()` di asset.
_KOLOM_POST = "likes, views, followers_count, lolos"

#: Tipe kolom, sama seperti di `l1_silver.unified_post`. Daftar kolom sebuah
#: CTE tidak boleh menyebut tipe, jadi tipenya dipasang sebagai cast di baris
#: VALUES PERTAMA -- dari situ Postgres menurunkan tipe seluruh kolom. Tanpa
#: cast ini, kolom yang baris pertamanya NULL akan bertipe `text` dan
#: `sum()`/`percentile_cont()` menolaknya.
_TIPE_POST = ("bigint", "bigint", "bigint", "boolean")


def hitung(conn, baris):
    """Jalankan KELIMA ekspresi produksi atas `baris` buatan.

    `baris` adalah list of (likes, views, followers_count, lolos).
    Mengembalikan dict berisi kelima hasil.

    CTE-nya dinamai `post` dan berkolom sama seperti `_cte_dasar()` di asset,
    sehingga ekspresi yang diimpor bisa ditempel apa adanya tanpa diubah
    satu karakter pun.
    """
    baris_pertama = "(" + ", ".join(f"%s::{t}" for t in _TIPE_POST) + ")"
    sisanya = ["(%s, %s, %s, %s)"] * (len(baris) - 1)
    nilai = ", ".join([baris_pertama] + sisanya)
    params = [v for r in baris for v in r]
    sql = f"""
        WITH post({_KOLOM_POST}) AS (VALUES {nilai})
        SELECT {FE['_N_VIEWS']},
               {FE['_AVG_VIEWS']},
               {FE['_MEDIAN_VIEWS']},
               {FE['_V2F']},
               {FE['_L2V']}
        FROM post
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        n, avg, med, v2f, l2v = cur.fetchone()
    return {
        "n": n,
        "avg_views": None if avg is None else float(avg),
        "median_views": None if med is None else float(med),
        "v2f": None if v2f is None else float(v2f),
        "l2v": None if l2v is None else float(l2v),
    }


# Baris = (likes, views, followers, lolos). `L` = lolos sampel.
L = True


# --- Avg Views --------------------------------------------------------

@pytest.mark.needs_db
def test_avg_beberapa_post_valid(conn):
    h = hitung(conn, [(10, 100, 1000, L), (20, 200, 1000, L), (30, 300, 1000, L)])
    assert h["n"] == 3
    assert h["avg_views"] == 200.0


@pytest.mark.needs_db
def test_avg_satu_post(conn):
    h = hitung(conn, [(10, 777, 1000, L)])
    assert h["n"] == 1
    assert h["avg_views"] == 777.0


@pytest.mark.needs_db
def test_avg_mengabaikan_null_bukan_menganggapnya_nol(conn):
    """Inti dari seluruh perubahan ini.

    Dua post ber-views 100 dan 200, satu post tanpa views. Jawaban yang benar
    150 (dibagi 2), BUKAN 100 (dibagi 3).
    """
    h = hitung(conn, [(10, 100, 1000, L), (20, 200, 1000, L), (30, None, 1000, L)])
    assert h["n"] == 2, "post ber-views NULL ikut jadi penyebut"
    assert h["avg_views"] == 150.0
    assert h["avg_views"] != 100.0


@pytest.mark.needs_db
def test_avg_semua_views_null(conn):
    """Hasilnya NULL, bukan 0 -- 0 akan terbaca 'diukur, tidak ada yang nonton'."""
    h = hitung(conn, [(10, None, 1000, L), (20, None, 1000, L)])
    assert h["n"] == 0
    assert h["avg_views"] is None


@pytest.mark.needs_db
def test_avg_views_nol_dikeluarkan_seperti_null(conn):
    """`views = 0` diperlakukan sama dengan NULL: tidak diukur.

    Bukan pilihan estetika. Diukur di l1_silver.unified_post 2026-09-09, pada
    Instagram nilai 0 HANYA muncul di carousel (10 dari 68) dan feed (10 dari
    22) -- dua tipe media yang tidak pernah menghasilkan views positif satu
    kali pun -- sementara tipe yang sama juga mengembalikan NULL untuk hal yang
    persis sama (58 dan 12). Nol di situ berarti "actor tidak melaporkan play
    count untuk tipe ini", bukan "tidak ada yang menonton".

    Memasukkannya = memasukkan NULL sebagai 0 lewat pintu belakang. Efek
    nyatanya sebelum diperbaiki: `febbyrastanty` dan `bobbykertanegara` keluar
    dengan MEDIAN 0 padahal reel mereka rata-rata di atas 100 ribu views.
    """
    h = hitung(conn, [(10, 0, 1000, L), (20, 100, 1000, L)])
    assert h["n"] == 1, "post ber-views 0 masih ikut jadi penyebut"
    assert h["avg_views"] == 100.0


@pytest.mark.needs_db
def test_median_tidak_lagi_nol_karena_post_tanpa_views(conn):
    """Regresi untuk kasus febbyrastanty/bobbykertanegara: mayoritas sampel
    adalah foto ber-views 0, dan median ikut jadi 0."""
    h = hitung(conn, [(1, 0, 1000, L), (1, 0, 1000, L), (1, 0, 1000, L),
                      (1, 100_000, 1000, L), (1, 200_000, 1000, L)])
    assert h["n"] == 2
    assert h["median_views"] == 150_000.0
    assert h["median_views"] != 0.0


@pytest.mark.needs_db
def test_avg_mengabaikan_post_di_luar_sampel(conn):
    """Post ber-likes_hidden / kolaborasi tidak boleh ikut sama sekali."""
    h = hitung(conn, [(10, 100, 1000, L), (20, 900, 1000, False)])
    assert h["n"] == 1
    assert h["avg_views"] == 100.0


@pytest.mark.needs_db
def test_avg_tanpa_post_sama_sekali(conn):
    h = hitung(conn, [(None, None, None, L)])
    assert h["n"] == 0
    assert h["avg_views"] is None


# --- Median Views -----------------------------------------------------

@pytest.mark.needs_db
def test_median_jumlah_ganjil(conn):
    h = hitung(conn, [(1, 10, 100, L), (1, 30, 100, L), (1, 20, 100, L)])
    assert h["median_views"] == 20.0


@pytest.mark.needs_db
def test_median_jumlah_genap_merata_ratakan_dua_nilai_tengah(conn):
    """10, 20, 30, 40 -> (20+30)/2 = 25. percentile_disc akan menjawab 20."""
    h = hitung(conn, [(1, 10, 100, L), (1, 20, 100, L),
                      (1, 30, 100, L), (1, 40, 100, L)])
    assert h["median_views"] == 25.0


@pytest.mark.needs_db
def test_median_genap_bisa_berdesimal(conn):
    """4 dan 5 -> 4,5. Kolomnya numeric(18,2) supaya .5 tidak hilang."""
    h = hitung(conn, [(1, 4, 100, L), (1, 5, 100, L)])
    assert h["median_views"] == 4.5


@pytest.mark.needs_db
def test_median_mengabaikan_null(conn):
    """NULL tidak boleh masuk urutan sebagai 0, yang akan menarik median turun."""
    h = hitung(conn, [(1, 10, 100, L), (1, 20, 100, L),
                      (1, 30, 100, L), (1, None, 100, L)])
    assert h["n"] == 3
    assert h["median_views"] == 20.0


@pytest.mark.needs_db
def test_median_semua_null(conn):
    h = hitung(conn, [(1, None, 100, L), (1, None, 100, L)])
    assert h["median_views"] is None


@pytest.mark.needs_db
def test_median_satu_post(conn):
    h = hitung(conn, [(1, 42, 100, L)])
    assert h["median_views"] == 42.0


@pytest.mark.needs_db
def test_median_tahan_pencilan_sementara_rata_rata_tidak(conn):
    """Alasan metrik ini ada di samping Avg Views: satu video viral menggeser
    rata-rata jauh, median hampir tidak bergerak."""
    h = hitung(conn, [(1, 100, 1000, L), (1, 110, 1000, L),
                      (1, 120, 1000, L), (1, 1_000_000, 1000, L)])
    assert h["median_views"] == 115.0
    assert h["avg_views"] > 250_000


# --- V2F --------------------------------------------------------------

@pytest.mark.needs_db
def test_v2f_views_dan_followers_valid(conn):
    """500 views / 1.000 followers = 50%."""
    h = hitung(conn, [(1, 500, 1000, L)])
    assert h["v2f"] == 50.0


@pytest.mark.needs_db
def test_v2f_penyebut_aditif_bukan_rata_rata_rasio(conn):
    """Dua post: 100/1.000 dan 900/1.000.

    Aditif : (100+900) / (1.000+1.000) = 50%
    Rata-rata rasio : (10% + 90%) / 2 = 50% -- kebetulan sama, jadi dipakai
    kasus dengan followers BERBEDA supaya keduanya berpisah:
    (100+900)/(1.000+9.000) = 10%, sedangkan rata-rata rasio = (10%+10%)/2.
    """
    h = hitung(conn, [(1, 100, 1000, L), (1, 900, 9000, L)])
    assert h["v2f"] == 10.0


@pytest.mark.needs_db
def test_v2f_followers_nol_dikeluarkan(conn):
    """Bukan dibagi nol, bukan error -- post-nya tidak ikut sama sekali."""
    h = hitung(conn, [(1, 500, 0, L)])
    assert h["v2f"] is None


@pytest.mark.needs_db
def test_v2f_followers_nol_tidak_merusak_post_lain(conn):
    """Post ber-followers 0 keluar dari KEDUA sisi pecahan. Kalau views-nya
    tetap masuk pembilang, hasilnya akan 150% bukan 50%."""
    h = hitung(conn, [(1, 500, 1000, L), (1, 1000, 0, L)])
    assert h["v2f"] == 50.0


@pytest.mark.needs_db
def test_v2f_followers_null_dikeluarkan(conn):
    h = hitung(conn, [(1, 500, None, L)])
    assert h["v2f"] is None


@pytest.mark.needs_db
def test_v2f_views_null_dikeluarkan(conn):
    h = hitung(conn, [(1, None, 1000, L)])
    assert h["v2f"] is None


@pytest.mark.needs_db
def test_v2f_views_nol_dikeluarkan(conn):
    """Konsisten dengan Avg/Median: views = 0 berarti tidak diukur, jadi
    post-nya keluar dan hasilnya NULL -- bukan 0%, yang akan terbaca sebagai
    'diukur, dan tidak ada yang menonton'."""
    h = hitung(conn, [(1, 0, 1000, L)])
    assert h["v2f"] is None


@pytest.mark.needs_db
def test_v2f_views_nol_tidak_mengempiskan_post_lain(conn):
    """Post ber-views 0 keluar dari KEDUA sisi. Kalau followers-nya tetap
    tinggal di penyebut, V2F turun dari 50% ke 25%."""
    h = hitung(conn, [(1, 500, 1000, L), (1, 0, 1000, L)])
    assert h["v2f"] == 50.0


@pytest.mark.needs_db
def test_v2f_boleh_melebihi_100_persen(conn):
    """5.000 views / 500 followers = 1.000%. numeric(5,2) akan overflow di sini;
    inilah alasan kolomnya numeric(12,4)."""
    h = hitung(conn, [(1, 5000, 500, L)])
    assert h["v2f"] == 1000.0


@pytest.mark.needs_db
def test_v2f_tidak_pernah_nan_atau_infinity(conn):
    """Postgres numeric melempar division_by_zero, bukan menghasilkan Inf.
    NULLIF-lah yang menangkapnya, dan hasilnya NULL."""
    h = hitung(conn, [(1, 100, 0, L), (1, None, None, L)])
    assert h["v2f"] is None


# --- L2V --------------------------------------------------------------

@pytest.mark.needs_db
def test_l2v_likes_dan_views_valid(conn):
    """50 likes / 1.000 views = 5%."""
    h = hitung(conn, [(50, 1000, 10000, L)])
    assert h["l2v"] == 5.0


@pytest.mark.needs_db
def test_l2v_setara_avg_likes_dibagi_avg_views(conn):
    """SUM(likes)/SUM(views) = AVG(likes)/AVG(views) karena penyebutnya jumlah
    post yang sama. Ini yang membuat rumusnya cocok dengan definisi
    'avg likes / views' di prototype."""
    baris = [(10, 100, 5000, L), (40, 300, 5000, L)]
    h = hitung(conn, baris)
    avg_likes = (10 + 40) / 2
    avg_views = (100 + 300) / 2
    assert h["l2v"] == pytest.approx(avg_likes / avg_views * 100, rel=1e-9)


@pytest.mark.needs_db
def test_l2v_views_nol_dikeluarkan(conn):
    """Satu-satunya post ber-views 0 -> tidak ada penyebut -> NULL, bukan error."""
    h = hitung(conn, [(50, 0, 10000, L)])
    assert h["l2v"] is None


@pytest.mark.needs_db
def test_l2v_views_nol_tidak_menggelembungkan_post_lain(conn):
    """Kalau post ber-views 0 hanya dibuang dari penyebut, likes-nya tetap
    menumpuk di pembilang dan L2V melonjak dari 5% ke 15%."""
    h = hitung(conn, [(50, 1000, 10000, L), (100, 0, 10000, L)])
    assert h["l2v"] == 5.0


@pytest.mark.needs_db
def test_l2v_views_null_dikeluarkan(conn):
    h = hitung(conn, [(50, None, 10000, L)])
    assert h["l2v"] is None


@pytest.mark.needs_db
def test_l2v_likes_null_dikeluarkan(conn):
    """Likes tidak diketahui bukan berarti nol like."""
    h = hitung(conn, [(None, 1000, 10000, L)])
    assert h["l2v"] is None


@pytest.mark.needs_db
def test_l2v_likes_null_tidak_merusak_post_lain(conn):
    """Post ber-likes NULL keluar dari kedua sisi: views-nya tidak boleh
    tinggal di penyebut dan mengecilkan rasio."""
    h = hitung(conn, [(50, 1000, 10000, L), (None, 9000, 10000, L)])
    assert h["l2v"] == 5.0


@pytest.mark.needs_db
def test_l2v_semua_post_tanpa_views(conn):
    h = hitung(conn, [(50, None, 10000, L), (60, None, 10000, L)])
    assert h["l2v"] is None


# --- Gabungan & regresi silang ---------------------------------------

@pytest.mark.needs_db
def test_data_kosong_semua_metrik_null_bukan_nol(conn):
    """Aturan yang paling sering dilanggar: kalau data tidak cukup, hasilnya
    NULL. 0 palsu akan membuat KOL tanpa data ikut lolos filter 'minimal 0'."""
    h = hitung(conn, [(None, None, None, L)])
    assert h["n"] == 0
    assert h["avg_views"] is None
    assert h["median_views"] is None
    assert h["v2f"] is None
    assert h["l2v"] is None


@pytest.mark.needs_db
def test_semua_post_di_luar_sampel(conn):
    """Akun yang seluruh post-nya terbuang tetap dapat baris, tapi metriknya
    NULL -- butir 2 di docstring asset."""
    h = hitung(conn, [(10, 100, 1000, False), (20, 200, 1000, False)])
    assert h["n"] == 0
    assert h["avg_views"] is None
    assert h["median_views"] is None
    assert h["v2f"] is None
    assert h["l2v"] is None


@pytest.mark.needs_db
def test_satu_akun_banyak_post_campur_aduk(conn):
    """Kasus nyata: post video ber-views, post foto tanpa views, satu post
    kolaborasi, satu post ber-followers belum diketahui.

    Yang lolos sampel & ber-views : 100, 200, 300  -> n=3
      avg    = 200
      median = 200
      v2f    = (100+200) / (1.000+1.000) * 100 = 15%   (post 300 followers NULL)
      l2v    = (10+20+30) / (100+200+300) * 100 = 10%
    """
    h = hitung(conn, [
        (10, 100, 1000, L),        # video, lengkap
        (20, 200, 1000, L),        # video, lengkap
        (30, 300, None, L),        # video, followers belum diketahui
        (40, None, 1000, L),       # foto, tidak ada views
        (50, 999, 1000, False),    # kolaborasi -- dibuang
    ])
    assert h["n"] == 3
    assert h["avg_views"] == 200.0
    assert h["median_views"] == 200.0
    assert h["v2f"] == 15.0
    assert h["l2v"] == 10.0


@pytest.mark.needs_db
def test_pembulatan_sesuai_presisi_kolom(conn):
    """avg/median 2 desimal, rasio 4 desimal. Rasio butuh 4 karena L2V akun
    besar sering di bawah 1% dan 2 desimal akan memampatkan papan atas."""
    h = hitung(conn, [(1, 10, 3000, L), (1, 11, 3000, L), (1, 13, 3000, L)])
    # avg = 34/3 = 11,333... -> 11,33
    assert h["avg_views"] == 11.33
    # l2v = 3/34 = 8,8235...% -> 8,8235
    assert h["l2v"] == 8.8235


@pytest.mark.needs_db
def test_hasil_muat_di_tipe_kolom(conn):
    """Nilai ekstrem yang masuk akal harus muat tanpa clamp: 500 juta views,
    dan V2F 100.000%."""
    h = hitung(conn, [(1_000_000, 500_000_000, 500_000, L)])
    assert h["avg_views"] == 500_000_000.0
    assert h["v2f"] == 100_000.0        # muat di numeric(12,4)
    assert h["l2v"] == 0.2
