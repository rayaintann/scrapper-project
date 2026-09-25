"""Regression: evidence yang SUDAH ADA di DB harus sampai ke classifier.

1. Geo audiens (`audience_classification.SQL_GEO`) dibaca dari SEMUA tanggal
   L2, bukan tanggal terakhir saja -- batch follower per tanggal berisi follower
   yang berbeda. Snapshot `measured` tidak dijumlah.
2. `latestPosts` IG dibaca dari SEMUA snapshot profil
   (`creator_classification_dryrun.merge_latest_posts`), bukan snapshot terakhir.

Ambang tidak disentuh: test hanya memeriksa bukti yang SAMPAI ke rule.
"""

from __future__ import annotations

from collections import defaultdict

import pytest

import audience_classification as A
import creator_classification_dryrun as D


# ---------------------------------------------------------------------------
# latestPosts
# ---------------------------------------------------------------------------
def test_merge_latest_posts_unions_snapshots_newest_first():
    terbaru = [{"id": "3", "caption": "baru"}, {"id": "2", "caption": "versi baru"}]
    lama = [{"id": "2", "caption": "versi lama"}, {"id": "1", "caption": "hanya di snapshot lama"}]
    out = D.merge_latest_posts([terbaru, lama])
    assert [p["id"] for p in out] == ["3", "2", "1"]
    assert out[1]["caption"] == "versi baru"            # id ganda: versi terbaru menang


def test_merge_latest_posts_single_snapshot_is_unchanged():
    snap = [{"id": "1"}, {"caption": "tanpa id"}, {"id": "2"}]
    assert D.merge_latest_posts([snap]) == snap
    assert D.merge_latest_posts([None]) == []
    # post tanpa id dari snapshot LAMA tidak bisa dideduplikasi -> tidak diambil
    assert D.merge_latest_posts([[{"id": "1"}], [{"caption": "x"}]]) == [{"id": "1"}]


# ---------------------------------------------------------------------------
# Geo audiens
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def conn():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        from config import load_config
        cn = psycopg2.connect(connect_timeout=10, **load_config().postgres.as_connect_kwargs())
    except Exception as exc:                        # pragma: no cover
        pytest.skip(f"database tidak bisa dijangkau: {exc}")
    yield cn
    cn.rollback()
    cn.close()


@pytest.mark.needs_db
def test_geo_sql_sums_inferred_dates_but_not_measured_snapshots(conn):
    """SQL_GEO dijalankan terhadap TEMP TABLE berbentuk sama (lalu ROLLBACK)."""
    cur = conn.cursor()
    cur.execute("""CREATE TEMP TABLE geo_uji (social_account_id uuid, geo_level text, geo_key text,
                   audience_count int, confidence text, audience_date date) ON COMMIT DROP""")
    a, b = "00000000-0000-0000-0000-00000000000a", "00000000-0000-0000-0000-00000000000b"
    cur.execute("""INSERT INTO geo_uji VALUES
        (%(a)s,'country','ID',3,'inferred_high','2026-09-01'),
        (%(a)s,'country','ID',4,'inferred_low', '2026-09-08'),
        (%(a)s,'country','MY',1,'inferred_high','2026-09-01'),
        (%(b)s,'country','ID',50,'measured',     '2026-09-01'),
        (%(b)s,'country','ID',60,'measured',     '2026-09-08'),
        (%(b)s,'country','ID',9,'inferred_high', '2026-09-08')""", {"a": a, "b": b})
    cur.execute(A.SQL_GEO.replace("l2_gold.audience_geo_daily", "pg_temp.geo_uji"))
    got = {(sa, k): (float(n), c) for sa, _lvl, k, n, c in cur.fetchall()}
    conn.rollback()
    assert got[(a, "ID")] == (7.0, "inferred_low")      # 3 + 4, confidence terlemah
    assert got[(a, "MY")] == (1.0, "inferred_high")
    assert got[(b, "ID")] == (60.0, "measured")         # snapshot terukur terakhir, tidak dijumlah


@pytest.mark.needs_db
def test_classifier_geo_counts_every_l2_date(conn):
    """Untuk tiap akun, jumlah geo yang dibaca classifier == jumlah L2 semua tanggal."""
    conn.set_session(readonly=True)
    data = A.load(conn)
    cur = conn.cursor()
    cur.execute("""SELECT social_account_id::text, geo_level, sum(audience_count)
                     FROM l2_gold.audience_geo_daily
                    WHERE geo_level IN ('city','country') AND confidence <> 'measured'
                    GROUP BY 1, 2""")
    want = {(sa, lvl): float(n) for sa, lvl, n in cur.fetchall()}
    cur.execute("""SELECT count(*) FROM (SELECT social_account_id FROM l2_gold.audience_geo_daily
                    GROUP BY 1 HAVING count(DISTINCT audience_date) > 1) z""")
    multi = cur.fetchone()[0]
    conn.rollback()
    conn.set_session(readonly=False)
    got = defaultdict(float)
    for sa, inp in data.items():
        for lvl in ("city", "country"):
            got[(sa, lvl)] = sum(n for n, _c in getattr(inp, lvl).values())
    checked = [k for k in want if k[0] in data]
    assert checked and multi > 0
    assert all(got[k] == pytest.approx(want[k]) for k in checked)


# ---------------------------------------------------------------------------
# Normalisasi teks: emoji/simbol non-ASCII adalah pemisah kata
# ---------------------------------------------------------------------------
def test_normalisasi_emoji_between_words_is_a_separator():
    import audience_inference as AI
    assert AI._normalisasi("BDG📍Cosplay") == "bdg cosplay"
    assert AI._normalisasi("Lifestyle📍Tangerang sekitarnya") == "lifestyle tangerang sekitarnya"
    assert AI._normalisasi("𝓙𝓪𝓴𝓪𝓻𝓽𝓪") == "jakarta"          # huruf bergaya tetap dilipat
    assert AI._normalisasi("Café  crème") == "cafe creme"


def test_city_after_emoji_is_recognised():
    import audience_inference as AI
    h = AI.analisis_follower(None, "BDG📍Cosplay-Beauty", None, None)
    assert h.kota is not None and h.kota.nilai == "Bandung"
    h = AI.analisis_follower(None, "Beauty•Lifestyle📍Tangerang sekitarnya", None, None)
    assert h.kota is not None and h.kota.nilai == "Tangerang"
