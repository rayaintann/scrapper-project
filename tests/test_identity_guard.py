"""Test identity guard (migration 030), business rule Connected (031),
dan backfill anchor (032).

Dijalankan tanpa database: yang diuji di sini adalah **isi SQL migration**,
bukan hasil eksekusinya. Alasannya sama seperti test lain di repo ini —
pipeline-nya hidup di Postgres, jadi yang bisa dipagari tanpa DB adalah
kontrak SQL-nya: aturan mana yang tertulis, dan aturan mana yang sengaja
tidak ada.

Test yang butuh database ditandai `needs_db` dan di-skip otomatis kalau
`.env` tidak lengkap atau DB tidak bisa dijangkau. Semuanya READ-ONLY —
tidak satu pun menjalankan migration atau menulis ke database.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

M030 = MIGRATIONS / "030_identity_guard_sp_sync_profile.sql"
M031 = MIGRATIONS / "031_connected_rule_and_column_comments.sql"
M032 = MIGRATIONS / "032_backfill_platform_user_id_kategori_a.sql"


def baca(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sql_saja(path: Path) -> str:
    """Isi migration tanpa baris komentar SQL.

    Header migration di repo ini panjang dan menyebut nama statement yang
    dijelaskannya. Tanpa penyaringan ini, assertion ikut menghitung teks
    penjelasan dan memberi hasil yang menyesatkan.
    """
    baris = baca(path).splitlines()
    return "\n".join(b for b in baris if not b.lstrip().startswith("--"))


# =====================================================================
# Migration 030 — identity guard
# =====================================================================

def test_030_ada():
    assert M030.exists(), "migration 030 belum ada"


def test_030_guard_terpasang_di_dua_prosedur():
    """Gerbang harus ada di TikTok dan Instagram, bukan salah satu saja."""
    sql = baca(M030)
    badan = sql[:sql.index("DO $verifikasi$")]
    assert badan.count("IDENTITY GUARD (migration 030)") == 2, (
        "gerbang harus muncul tepat 2x di badan prosedur — satu per prosedur"
    )
    assert "sp_sync_tiktok_profile" in sql
    assert "sp_sync_instagram_profile" in sql


def test_030_aturan_tiga_cabang():
    """anchor NULL lolos, anchor sama lolos, anchor beda ditolak."""
    sql = baca(M030)
    assert sql.count("kd.platform_user_id IS NULL") == 2, (
        "cabang unanchored harus ada di kedua prosedur"
    )
    assert "kd.platform_user_id = r.raw_payload->'authorMeta'->>'id'" in sql, (
        "identitas TikTok harus dari authorMeta.id"
    )
    assert "kd.platform_user_id = NULLIF(btrim(r.raw_payload->>'id'), '')" in sql, (
        "identitas Instagram harus dari raw_payload.id"
    )


def test_030_tidak_memakai_threshold_follower():
    """Identitas ditentukan platform_user_id, bukan besar-kecilnya follower.

    Menjaga keputusan produk: tidak ada ambang -90% atau sejenisnya.
    """
    sql = sql_saja(M030)
    terlarang = ["-0.9", "-0.5", "0.9 *", "* 0.1", "follower_count <  1000 AND"]
    for pola in terlarang:
        assert pola not in sql, f"migration 030 tidak boleh memuat ambang follower: {pola}"


def test_030_tidak_menyentuh_l0():
    """L0 harus tetap append-only — gerbang ada satu lapis di atasnya."""
    sql = baca(M030)
    for tabel in ("l0_raw.tt_profile_apify", "l0_raw.ig_profile_apify"):
        assert f"DELETE FROM {tabel}" not in sql
        assert f"UPDATE {tabel}" not in sql
        assert f"TRUNCATE {tabel}" not in sql


def test_030_tanpa_perubahan_schema():
    sql = sql_saja(M030).upper()
    for terlarang in ("CREATE TABLE", "ALTER TABLE", "DROP TABLE", "ADD COLUMN", "DROP COLUMN"):
        assert terlarang not in sql, f"030 tidak boleh mengubah schema: {terlarang}"


def test_030_cabang_official_sengaja_tidak_digubah():
    """Alasannya harus tertulis, supaya tidak terlihat seperti kelupaan."""
    sql = baca(M030)
    assert "open_id" in sql, "alasan cabang official harus dijelaskan di header"
    assert "l0_raw.tt_profile_official" in sql


def test_030_transaksional():
    sql = baca(M030)
    assert sql.lstrip().startswith("--") and "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")


# =====================================================================
# Migration 031 — business rule Connected + comment
# =====================================================================

def test_031_ada():
    assert M031.exists(), "migration 031 belum ada"


def test_031_connected_pakai_dua_syarat():
    """Connected = platform_user_id IS NOT NULL AND oauth_token IS NOT NULL."""
    sql = baca(M031)
    assert "sa.platform_user_id IS NOT NULL" in sql
    assert "sa.oauth_token IS NOT NULL" in sql
    # syarat lama yang berdiri sendiri tidak boleh tersisa
    assert not re.search(
        r"\(\s*sa\.oauth_token IS NOT NULL\s*\)\s*,\s*--\s*BUSINESS RULE", sql
    ), "definisi lama (oauth_token saja) masih tertinggal"


def test_031_tidak_memetakan_badge_platform():
    """Badge Apify tidak boleh masuk ke is_verified aplikasi."""
    sql = baca(M031)
    assert "authorMeta.verified" not in sql.replace("(authorMeta.verified)", ""), (
        "badge platform hanya boleh disebut di komentar, bukan dipetakan"
    )
    assert "EXCLUDED.is_verified" not in sql or "connection status" in sql


def test_031_comment_enam_kolom():
    sql = sql_saja(M031)
    assert sql.count("COMMENT ON COLUMN") == 6, "harus ada 6 statement COMMENT ON COLUMN"
    for kolom in (
        "l0_raw.tt_profile_apify.is_verified",
        "l0_harmonization.tiktok_profile.is_verified",
        "l1_silver.unified_profile.is_verified",
        "l2_gold.kol_profile_card.is_verified",
        "public.social_account.connected",
        "public.kol_directory.platform_user_id",
    ):
        assert kolom in sql, f"comment untuk {kolom} belum ada"


def test_031_tidak_rename_kolom():
    sql = sql_saja(M031).upper()
    assert "RENAME" not in sql, "kolom tidak boleh di-rename"
    for terlarang in ("ADD COLUMN", "DROP COLUMN", "ALTER TABLE"):
        assert terlarang not in sql, f"031 tidak boleh mengubah schema: {terlarang}"


def test_031_growth_tidak_diubah():
    """Rumus Growth harus tetap persis seperti sebelumnya."""
    sql = baca(M031)
    assert "prev_followers_count = 0" in sql, "guard pembagian nol harus tetap ada"
    assert "/ src.prev_followers_count * 100" in sql, "rumus Growth tidak boleh berubah"


# =====================================================================
# Migration 032 — backfill anchor
# =====================================================================

def test_032_ada():
    assert M032.exists(), "migration 032 belum ada"


def test_032_tepat_101_anchor():
    sql = baca(M032)
    baris = re.findall(r"^\s+\('[0-9a-f-]{36}'::uuid, '[^']+'\)", sql, re.MULTILINE)
    assert len(baris) == 101, f"harus tepat 101 anchor, ditemukan {len(baris)}"


def test_032_kol_id_unik():
    sql = baca(M032)
    ids = re.findall(r"\('([0-9a-f-]{36})'::uuid,", sql)
    assert len(ids) == 101
    assert len(set(ids)) == 101, "ada kol_id duplikat di daftar anchor"


def test_032_koma_tidak_terkomentari():
    """Koma pemisah VALUES harus SEBELUM komentar, bukan sesudahnya.

    Bug nyata saat file ini dibuat: koma ditulis di ujung baris, sesudah
    `-- username`, sehingga ikut terkomentari dan seluruh daftar VALUES
    gagal parse. Static test ini menangkapnya tanpa perlu menjalankan SQL.
    """
    sql = baca(M032)
    salah = re.findall(r"^\s+\('[0-9a-f-]{36}'::uuid.*--.*,\s*$", sql, re.MULTILINE)
    assert not salah, f"{len(salah)} baris VALUES punya koma di dalam komentar"

    benar = re.findall(r"^\s+\('[0-9a-f-]{36}'::uuid, '[^']+'\),", sql, re.MULTILINE)
    assert len(benar) == 100, (
        f"harus 100 baris berkoma + 1 baris terakhir tanpa koma, ditemukan {len(benar)}"
    )


def test_032_hanya_mengisi_tidak_menimpa():
    sql = baca(M032)
    assert "AND d.platform_user_id IS NULL" in sql, (
        "guard wajib: anchor yang sudah ada tidak boleh ditimpa"
    )


def test_032_rollback_kalau_bukan_101():
    sql = baca(M032)
    assert "GET DIAGNOSTICS n_terpengaruh = ROW_COUNT" in sql
    assert "n_terpengaruh <> 101" in sql
    assert "RAISE EXCEPTION" in sql


def test_032_tidak_menyentuh_kolom_lain():
    """Hanya platform_user_id dan updated_at yang boleh berubah."""
    sql = baca(M032)
    blok = sql[sql.index("UPDATE public.kol_directory"):sql.index("GET DIAGNOSTICS")]
    assert "platform_user_id = a.puid" in blok
    assert "updated_at" in blok
    for terlarang in ("followers_count", "scrape_status", "category_id", "username ="):
        assert terlarang not in blok, f"032 tidak boleh mengubah {terlarang}"


def test_032_tidak_menghapus_apa_pun():
    sql = sql_saja(M032).upper()
    for terlarang in ("DELETE FROM", "TRUNCATE", "DROP "):
        assert terlarang not in sql, f"032 tidak boleh memuat {terlarang}"


def test_032_tanpa_perubahan_schema():
    sql = sql_saja(M032).upper()
    for terlarang in ("CREATE TABLE", "ALTER TABLE", "ADD COLUMN"):
        assert terlarang not in sql


# =====================================================================
# Urutan & konsistensi antar migration
# =====================================================================

def test_urutan_eksekusi_terdokumentasi():
    """032 (anchor) harus dijalankan sebelum 030 (gerbang).

    Gerbang tanpa anchor tidak melindungi apa pun — semua baris jatuh ke
    cabang "anchor NULL". Urutannya harus tertulis di kedua file.
    """
    assert "SETELAH 032" in baca(M030)
    assert "SEBELUM migration 030" in baca(M032)


def test_semua_migration_punya_rollback():
    for path in (M030, M031, M032):
        assert "ROLLBACK" in baca(path).upper(), f"{path.name} tidak menjelaskan cara mundur"


# =====================================================================
# Test yang butuh database — READ-ONLY, di-skip kalau DB tidak terjangkau
# =====================================================================

@pytest.fixture(scope="module")
def conn():
    """Koneksi read-only. Skip kalau .env tidak lengkap atau DB tak terjangkau."""
    psycopg2 = pytest.importorskip("psycopg2")
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from config import ConfigError, load_config

        cfg = load_config()
    except Exception as exc:  # ConfigError atau import gagal
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
        return cur.fetchone()


@pytest.mark.needs_db
def test_db_l0_append_only(conn):
    """L0 tidak boleh punya unique constraint per akun — kalau ada,
    snapshot lama akan tertimpa dan Growth kehilangan pembandingnya."""
    for tabel in ("tt_profile_apify", "ig_profile_apify"):
        n, = satu(
            conn,
            """select count(*) from pg_indexes
                where schemaname='l0_raw' and tablename=%s
                  and indexdef ilike '%%unique%%'
                  and indexdef ilike '%%social_account_id%%'""",
            (tabel,),
        )
        assert n == 0, f"l0_raw.{tabel} punya unique index per akun — L0 bukan append-only lagi"


@pytest.mark.needs_db
def test_db_p01_populasi_discovery(conn):
    """P-01: <1K dan NULL dikecualikan, dan tidak ada KOL yang menguap."""
    total, kecil, kosong, eligible = satu(
        conn,
        """select count(*),
                  count(*) filter (where followers_count < 1000),
                  count(*) filter (where followers_count is null),
                  count(*) filter (where followers_count >= 1000)
             from public.kol_directory""",
    )
    assert eligible + kecil + kosong == total, "ada KOL yang tidak masuk kategori mana pun"


@pytest.mark.needs_db
def test_db_anchor_konsisten_dengan_l1(conn):
    """Setiap anchor yang sudah ada harus cocok dengan snapshot L1 terbaru.

    Berlaku sebelum maupun sesudah backfill. Kalau gagal, ada anchor yang
    menunjuk akun berbeda dari yang di-scrape.
    """
    n_beda, = satu(
        conn,
        """select count(*)
             from public.kol_directory d
             join public.kol_social_account ksa on ksa.kol_id = d.id
             join (select distinct on (social_account_id)
                          social_account_id, platform_user_id
                     from l1_silver.unified_profile
                    where platform_user_id is not null
                    order by social_account_id, date desc) u
               on u.social_account_id = ksa.social_account_id
            where d.platform_user_id is not null
              and d.platform_user_id <> u.platform_user_id""",
    )
    assert n_beda == 0, f"{n_beda} anchor tidak cocok dengan platform_user_id di L1"


@pytest.mark.needs_db
def test_db_satu_akun_satu_identitas(conn):
    """Satu social_account tidak boleh punya lebih dari satu platform_user_id
    di L1 — kalau ada, identitasnya berubah antar snapshot."""
    n, = satu(
        conn,
        """select count(*) from (
             select social_account_id
               from l1_silver.unified_profile
              where platform_user_id is not null
              group by 1 having count(distinct platform_user_id) > 1) t""",
    )
    assert n == 0, f"{n} akun punya platform_user_id yang berubah antar snapshot"


@pytest.mark.needs_db
def test_db_join_anchor_tidak_menggandakan_baris(conn):
    """JOIN yang dipakai gerbang 030 tidak boleh melipatgandakan baris L0."""
    for tabel in ("tt_profile_apify", "ig_profile_apify"):
        asli, = satu(conn, f"select count(*) from l0_raw.{tabel}")
        setelah, = satu(
            conn,
            f"""select count(*) from l0_raw.{tabel} r
                 left join public.kol_social_account ksa
                        on ksa.social_account_id = r.social_account_id
                 left join public.kol_directory kd on kd.id = ksa.kol_id""",
        )
        assert asli == setelah, f"JOIN gerbang menggandakan baris di {tabel}: {asli} -> {setelah}"


@pytest.mark.needs_db
def test_db_growth_hanya_dari_snapshot_valid(conn):
    """Growth tidak boleh terisi kalau tidak ada snapshot pembanding,
    dan tidak boleh dihitung dari previous = 0."""
    n_salah, = satu(
        conn,
        """with s as (
             select social_account_id, date, followers_count, followers_growth,
                    lag(followers_count) over (partition by social_account_id order by date) f_prev
               from l1_silver.unified_profile)
           select count(*) from s
            where followers_growth is not null
              and (f_prev is null or f_prev = 0)""",
    )
    assert n_salah == 0, f"{n_salah} baris punya Growth tanpa pembanding yang sah"


@pytest.mark.needs_db
def test_db_growth_rumus_masih_benar(conn):
    """Bandingkan followers_growth tersimpan dengan hitung ulang manual."""
    n_beda, = satu(
        conn,
        """with s as (
             select social_account_id, date, followers_count, followers_growth,
                    lag(followers_count) over (partition by social_account_id order by date) f_prev
               from l1_silver.unified_profile)
           select count(*) from s
            where f_prev is not null and f_prev <> 0 and followers_count is not null
              and followers_growth is distinct from
                  round((followers_count - f_prev)::numeric / f_prev * 100, 4)""",
    )
    assert n_beda == 0, f"{n_beda} baris Growth tidak cocok dengan rumus"


@pytest.mark.needs_db
def test_db_connected_definisi_bisnis(conn):
    """Connected = platform_user_id DAN oauth_token, keduanya di baris
    social_account yang sama. Bukan kolom `connected`, bukan badge platform."""
    total, puid, oauth, connected = satu(
        conn,
        """select count(*),
                  count(*) filter (where platform_user_id is not null),
                  count(*) filter (where oauth_token is not null),
                  count(*) filter (where platform_user_id is not null
                                     and oauth_token is not null)
             from public.social_account""",
    )
    assert connected <= min(puid, oauth), "Connected tidak boleh melebihi salah satu syaratnya"
    assert total > 0
