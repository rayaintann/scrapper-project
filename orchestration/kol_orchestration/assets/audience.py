"""Asset audiens: dari daftar follower L1 ke Feature, lalu ke L2 Gold.

    unified_follower (L1)
        -> audience_feature   -> feature.{ig,tt}_audience_analysis   (SCRUM-)
        -> audience_gold      -> l2_gold.audience_{demographics,geo,interest}_daily

============================================================================
KENAPA JALUR INI ADA, DAN BEDANYA DENGAN unified_audience
============================================================================

Ada DUA jalur berbeda menuju tabel `l2_gold.audience_*`, dan keduanya sah:

  A. TERUKUR   l0_raw.ig_profile_official.demographics_{age,gender,country,city}
               -> l0_harmonization.instagram_audience
               -> l1_silver.unified_audience
               Sumbernya Instagram Insights API. Angkanya adalah demografi
               audiens yang SEBENARNYA, dilaporkan platform. Saat ini 0 baris --
               butuh business account + token.

  B. DITURUNKAN (jalur ini)
               l1_silver.unified_follower -> aturan di audience_inference.py
               Sumbernya daftar follower. Gender/lokasi/interest TIDAK ada di
               data; ketiganya diturunkan dari `full_name` dan `bio`.

Jalur B TIDAK menyentuh `unified_audience` sama sekali. Alasannya: tabel itu
adalah representasi L1 dari data Insights yang terukur, dan mencampur hasil
turunan ke sana akan membuat keduanya tidak bisa dibedakan lagi di hilir.

Yang membedakan keduanya di L2 adalah kolom `confidence`. Jalur ini SELALU
menulis awalan `inferred_`, jadi satu query bisa memisahkan mana yang diukur
dan mana yang diturunkan:

    inferred_high    -- bukti tidak ambigu (emoji bendera -> kode ISO)
    inferred_medium  -- kecocokan leksikon kuat (nama depan persis di kamus)
    inferred_low     -- kecocokan lemah (kata kunci di posisi bukan utama)

Tanpa awalan itu, angka turunan akan terbaca sebagai angka Insights begitu
kedua jalur sama-sama terisi -- kesalahan yang tidak bisa diperbaiki di hilir.

============================================================================
KEPUTUSAN DESAIN
============================================================================

1. `unknown` IKUT DISIMPAN, TIDAK DIBUANG.
   Kalau hanya gender yang terdeteksi yang disimpan, pembaca L2 akan melihat
   "male 126, female 88" dan menyimpulkan audiens Instagram terbagi 59/41.
   Padahal 1.086 dari 1.300 tidak diketahui. Menyimpan `unknown` sebagai baris
   tersendiri membuat penyebutnya terlihat dan mustahil disalahbaca.

2. GRAIN FEATURE = (social_account_id), MENGIKUTI SAUDARANYA.
   Sama seperti `feature.ig_engagement_analysis`. Constraint UNIQUE-nya
   ditambahkan migration 026 -- tanpa itu asset ini tidak bisa idempoten.

3. L2 DIBANGUN DARI FEATURE, BUKAN MENGHITUNG ULANG DARI L1.
   Prinsip yang sama dipakai `kol_metric_monthly` terhadap `kol_metric_daily`:
   kalau rumusnya ditulis dua kali, cepat atau lambat kedua angkanya berbeda.
   Feature memegang breakdown jsonb; L2 hanya memekarkannya jadi baris.

4. KOLOM TANPA SUMBER TIDAK DITULIS SAMA SEKALI.
   `age_gender_breakdown`  -- tidak ada satu pun sinyal umur di data follower.
   `active_hours_heatmap`  -- butuh waktu aktivitas, follower tidak punya.
   `avg_reach`, `cpe`, `emv` -- butuh reach/biaya kampanye, di luar jalur ini.
   Semuanya dibiarkan NULL, mengikuti pola "kolom blocked" di gold.py.

5. `audience_date` DARI `unified_follower.date`, BUKAN tanggal hari ini.
   Tanggal itu menandai kapan follower-nya diambil. Memakai `current_date`
   akan membuat rerun besok menghasilkan baris baru untuk data yang sama --
   duplikat yang menyamar sebagai deret waktu.

6. UPSERT DENGAN PENJAGA `IS DISTINCT FROM`, konsisten dengan seluruh L2.
   Ditambah penghapusan baris L2 yang sudah tidak lagi dihasilkan untuk
   (akun, tanggal) yang sama -- lihat komentar di `_tulis_gold`.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

# audience_inference.py ada di root project, satu level di atas folder
# orchestration/. Ditambahkan ke sys.path supaya asset ini bisa memakainya
# tanpa menduplikasi aturan inferensi ke dalam paket Dagster.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from audience_inference import analisis_follower, skor_kualitas  # noqa: E402

GROUP = "audience"
_FOLLOWER = AssetKey("unified_follower")

TABEL_FEATURE = {"instagram": "feature.ig_audience_analysis",
                 "tiktok": "feature.tt_audience_analysis"}

SQL_FOLLOWER = """
    SELECT f.social_account_id,
           pl.key                AS platform,
           f.date,
           f.full_name, f.bio, f.username,
           f.is_private, f.is_verified,
           f.followers_count, f.following_count,
           f.profile_pic_url, f.social_links
    FROM l1_silver.unified_follower f
    JOIN public.platforms pl ON pl.id = f.platform_id
    WHERE f.social_account_id IS NOT NULL
"""


def _kunci_confidence(level: str) -> str:
    """Beri awalan `inferred_` supaya turunan tidak tertukar dengan Insights."""
    return f"inferred_{level}"


def _modus_confidence(levels: list[str]) -> str:
    """Confidence wakil untuk satu ember agregat.

    Dipilih level TERLEMAH yang menyumbang, bukan yang terkuat atau yang paling
    sering. Satu ember berisi bukti campuran, dan melaporkannya sebagai `high`
    karena kebetulan mayoritas buktinya kuat akan melebih-lebihkan keyakinan.
    Melaporkan yang terlemah membuat angkanya tidak pernah terbaca lebih pasti
    daripada bukti terburuk yang menyusunnya.
    """
    urutan = {"low": 0, "medium": 1, "high": 2}
    if not levels:
        return "low"
    return min(levels, key=lambda x: urutan.get(x, 0))


# ---------------------------------------------------------------------------
# Feature
# ---------------------------------------------------------------------------
def _hitung_per_akun(baris: list[tuple]) -> dict:
    """Jalankan inferensi untuk semua follower satu akun, lalu agregasi."""
    gender: Counter = Counter()
    gender_conf: dict[str, list[str]] = {}
    negara: Counter = Counter()
    negara_conf: dict[str, list[str]] = {}
    kota: Counter = Counter()
    kota_conf: dict[str, list[str]] = {}
    minat: Counter = Counter()
    minat_conf: dict[str, list[str]] = {}

    followers_untuk_skor = []

    for r in baris:
        (_sid, _plat, _tgl, full_name, bio, username,
         is_private, is_verified, fc, fg, pic, links) = r

        # social_links bertipe jsonb; inference bekerja pada teks.
        teks_links = None if links is None else str(links)
        h = analisis_follower(full_name, bio, username, teks_links)

        gender[h.gender.nilai] += 1
        gender_conf.setdefault(h.gender.nilai, []).append(h.gender.confidence)

        negara[h.negara.nilai] += 1
        negara_conf.setdefault(h.negara.nilai, []).append(h.negara.confidence)

        if h.kota:
            kota[h.kota.nilai] += 1
            kota_conf.setdefault(h.kota.nilai, []).append(h.kota.confidence)

        if h.interests:
            for i in h.interests:
                minat[i.nilai] += 1
                minat_conf.setdefault(i.nilai, []).append(i.confidence)
        else:
            minat["unknown"] += 1
            minat_conf.setdefault("unknown", []).append("high")

        followers_untuk_skor.append({
            "full_name": full_name, "username": username, "bio": bio,
            "is_private": is_private, "is_verified": is_verified,
            "followers_count": fc, "following_count": fg,
            "profile_pic_url": pic,
        })

    return {
        "n": len(baris),
        "gender": dict(gender), "gender_conf": gender_conf,
        "negara": dict(negara), "negara_conf": negara_conf,
        "kota": dict(kota), "kota_conf": kota_conf,
        "minat": dict(minat), "minat_conf": minat_conf,
        "skor": skor_kualitas(followers_untuk_skor),
    }


def _jalankan_feature(postgres: PostgresResource) -> Output:
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_FOLLOWER)
            semua = cur.fetchall()

            if not semua:
                conn.rollback()
                return Output(0, metadata={
                    "baris_ditulis": 0,
                    "catatan": MetadataValue.text(
                        "l1_silver.unified_follower kosong — tidak ada yang "
                        "bisa dianalisis. Bukan kegagalan."),
                })

            # Kelompokkan per (akun, platform).
            per_akun: dict[tuple, list] = {}
            for r in semua:
                per_akun.setdefault((r[0], r[1]), []).append(r)

            ditulis = {"instagram": 0, "tiktok": 0}
            ringkas = {}
            for (sid, plat), baris in per_akun.items():
                agg = _hitung_per_akun(baris)
                tabel = TABEL_FEATURE[plat]
                skor = agg["skor"]

                # top_interest: urut menurun, `unknown` ikut supaya penyebut jelas.
                top = sorted(agg["minat"].items(), key=lambda x: (-x[1], x[0]))
                top_json = [{"interest": k, "count": v} for k, v in top]

                cur.execute(
                    f"""
                    INSERT INTO {tabel} (
                        social_account_id,
                        audience_quality_score, authenticity_score,
                        follower_quality_score,
                        gender_breakdown, top_interest, geo_distribution,
                        created_at, updated_at
                        -- SENGAJA tidak disebut (tetap NULL):
                        -- age_gender_breakdown, active_hours_heatmap,
                        -- avg_reach, cpe, emv
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                              now(), now())
                    ON CONFLICT (social_account_id) DO UPDATE SET
                        audience_quality_score = EXCLUDED.audience_quality_score,
                        authenticity_score     = EXCLUDED.authenticity_score,
                        follower_quality_score = EXCLUDED.follower_quality_score,
                        gender_breakdown       = EXCLUDED.gender_breakdown,
                        top_interest           = EXCLUDED.top_interest,
                        geo_distribution       = EXCLUDED.geo_distribution,
                        updated_at             = now()
                    WHERE {tabel.split('.')[1]}.audience_quality_score
                              IS DISTINCT FROM EXCLUDED.audience_quality_score
                       OR {tabel.split('.')[1]}.authenticity_score
                              IS DISTINCT FROM EXCLUDED.authenticity_score
                       OR {tabel.split('.')[1]}.follower_quality_score
                              IS DISTINCT FROM EXCLUDED.follower_quality_score
                       OR {tabel.split('.')[1]}.gender_breakdown
                              IS DISTINCT FROM EXCLUDED.gender_breakdown
                       OR {tabel.split('.')[1]}.top_interest
                              IS DISTINCT FROM EXCLUDED.top_interest
                       OR {tabel.split('.')[1]}.geo_distribution
                              IS DISTINCT FROM EXCLUDED.geo_distribution
                    """,
                    (sid, skor["audience_quality_score"], skor["authenticity_score"],
                     skor["follower_quality_score"],
                     json.dumps(agg["gender"], ensure_ascii=False),
                     json.dumps(top_json, ensure_ascii=False),
                     json.dumps({"country": agg["negara"], "city": agg["kota"]},
                                ensure_ascii=False)),
                )
                ditulis[plat] += 1
                ringkas[str(sid)] = agg

            cur.execute("SELECT count(*) FROM feature.ig_audience_analysis")
            n_ig = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM feature.tt_audience_analysis")
            n_tt = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    total_gender_known = sum(
        v for a in ringkas.values() for k, v in a["gender"].items() if k != "unknown")
    total_follower = sum(a["n"] for a in ringkas.values())

    return Output(
        n_ig + n_tt,
        metadata={
            "akun_diproses": len(ringkas),
            "follower_dianalisis": total_follower,
            "baris_ig_audience_analysis": n_ig,
            "baris_tt_audience_analysis": n_tt,
            "gender_terdeteksi": total_gender_known,
            "gender_unknown": total_follower - total_gender_known,
            "kolom_sengaja_null": MetadataValue.text(
                "age_gender_breakdown (tidak ada sinyal umur di data follower); "
                "active_hours_heatmap (tidak ada waktu aktivitas); "
                "avg_reach, cpe, emv (butuh reach/biaya kampanye)."),
        },
    )


# ---------------------------------------------------------------------------
# L2 Gold
# ---------------------------------------------------------------------------
def _tulis_gold(postgres: PostgresResource) -> Output:
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(SQL_FOLLOWER)
            semua = cur.fetchall()
            if not semua:
                conn.rollback()
                return Output(0, metadata={"baris_ditulis": 0, "catatan":
                              MetadataValue.text("unified_follower kosong.")})

            per_akun: dict[tuple, list] = {}
            for r in semua:
                per_akun.setdefault((r[0], r[1], r[2]), []).append(r)

            n_demo = n_geo = n_int = 0
            n_basi = 0

            for (sid, plat, tgl), baris in per_akun.items():
                agg = _hitung_per_akun(baris)

                # BUANG BARIS BASI LEBIH DULU.
                #
                # Upsert saja tidak cukup saat aturan inferensi diperbarui:
                # kunci dimensi bisa HILANG dari hasil yang baru. Contoh nyata --
                # setelah aturan awalan-nama dibuang, beberapa negara (BR) dan
                # sejumlah gender tidak lagi dihasilkan. Tanpa penghapusan ini,
                # baris lamanya tetap berdiri dengan angka versi lama dan
                # tercampur dengan angka versi baru.
                #
                # Dibatasi ke (akun, platform, tanggal) yang sedang ditulis,
                # jadi riwayat tanggal lain tidak ikut terhapus.
                cur.execute("""
                    DELETE FROM l2_gold.audience_demographics_daily
                    WHERE social_account_id=%s AND platform=%s AND audience_date=%s
                      AND audience_type='gender' AND dimension_key <> ALL(%s)""",
                    (sid, plat, tgl, list(agg["gender"].keys())))
                n_basi += cur.rowcount or 0

                # Dihapus per geo_level dengan array teks biasa. Membandingkan
                # baris `(geo_level, geo_key)` terhadap array record gagal di
                # Postgres ("cannot compare dissimilar column types ... and
                # unknown") karena tipe elemen array tidak bisa disimpulkan dari
                # parameter. Dua query sederhana lebih murah daripada cast manual.
                for level, kunci in (("country", list(agg["negara"].keys())),
                                     ("city", list(agg["kota"].keys()))):
                    cur.execute("""
                        DELETE FROM l2_gold.audience_geo_daily
                        WHERE social_account_id=%s AND platform=%s
                          AND audience_date=%s AND geo_level=%s
                          AND geo_key <> ALL(%s::varchar[])""",
                        (sid, plat, tgl, level, kunci or [""]))
                    n_basi += cur.rowcount or 0

                cur.execute("""
                    DELETE FROM l2_gold.audience_interest_daily
                    WHERE social_account_id=%s AND platform=%s AND audience_date=%s
                      AND interest_key <> ALL(%s)""",
                    (sid, plat, tgl, list(agg["minat"].keys())))
                n_basi += cur.rowcount or 0

                # --- demografi (gender) ---
                for kunci, jml in agg["gender"].items():
                    conf = _kunci_confidence(
                        _modus_confidence(agg["gender_conf"].get(kunci, [])))
                    cur.execute("""
                        INSERT INTO l2_gold.audience_demographics_daily (
                            social_account_id, platform, audience_date,
                            audience_type, dimension_key, audience_count,
                            confidence, created_at, updated_at)
                        VALUES (%s,%s,%s,'gender',%s,%s,%s,now(),now())
                        ON CONFLICT (social_account_id, platform, audience_date,
                                     audience_type, dimension_key)
                        DO UPDATE SET audience_count = EXCLUDED.audience_count,
                                      confidence     = EXCLUDED.confidence,
                                      updated_at     = now()
                        WHERE audience_demographics_daily.audience_count
                                  IS DISTINCT FROM EXCLUDED.audience_count
                           OR audience_demographics_daily.confidence
                                  IS DISTINCT FROM EXCLUDED.confidence
                    """, (sid, plat, tgl, kunci, jml, conf))
                    n_demo += 1

                # --- geo: negara lalu kota, dua geo_level di tabel yang sama ---
                for level, sumber, conf_src in (
                    ("country", agg["negara"], agg["negara_conf"]),
                    ("city", agg["kota"], agg["kota_conf"]),
                ):
                    for kunci, jml in sumber.items():
                        conf = _kunci_confidence(
                            _modus_confidence(conf_src.get(kunci, [])))
                        cur.execute("""
                            INSERT INTO l2_gold.audience_geo_daily (
                                social_account_id, platform, audience_date,
                                geo_level, geo_key, audience_count,
                                confidence, created_at, updated_at)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,now(),now())
                            ON CONFLICT (social_account_id, platform,
                                         audience_date, geo_level, geo_key)
                            DO UPDATE SET audience_count = EXCLUDED.audience_count,
                                          confidence     = EXCLUDED.confidence,
                                          updated_at     = now()
                            WHERE audience_geo_daily.audience_count
                                      IS DISTINCT FROM EXCLUDED.audience_count
                               OR audience_geo_daily.confidence
                                      IS DISTINCT FROM EXCLUDED.confidence
                        """, (sid, plat, tgl, level, kunci, jml, conf))
                        n_geo += 1

                # --- interest ---
                for kunci, jml in agg["minat"].items():
                    conf = _kunci_confidence(
                        _modus_confidence(agg["minat_conf"].get(kunci, [])))
                    cur.execute("""
                        INSERT INTO l2_gold.audience_interest_daily (
                            social_account_id, platform, audience_date,
                            interest_key, audience_count, confidence,
                            created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,now(),now())
                        ON CONFLICT (social_account_id, platform, audience_date,
                                     interest_key)
                        DO UPDATE SET audience_count = EXCLUDED.audience_count,
                                      confidence     = EXCLUDED.confidence,
                                      updated_at     = now()
                        WHERE audience_interest_daily.audience_count
                                  IS DISTINCT FROM EXCLUDED.audience_count
                           OR audience_interest_daily.confidence
                                  IS DISTINCT FROM EXCLUDED.confidence
                    """, (sid, plat, tgl, kunci, jml, conf))
                    n_int += 1

            for t in ("audience_demographics_daily", "audience_geo_daily",
                      "audience_interest_daily"):
                cur.execute(f"SELECT count(*) FROM l2_gold.{t}")
            cur.execute("""
                SELECT (SELECT count(*) FROM l2_gold.audience_demographics_daily),
                       (SELECT count(*) FROM l2_gold.audience_geo_daily),
                       (SELECT count(*) FROM l2_gold.audience_interest_daily)""")
            tot_demo, tot_geo, tot_int = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    return Output(
        tot_demo + tot_geo + tot_int,
        metadata={
            "audience_demographics_daily": tot_demo,
            "audience_geo_daily": tot_geo,
            "audience_interest_daily": tot_int,
            "baris_disentuh_demografi": n_demo,
            "baris_disentuh_geo": n_geo,
            "baris_disentuh_interest": n_int,
            "baris_basi_dihapus": n_basi,
            "confidence": MetadataValue.text(
                "Semua baris dari jalur ini berawalan `inferred_` — turunan "
                "dari nama/bio follower, BUKAN demografi terukur dari Insights "
                "API. Jangan disamakan dengan baris yang nanti datang dari "
                "l1_silver.unified_audience."),
        },
    )


@asset(
    name="audience_feature",
    group_name=GROUP,
    deps=[_FOLLOWER],
    kinds={"postgres", "python"},
    description=(
        "feature.{ig,tt}_audience_analysis — ringkasan audiens per akun, "
        "diturunkan dari l1_silver.unified_follower memakai aturan "
        "deterministik di audience_inference.py. Gender/lokasi/interest TIDAK "
        "ada di data follower; ketiganya hasil inferensi dari full_name dan "
        "bio, dan `unknown` ikut disimpan supaya penyebutnya terlihat. "
        "age_gender_breakdown, active_hours_heatmap, avg_reach, cpe, emv "
        "sengaja dibiarkan NULL."
    ),
)
def audience_feature(postgres: PostgresResource) -> Output:
    return _jalankan_feature(postgres)


@asset(
    name="audience_gold",
    group_name=GROUP,
    deps=[AssetKey("audience_feature")],
    kinds={"postgres", "python"},
    description=(
        "l2_gold.audience_{demographics,geo,interest}_daily — hasil inferensi "
        "audiens dipekarkan jadi baris, grain per (akun, platform, tanggal, "
        "dimensi). Kolom `confidence` SELALU berawalan `inferred_` supaya bisa "
        "dibedakan dari demografi terukur Instagram Insights yang nanti masuk "
        "lewat l1_silver.unified_audience."
    ),
)
def audience_gold(postgres: PostgresResource) -> Output:
    return _tulis_gold(postgres)


audience_assets = [audience_feature, audience_gold]
