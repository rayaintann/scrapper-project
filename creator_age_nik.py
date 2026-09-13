"""Umur kreator dari NIK KTP -- AKTIF sejak 12 September 2026.

Dipakai asset `creator_age` sebagai sumber CADANGAN, di bawah bio.

============================================================================
STATUS: DISETUJUI, DAN APA YANG BERUBAH KARENANYA
============================================================================

NIK adalah satu-satunya sumber di seluruh database ini yang memuat tanggal
lahir sungguhan. Bio menghasilkan 2 umur dari 1.873 profil; NIK menghasilkan
25 lagi dari roster. Selisih itu yang membuat pertanyaannya layak diajukan.

Memakainya adalah keputusan kebijakan, bukan keputusan teknis, dan modul ini
lahir dalam keadaan MATI sambil menunggu keputusan itu. Keputusannya turun 12
September 2026: `influencer_no_ktp` boleh dipakai sebagai sumber tambahan
Creator Age. Yang berubah:

    sebelum                          sesudah
    -----------------------------    ---------------------------------------
    tidak diimpor asset mana pun     diimpor `assets/creator_age.py`
    `nik_diizinkan()`, default MATI  `nik_aktif()`, default HIDUP
    `ktp_nik` ditolak CHECK          `roster_ktp` didaftarkan migration 044

Yang TIDAK berubah, dan tidak boleh berubah:

  * NIK tetap hanya CADANGAN. `bio_self_declared` selalu menang. Umur yang
    dinyatakan kreator sendiri adalah pernyataan publik; NIK tidak.
  * Baris `manual` tetap tidak pernah ditimpa siapa pun.
  * NIK yang rusak tetap ditolak. Persetujuan memperbolehkan PEMAKAIAN
    nomornya, bukan pelonggaran syarat keabsahannya -- 102 dari 157 nomor di
    roster terpotong (7 digit, 1 digit, 11 digit) dan tetap harus ditolak.

============================================================================
NOMOR KTP TIDAK PERNAH KELUAR DARI MODUL INI
============================================================================

Ini syarat yang paling penting di file ini, dan ia tidak ikut longgar
bersama persetujuan.

Tidak satu pun fungsi di sini mengembalikan, mencatat, atau menyimpan nomor
KTP. `HasilNIK` memuat umur, tahun lahir, band, dan confidence -- tidak ada
field untuk nomornya, dan itu bukan kelalaian melainkan syarat.

`umur_per_akun()` melakukan SELECT-nya SENDIRI dan mengembalikan hasil yang
sudah diurai. Itu sebabnya query-nya di sini dan bukan di asset: kalau asset
yang meng-SELECT kolomnya, nomor itu hidup di variabel asset, ikut masuk ke
stack trace saat ada exception, dan cepat atau lambat ikut tercetak di
metadata run oleh orang yang sedang men-debug hal lain.

Pesan kegagalan pun tidak pernah menyisipkan nomor yang gagal diurai: yang
dilaporkan adalah JENIS kegagalan ("panjang 7 digit, seharusnya 16"), bukan
datanya. Log yang memuat NIK adalah kebocoran yang sama seriusnya dengan
kolom yang memuat NIK, dan lebih sulit ditarik kembali.

Yang boleh ditulis ke `kol_profile_card` hanya `creator_age`,
`creator_birth_year`, `creator_age_band`, `creator_age_source='roster_ktp'`,
dan `creator_age_confidence`. TIDAK ADA kolom untuk nomornya, dan tidak boleh
ditambahkan.

============================================================================
BENTUK NIK, DAN KENAPA PENGURAIANNYA TIDAK SESEPELE KELIHATANNYA
============================================================================

    P P R R S S D D M M Y Y N N N N     16 digit
    | | | | | | | | | | | | +-+-+-+---- nomor urut
    | | | | | | | | | | +-+------------ tahun lahir, DUA digit
    | | | | | | | | +-+---------------- bulan lahir
    | | | | | | +-+-------------------- tanggal lahir, +40 kalau PEREMPUAN
    | | | | +-+------------------------ kode kecamatan
    | | +-+---------------------------- kode kabupaten/kota
    +-+-------------------------------- kode provinsi

Dua jebakan:

  * TANGGAL PEREMPUAN DITAMBAH 40. `671289` bukan tanggal 67 yang tidak sah
    melainkan 27 Desember. Parser yang menolak DD>31 akan membuang SELURUH
    kreator perempuan diam-diam -- separuh data hilang tanpa satu pun error.

  * TAHUN CUMA DUA DIGIT. `89` bisa 1989 atau 2089. Dipilih abad yang
    menghasilkan umur di dalam `AGE_MIN..AGE_MAX`; kalau KEDUANYA masuk akal
    atau TIDAK SATU PUN masuk akal, hasilnya `unknown` -- bukan yang lebih
    mungkin. Tebakan yang benar 95% tetap salah untuk 1 dari 20 orang, dan di
    sini "salah" berarti umur meleset seratus tahun.

    Cabang "keduanya masuk akal" HARI INI TIDAK BISA TERCAPAI, dan itu
    disengaja untuk dicatat di sini supaya ia tidak terlihat seperti kode
    mati yang boleh dibuang. Supaya 19YY dan 20YY sama-sama sah, rentang umur
    yang diterima harus membentang seratus tahun; `AGE_MAX - AGE_MIN` = 67.
    Cabang itu menjadi hidup begitu `AGE_MAX` dinaikkan melewati 112, dan
    `tests/test_creator_age_nik.py` gagal pada saat itu supaya keputusannya
    diambil sadar.

============================================================================
KALAU SUATU SAAT HARUS DIMATIKAN LAGI
============================================================================

Set `CREATOR_AGE_NIK_ENABLED=0` di environment, lalu materialisasi ulang
asset `creator_age`. Baris bersumber `roster_ktp` yang sudah ada akan DICABUT
pada run berikutnya, karena asset itu menulis hasil apa adanya untuk tiap
baris yang dibacanya -- termasuk NULL.

Memastikannya: metadata run memuat `nik_aktif`. Jangan berasumsi dari isi
environment; salah ketik pada nilai MATI membuatnya tetap hidup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

from metrics_thresholds import AGE_MAX, AGE_MIN, bucket_age

#: Nilai `creator_age_source` untuk jalur ini. Didaftarkan ke CHECK
#: `ck_kpc_creator_age_source` oleh migration 044, bersamaan dengan
#: persetujuan pemakaian NIK (12 September 2026). Sebelum migration itu,
#: penulisan dengan nilai ini DITOLAK database -- penjagaan yang sengaja
#: dipasang selama izinnya belum turun.
#:
#: Namanya `roster_ktp`, bukan `ktp_nik`: yang menjadi sumber adalah KOLOM di
#: roster, dan penamaan itu yang dipakai di keputusan. Menyebut mekanismenya
#: (`nik`) alih-alih asalnya akan membuat kolom `creator_age_source` bercerita
#: tentang cara menghitung, padahal yang ditanyakan pembacanya selalu "datanya
#: dari mana".
SUMBER_NIK = "roster_ktp"

#: Tabel dan kolom sumber. Ditulis di sini supaya query di bawah adalah
#: SATU-SATUNYA tempat di seluruh repo yang menyentuh kolom NIK.
TABEL_ROSTER = "l0_raw.kol_roster_import"

#: Nama kolom yang memuat nomornya. Ditulis sekali di sini supaya tidak
#: tersebar sebagai literal di beberapa query.
KOLOM_NIK = "influencer_no_ktp"

#: Offset tanggal lahir untuk perempuan pada NIK.
OFFSET_PEREMPUAN = 40

#: Nilai env yang MEMATIKAN jalur ini. Sisanya, termasuk env yang tidak
#: diset sama sekali, berarti hidup.
#:
#: ARAHNYA SENGAJA DIBALIK PADA 12 SEPTEMBER 2026.
#: Sebelum itu daftar ini adalah daftar PUTIH dan default-nya MATI, karena
#: memakai NIK belum disetujui dan salah ketik tidak boleh sampai
#: menyalakannya. Sesudah persetujuan turun, keadaan yang benar adalah HIDUP,
#: dan yang tersisa gunanya hanyalah tombol mati darurat -- supaya jalur ini
#: bisa dihentikan lewat environment tanpa menunggu deploy.
#:
#: Konsekuensinya harus disadari: salah ketik pada nilai MATI (mis. `flase`)
#: membuatnya tetap hidup. Siapa pun yang mematikannya wajib memastikan
#: lewat metadata run (`nik_aktif` di asset `creator_age`), bukan berasumsi.
_NILAI_MATI = {"0", "false", "no", "off", "tidak", "nonaktif", "disabled"}

_HARI_PER_BULAN = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass(frozen=True)
class HasilNIK:
    """Hasil untuk satu NIK. SENGAJA tanpa field untuk nomornya.

    `umur is None` berarti `unknown`. `alasan` selalu terisi dan selalu aman
    dicatat ke log -- ia menyebut JENIS kegagalan, tidak pernah datanya.
    """

    umur: int | None = None
    tahun_lahir: int | None = None
    band: str | None = None
    source: str | None = None
    confidence: str | None = None
    alasan: str = "tidak diurai"

    @property
    def diketahui(self) -> bool:
        return self.umur is not None


def nik_aktif() -> bool:
    """True kecuali env mematikannya secara eksplisit. Default HIDUP.

    Lihat `_NILAI_MATI` untuk kenapa arahnya dibalik pada 12 September 2026.
    """
    raw = (os.getenv("CREATOR_AGE_NIK_ENABLED") or "").strip().lower()
    return raw not in _NILAI_MATI if raw else True


def _tanggal_sah(hari: int, bulan: int) -> bool:
    if not 1 <= bulan <= 12:
        return False
    return 1 <= hari <= _HARI_PER_BULAN[bulan - 1]


def umur_dari_nik(nik: str | None, tahun_acuan: int | None = None) -> HasilNIK:
    """NIK -> umur. Tidak menyentuh database dan tidak mencatat nomornya.

    Fungsi MURNI: aman dipanggil kapan pun, termasuk dari test, karena ia
    tidak bisa menulis apa pun ke mana pun. `nik_diizinkan()` menjaga
    PEMAKAIAN hasilnya, bukan penguraiannya -- memisahkan keduanya membuat
    penguraian bisa diuji tanpa menyalakan flag produksi.

    `tahun_acuan` default ke tahun berjalan; test WAJIB mengopernya supaya
    hasilnya tidak berubah tiap 1 Januari.
    """
    tahun_acuan = tahun_acuan or date.today().year

    bersih = "".join(ch for ch in (nik or "") if ch.isdigit())
    if not bersih:
        return HasilNIK(alasan="kosong")
    if len(bersih) != 16:
        return HasilNIK(alasan=f"panjang {len(bersih)} digit, seharusnya 16")

    hari_mentah = int(bersih[6:8])
    bulan = int(bersih[8:10])
    yy = int(bersih[10:12])

    # Perempuan: tanggal + 40. Dikurangi LEBIH DULU, sebelum divalidasi --
    # kalau tidak, seluruh kreator perempuan tertolak sebagai tanggal tak sah.
    hari = hari_mentah - OFFSET_PEREMPUAN if hari_mentah > OFFSET_PEREMPUAN else hari_mentah
    if not _tanggal_sah(hari, bulan):
        return HasilNIK(alasan="digit tanggal/bulan di luar rentang")

    # Dua abad yang mungkin, disaring oleh rentang umur yang sah. Ambigu ->
    # unknown, bukan yang lebih mungkin.
    kandidat = []
    for abad in (1900, 2000):
        tahun = abad + yy
        umur = tahun_acuan - tahun
        if AGE_MIN <= umur <= AGE_MAX:
            kandidat.append((umur, tahun))

    if not kandidat:
        return HasilNIK(alasan=f"umur di luar {AGE_MIN}..{AGE_MAX} untuk kedua abad")
    if len(kandidat) > 1:
        return HasilNIK(alasan="abad ambigu: 19xx dan 20xx sama-sama masuk akal")

    umur, tahun = kandidat[0]
    return HasilNIK(
        umur=umur,
        tahun_lahir=tahun,
        band=bucket_age(umur),
        source=SUMBER_NIK,
        # `high`, bukan lebih rendah: tanggal lahirnya dinyatakan dokumen
        # negara, bukan disimpulkan dari teks bebas. Yang membatasi jalur ini
        # adalah IZIN, bukan kualitas datanya.
        confidence="high",
        alasan="tanggal lahir dari digit 7-12 NIK",
    )


# ---------------------------------------------------------------------------
# Jalur produksi: umur per akun, TANPA nomornya ikut keluar
# ---------------------------------------------------------------------------
#: Query sumber. Ini SATU-SATUNYA SELECT di seluruh repo yang menyebut kolom
#: NIK, dan hasilnya habis di dalam `umur_per_akun` di bawah.
#:
#: Disaring `social_account_id IS NOT NULL` karena tanpa kunci itu barisnya
#: tidak bisa disambungkan ke kartu profil mana pun -- 26 dari 183 baris
#: ber-KTP memang begitu, dan mengikutsertakannya hanya menambah nomor yang
#: dibaca tanpa menambah satu pun umur.
_SQL_NIK = f"""
    SELECT r.social_account_id, r.{{kolom}}
      FROM {{tabel}} r
     WHERE r.{{kolom}} IS NOT NULL
       AND btrim(r.{{kolom}}) <> ''
       AND r.social_account_id IS NOT NULL
"""


def umur_per_akun(conn, tahun_acuan: int | None = None) -> tuple[dict, dict]:
    """`{social_account_id: HasilNIK}` untuk NIK yang berhasil diurai.

    INI BATAS TEMPAT NOMOR KTP BERHENTI. Pemanggil menerima `HasilNIK` --
    umur, tahun lahir, band, source, confidence -- dan tidak pernah menerima
    nomornya. Itu sebabnya query-nya ada di SINI dan bukan di asset: kalau
    asset yang meng-SELECT kolomnya, nomor itu hidup di variabel asset, masuk
    ke stack trace kalau ada exception, dan cepat atau lambat ikut tercetak di
    metadata run oleh orang yang sedang men-debug hal lain.

    Mengembalikan `(per_akun, statistik)`. `statistik` hanya berisi CACAH dan
    alasan kegagalan -- aman dicetak ke log dan metadata Dagster apa adanya.

    AKUN YANG MUNCUL DUA KALI DENGAN UMUR BERBEDA DIBUANG, bukan diambil salah
    satu. Roster adalah data yang diketik manusia; satu akun dengan dua NIK
    yang menghasilkan umur berbeda berarti setidaknya satu di antaranya salah,
    dan tidak ada cara memilih yang benar dari sini. Ini aturan yang sama
    dengan "bukti bertentangan -> unknown" di `creator_age_inference`.
    Selisih dalam toleransi tidak mungkin muncul di sini -- NIK memberi
    tanggal lahir pasti, bukan perkiraan -- jadi pembandingnya persamaan biasa.
    """
    from collections import Counter

    tahun_acuan = tahun_acuan or date.today().year
    sql = _SQL_NIK.format(tabel=TABEL_ROSTER, kolom=KOLOM_NIK)

    with conn.cursor() as cur:
        cur.execute(sql)
        baris = cur.fetchall()

    kandidat: dict = {}
    gagal: Counter = Counter()
    n_baris = len(baris)

    for sid, nomor in baris:
        hasil = umur_dari_nik(nomor, tahun_acuan=tahun_acuan)
        if not hasil.diketahui:
            gagal[hasil.alasan] += 1
            continue
        kandidat.setdefault(sid, []).append(hasil)
    del baris, sql          # eksplisit: tidak ada nomor yang hidup lebih lama

    per_akun = {}
    bertentangan = 0
    for sid, daftar in kandidat.items():
        if len({h.umur for h in daftar}) > 1:
            bertentangan += 1
            continue
        per_akun[sid] = daftar[0]

    return per_akun, {
        "baris_sumber": n_baris,
        "akun_berhasil": len(per_akun),
        "gagal_diurai": sum(gagal.values()),
        "akun_umur_bertentangan_dibuang": bertentangan,
        "per_alasan_gagal": dict(gagal),
    }


# ---------------------------------------------------------------------------
# Audit -- SATU-SATUNYA fungsi di sini yang menyentuh database. Hanya SELECT.
# ---------------------------------------------------------------------------
def audit_cakupan_nik(conn, tabel: str, tahun_acuan: int | None = None) -> dict:
    """Berapa banyak umur yang BISA terisi lewat NIK, tanpa mengisinya.

    Dipakai untuk menjawab "seberapa besar bedanya kalau jalur ini disetujui"
    SEBELUM ada yang menyetujuinya -- pertanyaan yang wajar dan tidak
    memerlukan satu baris pun ditulis.

    `tabel` dioper pemanggil, tidak ditebak di sini: kolom `influencer_no_ktp`
    belum pernah muncul di repo ini, jadi letaknya harus disebut orang yang
    tahu, bukan dicari-cari oleh kode.

    Mengembalikan CACAH saja. Tidak ada satu pun nomor yang ikut keluar, dan
    `per_alasan` hanya memuat jenis kegagalan.

    Kalau tabel atau kolomnya tidak ada, mengembalikan `{"tersedia": False}`
    dengan penjelasan -- bukan melempar exception. Ketiadaan kolom adalah
    jawaban yang sah untuk pertanyaan ini.
    """
    from collections import Counter

    tahun_acuan = tahun_acuan or date.today().year
    skema, _, nama = tabel.rpartition(".")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*) FROM information_schema.columns
             WHERE table_schema = %s AND table_name = %s AND column_name = %s
        """, (skema or "public", nama, KOLOM_NIK))
        if cur.fetchone()[0] == 0:
            return {
                "tersedia": False,
                "alasan": f"kolom {tabel}.{KOLOM_NIK} tidak ada di database ini",
                "diizinkan": nik_diizinkan(),
            }

        # Hanya kolom NIK yang dibaca, dan hasilnya tidak pernah keluar dari
        # fungsi ini -- ia habis di Counter di bawah.
        cur.execute(f"SELECT {KOLOM_NIK} FROM {tabel} WHERE {KOLOM_NIK} IS NOT NULL")
        nomor = [r[0] for r in cur.fetchall()]

    per_band: Counter = Counter()
    per_alasan: Counter = Counter()
    berhasil = 0
    for n in nomor:
        h = umur_dari_nik(n, tahun_acuan=tahun_acuan)
        if h.diketahui:
            berhasil += 1
            per_band[h.band] += 1
        else:
            per_alasan[h.alasan] += 1

    return {
        "tersedia": True,
        "diizinkan": nik_diizinkan(),
        "baris_punya_nik": len(nomor),
        "umur_bisa_terisi": berhasil,
        "gagal_diurai": len(nomor) - berhasil,
        "sebaran_band": dict(per_band),
        "per_alasan": dict(per_alasan),
        "catatan": (
            "AUDIT SAJA — tidak ada satu baris pun yang ditulis. Nomor KTP "
            "tidak ikut dikembalikan dan tidak dicatat ke log. Lihat docstring "
            "modul untuk langkah pengaktifan."
        ),
    }
