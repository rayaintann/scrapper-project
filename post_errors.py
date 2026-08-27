"""Klasifikasi kegagalan scraping POST/VIDEO menjadi kode yang bisa diaudit.

Dipakai bersama Instagram (`apify/instagram-scraper`) dan TikTok
(`clockworks/tiktok-scraper`). Actor keduanya melaporkan kegagalan dengan cara
yang berbeda:

- Instagram mengembalikan **item error eksplisit** di dalam dataset, mis.
  ``{"error": "not_found", "errorDescription": "Post does not exist"}``.
  Item seperti ini tidak boleh masuk L0 sebagai post.
- TikTok umumnya tidak mengembalikan item error; akun yang gagal cukup **tidak
  muncul** di hasil, walau status run tetap SUCCEEDED.

Keduanya harus berakhir sebagai satu baris `public.scheduler_logs` per akun,
dengan kode yang sama-sama bisa dibaca.
"""

from __future__ import annotations

import re
from typing import Any

# --- kode status per akun ---------------------------------------------------
# Nilai ini masuk ke public.scheduler_logs.status apa adanya.

SUCCESS = "success"
NOT_FOUND = "not_found"
PRIVATE_UNAVAILABLE = "private_unavailable"
RATE_LIMIT = "rate_limit"
TIMEOUT = "timeout"
ACTOR_ERROR = "actor_error"
UNKNOWN = "unknown"

ERROR_CODES = (
    NOT_FOUND,
    PRIVATE_UNAVAILABLE,
    RATE_LIMIT,
    TIMEOUT,
    ACTOR_ERROR,
    UNKNOWN,
)
ALL_CODES = (SUCCESS,) + ERROR_CODES

# Pola dicek berurutan; yang pertama cocok yang dipakai. Urutannya penting:
# "not found" harus dites sebelum pola umum, dan rate limit sebelum actor_error
# supaya 429 tidak tertelan sebagai error actor biasa.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (NOT_FOUND, re.compile(
        r"not[\s_-]?found|does\s+not\s+exist|no\s+such|tidak\s+ditemukan|"
        r"user\s+not\s+exist|page\s+not\s+found|\b404\b", re.I)),
    (PRIVATE_UNAVAILABLE, re.compile(
        r"private|restricted|unavailable|forbidden|not\s+accessible|"
        r"login\s+required|age[\s_-]?restricted|blocked|banned|suspended|"
        r"\b403\b", re.I)),
    (RATE_LIMIT, re.compile(
        r"rate[\s_-]?limit|too\s+many\s+requests|throttl|quota\s+exceeded|"
        r"\b429\b", re.I)),
    (TIMEOUT, re.compile(
        r"timed?\s*out|timeout|deadline\s+exceeded|read\s+timeout", re.I)),
    (ACTOR_ERROR, re.compile(
        r"actor|apify|dataset|run\s+(failed|aborted|selesai)|"
        r"ApifyRunError|Unauthorized|InvalidRequest|\b5\d\d\b", re.I)),
)

# Field yang mungkin memuat keterangan error, diperiksa berurutan.
_ERROR_KEYS = ("error", "errorDescription", "error_description", "errorMessage", "message")


def _text_of(value: Any) -> str:
    """Ubah nilai apa pun jadi teks yang bisa dicocokkan pola."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_text_of(v) for v in value)
    if isinstance(value, dict):
        return " ".join(_text_of(v) for v in value.values())
    return str(value)


def classify_text(text: str | None) -> str:
    """Petakan satu potongan teks error ke salah satu kode.

    Teks kosong dianggap `unknown`, bukan `success` — pemanggil yang tahu
    sesuatu berhasil tidak perlu lewat sini.
    """
    if not text or not text.strip():
        return UNKNOWN
    for code, pattern in _PATTERNS:
        if pattern.search(text):
            return code
    return UNKNOWN


def is_error_item(item: dict) -> bool:
    """Apakah item ini laporan kegagalan, bukan post/video yang sah.

    Dua penanda:
      1. ada field error yang terisi, atau
      2. tidak ada satu pun id konten — tanpa id, baris L0 tidak bisa dibentuk.
    """
    if not isinstance(item, dict):
        return True
    for key in _ERROR_KEYS[:3]:
        if _text_of(item.get(key)).strip():
            return True
    # `id` dipakai Instagram maupun TikTok sebagai id konten.
    return not _text_of(item.get("id")).strip()


def error_text(item: dict) -> str:
    """Gabungan keterangan error dari satu item, untuk disimpan apa adanya."""
    if not isinstance(item, dict):
        return "item bukan objek JSON"
    parts = []
    for key in _ERROR_KEYS:
        value = _text_of(item.get(key)).strip()
        if value and value not in parts:
            parts.append(value)
    return " | ".join(parts)


def classify_item(item: dict) -> tuple[str, str]:
    """Kode dan pesan untuk satu item error dari dataset actor.

    Mengembalikan `(kode, pesan)`. Untuk item yang sebenarnya sah, pemanggil
    tidak boleh memanggil fungsi ini — cek `is_error_item` lebih dulu.
    """
    pesan = error_text(item)
    if not pesan:
        pesan = "item tidak membawa id konten dan tidak menyebutkan error"
    return classify_text(pesan), pesan


def classify_exception(exc: BaseException) -> tuple[str, str]:
    """Kode dan pesan untuk kegagalan level batch/run."""
    pesan = f"{type(exc).__name__}: {exc}".strip()
    code = classify_text(pesan)
    if code == UNKNOWN:
        # Exception selalu berasal dari jalur actor/HTTP, jadi lebih informatif
        # dijatuhkan ke actor_error daripada dibiarkan unknown.
        code = ACTOR_ERROR
    return code, pesan


def classify_missing(reason: str | None = None) -> tuple[str, str]:
    """Kode untuk username yang dikirim tapi tidak muncul di hasil.

    Tidak ada item error, tidak ada exception — actor hanya diam. Penyebabnya
    tidak bisa dipastikan dari data yang ada, jadi sengaja `unknown` dan bukan
    ditebak sebagai `not_found`.
    """
    pesan = reason or (
        "username dikirim ke actor tapi tidak muncul di hasil dan tidak ada "
        "item error; penyebab tidak bisa dipastikan"
    )
    if reason:
        code = classify_text(reason)
        if code != UNKNOWN:
            return code, pesan
    return UNKNOWN, pesan
