"""Test sanity guard followers_count (migration 035).

Dua jenis test, dua alasan berbeda.

**Kontrak SQL (tanpa database).** Sama seperti test_identity_guard.py: yang
dipagari adalah isi file migration -- aturan mana yang tertulis, dan aturan
mana yang sengaja TIDAK ada. Tidak menjalankan migration, tidak menulis.

**Perilaku (butuh database, READ-ONLY).** Dua belas skenario yang diminta
Step 3B dijalankan lewat mesin SQL sungguhan, tetapi terhadap baris sintetis
di dalam VALUES -- tidak satu pun tabel dibaca-tulis, dan prosedurnya sendiri
tidak pernah dipanggil.

Yang membuat test ini bermakna: rantai CTE-nya TIDAK diketik ulang di sini.
`rantai_guard()` memotong rantai yang sesungguhnya dari file migration di
antara penanda `-- >>> ROSTER END (035)` dan `INSERT INTO`, lalu hanya
menukar dua CTE sumber datanya dengan VALUES sintetis. Ekspresi guard dan
rumus Growth yang diuji adalah teks yang benar-benar akan dijalankan di
Postgres, sehingga test ini tidak bisa hanyut dari migration-nya.

Kalau `.env` tidak lengkap atau DB tidak terjangkau, bagian perilaku di-skip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
M035 = MIGRATIONS / "035_followers_sanity_guard.sql"
M034 = MIGRATIONS / "034_remove_tier_fallback_p01.sql"

AMBANG_DASAR = 1000
RASIO_RUNTUH = 0.10


def baca(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sql_saja(path: Path) -> str:
    """Isi migration tanpa baris komentar SQL.

    Header migration di repo ini panjang dan menyebut nama statement yang
    dijelaskannya. Tanpa penyaringan ini, assertion ikut menghitung teks
    penjelasan dan memberi hasil yang menyesatkan.
    """
    return "\n".join(b for b in baca(path).splitlines() if not b.lstrip().startswith("--"))


def potong(teks: str, awal: str, akhir: str) -> str:
    i = teks.index(awal) + len(awal)
    return teks[i:teks.index(akhir, i)]


# =====================================================================
# Kontrak SQL -- tanpa database
# =====================================================================

def test_035_ada():
    assert M035.exists(), "migration 035 belum ada"


def test_035_transaksional():
    sql = baca(M035)
    assert sql.lstrip().startswith("--"), "migration harus diawali header penjelasan"
    assert "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;"), (
        "apply_migration.py --dry-run menukar COMMIT; dengan ROLLBACK; "
        "-- file harus berakhir tepat dengan COMMIT;"
    )


def test_035_punya_cara_mundur():
    sql = baca(M035)
    assert "ROLLBACK" in sql.upper(), "cara mundur harus tertulis"
    assert "034_remove_tier_fallback_p01.sql" in sql, (
        "cara mundur harus menunjuk migration yang memuat definisi sebelumnya"
    )
    assert M034.exists(), "file rollback yang dirujuk harus benar-benar ada"


def test_035_tanpa_perubahan_schema():
    """Keputusan Step 3B nomor 7: tidak ada kolom reason, tidak ada tabel baru."""
    sql = sql_saja(M035).upper()
    for terlarang in (
        "CREATE TABLE", "ALTER TABLE", "DROP TABLE", "ADD COLUMN",
        "DROP COLUMN", "CREATE TYPE", "CREATE INDEX", "RENAME",
    ):
        assert terlarang not in sql, f"035 tidak boleh mengubah schema: {terlarang}"
    assert "REASON" not in sql, "tidak boleh ada kolom/atribut alasan"


def test_035_hanya_mengganti_satu_fungsi():
    sql = sql_saja(M035)
    assert sql.count("CREATE OR REPLACE FUNCTION") == 1
    assert "l1_silver.sp_build_unified_profile()" in sql


def test_035_tidak_menghapus_atau_menulis_data():
    sql = sql_saja(M035).upper()
    for terlarang in ("DELETE FROM", "TRUNCATE", "DROP ", "UPDATE L0_", "INSERT INTO L0_"):
        assert terlarang not in sql, f"035 tidak boleh memuat {terlarang}"


def test_035_tidak_menyentuh_l0():
    """Keputusan Step 3B nomor 4: nilai mentah harus tetap utuh untuk audit."""
    sql = sql_saja(M035)
    for tabel in (
        "l0_raw.tt_profile_apify", "l0_raw.ig_profile_apify",
        "l0_harmonization.tiktok_profile", "l0_harmonization.instagram_profile",
    ):
        for kata in ("DELETE FROM", "UPDATE", "TRUNCATE"):
            assert f"{kata} {tabel}" not in sql, f"L0 tidak boleh di-{kata}: {tabel}"


def test_035_tidak_memakai_ambang_mutlak_pada_nilai_baru():
    """Larangan eksplisit user: `followers < 1000 = invalid` tidak boleh ada.

    Ambang 1.000 hanya boleh muncul sebagai syarat ACUAN atau sebagai bagian
    lapis 3 yang bersyarat rangkap tiga -- tidak pernah sebagai vonis tunggal
    atas nilai baru.
    """
    guard = potong(baca(M035), "GUARD BEGIN (035)", "-- >>> GUARD END")
    baris = [b.strip() for b in guard.splitlines() if not b.strip().startswith("--")]
    vonis_tunggal = [
        b for b in baris
        if "followers_count < 1000" in b and "THEN NULL" in b
    ]
    assert not vonis_tunggal, (
        f"ada vonis ambang mutlak atas nilai baru: {vonis_tunggal}"
    )


def test_035_ambang_diterapkan_pada_acuan():
    """Inti keamanannya: >= 1000 diuji pada ACUAN, bukan pada nilai baru."""
    guard = potong(baca(M035), "GUARD BEGIN (035)", "-- >>> GUARD END")
    assert "COALESCE(c.prev_ref, c.roster_followers) >= 1000" in guard, (
        "syarat AMBANG_DASAR harus melekat pada acuan"
    )
    assert "* 0.10" in guard, "RASIO_RUNTUH 0,10 harus tertulis"


def test_035_tiga_lapis_lengkap():
    guard = potong(baca(M035), "GUARD BEGIN (035)", "-- >>> GUARD END")
    assert "c.followers_count < 0" in guard, "lapis 1 (nilai negatif) hilang"
    assert "c.prev_ref" in guard and "c.roster_followers" in guard, "lapis 2 hilang"
    assert "c.src_platform = 'tiktok'" in guard, "lapis 3 hilang"
    assert "c.likes_count = 0" in guard and "c.media_count = 0" in guard, (
        "lapis 3 harus mensyaratkan likes DAN video nol"
    )


def test_035_acuan_mendahulukan_snapshot_daripada_roster():
    """COALESCE(prev_ref, roster) -- bukan sebaliknya.

    Roster terukur basi untuk seluruh 1.024 akun (Step 2B), jadi snapshot
    sebelumnya harus lebih dipercaya kalau ada.
    """
    guard = potong(baca(M035), "GUARD BEGIN (035)", "-- >>> GUARD END")
    assert "COALESCE(c.prev_ref, c.roster_followers)" in guard
    assert "COALESCE(c.roster_followers, c.prev_ref)" not in guard


def test_035_rumus_growth_tidak_berubah():
    """Larangan eksplisit: rumus Growth tidak boleh diubah."""
    growth = potong(baca(M035), "GROWTH BEGIN (035)", "-- >>> GROWTH END")
    assert "/ src.prev_followers_count * 100, 4)" in growth
    assert "src.prev_followers_count = 0" in growth, "penjaga pembagian nol harus tetap"
    lama = potong(baca(M034), "/ src.prev_followers_count * 100, 4)", "\n")
    assert lama is not None  # migration 034 memang memuat rumus yang sama


def test_035_pembanding_growth_melompati_null():
    """Bagian terpenting Step 3B: LAG mentah tidak boleh tersisa."""
    sql = baca(M035)
    assert "LAG(u.followers_count) OVER" not in sql, (
        "pembanding lama (LAG langsung atas nilai mentah) masih ada"
    )
    assert "lag(f.dijaga_incl)" in sql, "pembanding harus LAG atas rantai bawa-maju"
    assert sql.count("first_value(") >= 2, (
        "harus ada dua bawa-maju: satu untuk acuan guard, satu untuk pembanding Growth"
    )


def test_035_followers_count_penugasan_langsung():
    """Tanpa ini, 54 baris rusak yang sudah tersimpan tidak akan pernah bersih."""
    sql = sql_saja(M035)
    assert "followers_count = EXCLUDED.followers_count," in sql
    assert "followers_count = COALESCE(EXCLUDED.followers_count" not in sql


def test_035_aturan_lama_tetap_utuh():
    """Migration 035 tidak boleh diam-diam membatalkan 020/031/034."""
    sql = baca(M035)
    assert "sa.platform_user_id IS NOT NULL" in sql and "sa.oauth_token IS NOT NULL" in sql, (
        "business rule Connected (031) hilang"
    )
    assert "ORDER BY t.min_followers DESC LIMIT 1" in sql, "aturan tier (034) hilang"
    assert "OR COALESCE(l1_silver.unified_profile.has_insights, false)" in sql, (
        "aturan has_insights sekali-TRUE-tetap-TRUE (020) hilang"
    )


def test_035_punya_blok_verifikasi_yang_menggagalkan():
    sql = baca(M035)
    assert "DO $verifikasi$" in sql
    assert sql.count("RAISE EXCEPTION") >= 8, (
        "blok verifikasi harus benar-benar menggagalkan migration, bukan sekadar NOTICE"
    )


def test_035_daftar_kolom_insert_sama_dengan_034():
    """Guard tidak boleh menambah/mengurangi kolom yang ditulis ke L1."""
    def kolom(path: Path) -> list[str]:
        blok = potong(
            baca(path), "INSERT INTO l1_silver.unified_profile (", ")\n    SELECT"
        )
        return sorted(k.strip() for k in blok.replace("\n", " ").split(",") if k.strip())

    assert kolom(M035) == kolom(M034), "daftar kolom yang ditulis ke L1 berubah"


# =====================================================================
# Perilaku -- butuh database, READ-ONLY, hanya baris sintetis
# =====================================================================

@pytest.fixture(scope="module")
def conn():
    """Koneksi read-only. Skip kalau .env tidak lengkap atau DB tak terjangkau."""
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


@pytest.fixture(scope="module")
def rantai_guard() -> str:
    """Rantai CTE yang SESUNGGUHNYA, dipotong dari file migration.

    Dimulai tepat sesudah CTE `roster`, sehingga dua CTE sumber datanya bisa
    ditukar dengan VALUES sintetis tanpa menyentuh satu baris pun logika.
    """
    sql = baca(M035)
    return potong(sql, "-- >>> ROSTER END (035)", "\n    INSERT INTO l1_silver.unified_profile")


@pytest.fixture(scope="module")
def rumus_growth() -> str:
    return potong(baca(M035), "GROWTH BEGIN (035)", "-- >>> GROWTH END").strip()


def jalankan(conn, rantai, growth, snapshots, roster=None, platform="tiktok"):
    """Jalankan rantai guard atas satu akun sintetis.

    `snapshots`: list of (followers_count, likes_count, media_count).
    Mengembalikan list dict per snapshot, urut tanggal.
    """
    baris = []
    for i, (f, lk, vd) in enumerate(snapshots, start=1):
        baris.append(
            "('akun-uji'::text, DATE '2026-01-%02d', %s::bigint, '%s'::text, %s::bigint, %s::bigint)"
            % (i, "NULL" if f is None else f, platform,
               "NULL" if lk is None else lk, "NULL" if vd is None else vd)
        )
    roster_values = (
        "SELECT NULL::text, NULL::bigint WHERE false"
        if roster is None
        else "VALUES ('akun-uji'::text, %d::bigint)" % roster
    )

    sql = f"""
    WITH sumber (social_account_id, date, followers_count, src_platform,
                 likes_count, media_count) AS (
        VALUES {", ".join(baris)}
    ),
    roster (social_account_id, roster_followers) AS (
        {roster_values}
    ),{rantai}
    SELECT src.date,
           src.followers_count      AS mentah,
           src.followers_dijaga     AS tersimpan,
           src.prev_followers_count AS pembanding,
           {growth}                 AS growth
      FROM src
     ORDER BY src.date
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        kolom = [d[0] for d in cur.description]
        return [dict(zip(kolom, r)) for r in cur.fetchall()]


# --- 1-3: snapshot pertama, tiga macam acuan -------------------------

@pytest.mark.needs_db
def test_1_snapshot_pertama_500_tanpa_roster_valid(conn, rantai_guard, rumus_growth):
    """Tidak ada acuan sama sekali -> guard tidak menebak."""
    r = jalankan(conn, rantai_guard, rumus_growth, [(500, 1200, 30)], roster=None)
    assert r[0]["tersimpan"] == 500
    assert r[0]["growth"] is None, "snapshot pertama tidak punya pembanding"


@pytest.mark.needs_db
def test_2_snapshot_pertama_500_roster_480_valid(conn, rantai_guard, rumus_growth):
    """Acuan di bawah AMBANG_DASAR -> guard tidak berlaku.

    Inilah yang melindungi 304 KOL kecil yang sah di kol_directory.
    """
    r = jalankan(conn, rantai_guard, rumus_growth, [(500, 1200, 30)], roster=480)
    assert r[0]["tersimpan"] == 500


@pytest.mark.needs_db
def test_3_snapshot_pertama_500_roster_45juta_suspect(conn, rantai_guard, rumus_growth):
    """Acuan besar dan nilainya runtuh -> suspect, walau ini snapshot pertama."""
    r = jalankan(conn, rantai_guard, rumus_growth, [(500, 1200, 30)], roster=4_500_000)
    assert r[0]["tersimpan"] is None
    assert r[0]["mentah"] == 500, "nilai mentah harus tetap terbaca untuk audit"


# --- 4-6: dua snapshot ------------------------------------------------

@pytest.mark.needs_db
def test_4_500_ke_700_valid(conn, rantai_guard, rumus_growth):
    """Akun kecil yang tumbuh wajar tidak boleh tersentuh."""
    r = jalankan(conn, rantai_guard, rumus_growth, [(500, 1200, 30), (700, 1500, 32)])
    assert [x["tersimpan"] for x in r] == [500, 700]
    assert r[1]["pembanding"] == 500
    assert float(r[1]["growth"]) == pytest.approx(40.0)


@pytest.mark.needs_db
def test_5_45juta_ke_17_suspect(conn, rantai_guard, rumus_growth):
    """Kasus acuan zeejkt48."""
    r = jalankan(conn, rantai_guard, rumus_growth,
                 [(4_500_000, 90_000_000, 1200), (17, 0, 0)])
    assert r[0]["tersimpan"] == 4_500_000
    assert r[1]["tersimpan"] is None
    assert r[1]["growth"] is None, "baris suspect tidak boleh melahirkan Growth"


@pytest.mark.needs_db
def test_6_45juta_ke_46juta_valid(conn, rantai_guard, rumus_growth):
    r = jalankan(conn, rantai_guard, rumus_growth,
                 [(4_500_000, 90_000_000, 1200), (4_600_000, 92_000_000, 1230)])
    assert [x["tersimpan"] for x in r] == [4_500_000, 4_600_000]
    assert float(r[1]["growth"]) == pytest.approx(2.2222, abs=1e-4)


# --- 7-8: nilai tak terpakai -----------------------------------------

@pytest.mark.needs_db
def test_7_null_tetap_null(conn, rantai_guard, rumus_growth):
    """NULL bukan temuan guard: 'tidak diketahui' sudah bahasa pipeline ini."""
    r = jalankan(conn, rantai_guard, rumus_growth, [(None, 1200, 30)], roster=4_500_000)
    assert r[0]["tersimpan"] is None
    assert r[0]["growth"] is None


@pytest.mark.needs_db
def test_8_negatif_jadi_null(conn, rantai_guard, rumus_growth):
    """Lapis 1: tidak butuh acuan apa pun."""
    r = jalankan(conn, rantai_guard, rumus_growth, [(-1, 1200, 30)], roster=None)
    assert r[0]["tersimpan"] is None


# --- 9-10: lapis 3 khusus TikTok --------------------------------------

@pytest.mark.needs_db
@pytest.mark.parametrize(
    "followers, likes, video",
    [
        (635, 3378, 15),    # ayobersyucure
        (482, 464, 57),     # lintangraina
        (158, 16700, 127),  # minijetplane
        (16, 9, 13),        # emilutfi
        (2, 208, 1),        # randikanurmauli
    ],
)
def test_9_tiktok_kecil_tapi_hidup_tidak_diblokir(
    conn, rantai_guard, rumus_growth, followers, likes, video
):
    """Keputusan Step 3B nomor 6: KOL kecil yang valid tidak boleh diblokir.

    Bentuk angkanya diambil dari akun nyata (G5, Step 3A). Tanpa acuan yang
    membantah, akun ber-follower kecil TETAPI punya video dan like harus
    lolos -- lapis 3 mensyaratkan tiga hal sekaligus, bukan satu.
    """
    r = jalankan(conn, rantai_guard, rumus_growth,
                 [(followers, likes, video)], roster=None)
    assert r[0]["tersimpan"] == followers


@pytest.mark.needs_db
def test_9b_tiktok_kecil_dengan_roster_kecil_tidak_diblokir(conn, rantai_guard, rumus_growth):
    """Akun kecil yang rosternya juga kecil: dua-duanya sepakat, harus lolos."""
    r = jalankan(conn, rantai_guard, rumus_growth, [(900, 0, 0)], roster=480)
    assert r[0]["tersimpan"] == 900, (
        "lapis 3 tidak boleh menang atas kesepakatan acuan yang memang kecil"
    )


@pytest.mark.needs_db
def test_10_tiktok_kecil_dan_profil_kosong_terdeteksi(conn, rantai_guard, rumus_growth):
    """Tanpa acuan apa pun, profil TikTok kosong tetap tertangkap lapis 3."""
    r = jalankan(conn, rantai_guard, rumus_growth, [(40, 0, 0)], roster=None)
    assert r[0]["tersimpan"] is None


@pytest.mark.needs_db
def test_10b_instagram_tidak_kena_lapis_3(conn, rantai_guard, rumus_growth):
    """Lapis 3 sengaja khusus TikTok -- perbedaan yang disengaja, bukan lupa."""
    r = jalankan(conn, rantai_guard, rumus_growth, [(40, None, 0)],
                 roster=None, platform="instagram")
    assert r[0]["tersimpan"] == 40


# --- 11-12: pembanding Growth -----------------------------------------

@pytest.mark.needs_db
def test_11_suspect_tidak_menjadi_pembanding_growth(conn, rantai_guard, rumus_growth):
    """4.500.000 -> 17(suspect) -> 4.500.000.

    Snapshot ketiga wajib membandingkan ke 4.500.000 yang VALID -- bukan ke
    17, dan bukan ke NULL. Inilah yang mencegah Growth +26.470.588%.
    """
    r = jalankan(conn, rantai_guard, rumus_growth, [
        (4_500_000, 90_000_000, 1200),
        (17, 0, 0),
        (4_500_000, 90_100_000, 1210),
    ])
    assert [x["tersimpan"] for x in r] == [4_500_000, None, 4_500_000]

    assert r[2]["pembanding"] == 4_500_000, (
        f"snapshot 3 membandingkan ke {r[2]['pembanding']}, seharusnya 4.500.000"
    )
    assert r[2]["pembanding"] != 17
    assert float(r[2]["growth"]) == pytest.approx(0.0), (
        "Growth harus 0%, bukan angka absurd"
    )


@pytest.mark.needs_db
def test_11b_tanpa_guard_growth_meledak(conn, rantai_guard, rumus_growth):
    """Pembanding: seperti apa hasilnya kalau 17 dipakai sebagai penyebut.

    Bukan menguji kode, melainkan mengunci ALASAN guard ini ada -- supaya
    angkanya tidak bisa dianggap berlebihan di kemudian hari.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT round((4500000 - 17)::numeric / 17 * 100, 4)")
        meledak, = cur.fetchone()
    assert meledak > 26_000_000, "skenario yang dicegah harus benar-benar absurd"


@pytest.mark.needs_db
def test_12_memilih_snapshot_valid_terakhir(conn, rantai_guard, rumus_growth):
    """Empat snapshot, satu di antaranya suspect di tengah.

    Pembanding snapshot terakhir harus 2.000.000 (snapshot VALID terakhir),
    melompati baris suspect -- bukan snapshot pertama, bukan NULL.
    """
    r = jalankan(conn, rantai_guard, rumus_growth, [
        (1_000_000, 20_000_000, 400),
        (2_000_000, 40_000_000, 500),
        (5, 0, 0),
        (2_200_000, 44_000_000, 520),
    ])
    assert [x["tersimpan"] for x in r] == [1_000_000, 2_000_000, None, 2_200_000]
    assert [x["pembanding"] for x in r] == [None, 1_000_000, 2_000_000, 2_000_000]
    assert float(r[3]["growth"]) == pytest.approx(10.0)


@pytest.mark.needs_db
def test_12b_dua_suspect_berturut_turut(conn, rantai_guard, rumus_growth):
    """Rantai suspect tidak boleh memutus riwayat, sepanjang apa pun."""
    r = jalankan(conn, rantai_guard, rumus_growth, [
        (3_000_000, 60_000_000, 900),
        (7, 0, 0),
        (0, 0, 0),
        (3_100_000, 62_000_000, 910),
    ])
    assert [x["tersimpan"] for x in r] == [3_000_000, None, None, 3_100_000]
    assert r[3]["pembanding"] == 3_000_000
    assert float(r[3]["growth"]) == pytest.approx(3.3333, abs=1e-4)


# =====================================================================
# Uji-balik terhadap data nyata -- READ-ONLY, tidak menulis apa pun
# =====================================================================

@pytest.mark.needs_db
def test_db_kol_kecil_yang_sah_tidak_tersentuh(conn, rantai_guard, rumus_growth):
    """Sifat keamanan utama, diuji atas seluruh isi harmonization.

    Dua invarian, keduanya sifat ATURAN dan bukan angka pengamatan:

    1. Tidak satu pun baris yang ACUAN-nya di bawah 1.000 boleh jadi suspect.
    2. Setiap baris Instagram yang kena harus punya alasan lapis 1 atau 2.
       Lapis 3 khusus TikTok, jadi tidak boleh ada baris Instagram yang kena
       tanpa nilai negatif atau keruntuhan terhadap acuan yang sah.

    Versi pertama test ini menuliskan invarian 2 sebagai `instagram == 0`.
    Itu keliru: nol hanyalah keadaan data saat itu, bukan aturannya. Lapis 1
    dan 2 memang berlaku untuk kedua platform, dan scrape Instagram
    2026-09-08 (its.fadil_ = 9 padahal roster 10.063) membuktikannya dengan
    membantah assertion lama.
    """
    sql = f"""
    WITH sumber AS (
        SELECT social_account_id, date, follower_count AS followers_count,
               'tiktok'::text AS src_platform, likes_count, video_count::bigint AS media_count
          FROM l0_harmonization.tiktok_profile
        UNION ALL
        SELECT social_account_id, date, followers_count, 'instagram'::text,
               NULL::bigint, media_count::bigint
          FROM l0_harmonization.instagram_profile
    ),
    roster AS (
        SELECT k.social_account_id, kd.followers_count AS roster_followers
          FROM public.kol_social_account k
          JOIN public.kol_directory kd ON kd.id = k.kol_id
    ),{rantai_guard}
    SELECT count(*) FILTER (WHERE src.followers_dijaga IS NULL
                              AND src.followers_count IS NOT NULL),
           count(*) FILTER (WHERE src.followers_dijaga IS NULL
                              AND src.followers_count IS NOT NULL
                              AND COALESCE(src.prev_ref, src.roster_followers) < 1000),
           count(*) FILTER (WHERE src.followers_dijaga IS NULL
                              AND src.followers_count IS NOT NULL
                              AND src.src_platform = 'instagram'
                              AND NOT (src.followers_count < 0
                                       OR (COALESCE(src.prev_ref, src.roster_followers) >= 1000
                                           AND src.followers_count
                                               < COALESCE(src.prev_ref,
                                                          src.roster_followers) * 0.10)))
      FROM src
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        kena, acuan_kecil, ig_tanpa_alasan = cur.fetchone()

    assert acuan_kecil == 0, f"{acuan_kecil} baris ber-acuan kecil ikut diblokir"
    assert ig_tanpa_alasan == 0, (
        f"{ig_tanpa_alasan} baris Instagram kena tanpa alasan lapis 1/2 "
        "-- lapis 3 bocor ke platform yang salah"
    )
    assert kena > 0, "guard tidak menandai apa pun -- kemungkinan salah pasang"


@pytest.mark.needs_db
def test_db_guard_tidak_menambah_atau_menghilangkan_baris(conn, rantai_guard):
    """Rantai CTE tidak boleh mengubah jumlah baris yang masuk ke L1.

    LEFT JOIN ke roster akan menggandakan baris kalau tautan KOL <-> akun
    ternyata tidak 1:1. Ini menangkapnya sebelum L1 rusak.
    """
    sql = f"""
    WITH sumber AS (
        SELECT social_account_id, date, follower_count AS followers_count,
               'tiktok'::text AS src_platform, likes_count, video_count::bigint AS media_count
          FROM l0_harmonization.tiktok_profile
        UNION ALL
        SELECT social_account_id, date, followers_count, 'instagram'::text,
               NULL::bigint, media_count::bigint
          FROM l0_harmonization.instagram_profile
    ),
    roster AS (
        SELECT k.social_account_id, kd.followers_count AS roster_followers
          FROM public.kol_social_account k
          JOIN public.kol_directory kd ON kd.id = k.kol_id
    ),{rantai_guard}
    SELECT (SELECT count(*) FROM sumber), (SELECT count(*) FROM src)
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        masuk, keluar = cur.fetchone()
    assert masuk == keluar, f"jumlah baris berubah {masuk} -> {keluar}"


@pytest.mark.needs_db
def test_db_l0_tetap_append_only(conn):
    """Guard hidup satu lapis di atas L0; L0 harus tetap tanpa unique per akun."""
    for tabel in ("tt_profile_apify", "ig_profile_apify"):
        with conn.cursor() as cur:
            cur.execute(
                """select count(*) from pg_indexes
                    where schemaname='l0_raw' and tablename=%s
                      and indexdef ilike '%%unique%%'
                      and indexdef ilike '%%social_account_id%%'""",
                (tabel,),
            )
            n, = cur.fetchone()
        assert n == 0, f"l0_raw.{tabel} bukan append-only lagi"
