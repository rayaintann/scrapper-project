"""Test untuk perbaikan audit iben_ma (17 Sep 2026): like tersembunyi dan Rate Card.

Kelompok 1 -- isi migrasi 048/049/050 dan SQL asset, tanpa database.
Kelompok 2 -- CTE `post_metric` produksi dijalankan sebagai SELECT di sesi
              read-only. Tidak ada yang ditulis ke database.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations"
sys.path.insert(0, str(ROOT / "orchestration"))
sys.path.insert(0, str(ROOT))

from kol_orchestration.assets import gold_post  # noqa: E402


def _baca(nama: str) -> str:
    return (MIG / nama).read_text(encoding="utf-8")


# ===========================================================================
# 1. ISI MIGRASI & SQL ASSET
# ===========================================================================

def test_048_menonaktifkan_procedure_roster():
    sql = _baca("048_disable_roster_rate_card.sql")
    tubuh = sql.split("$procedure$")[1]
    assert "RAISE EXCEPTION" in tubuh
    assert "INSERT" not in tubuh.upper()
    assert "kol_roster_import r" not in tubuh
    assert "DELETE" not in sql.upper(), "048 tidak boleh menghapus data"


def test_048_tidak_membuat_writer_l2():
    kode = "\n".join(baris for baris in _baca("048_disable_roster_rate_card.sql").splitlines()
                     if not baris.lstrip().startswith("--"))
    assert "kol_profile_card" not in kode.lower()


def test_049_menormalkan_likes_tersembunyi():
    sql = _baca("049_unified_post_hidden_likes_null.sql")
    assert "CASE WHEN src.likes = -1 THEN NULL ELSE src.likes END" in sql
    assert "EXCLUDED.likes_hidden IS TRUE THEN NULL" in sql
    # penanda tetap diturunkan dari nilai sumber, bukan dari kolom yang sudah NULL
    assert "CASE WHEN src.likes IS NULL THEN NULL ELSE (src.likes = -1) END" in sql
    # logic migrasi 024 ikut tersalin
    assert "prof_foll.followers_count" in sql and "prof_id.username" in sql
    assert "likes = COALESCE(EXCLUDED.likes, l1_silver.unified_post.likes)" not in sql


def test_050_hanya_menghapus_baris_roster_dan_dijaga():
    sql = _baca("050_cleanup_roster_rate_card.sql")
    assert "Migrasi 048 belum diterapkan" in sql
    for potongan in sql.split("DELETE FROM")[1:]:
        klausa = potongan.split(";")[0]
        assert "WHERE" in klausa, "DELETE tanpa WHERE"
    assert "TRUNCATE" not in sql.upper()
    assert "kol_roster_import" in sql and "DELETE FROM l0_raw" not in sql


def test_post_metric_menormalkan_like_tersembunyi():
    sql = gold_post._CTE_POST
    assert "AS like_tersembunyi" in sql
    assert "CASE WHEN u.likes_hidden IS TRUE OR u.likes < 0 THEN NULL" in sql
    assert sql.count("CASE WHEN d.like_tersembunyi THEN NULL") == 2


# ===========================================================================
# 2. CTE PRODUKSI, READ-ONLY
# ===========================================================================

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


def _satu(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()


def test_post_metric_tanpa_likes_negatif(conn):
    n_neg, = _satu(conn, gold_post._CTE_POST +
                   " SELECT count(*) FILTER (WHERE likes < 0) FROM final")
    assert n_neg == 0


def test_post_metric_engagement_like_tersembunyi_null(conn):
    n_bocor, = _satu(conn, gold_post._CTE_POST + """
        SELECT count(*) FROM final
         WHERE like_tersembunyi
           AND (likes IS NOT NULL OR engagement_owned IS NOT NULL
                OR engagement_public IS NOT NULL)""")
    assert n_bocor == 0


def test_post_metric_engagement_post_terlihat_tidak_berubah(conn):
    n_beda, = _satu(conn, gold_post._CTE_POST + """
        SELECT count(*) FROM final
         WHERE NOT like_tersembunyi
           AND engagement_owned IS DISTINCT FROM
               COALESCE(likes, 0) + COALESCE(comments, 0) + COALESCE(shares, 0)""")
    assert n_beda == 0
