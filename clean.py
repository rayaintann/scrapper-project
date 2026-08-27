"""Aturan pembersihan teks untuk layer harmonisasi.

Dipisah dari transform.py karena sifatnya beda: transform.py memetakan bentuk
data dari Apify, sedangkan modul ini menentukan seperti apa nilai yang sudah
"bersih" menurut standar kita.
"""

import re

# Karakter tak kasat mata yang sering menempel di bio Instagram. NBSP diganti
# spasi biasa; sisanya dibuang karena tidak membawa makna.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_NBSP = {ord(" "): " ", ord(" "): " "}

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")
# Cocokkan skema apa pun, termasuk yang tanpa '//' seperti mailto: dan tel:.
_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_EDGE_JUNK = "<>()[]{}\"' \t,;.|"


def _strip_invisibles(value: str) -> str:
    return value.translate(_ZERO_WIDTH).translate(_NBSP)


def clean_line(value) -> str | None:
    """Untuk nilai satu baris seperti nama tampilan.

    Newline dan spasi berlebih diratakan jadi satu spasi. String kosong menjadi
    None supaya kolomnya NULL, bukan '' — dua hal itu beda arti saat dianalisis.
    """
    if not isinstance(value, str):
        return None
    text = _strip_invisibles(value).replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_SPACE.sub(" ", text.replace("\n", " ")).strip()
    return text or None


def clean_text(value) -> str | None:
    """Untuk teks panjang seperti biography.

    Baris baru dipertahankan karena membawa struktur (kontak, daftar), tapi
    dirapikan: maksimal satu baris kosong berturut-turut, tidak ada spasi
    menggantung di ujung baris.
    """
    if not isinstance(value, str):
        return None
    text = _strip_invisibles(value).replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_SPACE.sub(" ", text)
    text = _TRAILING_SPACE.sub("\n", text)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip() or None


def clean_website(value) -> str | None:
    """Kembalikan URL yang punya skema, atau None kalau tidak masuk akal.

    Instagram menyimpan sebagian tautan tanpa skema ('linktr.ee/foo'), yang
    membuat kolomnya tidak bisa langsung dipakai sebagai href.
    """
    if not isinstance(value, str):
        return None
    # Tanda kurung, kutip, dan tanda baca di ujung sering ikut terbawa dari bio,
    # dan bisa bertumpuk ('<https://x.com>,'), jadi dikupas sampai habis.
    text = _strip_invisibles(value).strip(_EDGE_JUNK)
    if not text:
        return None
    if _URL_SCHEME.match(text):
        return text
    # Tanpa skema: hanya diterima kalau bentuknya masih seperti domain.
    host = text.split("/", 1)[0]
    if "." in host and " " not in host and host.count(".") <= 4:
        return f"https://{text}"
    return None
