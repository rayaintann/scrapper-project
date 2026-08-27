"""Menulis hasil scrape follower ke l0_raw.{ig,tt}_followers_apify.

Satu baris per follower per akun KOL per tanggal scrape.

============================================================================
KENAPA MAPPER-NYA DEFENSIF
============================================================================

Kedua actor follower tidak menerbitkan skema output yang stabil, dan nama
fieldnya berbeda antar-actor bahkan antar-versi (`pk` vs `id` vs `userId`,
`full_name` vs `fullName` vs `nickname`). Kalau mapper-nya menuntut satu nama
persis, satu perubahan kecil di actor akan membuat seluruh kolom jadi NULL
diam-diam -- data terlihat masuk, isinya kosong.

Karena itu tiap kolom dibaca lewat `_ambil()` yang mencoba beberapa nama
kandidat, dan `raw_payload` SELALU menyimpan item aslinya utuh. Kalau nanti
ternyata ada field yang terlewat, datanya masih ada di L0 dan bisa dipetakan
ulang tanpa scrape ulang -- ini alasan utama layer L0 raw ada.

============================================================================
DEDUP -- KENAPA DI SINI, BUKAN DI HARMONIZATION
============================================================================

Tabel L0 sengaja tidak punya UNIQUE (lihat migration 023: L0 menyimpan apa
adanya). Tapi menulis dua kali untuk (akun, follower, tanggal) yang sama akan
menggandakan hitungan di seluruh layer di atasnya.

Jadi sebelum INSERT, baris yang sudah ada untuk kombinasi
(social_account_id, source_actor, tanggal scrape) DIHAPUS lebih dulu. Efeknya:
menjalankan ulang scrape di hari yang sama MENGGANTI, bukan menumpuk. Ini yang
membuat seluruh alur bisa diulang tanpa duplikat.

Penghapusan dibatasi ke tanggal scrape yang sama supaya riwayat hari lain tidak
ikut hilang.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

TABEL = {
    "instagram": "l0_raw.ig_followers_apify",
    "tiktok": "l0_raw.tt_followers_apify",
}

# Nama kolom id follower dan nama tampilan berbeda antar dua tabel L0.
KOLOM_ID = {"instagram": "followers_ig_id", "tiktok": "followers_tt_id"}
KOLOM_NAMA = {"instagram": "full_name", "tiktok": "display_name"}
KOLOM_FOTO = {"instagram": "profile_pic_url", "tiktok": "avatar_url"}


@dataclass
class StatsL0:
    akun: str = ""
    platform: str = ""
    dibaca: int = 0
    dihapus: int = 0
    ditulis: int = 0
    dilewati_tanpa_id: int = 0
    duplikat_dalam_batch: int = 0


def _ambil(item: dict, *kandidat: str) -> Any:
    """Kembalikan nilai pertama yang ada dan tidak kosong."""
    for k in kandidat:
        if k in item:
            v = item[k]
            if v not in (None, "", [], {}):
                return v
        # dukung path bersarang sederhana "a.b"
        if "." in k:
            cur: Any = item
            for bagian in k.split("."):
                if isinstance(cur, dict) and bagian in cur:
                    cur = cur[bagian]
                else:
                    cur = None
                    break
            if cur not in (None, "", [], {}):
                return cur
    return None


def _str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in {"true", "false"}:
        return v.strip().lower() == "true"
    return None


def _links(v: Any) -> str | None:
    """social_links bertipe text di kedua tabel L0, jadi list/dict di-JSON-kan."""
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    try:
        return json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


def petakan(item: dict, platform: str) -> dict[str, Any]:
    """Ubah satu item actor jadi dict kolom L0. Tidak menyentuh database.

    BENTUK ITEM SANGAT BERBEDA ANTAR PLATFORM -- diverifikasi lewat smoke test,
    bukan dari dokumentasi actor:

      Instagram (apify/instagram-followers-following-scraper)
        datar, dan MISKIN: fullName, username, userId, isPrivate, isVerified,
        profilePicUrl. TIDAK ADA bio, followers_count, maupun following_count.

      TikTok (clockworks/tiktok-followers-scraper)
        bersarang di `authorMeta`, dan KAYA: nickName, signature (bio), fans,
        following, verified, privateAccount, bioLink.

    Konsekuensinya ada di layer inference: bio adalah satu-satunya sumber untuk
    lokasi dan interest, jadi kedua dimensi itu praktis hanya bisa diisi untuk
    TikTok. Ini batas DATA, bukan batas kode.
    """
    # TikTok membungkus profil follower di authorMeta; Instagram tidak membungkus.
    src = item.get("authorMeta") if isinstance(item.get("authorMeta"), dict) else item

    follower_id = _str(_ambil(src, "id", "pk", "userId", "user_id", "secUid", "fbid"))
    username = _str(_ambil(src, "username", "userName", "uniqueId", "handle", "name"))
    nama = _str(_ambil(src, "fullName", "full_name", "nickName", "nickname",
                       "displayName", "title"))
    bio = _str(_ambil(src, "biography", "bio", "signature", "description", "about"))
    foto = _str(_ambil(src, "profilePicUrl", "profile_pic_url", "avatar",
                       "avatarUrl", "originalAvatarUrl", "avatarMedium",
                       "avatarThumb", "profilePicture"))
    return {
        "follower_id": follower_id,
        "username": username,
        "nama": nama,
        "bio": bio,
        "foto": foto,
        "is_private": _bool(_ambil(src, "isPrivate", "privateAccount", "private",
                                   "secret")),
        "is_verified": _bool(_ambil(src, "isVerified", "verified")),
        "is_business": _bool(_ambil(src, "isBusinessAccount", "is_business_account",
                                    "isBusiness", "ttSeller", "commerceUser")),
        # TikTok memakai `fans`/`following`; Instagram tidak mengirim keduanya.
        "followers_count": _int(_ambil(src, "followersCount", "followers_count",
                                       "followerCount", "fans",
                                       "edge_followed_by.count")),
        "following_count": _int(_ambil(src, "followingCount", "following_count",
                                       "followsCount", "following")),
        "email": _str(_ambil(src, "email", "publicEmail", "businessEmail")),
        "phones": _str(_ambil(src, "phone", "phones", "contactPhoneNumber",
                              "publicPhoneNumber")),
        "social_links": _links(_ambil(src, "socialLinks", "social_links",
                                      "externalUrl", "bioLink", "links")),
    }


def simpan(
    conn,
    platform: str,
    social_account_id: str,
    username_kol: str,
    items: Sequence[dict],
    source_actor: str,
    scraped_at: datetime,
    scrape_run_id: str | None = None,
    commit: bool = True,
) -> StatsL0:
    """Tulis follower satu akun KOL ke tabel L0 platform-nya.

    Menghapus lebih dulu baris untuk (akun, actor, tanggal scrape) yang sama,
    jadi menjalankan ulang di hari yang sama MENGGANTI dan tidak menumpuk.
    """
    if platform not in TABEL:
        raise ValueError(f"platform tidak dikenal: {platform!r}")

    tabel = TABEL[platform]
    kol_id = KOLOM_ID[platform]
    kol_nama = KOLOM_NAMA[platform]
    kol_foto = KOLOM_FOTO[platform]

    st = StatsL0(akun=username_kol, platform=platform, dibaca=len(items))
    run_id = scrape_run_id or str(uuid.uuid4())
    tgl: date = scraped_at.date()
    sekarang = datetime.now(timezone.utc)

    with conn.cursor() as cur:
        # 1. Buang hasil sebelumnya untuk akun+actor+tanggal yang sama.
        cur.execute(
            f"""DELETE FROM {tabel}
                 WHERE social_account_id = %s
                   AND source_actor      = %s
                   AND (scraped_at AT TIME ZONE 'UTC')::date = %s""",
            (social_account_id, source_actor, tgl),
        )
        st.dihapus = cur.rowcount or 0

        # 2. Dedup di dalam batch: actor kadang mengirim follower yang sama dua kali.
        terlihat: set[str] = set()
        baris: list[tuple] = []
        for item in items:
            m = petakan(item, platform)
            kunci = m["follower_id"] or m["username"]
            if not kunci:
                st.dilewati_tanpa_id += 1
                continue
            if kunci in terlihat:
                st.duplikat_dalam_batch += 1
                continue
            terlihat.add(kunci)
            baris.append((
                social_account_id, run_id, m["follower_id"], m["username"], m["nama"],
                m["is_private"], m["is_verified"], m["foto"], m["is_business"],
                m["followers_count"], m["following_count"], m["bio"],
                m["email"], m["phones"], m["social_links"],
                json.dumps(item, ensure_ascii=False), scraped_at, source_actor, sekarang,
            ))

        if baris:
            # `is_bussiness_account` memang salah eja di schema L0 (kedua tabel).
            # Ditulis persis seperti di database -- bukan typo di sini.
            sql = f"""
                INSERT INTO {tabel} (
                    social_account_id, scrape_run_id, {kol_id}, username, {kol_nama},
                    is_private, is_verified, {kol_foto}, is_bussiness_account,
                    followers_count, following_count, bio,
                    email, phones, social_links,
                    raw_payload, scraped_at, source_actor, insert_at
                ) VALUES ({', '.join(['%s'] * 19)})"""
            cur.executemany(sql, baris)
            st.ditulis = len(baris)

    if commit:
        conn.commit()
    return st
