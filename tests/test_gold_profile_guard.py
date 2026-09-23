"""Penjaga `ON CONFLICT ... WHERE` di `kol_profile_card` harus lengkap.

Upsert kartu L2 sengaja tidak menulis ulang baris yang isinya tidak berubah,
supaya `updated_at` menandai perubahan nyata dan rerun idempoten. Penjaganya
adalah daftar `IS DISTINCT FROM` yang ditulis manual.

Kalau sebuah kolom ada di daftar SET tapi TIDAK ada di penjaga, baris yang
HANYA berubah di kolom itu dianggap tidak berubah: upsert mengembalikan 0 dan
nilai barunya tidak pernah ditulis -- tanpa satu pun error. Komentar di
gold_profile.py sudah memperingatkan ini dua kali (migration 037 dan 039);
`audience_quality_score` dan `authenticity_score` tetap lolos sampai
23 September, ketika 34 kartu IG masih memakai authenticity lama sesudah
materialisasi ulang.

Test ini menutup celahnya untuk SEMUA kolom sekaligus, bukan hanya dua itu.
"""

import re

from kol_orchestration.assets.gold_profile import SQL_UPSERT


#: Kolom yang memang TIDAK boleh ikut penjaga, dengan alasannya.
DIKECUALIKAN = {
    # Selalu now(); kalau ikut penjaga, setiap baris selalu "berubah".
    "updated_at",
    # Diisi asset lain. Ada di SET hanya lewat COALESCE, bukan sumber kebenaran.
    "created_at",
}


def _bagian_set() -> str:
    """Potongan SQL antara `DO UPDATE SET` dan `WHERE` penjaga."""
    m = re.search(r"DO UPDATE SET(.*?)\n\s*WHERE kol_profile_card\.",
                  SQL_UPSERT, re.S)
    assert m, "bentuk SQL_UPSERT berubah: blok DO UPDATE SET tidak ketemu"
    return m.group(1)


def _bagian_penjaga() -> str:
    m = re.search(r"\n(\s*WHERE kol_profile_card\..*)$", SQL_UPSERT, re.S)
    assert m, "bentuk SQL_UPSERT berubah: blok WHERE penjaga tidak ketemu"
    return m.group(1)


def _tanpa_komentar(sql: str) -> str:
    return "\n".join(b.split("--")[0] for b in sql.splitlines())


def test_setiap_kolom_yang_ditulis_ikut_penjaga():
    set_sql = _tanpa_komentar(_bagian_set())
    guard_sql = _tanpa_komentar(_bagian_penjaga())

    ditulis = {m.group(1) for m in
               re.finditer(r"^\s*(\w+)\s*=\s*", set_sql, re.M)} - DIKECUALIKAN
    dijaga = set(re.findall(r"kol_profile_card\.(\w+)", guard_sql))

    assert ditulis, "tidak ada kolom terbaca dari blok SET -- parser test usang"
    lolos = sorted(ditulis - dijaga)
    assert not lolos, (
        "kolom ini ditulis upsert tapi tidak ada di penjaga, jadi baris yang "
        f"hanya berubah di situ tidak akan pernah diperbarui: {lolos}")


def test_dua_skor_audiens_ada_di_penjaga():
    """Regresi eksplisit 23 September, supaya kegagalannya bernama."""
    guard = _bagian_penjaga()
    for kolom in ("audience_quality_score", "authenticity_score"):
        assert f"kol_profile_card.{kolom}" in guard, \
            f"{kolom} hilang lagi dari penjaga upsert"
