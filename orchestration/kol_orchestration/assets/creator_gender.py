"""Asset Gender KREATOR: roster + username/display name -> `creator_gender*`.

    l0_raw.kol_roster_import.influencer_gender          (1 = female, 0 = male)
        -> creator_gender_source = 'roster'
    l2_gold.kol_profile_card.username + display_name
        (<- l1_silver.unified_profile <- l0_raw.ig/tt_profile_apify)
        -> creator_gender_inference.tebak_gender_kreator()
        -> creator_gender_source = 'name_inference'
    => l2_gold.kol_profile_card.creator_gender{,_source,_confidence}

Pola yang sama dengan `creator_age.py`: file sendiri (bukan fitur audiens),
berjalan SETELAH `kol_profile_card`, hanya meng-UPDATE tiga kolom miliknya
sendiri, tidak pernah INSERT baris, dan tidak pernah menyentuh tabel audiens.

URUTAN PRIORITAS
================
    manual           diisi manusia. TIDAK PERNAH ditimpa; disaring sejak SQL_BACA.
    roster           menang kapan pun roster punya kode 0/1 yang valid.
    name_inference   hanya kalau roster tidak punya nilai valid.
    NULL             sisanya -- dan itu tetap mayoritas.

Inference tidak pernah menimpa roster, dan tidak pernah menimpa manual.

KOL BARU
========
"Add New KOL" menulis `l0_raw.ig/tt_profile_apify`, yang dipantau
`l0_raw_new_data_sensor` -> `transform_chain_job` -> `kol_profile_card` ->
asset ini. KOL baru tidak masuk roster, jadi gendernya datang dari
username + display name. Tidak ada scraper atau pipeline baru.

ARTI KODE ROSTER BELUM RESMI
============================
1 = female / 0 = male adalah BUKTI DATA (cocok dengan digit jenis kelamin NIK
15/15 dan 49/51), belum kontrak dari pemilik data. Karena itu confidence roster
'medium', bukan 'high'.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from creator_gender_inference import SUMBER_MANUAL, pilih_gender  # noqa: E402

GROUP = "gold_profile"
_KARTU = AssetKey("kol_profile_card")

# Kode roster per akun. Akun dengan DUA kode berbeda (0 dan 1) dianggap tidak
# punya nilai roster -- saat ini tidak ada, tapi import berikutnya bisa
# membuatnya, dan memilih salah satu berarti menebak.
SQL_ROSTER = """
    SELECT social_account_id, min(btrim(influencer_gender))
      FROM l0_raw.kol_roster_import
     WHERE social_account_id IS NOT NULL
       AND btrim(influencer_gender) IN ('0', '1')
     GROUP BY social_account_id
    HAVING count(DISTINCT btrim(influencer_gender)) = 1
"""

SQL_BACA = """
    SELECT social_account_id, username, display_name
      FROM l2_gold.kol_profile_card
     WHERE creator_gender_source IS DISTINCT FROM %(manual)s
"""

# `IS DISTINCT FROM` menjaga idempotensi: baris yang hasilnya tidak berubah
# tidak ditulis, jadi `updated_at` tidak bergerak tanpa alasan. Baris yang
# dulu punya nilai tapi sekarang tidak lagi dihasilkan ikut DICABUT ke NULL --
# nilai tanpa sumber yang mendukungnya tidak boleh terus menyaring Discovery.
SQL_UPDATE = """
    UPDATE l2_gold.kol_profile_card
       SET creator_gender            = %(gender)s,
           creator_gender_source     = %(source)s,
           creator_gender_confidence = %(confidence)s,
           updated_at                = now()
     WHERE social_account_id = %(sid)s
       AND creator_gender_source IS DISTINCT FROM %(manual)s
       AND (creator_gender            IS DISTINCT FROM %(gender)s
         OR creator_gender_source     IS DISTINCT FROM %(source)s
         OR creator_gender_confidence IS DISTINCT FROM %(confidence)s)
"""


def _jalankan(postgres: PostgresResource) -> Output:
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_ROSTER)
            roster = {sid: kode for sid, kode in cur.fetchall()}

            cur.execute(SQL_BACA, {"manual": SUMBER_MANUAL})
            baris = cur.fetchall()

            ditulis = 0
            per_hasil: Counter = Counter()
            per_alasan_unknown: Counter = Counter()
            for sid, username, display_name in baris:
                hasil = pilih_gender(roster.get(sid), display_name, username)
                per_hasil[(hasil.source or "unknown", hasil.nilai or "unknown")] += 1
                if not hasil.diketahui:
                    per_alasan_unknown[hasil.alasan or "tanpa nama"] += 1
                cur.execute(SQL_UPDATE, {
                    "sid": sid,
                    "gender": hasil.nilai,
                    "source": hasil.source,
                    "confidence": hasil.confidence,
                    "manual": SUMBER_MANUAL,
                })
                ditulis += cur.rowcount or 0

            # Sebaran akhir dibaca dari TABEL, bukan dari hitungan di memori.
            cur.execute("""
                SELECT coalesce(creator_gender_source, 'unknown'),
                       coalesce(creator_gender, 'unknown'), count(*)
                  FROM l2_gold.kol_profile_card GROUP BY 1, 2""")
            di_tabel = {f"{s}/{g}": n for s, g, n in cur.fetchall()}
        conn.commit()
    finally:
        conn.close()

    diketahui = sum(n for (s, _g), n in per_hasil.items() if s != "unknown")
    return Output(
        diketahui,
        metadata={
            "baris_diperiksa": len(baris),
            "roster_valid_di_l0": len(roster),
            "baris_diupdate": ditulis,
            "sebaran_hasil": MetadataValue.json(
                {f"{s}/{g}": n for (s, g), n in sorted(per_hasil.items())}),
            "sebaran_di_tabel": MetadataValue.json(di_tabel),
            "alasan_unknown": MetadataValue.json(dict(per_alasan_unknown)),
            "urutan_prioritas": MetadataValue.text(
                "manual (tidak pernah ditimpa) > roster > name_inference > NULL."),
            "bukan_gender_audience": MetadataValue.text(
                "Asset ini tidak membaca kolom maupun tabel gender audiens, "
                "maupun data follower. Inputnya hanya roster dan nama akun kreator."),
            "mapping_roster_belum_resmi": MetadataValue.text(
                "1 = female, 0 = male: bukti data, belum kontrak pemilik data."),
        },
    )


@asset(
    name="creator_gender",
    group_name=GROUP,
    deps=[_KARTU],
    kinds={"postgres", "python"},
    description=(
        "l2_gold.kol_profile_card.creator_gender* — gender KREATOR (bukan "
        "audiens). Sumber berurut: 'manual' (tidak pernah ditimpa) > 'roster' "
        "(l0_raw.kol_roster_import.influencer_gender, 1=female 0=male — bukti "
        "data, belum resmi) > 'name_inference' (username + display name, aturan "
        "konservatif creator_gender_inference.py) > NULL. Dipakai filter "
        "Discovery dari Brand Profile gender_majority."
    ),
)
def creator_gender(postgres: PostgresResource) -> Output:
    return _jalankan(postgres)


creator_gender_assets = [creator_gender]
