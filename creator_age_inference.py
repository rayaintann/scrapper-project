"""Umur KREATOR dari teks profilnya sendiri -- ketat, dan hampir selalu `unknown`.

Dipakai asset `creator_age` untuk mengisi `l2_gold.kol_profile_card.creator_age*`.

JANGAN SAMAKAN DENGAN `audience_inference.py`. Modul itu menurunkan atribut
AUDIENS (follower) -- gender, lokasi, minat. Modul ini menentukan umur ORANG
KOL-NYA. Dua fitur berbeda, dua tabel berbeda, dan sengaja dua file berbeda.

============================================================================
KENAPA MODUL INI SANGAT MEMBATASI DIRI
============================================================================

Instagram dan TikTok TIDAK mengekspos umur kreator. Tidak ada field tanggal
lahir di actor Apify mana pun yang dipakai pipeline ini, dan tidak ada kolomnya
di seluruh database. Satu-satunya tempat umur BISA muncul adalah teks bio yang
ditulis kreator sendiri.

Sebelum modul ini ditulis, 902 bio ASLI hasil scrape
(`output/instagram_profiles_*.csv`) diperiksa untuk mengukur seberapa sering
sinyal umur benar-benar muncul:

    pola                          hit     benar setelah diperiksa satu per satu
    --------------------------------------------------------------------------
    umur eksplisit (`22 tahun`)     2      0
    `yo` / `years old`              0      -
    tahun 4-digit (19xx/20xx)      34      ~1
    tanggal lahir dd/mm/yyyy        0      -
    `born` / `lahir` + tahun        0      -
    angkatan / batch                0      -

Ke-34 bio yang memuat tahun 4-digit isinya:

    `Rekormuri 2019`, `IMAE Beauty Vlogger 2018`   -> tahun PENGHARGAAN
    `Est.2016`, `since 2013`, `quality since 1989` -> tahun BERDIRI brand
    `Korea Mei 2026`, `Thailand June 2026`         -> jadwal PERJALANAN
    `+62 815-1986-4471`                            -> potongan NOMOR TELEPON
    `20 Nov 2017 / 17 Sept 2020` (emoji anak)      -> tanggal lahir ANAK-nya

Yang terakhir adalah alasan paling kuat kenapa modul ini berbentuk seperti
sekarang: parser tanggal lahir yang naif akan menyimpulkan kreator itu berumur
delapan tahun.

Dua "umur eksplisit" yang ketemu pun dua-duanya salah baca: `36th online`
(ordinal bahasa Inggris) dan `20 thn bantu ribuan klien` (20 tahun PENGALAMAN).

Presisi "ada tahun di bio -> itu tahun lahir" karena itu sekitar 3%. Heuristik
seperti itu TIDAK dibangun di sini, dan tidak boleh ditambahkan nanti: 33 dari
34 akun akan mendapat umur karangan.

Hal yang sama berlaku untuk angka di belakang username. Dari 67 akun yang
username-nya berakhir dua digit, isinya nomor punggung (`bepe20`), tanggal
pernikahan (`raffinagita1717`), jam operasional (`infojkt24`), dan angka hoki.
Bukan tahun lahir. Username TIDAK dipakai sama sekali oleh modul ini.

============================================================================
ATURAN
============================================================================

  1. HANYA PERNYATAAN EKSPLISIT. Umur diambil hanya kalau kreator MENYEBUTKAN
     umur atau tahun lahirnya dengan kata kunci yang tidak bisa dibaca lain
     (`umur`, `usia`, `y.o`, `lahir`, `born`). Angka telanjang tidak pernah
     cukup.

  2. KONTEKS BISA MEMBATALKAN. Tiap calon diperiksa terhadap kata-kata di
     sekitarnya. `since`, `juara`, `pengalaman`, `anak` dan sejenisnya
     membatalkan calon itu -- lihat `_VETO`.

  3. BUKTI BERTENTANGAN -> `unknown`. Kalau dua calon memberi umur berbeda
     lebih dari toleransi, hasilnya `unknown`, bukan yang ketemu duluan.

  4. `unknown` ADALAH KEBERHASILAN, BUKAN KEGAGALAN. Terhadap 902 bio yang
     diuji, modul ini mengembalikan `unknown` untuk hampir semuanya. Itu
     jawaban yang benar. Modul yang mengembalikan angka untuk 34 akun akan
     salah pada 33 di antaranya.

  5. DETERMINISTIK. Tidak ada acak, tidak ada model, tidak ada panggilan
     jaringan. Input sama -> output sama, dengan satu pengecualian yang
     dijelaskan di bawah (`tahun_acuan`).

============================================================================
UMUR BERGESER, TAHUN LAHIR TIDAK
============================================================================

Umur yang dihitung dari tahun lahir ikut bertambah tiap tahun. Karena itu
`tahun_lahir` IKUT DIKEMBALIKAN dan ikut disimpan di kolomnya sendiri: itu
nilai yang tidak basi. `creator_age` adalah turunan terhadap `tahun_acuan`,
dan pemanggil yang butuh hasil reprodusibel (test) WAJIB mengoperkannya
secara eksplisit alih-alih membiarkannya default ke tahun berjalan.

Sebaliknya, umur yang dinyatakan langsung (`umur 24`) TIDAK bisa dipakai
menghitung tahun lahir yang pasti -- orangnya bisa saja sudah atau belum
berulang tahun tahun ini. Untuk kasus itu `tahun_lahir` dibiarkan None, bukan
ditebak.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from metrics_thresholds import AGE_MAX, AGE_MIN, bucket_age

# ---------------------------------------------------------------------------
# Nilai untuk kolom `creator_age_source`
# ---------------------------------------------------------------------------
#: Kreator menyatakannya sendiri di bio. Satu-satunya sumber otomatis yang ada.
SUMBER_BIO = "bio_self_declared"
#: Diisi manusia (roster/CRM), bukan oleh pipeline. Tidak pernah ditulis modul
#: ini -- didaftarkan di sini supaya daftar nilai sahnya hidup di satu tempat,
#: dan supaya asset tahu nilai mana yang TIDAK boleh ditimpa hasil otomatis.
SUMBER_MANUAL = "manual"

NILAI_SUMBER = (SUMBER_BIO, SUMBER_MANUAL)
NILAI_CONFIDENCE = ("high", "medium", "low")

#: Selisih umur (tahun) yang masih dianggap sepakat antar dua calon. Satu
#: tahun, karena "umur 24" dan "lahir 2001" bisa dua-duanya benar tergantung
#: sudah atau belum ulang tahun.
TOLERANSI_TAHUN = 1


@dataclass(frozen=True)
class HasilUmur:
    """Hasil untuk satu kreator. `umur is None` berarti `unknown`."""

    umur: int | None = None
    tahun_lahir: int | None = None
    band: str | None = None
    source: str | None = None
    confidence: str | None = None
    alasan: str = "tidak ada pernyataan umur yang eksplisit"

    @property
    def diketahui(self) -> bool:
        return self.umur is not None


# ---------------------------------------------------------------------------
# Normalisasi
# ---------------------------------------------------------------------------
_RE_SPASI = re.compile(r"\s+")


def _normalisasi(teks: str | None) -> str:
    """Lipat unicode bergaya ke ASCII huruf kecil, pertahankan angka & tanda baca.

    Bio KOL banyak memakai huruf matematis (mis. `Est.2016` ditulis dengan
    karakter bold matematis) dan huruf kecil berukuran kapital. Tanpa
    pelipatan NFKD, pola di bawah tidak akan pernah cocok -- dan yang lebih
    berbahaya, kata VETO-nya juga tidak akan cocok, sehingga justru calon yang
    salah yang lolos.
    """
    if not teks:
        return ""
    t = unicodedata.normalize("NFKD", teks)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    return _RE_SPASI.sub(" ", t).strip()


# ---------------------------------------------------------------------------
# VETO -- kata yang membatalkan calon di sekitarnya
# ---------------------------------------------------------------------------
# Tiap kelompok diambil dari false positive NYATA pada 902 bio yang diperiksa,
# bukan dikarang. Komentarnya menyebut contoh aslinya supaya siapa pun yang
# nanti tergoda membuang salah satu bisa melihat apa yang akan kembali rusak.
#
# VETO DISESUAIKAN DENGAN SEBERAPA AMBIGU POLANYA, BUKAN DIPUKUL RATA.
# --------------------------------------------------------------------
# Versi pertama modul ini memakai SATU daftar veto untuk semua pola, dan
# test-nya langsung menangkap dua kerusakan:
#
#     `usia 31 tahun, ibu dua anak`   -> terveto 'anak', padahal "usia 31"
#                                        jelas merujuk penulisnya sendiri
#     `travel blogger, 45 years old`  -> terveto 'travel', padahal 'travel'
#                                        hanya relevan untuk TAHUN telanjang
#                                        (`Korea Mei 2026`), bukan untuk umur
#
# Pelajarannya: makin eksplisit kata kunci sebuah pola, makin sedikit konteks
# yang boleh membatalkannya. `umur 31` menyebut dirinya sendiri; `2026` tidak
# menyebut apa pun. Karena itu tiap pola sekarang membawa daftar vetonya
# sendiri.

#: Menandakan angkanya milik ORANG LAIN (anak, pasangan). Berlaku untuk semua
#: pola, karena `20 Nov 2017` di bio orang tua memang tanggal lahir anaknya.
_VETO_ORANG_LAIN = (
    "anak", "son", "daughter", "putra", "baby", "bayi", "kids", "child",
    "children", "anniversary", "anniv", "hbd", "happy birthday", "ultah",
)

#: `20 thn bantu ribuan klien` -- angkanya lama PENGALAMAN, bukan umur.
_VETO_PENGALAMAN = (
    "pengalaman", "berpengalaman", "experience", "experienced", "melayani",
    "serving", "serve", "bantu", "membantu", "klien", "client", "clients",
    "member", "trusted", "dipercaya", "online",
)

#: Khusus TAHUN: `Est.2016`, `Rekormuri 2019`, `Vlogger 2018`, `Korea Mei 2026`.
#: Tidak berlaku untuk pola umur -- `travel blogger, 45 years old` tetap sah.
_VETO_TAHUN = (
    "since", "sejak", "est", "estd", "established", "berdiri", "founded",
    "juara", "winner", "runner", "award", "awards", "champion", "finalis",
    "finalist", "pemenang", "rekor", "muri", "miss", "mister", "puteri",
    "putri", "duta", "sampul", "ambassador", "nominasi", "piala",
    "angkatan", "batch", "alumni", "lulusan", "grads", "graduate",
    "trip", "tour", "travel", "jadwal", "schedule", "booking",
)

#: Jendela lebar, dipakai pola yang ambigu. 40 kira-kira satu frasa; cukup
#: untuk menangkap `Vlogger 2018` dan `since 2013` tanpa menelan seluruh bio
#: (yang akan membuat SEMUA calon terveto begitu bio menyebut "mom" sekali di
#: ujung lain).
_JENDELA_LEBAR = 40

#: Jendela sempit KIRI SAJA, dipakai pola umur yang eksplisit. Cukup untuk
#: menangkap `anak usia 15` (pemiliknya disebut tepat sebelum angka) tanpa
#: ikut membatalkan `usia 31 tahun, ibu dua anak`, yang pemiliknya adalah
#: penulis bio itu sendiri.
_JENDELA_SEMPIT = 14

_RE_KATA = re.compile(r"[a-z]+")


def _terveto(teks: str, awal: int, akhir: int,
             daftar: tuple[str, ...], jendela: int,
             hanya_kiri: bool = False) -> str | None:
    """Kembalikan kata veto pertama di sekitar calon, atau None kalau bersih."""
    kiri = teks[max(0, awal - jendela):awal]
    kanan = "" if hanya_kiri else teks[akhir:akhir + jendela]
    sekitar = set(_RE_KATA.findall(kiri)) | set(_RE_KATA.findall(kanan))
    for kata in daftar:
        if " " in kata:
            if kata in kiri or kata in kanan:
                return kata
        elif kata in sekitar:
            return kata
    return None


def _bagian_angka_lebih_panjang(teks: str, awal: int, akhir: int) -> bool:
    """True kalau angka ini sebenarnya potongan dari deret angka yang lebih panjang.

    Inilah yang menyelamatkan `+62 815-1986-4471` dari dibaca sebagai kelahiran
    1986. Pemisah `-`, `.`, dan spasi di dalam nomor telepon sengaja ikut
    dianggap penyambung.
    """
    i = awal - 1
    while i >= 0 and teks[i] in "-. ":
        i -= 1
    if i >= 0 and teks[i].isdigit():
        return True
    j = akhir
    while j < len(teks) and teks[j] in "-. ":
        j += 1
    return j < len(teks) and teks[j].isdigit()


# ---------------------------------------------------------------------------
# Pola calon
# ---------------------------------------------------------------------------
# `th` TELANJANG SENGAJA TIDAK DITERIMA. Dalam bahasa Inggris itu akhiran
# ordinal (`36th online`, false positive nyata di data), dan bio KOL Indonesia
# bercampur dua bahasa. `thn` dan `tahun` tidak ambigu, jadi hanya keduanya.
# Tiap entri: (regex, confidence, alasan, daftar_veto, jendela, hanya_kiri).
_POLA_UMUR = (
    # `umur 24`, `usia 24`, `age: 24` -- kata kuncinya di DEPAN, paling tegas.
    # Hanya kepemilikan orang lain yang boleh membatalkannya.
    (re.compile(r"\b(?:umur|usia|age)\s*:?\s*(\d{1,2})\b"), "high",
     "kata kunci umur di depan angka",
     _VETO_ORANG_LAIN, _JENDELA_SEMPIT, True),
    # `24 y.o`, `24yo`, `24 years old` -- satuannya tidak bisa dibaca lain.
    (re.compile(r"\b(\d{1,2})\s*(?:y\.?o\.?\b|yrs?\b|years?\s*old\b)"), "high",
     "satuan umur di belakang angka",
     _VETO_ORANG_LAIN, _JENDELA_SEMPIT, True),
    # `24 tahun`, `24 thn` -- paling rawan (`20 thn bantu ribuan klien`), jadi
    # confidence-nya `medium` DAN vetonya paling luas di antara pola umur.
    (re.compile(r"\b(\d{1,2})\s*(?:thn|tahun)\b"), "medium",
     "satuan tahun di belakang angka",
     _VETO_ORANG_LAIN + _VETO_PENGALAMAN, _JENDELA_LEBAR, False),
)

_POLA_LAHIR = (
    # `lahir 15/08/1998`, `born 15-08-1998`  -- tanggal penuh, paling tegas
    (re.compile(r"\b(?:lahir|born|dob|b)\b\W{0,3}"
                r"\d{1,2}[/\-.]\d{1,2}[/\-.](\d{4})\b"), "high",
     "kata kunci lahir + tanggal lengkap",
     _VETO_ORANG_LAIN + _VETO_TAHUN, _JENDELA_LEBAR, False),
    # `lahir 1998`, `born in 1998`, `b. 1998`
    (re.compile(r"\b(?:lahir|born|dob|b)\b\W{0,3}(?:in|pada|tahun|thn)?\W{0,3}"
                r"(\d{4})\b"), "high",
     "kata kunci lahir + tahun",
     _VETO_ORANG_LAIN + _VETO_TAHUN, _JENDELA_LEBAR, False),
)


def _tahun_masuk_akal(tahun: int, tahun_acuan: int) -> bool:
    umur = tahun_acuan - tahun
    return AGE_MIN <= umur <= AGE_MAX


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def ekstrak_umur(bio: str | None,
                 tahun_acuan: int | None = None) -> HasilUmur:
    """Ambil umur kreator dari bio. `HasilUmur` dengan `umur=None` = `unknown`.

    `tahun_acuan` menentukan umur yang dihitung dari tahun lahir. Default-nya
    tahun berjalan; test WAJIB mengoperkannya supaya hasilnya tidak berubah
    tiap 1 Januari.

    `username` dan `full_name` SENGAJA bukan parameter. Keduanya sudah diuji
    terhadap data nyata dan tidak membawa sinyal umur -- lihat docstring modul.
    """
    tahun_acuan = tahun_acuan or date.today().year
    teks = _normalisasi(bio)
    if not teks:
        return HasilUmur(alasan="bio kosong")

    calon: list[tuple[int, int | None, str, str]] = []   # umur, thn, conf, alasan
    ditolak: list[str] = []

    # --- pernyataan umur langsung ---
    for pola, conf, alasan, veto_daftar, jendela, kiri_saja in _POLA_UMUR:
        for m in pola.finditer(teks):
            umur = int(m.group(1))
            if not (AGE_MIN <= umur <= AGE_MAX):
                ditolak.append(f"{m.group(0).strip()!r}: di luar {AGE_MIN}..{AGE_MAX}")
                continue
            if _bagian_angka_lebih_panjang(teks, m.start(1), m.end(1)):
                ditolak.append(f"{m.group(0).strip()!r}: bagian deret angka panjang")
                continue
            veto = _terveto(teks, m.start(), m.end(),
                            veto_daftar, jendela, kiri_saja)
            if veto:
                ditolak.append(f"{m.group(0).strip()!r}: terveto {veto!r}")
                continue
            calon.append((umur, None, conf, alasan))

    # --- tahun lahir eksplisit ---
    for pola, conf, alasan, veto_daftar, jendela, kiri_saja in _POLA_LAHIR:
        for m in pola.finditer(teks):
            tahun = int(m.group(1))
            if not _tahun_masuk_akal(tahun, tahun_acuan):
                ditolak.append(
                    f"{m.group(0).strip()!r}: umur di luar {AGE_MIN}..{AGE_MAX}")
                continue
            if _bagian_angka_lebih_panjang(teks, m.start(1), m.end(1)):
                ditolak.append(f"{m.group(0).strip()!r}: bagian deret angka panjang")
                continue
            veto = _terveto(teks, m.start(), m.end(),
                            veto_daftar, jendela, kiri_saja)
            if veto:
                ditolak.append(f"{m.group(0).strip()!r}: terveto {veto!r}")
                continue
            calon.append((tahun_acuan - tahun, tahun, conf, alasan))

    if not calon:
        alasan = "tidak ada pernyataan umur yang eksplisit"
        if ditolak:
            alasan += "; calon ditolak: " + "; ".join(ditolak[:3])
        return HasilUmur(alasan=alasan)

    # --- bukti bertentangan -> unknown (aturan 3) ---
    umur_unik = {c[0] for c in calon}
    if max(umur_unik) - min(umur_unik) > TOLERANSI_TAHUN:
        return HasilUmur(alasan=(
            "bukti bertentangan: "
            + ", ".join(f"{u} tahun" for u in sorted(umur_unik))))

    # Ambil calon terkuat; `high` menang atas `medium`. Kalau seri, yang
    # membawa tahun lahir menang -- nilainya tidak basi.
    urutan = {"high": 0, "medium": 1, "low": 2}
    umur, tahun_lahir, conf, alasan = sorted(
        calon, key=lambda c: (urutan[c[2]], c[1] is None))[0]

    return HasilUmur(
        umur=umur,
        tahun_lahir=tahun_lahir,
        band=bucket_age(umur),
        source=SUMBER_BIO,
        confidence=conf,
        alasan=alasan,
    )
