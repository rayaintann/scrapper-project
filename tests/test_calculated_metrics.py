"""Test metrik kalkulasi migration 037: Paid Ratio, Share Rate, Post Frequency,
Female %/Male %.

Dua kelompok, alasan yang sama dengan tests/test_growth_metrics.py:

  * Ekspresi SQL (`_PAID_RATIO`, `_SHARE_RATE`, `_POST_FREQ`) dijalankan APA
    ADANYA terhadap Postgres, dengan `post` diganti klausa VALUES. Tidak ada
    CREATE/INSERT/UPDATE -- hanya SELECT atas literal di sesi read-only. Yang
    diuji adalah SQL yang benar-benar dipakai asset, bukan tiruannya.
  * `rasio_gender()` murni Python, jadi diuji langsung tanpa database.

Kelompok terakhir menguji hal yang justru TIDAK boleh ada: metrik yang masih
menunggu keputusan bisnis harus tetap NULL, dan tidak boleh diam-diam
mendapat kolom atau nilai.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestration"))

from kol_orchestration.assets.audience import rasio_gender  # noqa: E402
from kol_orchestration.assets.feature_engagement import (  # noqa: E402
    _PAID_RATIO, _PAID_D, _PAID_N, _POST_FREQ, _OBS_DAYS, _FREQ_N,
    _SHARE_RATE, _SHARE_D, _SHARE_N,
)


# ---------------------------------------------------------------------------
# Perkakas: klausa VALUES sebagai pengganti CTE `post`
# ---------------------------------------------------------------------------

def _post(baris: list[dict]) -> str:
    """CTE `post` dari literal.

    Tiap baris: likes, comments, shares, is_sponsored, posted_at, lolos.
    Cast eksplisit di baris pertama supaya Postgres tidak menebak `unknown`.
    """
    def sel(v, tipe):
        return "NULL::" + tipe if v is None else (
            f"'{v}'::{tipe}" if tipe.startswith("timestamp") else f"{v}::{tipe}")

    potongan = []
    for i, b in enumerate(baris):
        vals = [
            sel(b.get("likes"), "bigint"),
            sel(b.get("comments"), "bigint"),
            sel(b.get("shares"), "bigint"),
            sel(b.get("is_sponsored"), "boolean"),
            sel(b.get("posted_at"), "timestamptz"),
            sel(b.get("lolos", True), "boolean"),
        ]
        if i:  # cast cukup sekali, di baris pertama
            vals = [v.split("::")[0] if not v.startswith("NULL") else "NULL"
                    for v in vals]
        potongan.append("(" + ", ".join(vals) + ")")
    return ("(VALUES " + ", ".join(potongan) +
            ") AS post(likes, comments, shares, is_sponsored, posted_at, lolos)")


def hitung(conn, baris: list[dict]) -> dict:
    """Jalankan ekspresi produksi atas `baris`."""
    sql = f"""
        SELECT {_PAID_RATIO} AS paid_ratio,
               {_PAID_N}     AS paid_n,
               {_PAID_D}     AS paid_d,
               {_SHARE_RATE} AS share_rate,
               {_SHARE_N}    AS share_n,
               {_SHARE_D}    AS share_d,
               {_POST_FREQ}  AS post_frequency_monthly,
               {_FREQ_N}     AS freq_n,
               {_OBS_DAYS}   AS observation_days
          FROM {_post(baris)}
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        kolom = ("paid_ratio", "paid_n", "paid_d", "share_rate", "share_n",
                 "share_d", "post_frequency_monthly", "freq_n", "observation_days")
        return dict(zip(kolom, cur.fetchone()))


@pytest.fixture(scope="module")
def conn():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        from config import load_config
        cfg = load_config()
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"konfigurasi DB tidak tersedia: {exc}")
    try:
        cn = psycopg2.connect(connect_timeout=5, **cfg.postgres.as_connect_kwargs())
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    cn.set_session(readonly=True, autocommit=True)
    yield cn
    cn.close()


def P(**kw):
    """Satu post dengan nilai default yang masuk akal."""
    b = {"likes": 10, "comments": 5, "shares": 0, "is_sponsored": False,
         "posted_at": "2026-01-01 10:00:00+07", "lolos": True}
    b.update(kw)
    return b


# ===========================================================================
# PAID RATIO
# ===========================================================================

def test_paid_semua_organik(conn):
    h = hitung(conn, [P(is_sponsored=False) for _ in range(10)])
    assert h["paid_d"] == 10 and h["paid_n"] == 0
    # NOL, bukan NULL: "tidak ada yang berbayar" adalah jawaban.
    assert float(h["paid_ratio"]) == 0.0


def test_paid_semua_berbayar(conn):
    h = hitung(conn, [P(is_sponsored=True) for _ in range(4)])
    assert float(h["paid_ratio"]) == 100.0


def test_paid_campuran_sesuai_contoh_requirement(conn):
    """10 konten, 3 berbayar -> 30%."""
    baris = [P(is_sponsored=True) for _ in range(3)] + \
            [P(is_sponsored=False) for _ in range(7)]
    h = hitung(conn, baris)
    assert h["paid_n"] == 3 and h["paid_d"] == 10
    assert float(h["paid_ratio"]) == 30.0


def test_paid_sinyal_hilang_dikeluarkan_dari_penyebut(conn):
    """is_sponsored NULL berarti TIDAK DIKETAHUI, bukan organik.

    3 berbayar dari 5 yang diketahui = 60%. Kalau 5 baris NULL ikut penyebut,
    hasilnya jadi 30% -- akun yang datanya paling tidak lengkap akan tampak
    paling sedikit beriklan, persis kebalikan dari yang berguna.
    """
    baris = [P(is_sponsored=True) for _ in range(3)] + \
            [P(is_sponsored=False) for _ in range(2)] + \
            [P(is_sponsored=None) for _ in range(5)]
    h = hitung(conn, baris)
    assert h["paid_d"] == 5, "baris tak diketahui bocor ke penyebut"
    assert float(h["paid_ratio"]) == 60.0


def test_paid_tanpa_sinyal_sama_sekali_null(conn):
    h = hitung(conn, [P(is_sponsored=None) for _ in range(5)])
    assert h["paid_d"] == 0
    assert h["paid_ratio"] is None, "0% akan berbohong: tidak ada yang diketahui"


def test_paid_tidak_ada_konten_null(conn):
    h = hitung(conn, [P(lolos=False, is_sponsored=True)])
    assert h["paid_d"] == 0 and h["paid_ratio"] is None


def test_paid_menghormati_aturan_sampel_lolos(conn):
    """Post yang gagal sampel (likes_hidden / kolaborasi) tidak ikut."""
    baris = [P(is_sponsored=True), P(is_sponsored=True, lolos=False),
             P(is_sponsored=False)]
    h = hitung(conn, baris)
    assert h["paid_d"] == 2 and h["paid_n"] == 1
    assert float(h["paid_ratio"]) == 50.0


# ===========================================================================
# SHARE RATE
# ===========================================================================

def test_share_contoh_requirement_engagement_100_share_1(conn):
    """Engagement = 100, Shares = 1 -> 1%.

    Engagement memakai definisi bisnis yang sudah ada: like + comment + share.
    99 + 0 + 1 = 100.
    """
    h = hitung(conn, [P(likes=99, comments=0, shares=1)])
    assert h["share_d"] == 100
    assert float(h["share_rate"]) == pytest.approx(1.0)


def test_share_beberapa_post_diagregasi_bukan_dirata2(conn):
    """Total share dibagi total engagement, bukan rata-rata rasio per post.

    Konsisten dengan cara ER per akun dihitung (penyebut aditif).
    """
    h = hitung(conn, [P(likes=99, comments=0, shares=1),
                      P(likes=199, comments=0, shares=1)])
    assert h["share_n"] == 2 and h["share_d"] == 300
    assert float(h["share_rate"]) == pytest.approx(0.6667, abs=1e-4)


def test_share_nol_share_bukan_null(conn):
    h = hitung(conn, [P(likes=100, comments=0, shares=0)])
    assert float(h["share_rate"]) == 0.0


def test_share_null_kalau_platform_tidak_melaporkan(conn):
    """Instagram publik tidak pernah melaporkan shares -- seluruh post NULL.

    Hasilnya harus NULL, bukan 0%: 0% berarti "tidak ada yang membagikan",
    dan itu klaim yang tidak pernah diukur.
    """
    h = hitung(conn, [P(shares=None) for _ in range(5)])
    assert h["share_d"] is None
    assert h["share_rate"] is None


def test_share_penyebut_nol_null(conn):
    """Engagement 0 -> pembagian tidak terdefinisi."""
    h = hitung(conn, [P(likes=0, comments=0, shares=0)])
    assert h["share_d"] == 0
    assert h["share_rate"] is None


def test_share_post_tanpa_shares_tidak_menyumbang_penyebut(conn):
    """Penyebut disamakan dengan pembilang: hanya post ber-shares diketahui.

    Tanpa penyelarasan itu, engagement post yang share-nya tidak pernah
    dilaporkan akan menggelembungkan penyebut dan menekan Share Rate.
    """
    h = hitung(conn, [P(likes=99, comments=0, shares=1),
                      P(likes=900, comments=0, shares=None)])
    assert h["share_d"] == 100, "post ber-shares NULL bocor ke penyebut"
    assert float(h["share_rate"]) == pytest.approx(1.0)


# ===========================================================================
# POST FREQUENCY
# ===========================================================================

def test_frekuensi_normal(conn):
    """20 post dalam 30 hari -> 20/30*30 = 20 post/bulan."""
    baris = [P(posted_at=f"2026-01-{d:02d} 10:00:00+07")
             for d in range(1, 21)]  # 1..20 Januari, rentang 19 hari
    h = hitung(conn, baris)
    assert h["freq_n"] == 20 and h["observation_days"] == 19
    assert float(h["post_frequency_monthly"]) == pytest.approx(31.58, abs=0.01)


def test_frekuensi_rentang_31_hari(conn):
    h = hitung(conn, [P(posted_at="2026-01-01 10:00:00+07"),
                      P(posted_at="2026-02-01 10:00:00+07")])
    assert h["observation_days"] == 31
    assert float(h["post_frequency_monthly"]) == pytest.approx(1.94, abs=0.01)


def test_frekuensi_satu_post_null(conn):
    """Satu titik tidak menentukan frekuensi apa pun."""
    h = hitung(conn, [P()])
    assert h["freq_n"] == 1 and h["observation_days"] == 0
    assert h["post_frequency_monthly"] is None


def test_frekuensi_semua_di_hari_yang_sama_null(conn):
    """Rentang nol hari -> pembagian nol. Ditolak, bukan dibagi."""
    baris = [P(posted_at="2026-01-05 08:00:00+07"),
             P(posted_at="2026-01-05 20:00:00+07")]
    h = hitung(conn, baris)
    assert h["observation_days"] == 0
    assert h["post_frequency_monthly"] is None


def test_frekuensi_tanpa_post_null(conn):
    h = hitung(conn, [P(lolos=False)])
    assert h["freq_n"] == 0
    assert h["post_frequency_monthly"] is None


def test_frekuensi_posted_at_null_diabaikan(conn):
    h = hitung(conn, [P(posted_at=None), P(posted_at="2026-01-01 10:00:00+07"),
                      P(posted_at="2026-01-11 10:00:00+07")])
    assert h["freq_n"] == 2 and h["observation_days"] == 10


def test_frekuensi_memakai_rentang_terukur_bukan_periode_tetap(conn):
    """Dua akun dengan jumlah post sama tapi rentang berbeda harus berbeda.

    Ini yang membedakan periode terukur dari periode tetap: membagi keduanya
    dengan 30 hari yang sama akan memberi angka identik untuk perilaku yang
    jelas berbeda.
    """
    rapat = hitung(conn, [P(posted_at="2026-01-01 10:00:00+07"),
                          P(posted_at="2026-01-11 10:00:00+07")])
    renggang = hitung(conn, [P(posted_at="2026-01-01 10:00:00+07"),
                             P(posted_at="2026-04-01 10:00:00+07")])
    assert float(rapat["post_frequency_monthly"]) > \
           float(renggang["post_frequency_monthly"])


# ===========================================================================
# FEMALE % / MALE %   (murni Python, tanpa database)
# ===========================================================================

def test_gender_contoh_requirement():
    """Male 40, Female 60, unknown DIKELUARKAN -> 60% / 40%."""
    f, m, known = rasio_gender({"male": 40, "female": 60, "unknown": 0})
    assert f == 60.0 and m == 40.0


def test_gender_unknown_tidak_mengubah_rasio():
    """Inti kesepakatan: unknown sebesar apa pun tidak menggeser rasionya."""
    tanpa = rasio_gender({"male": 40, "female": 60})
    dengan = rasio_gender({"male": 40, "female": 60, "unknown": 9_000})
    assert tanpa[:2] == dengan[:2] == (60.0, 40.0)
    # Yang berubah hanya penanda keandalannya.
    assert dengan[2] == 1.10 and tanpa[2] == 100.0


def test_gender_hanya_male():
    f, m, _ = rasio_gender({"male": 12, "female": 0, "unknown": 5})
    assert f == 0.0 and m == 100.0


def test_gender_hanya_female():
    f, m, _ = rasio_gender({"male": 0, "female": 7, "unknown": 5})
    assert f == 100.0 and m == 0.0


def test_gender_semua_unknown_null():
    """Penyebut nol. 50/50 akan terlihat seperti pengukuran, jadi NULL."""
    f, m, known = rasio_gender({"unknown": 100})
    assert f is None and m is None
    assert known == 0.0, "known_pct tetap 0, bukan NULL: itu memang terukur"


def test_gender_kosong_null():
    f, m, known = rasio_gender({})
    assert (f, m, known) == (None, None, None)


def test_gender_selalu_berjumlah_100():
    for g in ({"male": 1, "female": 3}, {"male": 23, "female": 15, "unknown": 62},
              {"male": 7, "female": 7}):
        f, m, _ = rasio_gender(g)
        assert round(f + m, 2) == 100.0


def test_gender_nilai_none_diperlakukan_nol():
    f, m, _ = rasio_gender({"male": None, "female": 5, "unknown": None})
    assert f == 100.0 and m == 0.0


# ===========================================================================
# YANG HARUS TETAP KOSONG -- penjaga terhadap metrik karangan
# ===========================================================================

@pytest.mark.needs_db
def test_db_metrik_blocked_tidak_punya_kolom(conn):
    """Metrik yang masih menunggu keputusan bisnis tidak boleh diam-diam
    mendapat kolom. Kolom kosong yang menunggu ambang hanya mengundang
    seseorang mengisinya dengan tebakan.

    DAFTARNYA MENYUSUT DI MIGRATION 038, DAN ITU DISENGAJA.
    `growth_class`, `post_frequency_reliability`, dan `monitoring_priority`
    dulu ada di daftar ini karena ambangnya memang belum ada. Ambang KERJA
    untuk ketiganya sekarang ditetapkan eksplisit dan hidup di
    `metrics_thresholds.py`, jadi kolomnya punya alasan yang tidak dimilikinya
    kemarin -- dan test ini gagal saat 038 jalan, persis seperti seharusnya.

    Yang TERSISA di daftar adalah yang benar-benar masih HOLD: Brand Fit
    (`feature.brand_fit_analysis` 0 baris) dan EMV/CPE/CPV (rate card 0 baris,
    konstanta CPM tidak ada). Ketiganya tidak boleh mendapat kolom sampai
    sumber dan definisinya ada.
    """
    terlarang = ("brand_fit", "brand_fit_score", "partnership_score",
                 "emv", "cpe", "cpv", "estimated_media_value")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_schema || '.' || table_name || '.' || column_name
              FROM information_schema.columns
             WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
               AND column_name = ANY(%s)""", (list(terlarang),))
        ada = [r[0] for r in cur.fetchall()]
    assert not ada, f"kolom metrik BLOCKED muncul di kartu L2: {ada}"


@pytest.mark.needs_db
def test_db_emv_cpe_tetap_null_selama_rate_card_kosong(conn):
    """`feature.*_audience_analysis` sudah punya kolom cpe/emv sejak lama.
    Selama `unified_rate_card` kosong, keduanya HARUS tetap NULL."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM l1_silver.unified_rate_card")
        if cur.fetchone()[0] > 0:
            pytest.skip("rate card sudah terisi; asumsi test ini tidak berlaku lagi")
        cur.execute("""
            SELECT count(cpe) + count(emv) FROM feature.ig_audience_analysis
            UNION ALL
            SELECT count(cpe) + count(emv) FROM feature.tt_audience_analysis""")
        assert [r[0] for r in cur.fetchall()] == [0, 0]


@pytest.mark.needs_db
def test_db_brand_fit_masih_kosong(conn):
    """Kalau tabel ini mulai terisi, Brand Fit tidak lagi BLOCKED dan audit
    perlu diulang -- test ini yang memberi tahu."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM feature.brand_fit_analysis")
        assert cur.fetchone()[0] == 0, \
            "brand_fit_analysis terisi: tinjau ulang status BLOCKED-nya"


# ===========================================================================
# Konsistensi dengan data produksi
# ===========================================================================

@pytest.mark.needs_db
def test_db_l2_membawa_apa_adanya_dari_feature(conn):
    """Kartu L2 tidak boleh menghitung ulang; angkanya harus identik feature."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card c
            JOIN feature.ig_engagement_analysis f
              ON f.social_account_id = c.social_account_id
             WHERE c.platform = 'instagram'
               AND (c.paid_ratio IS DISTINCT FROM f.paid_ratio
                 OR c.share_rate IS DISTINCT FROM f.share_rate
                 OR c.post_frequency_monthly IS DISTINCT FROM f.post_frequency_monthly)""")
        assert cur.fetchone()[0] == 0
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card c
            JOIN feature.ig_audience_analysis a
              ON a.social_account_id = c.social_account_id
             WHERE c.platform = 'instagram'
               AND (c.female_pct IS DISTINCT FROM a.female_pct
                 OR c.male_pct   IS DISTINCT FROM a.male_pct)""")
        assert cur.fetchone()[0] == 0


@pytest.mark.needs_db
def test_db_female_male_berjumlah_100_pada_data_nyata(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card
             WHERE female_pct IS NOT NULL
               AND round(female_pct + male_pct, 2) <> 100.00""")
        assert cur.fetchone()[0] == 0


@pytest.mark.needs_db
def test_db_paid_ratio_dalam_rentang_wajar(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card
             WHERE paid_ratio IS NOT NULL
               AND (paid_ratio < 0 OR paid_ratio > 100)""")
        assert cur.fetchone()[0] == 0


@pytest.mark.needs_db
def test_db_paid_ratio_selalu_punya_penyebut(conn):
    """paid_ratio tidak boleh ada tanpa paid_signal_count -- kalau terjadi,
    penyebutnya hilang dan angkanya tidak bisa diaudit."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card
             WHERE paid_ratio IS NOT NULL
               AND (paid_signal_count IS NULL OR paid_signal_count = 0)""")
        assert cur.fetchone()[0] == 0


@pytest.mark.needs_db
def test_db_post_frequency_selalu_punya_observation_days(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM l2_gold.kol_profile_card
             WHERE post_frequency_monthly IS NOT NULL
               AND (observation_days IS NULL OR observation_days <= 0)""")
        assert cur.fetchone()[0] == 0

# ===========================================================================
# POST FREQUENCY -- kesepakatan final: HANYA satuan bulanan
# ===========================================================================

def test_frekuensi_20_post_30_hari(conn):
    """Contoh wajib: 20 post dalam 30 hari -> 20 post/bulan."""
    baris = [P(posted_at="2026-01-01 10:00:00+07")] + \
            [P(posted_at="2026-01-31 10:00:00+07")] * 19
    h = hitung(conn, baris)
    assert h["freq_n"] == 20 and h["observation_days"] == 30
    assert float(h["post_frequency_monthly"]) == pytest.approx(20.0)


def test_frekuensi_10_post_15_hari(conn):
    """Contoh wajib kedua: 10 post dalam 15 hari -> 20 post/bulan juga.

    Dua jumlah post yang berbeda menghasilkan angka yang SAMA karena
    periodenya berbeda -- itulah gunanya menormalkan ke 30 hari alih-alih
    melaporkan jumlah post mentah.
    """
    baris = [P(posted_at="2026-01-01 10:00:00+07")] + \
            [P(posted_at="2026-01-16 10:00:00+07")] * 9
    h = hitung(conn, baris)
    assert h["freq_n"] == 10 and h["observation_days"] == 15
    assert float(h["post_frequency_monthly"]) == pytest.approx(20.0)


def test_frekuensi_bukan_jumlah_post_mentah(conn):
    """Penjaga: nilainya tidak boleh diam-diam berubah jadi count."""
    baris = [P(posted_at="2026-01-01 10:00:00+07")] + \
            [P(posted_at="2026-01-16 10:00:00+07")] * 9
    h = hitung(conn, baris)
    assert float(h["post_frequency_monthly"]) != float(h["freq_n"])


# ===========================================================================
# POST FREQUENCY RELIABILITY -- batas final
# ===========================================================================

@pytest.mark.parametrize("hari, post, harapan", [
    (30, 20, "High"),      # contoh requirement
    (30, 10, "High"),      # batas High tepat: kedua syarat pas
    (30, 9, "Medium"),     # post kurang satu
    (29, 10, "Medium"),    # hari kurang satu
    (30, 7, "Medium"),     # contoh requirement
    (20, 7, "Medium"),     # contoh requirement
    (14, 5, "Medium"),     # batas Medium tepat
    (13, 5, "Low"),        # hari di bawah batas
    (14, 4, "Low"),        # post di bawah batas
    (10, 3, "Low"),        # contoh requirement
    (100, 0, None),        # tidak ada post valid
    (0, 0, None),
    (None, None, None),
])
def test_reliability_batas_final(hari, post, harapan):
    from metrics_thresholds import klasifikasi_post_frequency
    assert klasifikasi_post_frequency(hari, post) == harapan


def test_reliability_mengukur_keandalan_bukan_kerajinan():
    """Akun yang SANGAT sering posting tapi rentangnya pendek TIDAK reliable.

    Ini yang membedakan metrik ini dari Post Frequency itu sendiri: 200 post
    dalam 5 hari menghasilkan frekuensi yang sangat tinggi, tapi lima hari
    tidak cukup untuk mempercayainya.
    """
    from metrics_thresholds import klasifikasi_post_frequency
    assert klasifikasi_post_frequency(5, 200) == "Low"
    assert klasifikasi_post_frequency(60, 12) == "High"
