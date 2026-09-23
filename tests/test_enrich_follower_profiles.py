"""enrich_follower_profiles: tanggal per baris, bukan satu tanggal untuk semua.

Regresi 22 September: `scraped_at` diambil dari `baris[0][3]` untuk seluruh
target. Follower dari tanggal lain lalu ditulis ke tanggal yang salah dan tidak
pernah tergabung (COALESCE) dengan barisnya di harmonization.
"""

from datetime import date, timezone

import enrich_follower_profiles as E


def test_scraped_at_mengikuti_tanggal_baris_masing_masing():
    a = E._scraped_at(date(2026, 8, 26))
    b = E._scraped_at(date(2026, 9, 22))
    assert (a.date(), b.date()) == (date(2026, 8, 26), date(2026, 9, 22))
    assert a.tzinfo == timezone.utc and a.hour == 12


def test_target_bisa_dibatasi_ke_cohort_dan_yang_belum_diperkaya():
    args = E.parse_args(["--akun-file", "x.txt", "--hanya-belum", "--dry-run"])
    assert args.akun_file == "x.txt" and args.hanya_belum and args.dry_run


def test_tidak_ada_lagi_tanggal_tunggal_untuk_semua_baris():
    import inspect
    assert "tgl_kunci" not in inspect.getsource(E.main)


def test_enrichment_ditempatkan_sesudah_baris_asli_di_tanggal_yang_sama():
    # Regresi: baris asli di-scrape 13:12; enrichment jam 12:00 kalah
    # `processed_at` di sp_sync_instagram_follower dan bio tidak pernah masuk.
    from datetime import datetime, timedelta
    asli = datetime(2026, 9, 8, 13, 12, 14, tzinfo=timezone.utc)
    t = E._scraped_at(date(2026, 9, 8), asli)
    assert t > asli and t.date() == date(2026, 9, 8)
    assert t - asli == timedelta(seconds=1)


def test_enrichment_tidak_pernah_melewati_tanggalnya():
    from datetime import datetime
    asli = datetime(2026, 9, 8, 23, 59, 59, 500000, tzinfo=timezone.utc)
    t = E._scraped_at(date(2026, 9, 8), asli)
    assert t.date() == date(2026, 9, 8) and t > asli


def test_baris_asli_pagi_tetap_jam_12():
    from datetime import datetime
    asli = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)
    assert E._scraped_at(date(2026, 9, 22), asli).hour == 12


def test_ada_opsi_lewati_username_yang_sudah_dibayar():
    args = E.parse_args(["--lewati-file", "dibayar.txt"])
    assert args.lewati_file == "dibayar.txt"


# --- laporan tidak boleh mengaku menulis baris yang di-rollback --------------

class _CurPalsu:
    """Cursor yang meledak pada INSERT ke-N, sesudah beberapa baris ditulis."""

    def __init__(self, gagal_pada):
        self.gagal_pada = gagal_pada
        self.insert = 0
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, args=None):
        if "INSERT" in sql:
            self.insert += 1
            if self.insert == self.gagal_pada:
                raise RuntimeError("deadlock")


class _ConnPalsu:
    def __init__(self, cur):
        self._cur = cur
        self.commits = 0

    def cursor(self):
        return self._cur

    def commit(self):
        self.commits += 1


def _peta_dua_baris():
    return {"u1": [("sid1", "pid1", date(2026, 9, 8), None)],
            "u2": [("sid2", "pid2", date(2026, 9, 8), None)]}


def _item():
    return {"username": "u", "biography": "halo", "followersCount": 5,
            "followsCount": 3, "id": "pid"}


def test_hitungan_batch_yang_gagal_tidak_masuk_laporan():
    """Regresi: `hasil` dinaikkan di tengah loop, jadi batch yang caller
    rollback tetap meninggalkan angkanya dan laporan mengaku menulis baris
    yang tidak ada di database."""
    from datetime import datetime
    hasil = {"berhasil_user": 0, "gagal_user": [], "id_beda": [], "err_item": 0,
             "ditulis": 0, "dihapus": 0}
    conn = _ConnPalsu(_CurPalsu(gagal_pada=2))
    items = {"u1": _item(), "u2": _item()}
    try:
        E._tulis_batch(conn, "run", items, _peta_dua_baris(),
                       datetime(2026, 9, 8, tzinfo=timezone.utc), hasil)
    except RuntimeError:
        pass
    assert conn.commits == 0
    assert hasil["ditulis"] == 0 and hasil["dihapus"] == 0
    assert hasil["berhasil_user"] == 0


def test_hitungan_batch_yang_sukses_tetap_masuk_laporan():
    from datetime import datetime
    hasil = {"berhasil_user": 0, "gagal_user": [], "id_beda": [], "err_item": 0,
             "ditulis": 0, "dihapus": 0}
    conn = _ConnPalsu(_CurPalsu(gagal_pada=0))
    E._tulis_batch(conn, "run", {"u1": _item(), "u2": _item()}, _peta_dua_baris(),
                   datetime(2026, 9, 8, tzinfo=timezone.utc), hasil)
    assert conn.commits == 1
    assert hasil["ditulis"] == 2 and hasil["berhasil_user"] == 2


def test_maks_batch_dinilai_atas_batch_yang_benar_benar_dijalankan():
    """`--maks-batch` ada untuk menjalankan sebagian target ketika
    keseluruhannya tidak muat plafon; plafon karena itu diuji atas batch yang
    dijalankan, bukan atas seluruh target."""
    import inspect
    src = inspect.getsource(E.main)
    i_potong = src.index("chunks[:args.maks_batch]")
    i_plafon = src.index("melewati plafon")
    assert i_potong < i_plafon, "plafon diuji sebelum --maks-batch memotong target"
    assert "biaya_dijalankan > args.cap_total" in src
