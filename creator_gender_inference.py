"""Gender KREATOR dari username + display name, dengan aturan konservatif.

JANGAN SAMAKAN DENGAN `audience_inference.tebak_gender()`. Fungsi itu menebak
gender PENGIKUT dan dipakai `analisis_follower()` untuk
`feature.*_audience_analysis`. Modul ini menentukan gender ORANG KOL-nya, untuk
`l2_gold.kol_profile_card.creator_gender`. Yang dipakai bersama hanya KAMUS dan
helper normalisasi dari modul audiens (diimpor, tidak disalin, tidak diubah) --
aturan pengambilan keputusannya berbeda, dan memang harus berbeda.

Tidak ada data audiens yang dibaca di sini: tidak ada female_pct/male_pct,
gender_breakdown, maupun follower. Inputnya hanya username dan display name
kreator itu sendiri.

============================================================================
KENAPA ATURANNYA LEBIH KETAT DARI VERSI AUDIENS (Variant B, audit Sept 2026)
============================================================================

Diuji terhadap 2.824 KOL aktif yang punya `kol_roster_import.influencer_gender`
valid (1 = Female, 0 = Male -- BUKTI DATA, belum kontrak resmi pemilik data).
Aturan audiens apa adanya pada username + display name:

    tebakan Female  311   precision 98,1%
    tebakan Male    118   precision 63,6%   <- 43 perempuan ditebak laki-laki

Precision per aturan, dihitung tiap kali aturan menyala:

    sufiks pria (-wan, -anto, -hartono ...)       47,6%   (-wan 3 dari 17)
    token nama pria bukan kata pertama            51,4%   display name
    token nama pria di username                   61,4%
    sapaan pria (mas, mr ...)                     20,0%   (1 dari 5)
    nama depan pria, cocok persis                 72,7%
    aturan Female (nama depan, sufiks, token)     97,7% .. 100%

Pola di balik sufiks/token pria: nama keluarga dan nama ayah bergaya pria
(`... Hartono`, `... Santoso`) juga dipakai perempuan. Jadi:

  * FEMALE boleh keluar dari semua aturan Female yang sudah ada.
  * MALE hanya boleh keluar dari sinyal KUAT: simbol, partikel (`bin`), awalan
    (`muhammad`, `abdul` ...), atau nama depan display name yang cocok persis.
    Sufiks pria, token pria, dan sapaan pria TIDAK PERNAH menghasilkan Male.
  * Bukti yang bertentangan -- satu saja sinyal ke arah lain, sekuat apa pun
    -> unknown.
  * Akun bisnis (penanda bisnis modul audiens) dan akun grup/pasangan
    (`&`, `dan`, `family`, `twins` ...) -> unknown.

Plafon yang perlu diketahui: nama depan pria yang cocok persis sendiri hanya
72,7% benar di data roster, jadi precision Male tidak akan jauh di atas ~75%
tanpa koreksi per nama -- dan koreksi per nama sengaja tidak dilakukan (lihat
aturan 5 di `audience_inference`: tidak ada nilai yang diketik manual per akun).

`unknown` adalah jawaban yang sah dan tetap mayoritas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import audience_inference as _A

#: Nilai `creator_gender_source`, berurut menurut prioritas yang dijaga asset.
SUMBER_MANUAL = "manual"            # diisi manusia; TIDAK PERNAH ditimpa
SUMBER_ROSTER = "roster"            # l0_raw.kol_roster_import.influencer_gender
SUMBER_NAMA = "name_inference"      # modul ini

#: Kode roster -> gender. Bukti data (cocok dengan digit jenis kelamin NIK
#: 15/15 untuk 0 dan 49/51 untuk 1), BUKAN kontrak resmi pemilik data.
ROSTER_KODE = {"0": "male", "1": "female"}

#: Aturan yang boleh menghasilkan Male. Semua aturan Female boleh.
ATURAN_MALE_KUAT = frozenset({"simbol", "partikel", "awalan", "nama_depan"})

#: Penanda grup/pasangan. Dibaca sebagai kata utuh pada display name dan
#: username (pemisah `_`/`.` dianggap spasi).
_RE_GRUP = re.compile(
    r"(&|\+|\b(dan|and|n|x|family|fam|couple|twins?|kembar|bersaudara|sisters?|"
    r"brothers?|squad|team|duo|trio|club)\b)", re.I)


@dataclass(frozen=True)
class HasilGender:
    nilai: str | None = None          # 'female' | 'male' | None (unknown)
    source: str | None = None
    confidence: str | None = None     # high | medium | low
    alasan: str = ""

    @property
    def diketahui(self) -> bool:
        return self.nilai is not None


TIDAK_DIKETAHUI = HasilGender()


def _tampak_grup(display_name: str | None, username: str | None) -> bool:
    teks = f"{display_name or ''} {(username or '').replace('_', ' ').replace('.', ' ')}"
    return bool(_RE_GRUP.search(teks))


def _bukti(display_name: str | None, username: str | None) -> list[tuple[str, str, str, str]]:
    """Semua bukti (nilai, confidence, aturan, alasan). Aturannya sama dengan
    `audience_inference._bukti_gender` tanpa bio, tapi tiap bukti diberi nama
    aturannya supaya keputusan bisa memilih aturan mana yang dipercaya."""
    bukti: list[tuple[str, str, str, str]] = []
    mentah = display_name or ""
    if _A.SIMBOL_PRIA in mentah:
        bukti.append(("male", "high", "simbol", "simbol ♂"))
    if _A.SIMBOL_WANITA in mentah:
        bukti.append(("female", "high", "simbol", "simbol ♀"))

    tok_nama = _A._token(display_name)
    tok_user = _A._token(username)

    for t in tok_nama + tok_user:
        if t in _A.SAPAAN_PRIA:
            bukti.append(("male", "medium", "sapaan", f"sapaan '{t}'"))
        if t in _A.SAPAAN_WANITA:
            bukti.append(("female", "medium", "sapaan", f"sapaan '{t}'"))

    for t in tok_nama + tok_user:
        if t in _A.PARTIKEL_WANITA:
            bukti.append(("female", "high", "partikel", f"partikel '{t}'"))
        elif t in _A.PARTIKEL_PRIA:
            bukti.append(("male", "high", "partikel", f"partikel '{t}'"))

    n_norm = _A._normalisasi(display_name)
    for aw in _A.AWALAN_PRIA:
        if n_norm.startswith(aw.strip()):
            bukti.append(("male", "medium", "awalan", f"awalan '{aw.strip()}'"))
            break
    for aw in _A.AWALAN_WANITA:
        if n_norm.startswith(aw.strip()):
            bukti.append(("female", "medium", "awalan", f"awalan '{aw.strip()}'"))
            break

    if tok_nama:
        d = tok_nama[0]
        if d in _A.NAMA_PRIA:
            bukti.append(("male", "medium", "nama_depan", f"nama depan '{d}'"))
        elif d in _A.NAMA_WANITA:
            bukti.append(("female", "medium", "nama_depan", f"nama depan '{d}'"))

    for t in tok_nama[1:] + tok_user:
        if t in _A.NAMA_PRIA:
            bukti.append(("male", "low", "token", f"token '{t}'"))
        elif t in _A.NAMA_WANITA:
            bukti.append(("female", "low", "token", f"token '{t}'"))

    for t in tok_nama + tok_user:
        if len(t) < 6:
            continue
        if any(t.endswith(s) for s in _A.SUFIKS_WANITA):
            bukti.append(("female", "medium", "sufiks", f"sufiks pada '{t}'"))
        elif any(t.endswith(s) for s in _A.SUFIKS_PRIA):
            bukti.append(("male", "medium", "sufiks", f"sufiks pada '{t}'"))
    return bukti


def tebak_gender_kreator(display_name: str | None, username: str | None) -> HasilGender:
    """Female / Male / unknown untuk SATU kreator, dari nama akunnya sendiri."""
    if not (display_name or username):
        return TIDAK_DIKETAHUI
    if _A._tampak_bisnis(display_name, None, username, None):
        return HasilGender(alasan="akun bisnis")
    if _tampak_grup(display_name, username):
        return HasilGender(alasan="akun grup/pasangan")

    bukti = _bukti(display_name, username)
    if not bukti:
        return HasilGender(alasan="tidak ada sinyal")
    if len({b[0] for b in bukti}) > 1:
        return HasilGender(alasan="bukti bertentangan")

    boleh = [b for b in bukti if b[0] == "female" or b[2] in ATURAN_MALE_KUAT]
    if not boleh:
        return HasilGender(alasan="hanya sinyal pria yang lemah")
    nilai, conf, _aturan, alasan = max(boleh, key=lambda b: _A._KUAT[b[1]])
    return HasilGender(nilai=nilai, source=SUMBER_NAMA, confidence=conf, alasan=alasan)


def gender_roster(kode: str | None) -> str | None:
    """`influencer_gender` roster -> 'female'/'male', atau None bila kosong/invalid."""
    return ROSTER_KODE.get((kode or "").strip())


#: Confidence untuk jalur roster: nilainya diisi manusia, tapi arti kode 0/1
#: hanya didukung bukti data (lihat ROSTER_KODE), jadi tidak 'high'.
CONFIDENCE_ROSTER = "medium"


def pilih_gender(roster: str | None, display_name: str | None,
                 username: str | None) -> HasilGender:
    """Urutan prioritas (baris `manual` sudah disaring pemanggil):
    roster > name_inference > unknown. Inference tidak pernah menimpa roster."""
    g = gender_roster(roster)
    if g is not None:
        return HasilGender(nilai=g, source=SUMBER_ROSTER, confidence=CONFIDENCE_ROSTER,
                           alasan=f"roster influencer_gender={roster.strip()}")
    return tebak_gender_kreator(display_name, username)
