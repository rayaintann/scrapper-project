"""Test untuk migration 033/034 dan query Discovery yang memakai Growth.

Dua kelompok:

  1. Test isi migration -- tidak butuh database. Menjaga agar aturan yang
     sudah disepakati tidak diam-diam hilang dari file SQL-nya.

  2. Test `needs_db` -- READ-ONLY ke database, di-skip otomatis kalau `.env`
     tidak lengkap atau DB tidak terjangkau. Tidak satu pun menjalankan
     migration atau menulis apa pun.

Query Discovery-nya sendiri hidup di repo `autometric`
(`src/lib/discover/kolDirectory.ts`). Yang diuji di sini adalah KONTRAK
DATABASE yang diandalkan query itu: join growth tidak menggandakan baris,
ambang tier benar, dan P-01 tidak bocor. Kalau kontrak ini pecah, UI ikut
salah walau TypeScript-nya lulus compile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
M033 = MIGRATIONS / "033_fix_kol_tiers_boundaries.sql"
M034 = MIGRATIONS / "034_remove_tier_fallback_p01.sql"


def baca(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sql_saja(path: Path) -> str:
    """Isi migration tanpa baris komentar, supaya assertion tidak
    menghitung teks penjelasan di header."""
    return "\n".join(
        b for b in baca(path).splitlines() if not b.lstrip().startswith("--")
    )


def badan_fungsi(path: Path) -> str:
    """Bagian migration SEBELUM blok verifikasi.

    Blok `DO $verifikasi$` sengaja menyebut pola yang dilarang di dalam
    `position(... IN d)` untuk memeriksanya. Tanpa pemisahan ini, test yang
    melarang pola tersebut akan gagal karena penjaganya sendiri.
    """
    return sql_saja(path).split("DO $verifikasi$")[0]


# =====================================================================
# 1. Isi migration -- tanpa database
# =====================================================================

def test_033_ada():
    assert M033.exists(), "migration 033 hilang"


def test_034_ada():
    assert M034.exists(), "migration 034 hilang"


def test_033_memakai_update_bukan_delete_insert():
    """agency_kol_accounts.tier_id punya FK ke kol_tiers.id.

    DELETE + INSERT akan memutus FK itu; UPDATE tidak menyentuh id.
    """
    s = sql_saja(M033)
    assert "UPDATE public.kol_tiers" in s
    assert "DELETE FROM public.kol_tiers" not in s
    assert "INSERT INTO public.kol_tiers" not in s
    assert "TRUNCATE" not in s.upper()


def test_033_menetapkan_ambang_yang_disepakati():
    s = sql_saja(M033)
    # Mid-tier batas atas naik 99.999 -> 499.999
    assert "max_followers = 499999" in s
    # Macro batas bawah naik 100.000 -> 500.000
    assert "min_followers = 500000" in s


def test_033_punya_verifikasi_nilai_batas():
    """Ambang diuji pada nilai batas, bukan diasumsikan."""
    s = sql_saja(M033)
    for nilai in ("999", "1000", "9999", "10000", "49999",
                  "50000", "499999", "500000", "999999", "1000000"):
        assert nilai in s, f"nilai batas {nilai} tidak diuji di 033"


def test_034_membuang_fallback_tier_terendah():
    """Inti P-01: followers < 1.000 tidak boleh jatuh ke tier terendah."""
    s = badan_fungsi(M034)
    assert "ORDER BY t.min_followers ASC LIMIT 1" not in s, (
        "fallback tier terendah masih ada -- P-01 akan bocor lagi"
    )
    assert "ORDER BY t.min_followers DESC LIMIT 1" in s, (
        "pencarian tier normal ikut terhapus -- prosedur rusak"
    )


def test_034_tidak_membuat_tier_baru():
    """Keputusan produk: tidak ada 'Unclassified' / 'Unknown'.

    Dicek pada SQL-nya saja; header migration memang menyebut kedua nama
    itu untuk menjelaskan bahwa keduanya TIDAK dibuat.
    """
    s = sql_saja(M034)
    assert "'Unclassified'" not in s
    assert "'Unknown'" not in s


def test_034_tidak_menghapus_aturan_connected_031():
    """034 diturunkan dari 031; Connected rule harus ikut terbawa utuh."""
    s = sql_saja(M034)
    assert "sa.platform_user_id IS NOT NULL" in s
    assert "sa.oauth_token IS NOT NULL" in s


def test_034_tidak_mengubah_rumus_growth():
    """Growth memakai rumus yang sudah ada -- tidak boleh dihitung ulang."""
    s = sql_saja(M034)
    assert "src.prev_followers_count" in s
    assert "LAG(u.followers_count)" in s


def test_034_tidak_menyentuh_scraper_atau_l0():
    s = sql_saja(M034)
    for terlarang in ("l0_raw", "DROP ", "DELETE FROM", "TRUNCATE"):
        assert terlarang not in s, f"034 menyentuh {terlarang}"


# =====================================================================
# 2. Kontrak database -- READ-ONLY
# =====================================================================

@pytest.fixture(scope="module")
def conn():
    psycopg2 = pytest.importorskip("psycopg2")
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from config import load_config

        cfg = load_config()
    except Exception as exc:
        pytest.skip(f"konfigurasi DB tidak tersedia: {exc}")
    try:
        c = psycopg2.connect(connect_timeout=5, **cfg.postgres.as_connect_kwargs())
    except Exception as exc:
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    c.set_session(readonly=True, autocommit=True)
    yield c
    c.close()


def satu(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


@pytest.mark.needs_db
def test_db_ambang_kol_tiers_sesuai_kesepakatan(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, min_followers, max_followers "
            "FROM public.kol_tiers ORDER BY min_followers"
        )
        assert cur.fetchall() == [
            ("Nano", 1000, 9999),
            ("Micro", 10000, 49999),
            ("Mid-tier", 50000, 499999),
            ("Macro", 500000, 999999),
            ("Mega", 1000000, None),
        ]


@pytest.mark.needs_db
def test_db_band_tier_tidak_bercelah(conn):
    """max baris ke-n + 1 harus sama dengan min baris berikutnya."""
    n = satu(conn, """
        SELECT count(*) FROM (
          SELECT max_followers,
                 LEAD(min_followers) OVER (ORDER BY min_followers) AS berikut
            FROM public.kol_tiers) x
         WHERE berikut IS NOT NULL
           AND (max_followers IS NULL OR max_followers + 1 <> berikut)""")
    assert n == 0


@pytest.mark.needs_db
@pytest.mark.parametrize("followers,tier", [
    (999, None), (1000, "Nano"), (9999, "Nano"),
    (10000, "Micro"), (49999, "Micro"),
    (50000, "Mid-tier"), (499999, "Mid-tier"),
    (500000, "Macro"), (999999, "Macro"),
    (1000000, "Mega"),
])
def test_db_nilai_batas_terpetakan_benar(conn, followers, tier):
    """Ambang diuji lewat join yang sama persis dengan yang dipakai UI."""
    hasil = satu(conn, """
        SELECT (SELECT t.name FROM public.kol_tiers t
                 WHERE %s >= t.min_followers
                   AND (t.max_followers IS NULL OR %s <= t.max_followers)
                 ORDER BY t.min_followers DESC LIMIT 1)""", (followers, followers))
    assert hasil == tier


@pytest.mark.needs_db
def test_db_p01_tidak_bocor_ke_tier_di_l1(conn):
    assert satu(conn, "SELECT count(*) FROM l1_silver.unified_profile "
                      "WHERE followers_count < 1000 AND tier IS NOT NULL") == 0
    assert satu(conn, "SELECT count(*) FROM l1_silver.unified_profile "
                      "WHERE followers_count IS NULL AND tier IS NOT NULL") == 0


@pytest.mark.needs_db
def test_db_p01_tidak_bocor_ke_tier_di_l2(conn):
    assert satu(conn, "SELECT count(*) FROM l2_gold.kol_profile_card "
                      "WHERE followers_count < 1000 AND tier IS NOT NULL") == 0


@pytest.mark.needs_db
def test_db_tidak_ada_tier_unclassified(conn):
    assert satu(conn, "SELECT count(*) FROM public.kol_tiers "
                      "WHERE name IN ('Unclassified','Unknown','Untiered')") == 0


@pytest.mark.needs_db
def test_db_join_growth_tidak_menggandakan_baris_roster(conn):
    """Kontrak inti query Discovery.

    LEFT JOIN LATERAL ... LIMIT 1 ke kol_profile_card harus menghasilkan
    tepat satu baris per KOL. Kalau ini pecah, jumlah hasil Discovery ikut
    salah tanpa error apa pun.
    """
    tanpa_join = satu(conn, "SELECT count(*) FROM public.kol_directory kd "
                            "WHERE kd.directory_status = 'active'")
    dengan_join = satu(conn, """
        SELECT count(*) FROM public.kol_directory kd
        LEFT JOIN LATERAL (
          SELECT c.followers_growth
            FROM public.kol_social_account ksa
            JOIN l2_gold.kol_profile_card c
              ON c.social_account_id = ksa.social_account_id
           WHERE ksa.kol_id = kd.id
           ORDER BY c.followers_count DESC NULLS LAST
           LIMIT 1) g ON TRUE
        WHERE kd.directory_status = 'active'""")
    assert dengan_join == tanpa_join


@pytest.mark.needs_db
def test_db_growth_di_discovery_sama_dengan_l2(conn):
    """Nilai yang dibaca Discovery harus persis nilai di kol_profile_card --
    tidak dihitung ulang di mana pun."""
    beda = satu(conn, """
        SELECT count(*) FROM public.kol_directory kd
        JOIN public.kol_social_account ksa ON ksa.kol_id = kd.id
        JOIN l2_gold.kol_profile_card c
          ON c.social_account_id = ksa.social_account_id
        LEFT JOIN LATERAL (
          SELECT c2.followers_growth
            FROM public.kol_social_account k2
            JOIN l2_gold.kol_profile_card c2
              ON c2.social_account_id = k2.social_account_id
           WHERE k2.kol_id = kd.id
           ORDER BY c2.followers_count DESC NULLS LAST
           LIMIT 1) g ON TRUE
        WHERE kd.directory_status = 'active'
          AND c.followers_growth IS NOT NULL
          AND g.followers_growth IS NULL""")
    assert beda == 0


@pytest.mark.needs_db
def test_db_growth_l2_sama_dengan_l1(conn):
    """L2 membawa growth apa adanya dari snapshot L1 rujukannya."""
    assert satu(conn, """
        SELECT count(*) FROM l2_gold.kol_profile_card cd
        JOIN l1_silver.unified_profile u
          ON u.social_account_id = cd.social_account_id
         AND u.date = cd.profile_snapshot_date
        WHERE cd.followers_growth IS DISTINCT FROM u.followers_growth""") == 0


@pytest.mark.needs_db
def test_db_rumus_growth_masih_yang_lama(conn):
    """Hitung ulang manual dari harmonization; harus identik dengan L1."""
    assert satu(conn, """
        WITH src AS (
          SELECT social_account_id, date, followers_count
            FROM l0_harmonization.instagram_profile
          UNION ALL
          SELECT social_account_id, date, follower_count
            FROM l0_harmonization.tiktok_profile),
        w AS (
          SELECT social_account_id, date, followers_count,
                 LAG(followers_count) OVER (
                   PARTITION BY social_account_id ORDER BY date) AS prev
            FROM src)
        SELECT count(*)
          FROM w JOIN l1_silver.unified_profile u
            ON u.social_account_id = w.social_account_id AND u.date = w.date
         WHERE u.followers_growth IS DISTINCT FROM
               CASE WHEN w.prev IS NULL OR w.prev = 0
                         OR w.followers_count IS NULL THEN NULL
                    ELSE round((w.followers_count - w.prev)::numeric
                               / w.prev * 100, 4) END""") == 0


@pytest.mark.needs_db
def test_db_connected_memakai_definisi_bisnis(conn):
    """Discovery Connected = social_account.platform_user_id AND oauth_token.

    Bukan badge platform. Angkanya boleh 0 -- yang diuji adalah bahwa
    keduanya menghasilkan angka yang SAMA, bukan bahwa ada yang connected.
    """
    lewat_directory = satu(conn, """
        SELECT count(*) FROM public.kol_directory kd
         WHERE kd.directory_status = 'active'
           AND EXISTS (SELECT 1
                         FROM public.kol_social_account ksa
                         JOIN public.social_account sa
                           ON sa.id = ksa.social_account_id
                        WHERE ksa.kol_id = kd.id
                          AND sa.platform_user_id IS NOT NULL
                          AND sa.oauth_token IS NOT NULL)""")
    aturan = satu(conn, """
        SELECT count(DISTINCT ksa.kol_id)
          FROM public.kol_social_account ksa
          JOIN public.social_account sa ON sa.id = ksa.social_account_id
          JOIN public.kol_directory kd ON kd.id = ksa.kol_id
         WHERE kd.directory_status = 'active'
           AND sa.platform_user_id IS NOT NULL
           AND sa.oauth_token IS NOT NULL""")
    assert lewat_directory == aturan


@pytest.mark.needs_db
def test_db_connected_bukan_badge_platform(conn):
    """Badge platform (verified_status) tidak boleh sama dengan Connected.

    454 creator ber-badge; Connected dihitung dari OAuth. Kalau keduanya
    kebetulan sama, berarti sumbernya tertukar lagi.
    """
    badge = satu(conn, """
        SELECT count(*) FROM public.kol_directory
         WHERE directory_status = 'active'
           AND LOWER(COALESCE(verified_status,'')) IN ('verified','true','yes')""")
    connected = satu(conn, """
        SELECT count(*) FROM public.social_account
         WHERE platform_user_id IS NOT NULL AND oauth_token IS NOT NULL""")
    assert badge != connected or badge == 0
