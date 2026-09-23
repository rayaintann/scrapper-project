"""ER per post: followers point-in-time, dan tidak NULL saat snapshot tersedia.

ER di `l2_gold.post_metric` dibagi dengan followers dari snapshot
`l1_silver.unified_profile` TERAKHIR yang tidak melewati `post_date`
(carry-forward). Post yang lebih tua dari snapshot pertama akun memang tidak
punya penyebut -- ER-nya NULL, dan itu benar: followers historis tidak dikarang.

Yang diuji di sini kebalikannya: begitu snapshot tersedia, ER WAJIB terisi,
kecuali post kolaborasi atau like tersembunyi (dikecualikan aturan sampel).
"""

import pathlib

import pytest

GOLD_POST = (pathlib.Path(__file__).resolve().parents[1]
             / "orchestration" / "kol_orchestration" / "assets" / "gold_post.py")


def test_followers_diambil_point_in_time_bukan_snapshot_terbaru():
    sql = GOLD_POST.read_text(encoding="utf-8")
    assert "pr.date <= d.post_date" in sql
    assert "ORDER BY pr.date DESC" in sql


@pytest.mark.needs_db
def test_db_er_terisi_setiap_kali_snapshot_followers_tersedia():
    """READ-ONLY terhadap database sungguhan."""
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
            cur.execute("""
                SELECT count(*)
                  FROM l2_gold.post_metric pm
                 WHERE pm.er_followers IS NULL
                   AND pm.likes_hidden IS NOT TRUE
                   AND pm.is_collaboration IS NOT TRUE
                   AND EXISTS (SELECT 1 FROM l1_silver.unified_profile pr
                                WHERE pr.social_account_id = pm.social_account_id
                                  AND pr.date <= pm.post_date
                                  AND pr.followers_count > 0)
                   AND (SELECT pr.followers_count FROM l1_silver.unified_profile pr
                         WHERE pr.social_account_id = pm.social_account_id
                           AND pr.date <= pm.post_date
                         ORDER BY pr.date DESC LIMIT 1) > 0""")
            assert cur.fetchone()[0] == 0, "ada post dengan snapshot followers tapi ER NULL"
    finally:
        cn.close()
