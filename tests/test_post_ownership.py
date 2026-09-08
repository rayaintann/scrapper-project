"""Test kepemilikan post dan batas "N terbaru per pemilik".

Dijalankan tanpa database: `_filter_owned` dan `latest_posts` adalah fungsi
murni, dan pemetaan username -> social_account_id disuntikkan langsung supaya
tidak perlu query roster.

Yang dipagari di sini persis tiga aturan yang jadi alasan perubahan ini ada:

  1. post milik akun yang diminta   -> disimpan
  2. post milik KOL roster LAIN     -> disimpan, tertaut ke PEMILIK SEBENARNYA
  3. post milik akun non-roster     -> dibuang SEBELUM insert

Aturan 2 yang paling mudah hilang kalau seseorang menyederhanakan filternya
jadi "owner harus sama dengan username yang diminta" — dan itu akan membuang
post KOL roster yang sah.
"""

from __future__ import annotations

import inspect

import pytest

import post_raw_store
import scheduler_engine
from post_raw_store import (
    IG_TABLE,
    PostInsertStats,
    _filter_owned,
    insert_ig_posts,
    insert_tt_videos,
    latest_posts,
)

# social_account_id palsu; isinya tidak penting, yang penting bedanya.
SID_TARGET = "11111111-1111-1111-1111-111111111111"
SID_KOL_LAIN = "22222222-2222-2222-2222-222222222222"

# Peta roster: hanya dua akun ini yang punya baris social_account.
ROSTER = {"target_kol": SID_TARGET, "kol_roster_lain": SID_KOL_LAIN}


def post(owner: str, ts: str) -> tuple[str, dict]:
    """Satu pasangan (username, item) seperti yang dihasilkan `_partition`."""
    return owner, {"ownerUsername": owner, "timestamp": ts, "id": f"{owner}-{ts}"}


def stats_baru() -> PostInsertStats:
    return PostInsertStats(scrape_run_id="run-test", table=IG_TABLE)


def owners(hasil: list[tuple[str, dict]]) -> list[str]:
    return sorted(u for u, _ in hasil)


# --- 1. Kepemilikan ---------------------------------------------------------


def test_post_milik_target_disimpan():
    st = stats_baru()
    hasil = _filter_owned([post("target_kol", "2026-09-01")], ROSTER, "timestamp", None, st)
    assert owners(hasil) == ["target_kol"]
    assert st.skipped_non_roster == 0


def test_post_kol_roster_lain_TETAP_disimpan():
    """Aturan 2. Bukan dibuang, dan bukan pula dilekatkan ke akun yang diminta."""
    st = stats_baru()
    usable = [post("target_kol", "2026-09-01"), post("kol_roster_lain", "2026-09-02")]
    hasil = _filter_owned(usable, ROSTER, "timestamp", None, st)
    assert owners(hasil) == ["kol_roster_lain", "target_kol"]
    assert st.skipped_non_roster == 0
    # Pemiliknya tetap dirinya sendiri; penautan ke sid dilakukan pemanggil
    # lewat account_ids[username], jadi tidak mungkin tertukar.
    assert ROSTER["kol_roster_lain"] == SID_KOL_LAIN


def test_post_non_roster_dibuang_sebelum_insert():
    """Aturan 3. Inilah 36 baris NULL yang dulu tetap masuk L0."""
    st = stats_baru()
    usable = [
        post("target_kol", "2026-09-01"),
        post("neorheumacyl", "2026-09-02"),   # merek obat, bukan KOL
        post("bodrex", "2026-09-03"),
    ]
    hasil = _filter_owned(usable, ROSTER, "timestamp", None, st)
    assert owners(hasil) == ["target_kol"]
    assert st.skipped_non_roster == 2


def test_account_ids_kosong_membuang_semuanya():
    st = stats_baru()
    usable = [post("target_kol", "2026-09-01"), post("kol_roster_lain", "2026-09-02")]
    assert _filter_owned(usable, {}, "timestamp", None, st) == []
    assert st.skipped_non_roster == 2


def test_tidak_ada_hasil_dengan_pemilik_tak_terpetakan():
    """Tidak boleh ada baris lolos yang nanti ditulis dengan social_account_id NULL."""
    st = stats_baru()
    usable = [post("target_kol", "2026-09-01"), post("akun_asing", "2026-09-02")]
    hasil = _filter_owned(usable, ROSTER, "timestamp", None, st)
    assert all(ROSTER.get(u) for u, _ in hasil)


# --- 2. Batas N terbaru per pemilik -----------------------------------------


def test_ambil_10_terbaru_dari_25_post():
    st = stats_baru()
    usable = [post("target_kol", f"2026-09-{d:02d}") for d in range(1, 26)]
    hasil = _filter_owned(usable, ROSTER, "timestamp", 10, st)
    assert len(hasil) == 10
    assert st.skipped_over_limit == 15
    # Harus 10 TERBARU (25 s.d. 16), bukan 10 pertama yang kebetulan lewat.
    tanggal = sorted(item["timestamp"] for _, item in hasil)
    assert tanggal[0] == "2026-09-16"
    assert tanggal[-1] == "2026-09-25"


def test_batas_dihitung_per_pemilik_bukan_global():
    st = stats_baru()
    usable = (
        [post("target_kol", f"2026-09-{d:02d}") for d in range(1, 13)]
        + [post("kol_roster_lain", f"2026-08-{d:02d}") for d in range(1, 13)]
    )
    hasil = _filter_owned(usable, ROSTER, "timestamp", 10, st)
    assert len(hasil) == 20            # 10 per pemilik, bukan 10 total
    assert st.skipped_over_limit == 4  # 2 lebih untuk masing-masing


def test_satu_pemilik_dari_dua_url_tetap_dibatasi_10():
    """Pengelompokan pakai social_account_id, jadi dua URL tidak jadi 20 post."""
    st = stats_baru()
    usable = [post("target_kol", f"2026-09-{d:02d}") for d in range(1, 16)]
    hasil = _filter_owned(usable, ROSTER, "timestamp", 10, st)
    assert len(hasil) == 10


def test_post_tanpa_timestamp_kalah_dari_yang_punya():
    st = stats_baru()
    usable = [
        ("target_kol", {"ownerUsername": "target_kol", "id": "tanpa-waktu"}),
        post("target_kol", "2026-09-01"),
        post("target_kol", "2026-09-02"),
    ]
    hasil = _filter_owned(usable, ROSTER, "timestamp", 2, st)
    assert sorted(item["id"] for _, item in hasil) == [
        "target_kol-2026-09-01",
        "target_kol-2026-09-02",
    ]
    assert st.skipped_over_limit == 1


def test_limit_None_tidak_memotong_apa_pun():
    """Perilaku lama harus utuh untuk pemanggil yang belum meneruskan batas."""
    st = stats_baru()
    usable = [post("target_kol", f"2026-09-{d:02d}") for d in range(1, 26)]
    hasil = _filter_owned(usable, ROSTER, "timestamp", None, st)
    assert len(hasil) == 25
    assert st.skipped_over_limit == 0


def test_tiktok_memakai_createTimeISO():
    st = stats_baru()
    usable = [
        ("target_kol", {"ownerUsername": "target_kol", "createTimeISO": "2026-09-01", "id": "a"}),
        ("target_kol", {"ownerUsername": "target_kol", "createTimeISO": "2026-09-05", "id": "b"}),
    ]
    hasil = _filter_owned(usable, ROSTER, "createTimeISO", 1, st)
    assert [item["id"] for _, item in hasil] == ["b"]


# --- 3. Kontrak yang tidak boleh diam-diam berubah --------------------------


def test_latest_posts_satu_sumber_untuk_dua_pemakai():
    """Scheduler Engine dan post_pipeline wajib memakai fungsi yang sama."""
    assert scheduler_engine.latest_posts is post_raw_store.latest_posts


def test_latest_posts_mengurutkan_menurun():
    items = [{"timestamp": "2026-01-01"}, {"timestamp": "2026-03-01"}, {"timestamp": "2026-02-01"}]
    assert [i["timestamp"] for i in latest_posts(items, "timestamp", 2)] == [
        "2026-03-01",
        "2026-02-01",
    ]


@pytest.mark.parametrize("fn", [insert_ig_posts, insert_tt_videos])
def test_insert_menerima_per_account_limit_dan_defaultnya_None(fn):
    """Default None menjaga pemanggil lama tidak berubah perilakunya."""
    param = inspect.signature(fn).parameters["per_account_limit"]
    assert param.default is None


def test_stats_melaporkan_jumlah_yang_dibuang():
    """Yang dibuang harus terlihat di stats, bukan hilang diam-diam."""
    st = stats_baru()
    usable = [post("target_kol", f"2026-09-{d:02d}") for d in range(1, 13)] + [
        post("akun_asing", "2026-09-01")
    ]
    hasil = _filter_owned(usable, ROSTER, "timestamp", 10, st)
    assert len(hasil) == 10
    assert st.skipped_non_roster == 1
    assert st.skipped_over_limit == 2
