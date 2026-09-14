"""Test EMV.

Yang dijaga di sini bukan cuma "hasilnya benar", tapi tiga keputusan yang
gampang tergelincir kalau tidak dikunci:

  1. engagement EMV = likes + comments SAJA -- tanpa shares/saves/clicks;
  2. `likes_hidden` / `likes = -1` menghasilkan None, bukan 0 dan bukan angka
     negatif;
  3. EMV tidak pernah menyentuh campaign cost, rate card, atau TSDB.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

AKAR = Path(__file__).resolve().parents[1]
if str(AKAR) not in sys.path:
    sys.path.insert(0, str(AKAR))

import campaign_cost_metrics as ccm  # noqa: E402
import emv  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Rumus
# ---------------------------------------------------------------------------
class TestRumus:
    def test_konstanta_sesuai_kesepakatan(self):
        assert emv.EMV_MIN_PER_ENGAGEMENT == 500
        assert emv.EMV_MAX_PER_ENGAGEMENT == 2000
        assert emv.MATA_UANG == "IDR"

    def test_engagement_hanya_likes_dan_comments(self):
        assert emv.engagement_untuk_emv(100, 20) == 120

    def test_emv_min_engagement_kali_500(self):
        assert emv.emv_min(120) == 60_000

    def test_emv_max_engagement_kali_2000(self):
        assert emv.emv_max(120) == 240_000

    def test_rentang_mengembalikan_keduanya(self):
        assert emv.emv_rentang(10) == (5_000, 20_000)

    def test_max_selalu_empat_kali_min(self):
        for eng in (0, 1, 37, 1_000, 39_452_389):
            mn, mx = emv.emv_rentang(eng)
            assert mx == mn * 4

    @pytest.mark.parametrize("likes,comments,harap", [
        (0, 0, 0),
        (1, 0, 1),
        (3012, 7, 3019),        # Instagram
        (53700, 228, 53928),    # TikTok -- shares 746 TIDAK ikut
    ])
    def test_kombinasi_nyata(self, likes, comments, harap):
        assert emv.engagement_untuk_emv(likes, comments) == harap

    def test_definisi_engagement_sengaja_beda_dari_cpe(self):
        """EMV pakai 2 komponen, CPE pakai 3. Perbedaannya disengaja.

        CPE membagi biaya satu campaign, jadi ia boleh memakai seluruh
        interaksi yang platformnya laporkan. EMV membandingkan kreator lintas
        platform, jadi ia harus memakai penggaris yang sama untuk semua --
        dan `shares` hanya ada di TikTok.
        """
        assert emv.KOMPONEN_EMV == ("likes", "comments")
        assert ccm.KOMPONEN_ENGAGEMENT == ("likes", "comments", "shares")
        assert emv.KOMPONEN_EMV != ccm.KOMPONEN_ENGAGEMENT
        # 9+8=17 untuk EMV, 9+8+7=24 untuk CPE.
        assert emv.engagement_untuk_emv(9, 8) == 17
        assert ccm.total_engagement(9, 8, 7) == 24


# ---------------------------------------------------------------------------
# 2. Data yang tidak terukur
# ---------------------------------------------------------------------------
class TestTidakTerukur:
    def test_likes_hidden_menghasilkan_none(self):
        assert emv.engagement_untuk_emv(-1, 14, likes_hidden=True) is None

    def test_likes_negatif_menghasilkan_none_walau_flag_mati(self):
        """Sentinel -1 dikenali dari nilainya, bukan cuma dari flag."""
        assert emv.engagement_untuk_emv(-1, 14, likes_hidden=False) is None

    def test_emv_none_kalau_engagement_none(self):
        assert emv.emv_min(None) is None
        assert emv.emv_max(None) is None
        assert emv.emv_rentang(None) == (None, None)

    def test_semua_komponen_none_menghasilkan_none(self):
        assert emv.engagement_untuk_emv(None, None) is None

    def test_tidak_pernah_menghasilkan_emv_negatif(self):
        for likes in (-1, -5, -999):
            eng = emv.engagement_untuk_emv(likes, 10)
            assert eng is None
            assert emv.emv_min(eng) is None

    def test_nol_tetap_nol_bukan_none(self):
        """Engagement 0 itu terukur dan nyata, beda dari tidak diketahui."""
        assert emv.engagement_untuk_emv(0, 0) == 0
        assert emv.emv_min(0) == 0
        assert emv.emv_max(0) == 0


# ---------------------------------------------------------------------------
# 3. Yang dikeluarkan
# ---------------------------------------------------------------------------
class TestYangDikeluarkan:
    def test_shares_dan_sisanya_dikeluarkan(self):
        for k in ("shares", "saves", "clicks", "views", "reach", "impressions"):
            assert k in emv.DIKELUARKAN_DARI_EMV

    def test_signature_tidak_menerima_shares(self):
        import inspect
        p = inspect.signature(emv.engagement_untuk_emv).parameters
        assert set(p) == {"likes", "comments", "likes_hidden"}

    def test_sql_tidak_menyebut_shares_saves_views_reach(self):
        sql = emv.sql_emv_per_post() + emv.sql_emv_per_kol()
        for dilarang in ("shares", "saves", "views", "reach", "impressions",
                         "clicks"):
            assert not re.search(r"\b" + dilarang + r"\b", sql), dilarang

    def test_dataclass_tidak_lagi_punya_shares(self):
        import db
        assert "shares" not in emv.EmvPost.__dataclass_fields__
        assert "shares_terukur" not in emv.EmvPost.__dataclass_fields__
        assert "shares_terukur" not in db.EmvKol.__dataclass_fields__


# ---------------------------------------------------------------------------
# 4. Sumber data
# ---------------------------------------------------------------------------
class TestSumberData:
    def test_sumber_adalah_post_metric_di_db_kol(self):
        assert emv.SUMBER_EMV == "l2_gold.post_metric"
        assert "l2_gold.post_metric" in emv.sql_emv_per_post()
        assert "l2_gold.post_metric" in emv.sql_emv_per_kol()

    def test_tidak_memakai_campaign_cost_rate_card_atau_tsdb(self):
        sql = (emv.sql_emv_per_post() + emv.sql_emv_per_kol()).lower()
        for dilarang in emv.SUMBER_TERLARANG:
            assert dilarang.lower() not in sql, dilarang

    def test_modul_tidak_membuka_koneksi_ke_mana_pun(self):
        """emv.py murni hitungan: tidak connect, tidak baca env, tidak DSN.

        Dicek dari daftar import, bukan dari substring -- kata "tsdb" sendiri
        memang muncul di `SUMBER_TERLARANG` sebagai penjaga, dan itu justru
        yang diinginkan.
        """
        import ast
        pohon = ast.parse((AKAR / "emv.py").read_text(encoding="utf-8"))
        diimpor = set()
        for n in ast.walk(pohon):
            if isinstance(n, ast.Import):
                diimpor.update(a.name.split(".")[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module:
                diimpor.add(n.module.split(".")[0])
        assert diimpor <= {"__future__", "dataclasses"}, diimpor
        for dilarang in ("psycopg2", "os", "config", "db", "requests"):
            assert dilarang not in diimpor

    def test_daftar_sumber_terlarang_memuat_tsdb_dan_campaign_cost(self):
        assert "tsdb" in emv.SUMBER_TERLARANG
        assert "campaign_kols.deal_price" in emv.SUMBER_TERLARANG
        assert "unified_rate_card.fee" in emv.SUMBER_TERLARANG

    def test_tidak_menyentuh_brand_atau_campaign(self):
        sql = (emv.sql_emv_per_post() + emv.sql_emv_per_kol()).lower()
        for t in ("public.brand", "campaigns", "campaign_kols"):
            assert t not in sql


# ---------------------------------------------------------------------------
# 5. Ekspresi SQL
# ---------------------------------------------------------------------------
class TestSql:
    def test_engagement_memetakan_hidden_ke_null_bukan_nol(self):
        e = emv.sql_engagement_emv("m")
        assert "likes_hidden IS TRUE" in e
        assert "m.likes < 0" in e
        assert "THEN NULL" in e

    def test_engagement_sql_hanya_menjumlah_dua_kolom(self):
        e = emv.sql_engagement_emv("m")
        assert e.count("coalesce") == 2
        assert "m.likes" in e and "m.comments" in e

    def test_pengali_muncul_apa_adanya(self):
        eng = emv.sql_engagement_emv("m")
        assert emv.sql_emv_min(eng).endswith("* 500")
        assert emv.sql_emv_max(eng).endswith("* 2000")

    def test_per_post_mengembalikan_emv_min_dan_max(self):
        sql = emv.sql_emv_per_post()
        assert "AS emv_min" in sql and "AS emv_max" in sql

    def test_per_kol_melaporkan_post_tak_terukur(self):
        sql = emv.sql_emv_per_kol()
        assert "AS post_tak_terukur" in sql
        assert "AS emv_min" in sql and "AS emv_max" in sql

    def test_hanya_satu_migration_yang_menambah_kolom_emv(self):
        """Kolom EMV boleh lahir di SATU tempat saja.

        Dua migration yang sama-sama menambah emv_min berarti dua definisi
        yang bisa berbeda -- persis yang ingin dihindari kolom ini.
        """
        penambah = [
            f.name for f in (AKAR / "migrations").glob("*.sql")
            if "emv_min" in f.read_text(encoding="utf-8", errors="ignore").lower()
        ]
        assert penambah == ["046_post_metric_emv.sql"], penambah


# ---------------------------------------------------------------------------
# 5b. Migration 046 -- kolom EMV di l2_gold.post_metric
# ---------------------------------------------------------------------------
class TestMigration046:
    """Kunci antara migration dan `emv.py`.

    Rumus EMV sekarang hidup di dua tempat sekaligus: ekspresi Python/SQL di
    `emv.py` (dipakai jalur baca) dan kolom GENERATED di migration (dipakai UI
    Next.js yang query Postgres langsung). Keduanya HARUS bercerita hal yang
    sama; test ini yang memastikannya.
    """

    @staticmethod
    @pytest.fixture
    def sql():
        f = AKAR / "migrations" / "046_post_metric_emv.sql"
        assert f.exists(), "migration 046 tidak ada"
        return f.read_text(encoding="utf-8")

    @staticmethod
    @pytest.fixture
    def ekspresi(sql):
        """HANYA statement ALTER TABLE-nya.

        Komentar dan `COMMENT ON COLUMN` sengaja tidak ikut: keduanya memang
        menyebut "shares" dan "rate card" untuk menjelaskan bahwa keduanya
        TIDAK dipakai, dan mencari kata itu di sana akan salah tuduh.
        """
        low = sql.lower()
        awal = low.index("alter table")
        return low[awal:low.index(";", awal)]

    def test_menambah_kolom_bukan_tabel(self, sql):
        low = sql.lower()
        assert "add column if not exists emv_min" in low
        assert "add column if not exists emv_max" in low
        assert "create table" not in low
        assert "drop table" not in low
        assert "drop column" not in low
        assert "delete from" not in low
        assert "truncate" not in low
        assert "update l2_gold" not in low

    def test_kolom_generated_bukan_diisi_pipeline(self, sql):
        assert sql.lower().count("generated always as") == 2
        assert sql.upper().count("STORED") >= 2

    def test_target_tabel_benar(self, sql):
        assert "ALTER TABLE l2_gold.post_metric" in sql

    def test_pengali_diambil_dari_angka_yang_sama_dengan_emv_py(self, sql):
        assert f"* {emv.EMV_MIN_PER_ENGAGEMENT}\n" in sql or \
               f"* {emv.EMV_MIN_PER_ENGAGEMENT}" in sql
        assert f"* {emv.EMV_MAX_PER_ENGAGEMENT}" in sql

    def test_komponen_sama_dengan_emv_py(self, ekspresi):
        """Hanya likes + comments -- tidak ada komponen lain yang menyelinap."""
        for komponen in emv.KOMPONEN_EMV:
            assert f"coalesce({komponen}, 0)" in ekspresi

    def test_tidak_memakai_komponen_yang_dikeluarkan(self, ekspresi):
        for dilarang in emv.DIKELUARKAN_DARI_EMV:
            assert not re.search(r"\b" + dilarang + r"\b", ekspresi), dilarang

    def test_likes_hidden_jadi_null_bukan_nol(self, ekspresi):
        assert ekspresi.count("likes_hidden is true or likes < 0 then null") == 2

    def test_tidak_memakai_campaign_cost_rate_card_atau_tsdb(self, ekspresi):
        for dilarang in emv.SUMBER_TERLARANG:
            assert dilarang.lower() not in ekspresi, dilarang

    def test_tidak_memakai_engagement_public_yang_memuat_sentinel(self, ekspresi):
        """`engagement_public` = likes+comments TAPI memuat -1 apa adanya."""
        assert "engagement_public" not in ekspresi

    def test_punya_blok_verifikasi(self, sql):
        assert "DO $verifikasi$" in sql
        assert "RAISE EXCEPTION" in sql
        assert sql.rstrip().endswith("COMMIT;")
        assert sql.lstrip().startswith("--")


# ---------------------------------------------------------------------------
# 6. Integrasi db.py
# ---------------------------------------------------------------------------
class TestIntegrasiDb:
    def test_db_mengekspos_fetch_emv(self):
        import db
        assert callable(db.fetch_emv_per_post)
        assert callable(db.fetch_emv_per_kol)

    def test_dataclass_punya_emv_min_dan_max(self):
        import db
        for k in ("emv_min", "emv_max", "engagement"):
            assert k in emv.EmvPost.__dataclass_fields__
            assert k in db.EmvKol.__dataclass_fields__

    def test_ringkasan_konsisten(self):
        r = emv.ringkasan()
        assert r["min_per_engagement"] == 500
        assert r["max_per_engagement"] == 2000
        assert r["sumber"] == "l2_gold.post_metric"
        assert r["komponen"] == ("likes", "comments")


# ---------------------------------------------------------------------------
# 7. Tooltip UI
# ---------------------------------------------------------------------------
class TestTooltip:
    def test_teks_tooltip_sesuai_permintaan(self):
        assert emv.TOOLTIP_KALKULASI == (
            "EMV dihitung berdasarkan Likes + Comments. "
            "CPE yang digunakan Rp500-Rp2.000 per engagement."
        )

    def test_tooltip_menyebut_angka_yang_benar_benar_dipakai(self):
        t = emv.TOOLTIP_KALKULASI
        assert "Rp500" in t
        assert "Rp2.000" in t
        assert "Likes + Comments" in t
        assert "Shares" not in t

    def test_tooltip_ikut_ringkasan(self):
        assert emv.ringkasan()["tooltip"] == emv.TOOLTIP_KALKULASI
