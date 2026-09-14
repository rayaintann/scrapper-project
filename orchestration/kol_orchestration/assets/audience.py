"""Asset audiens: dari daftar follower L1 ke Feature, lalu ke L2 Gold.

    l0_raw.{ig,tt}_followers_apify -> ... -> unified_follower (L1)
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
               l0_raw.{ig,tt}_followers_apify
               -> l0_harmonization.{instagram,tiktok}_follower
               -> l1_silver.unified_follower -> audience_inference.py (gender,
                  lokasi, interest) + creator_age_inference.py (umur)
               Sumbernya daftar follower. Gender/lokasi/interest/umur TIDAK
               dilaporkan platform; keempatnya diturunkan dari `full_name` dan
               `bio` follower.

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
   `active_hours_heatmap`  -- butuh waktu aktivitas, follower tidak punya.
   `avg_reach`, `cpe`, `emv` -- butuh reach/biaya kampanye, di luar jalur ini.
   Semuanya dibiarkan NULL, mengikuti pola "kolom blocked" di gold.py.

   `age_gender_breakdown` DULU ada di daftar ini, dengan alasan "tidak ada
   satu pun sinyal umur di data follower". Itu ternyata terlalu keras. Yang
   benar: hampir tidak ada. Sebagian kecil follower MENYATAKAN umurnya di bio,
   dan pernyataan itu sah persis seperti pernyataan umur di bio kreator.
   Kolomnya sekarang diisi (lihat keputusan #7).

7. UMUR AUDIENS DITURUNKAN DARI BIO FOLLOWER, DENGAN ATURAN YANG SAMA PERSIS
   SEPERTI UMUR KREATOR.

   Sumbernya kolom `bio` di `unified_follower`, yang isinya
   `l0_raw.ig_followers_apify.bio` (dari `biography`) dan
   `l0_raw.tt_followers_apify.bio` (dari `authorMeta.signature`).

   Extractor-nya `creator_age_inference.ekstrak_umur` -- modul yang sama,
   dipakai apa adanya, TIDAK dilonggarkan. Bio follower memuat kebisingan yang
   persis sama dengan bio kreator (tahun penghargaan, tahun berdiri usaha,
   nomor telepon, tanggal lahir anak), jadi setiap VETO yang dibutuhkan di
   sana dibutuhkan sama persis di sini.

   LIPUTANNYA KECIL, DAN ITU BUKAN ALASAN UNTUK TIDAK MENGISINYA. Dari ~934
   bio follower yang ada, satu menyatakan umur. Yang keluar karena itu adalah
   satu bucket berisi 1 dan satu bucket `unknown` berisi sisanya -- dan itu
   jawaban yang benar. Yang TIDAK boleh dilakukan adalah melonggarkan aturan
   supaya kolomnya terlihat penuh; sebaran umur audiens yang 97% karangan
   lebih berbahaya daripada sebaran yang jujur menyebut penyebutnya, karena
   yang pertama akan dipakai orang untuk memilih KOL.

   UMUR KREATOR TIDAK PERNAH DIPAKAI SEBAGAI PROXY UMUR AUDIENS. Keduanya
   dihitung dari teks yang berbeda milik orang yang berbeda. "Kreatornya 24,
   jadi audiensnya 18-24" adalah asumsi bisnis, bukan pengukuran, dan tidak
   ada satu baris pun di file ini yang membuatnya.

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
from datetime import date
from pathlib import Path

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

# audience_inference.py ada di root project, satu level di atas folder
# orchestration/. Ditambahkan ke sys.path supaya asset ini bisa memakainya
# tanpa menduplikasi aturan inferensi ke dalam paket Dagster.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from audience_inference import (  # noqa: E402
    analisis_follower, skor_kualitas, tingkat_geo)
# Extractor umur yang SAMA dengan yang dipakai Age Kreator. Sengaja dipakai
# ulang apa adanya, bukan disalin dan dilonggarkan "karena ini cuma follower":
# bio follower berisi jenis kebisingan yang persis sama (tahun penghargaan,
# tahun berdiri usaha, nomor telepon, tanggal lahir anak), jadi aturan yang
# menahan umur karangan di kreator dibutuhkan sama persis di sini.
from creator_age_inference import ekstrak_umur  # noqa: E402
from metrics_thresholds import (  # noqa: E402
    AGE_UNKNOWN, BUCKET_AGE, klasifikasi_audience_quality,
    normalisasi_bucket_platform)

#: Kunci untuk follower yang bio-nya tidak menyatakan umur. IKUT DISIMPAN,
#: sesuai keputusan #1 di docstring modul: tanpa penyebut yang terlihat,
#: "18-24: 1" terbaca sebagai "audiensnya 100% 18-24".
#:
#: Alias, bukan nilai kedua. Definisinya di `metrics_thresholds` karena
#: `sql_filter_audience_age_band` harus mengeluarkan kunci yang SAMA dari
#: perhitungan bucket dominan -- dua literal yang diketik terpisah adalah
#: persis cara filter itu diam-diam berhenti cocok.
UMUR_UNKNOWN = AGE_UNKNOWN

#: Nilai `audience_demographics_daily.confidence` milik jalur A. Didefinisikan
#: sekali di sini dan dipakai KEDUA jalur: jalur A menulisnya, jalur B
#: memeriksanya supaya tidak pernah menimpanya.
CONF_TERUKUR = "measured"

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


def rasio_gender(gender: dict) -> tuple:
    """(female_pct, male_pct, gender_known_pct) dari cacah gender.

    PENYEBUT RASIO HANYA male + female. `unknown` DIKELUARKAN, sesuai
    kesepakatan: 40 male + 60 female -> female 60%, berapa pun unknown-nya.

    Ini TIDAK bertentangan dengan keputusan #1 di docstring modul ("unknown
    ikut disimpan, tidak dibuang"): `gender_breakdown` tetap menyimpan cacah
    unknown apa adanya, dan `gender_known_pct` justru menerbitkan seberapa
    besar unknown itu. Yang dikeluarkan hanya dari PENYEBUT rasio, dan hanya
    karena rasio male:female memang tidak terdefinisi atas orang yang
    gendernya tidak diketahui.

    Ketiganya None kalau tidak ada yang bisa dihitung. 50/50 tidak pernah
    dikembalikan sebagai tebakan -- itu akan terlihat seperti pengukuran.

    Dipisah jadi fungsi supaya bisa diuji tanpa database dan tanpa menjalankan
    seluruh asset.
    """
    n_male = gender.get("male", 0) or 0
    n_female = gender.get("female", 0) or 0
    n_tahu = n_male + n_female
    n_total = sum(v or 0 for v in gender.values())
    female_pct = round(n_female / n_tahu * 100, 2) if n_tahu else None
    male_pct = round(n_male / n_tahu * 100, 2) if n_tahu else None
    # Bukan bagian rumus di atas: ini yang memberi tahu pembaca seberapa jauh
    # kedua angka itu boleh dipercaya.
    known_pct = round(n_tahu / n_total * 100, 2) if n_total else None
    return female_pct, male_pct, known_pct


# ---------------------------------------------------------------------------
# Feature
# ---------------------------------------------------------------------------
def bucket_umur_follower(bio: str | None, tahun_acuan: int) -> tuple[str, str | None]:
    """Bio satu follower -> (bucket umur, confidence). `unknown` kalau tidak ada.

    Pembungkus setipis mungkin di atas `ekstrak_umur`, dipisah jadi fungsi
    supaya bisa diuji tanpa database dan supaya ada SATU tempat yang memetakan
    "tidak ketemu" ke kunci `unknown`.

    KENAPA EXTRACTOR-NYA TIDAK DILONGGARKAN UNTUK FOLLOWER
    ------------------------------------------------------
    Godaannya nyata: dari 934 bio follower yang ada, hanya SATU menyatakan umur
    secara eksplisit. Melonggarkan aturan -- menerima tahun telanjang, atau
    angka di belakang username -- akan membuat kolomnya terlihat penuh.

    Ia juga akan salah. Angka di belakang username follower diuji terhadap data
    nyata dan isinya nomor punggung, tanggal pernikahan, dan angka hoki (lihat
    docstring `creator_age_inference`). Sebaran umur audiens yang 97% karangan
    lebih buruk daripada sebaran yang jujur mengatakan "tidak diketahui":
    yang pertama akan dipakai orang untuk memilih KOL.

    `tahun_acuan` WAJIB dioper, tidak boleh default ke tahun berjalan. Umur
    yang diturunkan dari tahun lahir bergeser tiap 1 Januari, dan satu run
    harus memakai satu tahun acuan untuk SELURUH follower -- kalau tidak, run
    yang kebetulan melewati tengah malam pergantian tahun akan menaruh dua
    follower seumur di dua bucket berbeda.
    """
    hasil = ekstrak_umur(bio, tahun_acuan=tahun_acuan)
    if not hasil.diketahui or not hasil.band:
        return UMUR_UNKNOWN, None
    return hasil.band, hasil.confidence


def _hitung_per_akun(baris: list[tuple], tahun_acuan: int) -> dict:
    """Jalankan inferensi untuk semua follower satu akun, lalu agregasi."""
    gender: Counter = Counter()
    gender_conf: dict[str, list[str]] = {}
    # Semua bucket dimulai dari NOL, bukan dibiarkan absen. Bucket yang hilang
    # dari jsonb terbaca sebagai "belum dihitung"; bucket bernilai 0 terbaca
    # sebagai "dihitung, tidak ada satu pun". Keduanya berbeda, dan yang kedua
    # yang benar.
    umur: Counter = Counter({b: 0 for b in BUCKET_AGE})
    umur_conf: dict[str, list[str]] = {}
    umur_gender: dict[str, Counter] = {}
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

        # --- umur, dari bio follower yang sama ---
        band, conf_umur = bucket_umur_follower(bio, tahun_acuan)
        umur[band] += 1
        if conf_umur:
            umur_conf.setdefault(band, []).append(conf_umur)
        # Silang umur x gender, hanya untuk follower yang umurnya DIKETAHUI.
        # Baris `unknown` tidak ikut disilang: "umur tidak diketahui, gender
        # perempuan" bukan kelompok umur, dan menaruhnya di tabel silang akan
        # membuat totalnya terbaca seolah umurnya diketahui.
        if band != UMUR_UNKNOWN:
            umur_gender.setdefault(band, Counter())[h.gender.nilai] += 1

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
        "umur": dict(umur), "umur_conf": umur_conf,
        "umur_gender": {k: dict(v) for k, v in umur_gender.items()},
        "negara": dict(negara), "negara_conf": negara_conf,
        "kota": dict(kota), "kota_conf": kota_conf,
        "minat": dict(minat), "minat_conf": minat_conf,
        "skor": skor_kualitas(followers_untuk_skor),
    }


def age_gender_breakdown(agg: dict) -> dict:
    """Bentuk jsonb untuk `feature.{ig,tt}_audience_analysis.age_gender_breakdown`.

    Dipisah jadi fungsi murni supaya bentuknya bisa diuji tanpa database --
    dan karena bentuk inilah yang dibaca UI, jadi ia harus punya satu tempat
    yang bisa ditunjuk saat orang bertanya "isinya apa".

    KENAPA PENYEBUTNYA IKUT DITULIS
    -------------------------------
    Kolom ini akan dibaca sebagai "sebaran umur audiens". Dengan liputan nyata
    hari ini (1 dari 934 bio follower menyatakan umur), sebaran yang hanya
    memuat `{"18-24": 1}` terbaca sebagai "audiensnya 100% berumur 18-24".
    Karena itu `followers_analyzed`, `age_known` dan `age_unknown` ikut
    ditulis, dan `coverage_pct` dihitung di sini sekali supaya pembaca tidak
    perlu menghitungnya sendiri (dan salah).

    `age` SELALU memuat kelima bucket, termasuk yang bernilai nol. Bucket yang
    absen dan bucket bernilai nol adalah dua klaim berbeda.
    """
    umur = dict(agg.get("umur") or {})
    n_total = agg.get("n", 0) or 0
    n_unknown = umur.get(UMUR_UNKNOWN, 0)
    n_tahu = sum(v for k, v in umur.items() if k != UMUR_UNKNOWN)

    sebaran = {b: umur.get(b, 0) for b in BUCKET_AGE}
    sebaran[UMUR_UNKNOWN] = n_unknown

    # Bucket dominan: hanya di antara yang DIKETAHUI, dan None kalau tidak ada
    # satu pun. `unknown` tidak pernah jadi "bucket dominan" -- ia bukan
    # kelompok umur, dan melaporkannya begitu akan membuat filter Discovery
    # memperlakukan ketidaktahuan sebagai jawaban.
    tahu = {k: v for k, v in sebaran.items() if k != UMUR_UNKNOWN and v}
    dominan = (sorted(tahu.items(), key=lambda x: (-x[1], BUCKET_AGE.index(x[0])))[0][0]
               if tahu else None)

    return {
        "source": "follower_bio_self_declared",
        "buckets": list(BUCKET_AGE),
        "age": sebaran,
        "age_gender": agg.get("umur_gender") or {},
        "age_top": dominan,
        "followers_analyzed": n_total,
        "age_known": n_tahu,
        "age_unknown": n_unknown,
        "coverage_pct": round(n_tahu / n_total * 100, 2) if n_total else None,
        "confidence": {
            b: _kunci_confidence(_modus_confidence(agg.get("umur_conf", {}).get(b, [])))
            for b in BUCKET_AGE if sebaran.get(b)
        },
    }


def _jalankan_feature(postgres: PostgresResource, tahun_acuan: int) -> Output:
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

            # Topik konten per akun, dari feature engagement yang sudah
            # dihitung lebih dulu. Dipakai HANYA sebagai pengganti ketika minat
            # audiens seluruhnya `unknown`, dan hasilnya selalu ditandai
            # `interest_source='content_inferred'` -- tidak pernah bercampur
            # dengan minat yang benar-benar teramati dari follower.
            cur.execute("""
                SELECT social_account_id, content_topic
                  FROM feature.ig_engagement_analysis WHERE content_topic IS NOT NULL
                UNION ALL
                SELECT social_account_id, content_topic
                  FROM feature.tt_engagement_analysis WHERE content_topic IS NOT NULL
            """)
            topik_konten_akun = {str(r[0]): r[1] for r in cur.fetchall()}

            ditulis = {"instagram": 0, "tiktok": 0}
            ringkas = {}
            for (sid, plat), baris in per_akun.items():
                agg = _hitung_per_akun(baris, tahun_acuan)
                tabel = TABEL_FEATURE[plat]
                skor = agg["skor"]

                # top_interest: urut menurun, `unknown` ikut supaya penyebut jelas.
                top = sorted(agg["minat"].items(), key=lambda x: (-x[1], x[0]))
                top_json = [{"interest": k, "count": v} for k, v in top]

                # Female %/Male %: unknown dikeluarkan dari penyebut.
                # Rumusnya di `rasio_gender()` supaya bisa diuji sendiri.
                female_pct, male_pct, known_pct = rasio_gender(agg["gender"])

                # --- Audience Quality tier (migration 039) -------------------
                # Skornya SUDAH dihitung `skor_kualitas`; yang ditambahkan
                # hanya labelnya. Tidak ada skor kedua.
                tier_kualitas = klasifikasi_audience_quality(
                    skor["audience_quality_score"])

                # --- Interest teratas + ASAL-nya (migration 039) -------------
                # `unknown` dikeluarkan dari pencarian teratas: ia memang
                # mayoritas (2.278 dari ~2.600 sinyal), dan melaporkannya
                # sebagai "minat" audiens tidak memberi tahu apa pun.
                #
                # Kalau SELURUH minat audiens unknown, dipakai topik konten
                # creator sebagai pengganti -- dan `interest_source` yang
                # membedakannya, supaya turunan tidak menyamar jadi teramati.
                minat_tahu = {k: v for k, v in agg["minat"].items()
                              if k != "unknown" and v}
                if minat_tahu:
                    interest_top = sorted(minat_tahu.items(),
                                          key=lambda x: (-x[1], x[0]))[0][0]
                    interest_source = "audience"
                else:
                    interest_top = topik_konten_akun.get(str(sid))
                    interest_source = "content_inferred" if interest_top else None

                cur.execute(
                    f"""
                    INSERT INTO {tabel} (
                        social_account_id,
                        audience_quality_score, authenticity_score,
                        follower_quality_score,
                        gender_breakdown, top_interest, geo_distribution,
                        female_pct, male_pct, gender_known_pct,
                        audience_quality_tier, interest_top, interest_source,
                        age_gender_breakdown,
                        created_at, updated_at
                        -- SENGAJA tidak disebut (tetap NULL):
                        -- active_hours_heatmap, avg_reach, cpe, emv
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                              %s, %s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (social_account_id) DO UPDATE SET
                        audience_quality_score = EXCLUDED.audience_quality_score,
                        authenticity_score     = EXCLUDED.authenticity_score,
                        follower_quality_score = EXCLUDED.follower_quality_score,
                        gender_breakdown       = EXCLUDED.gender_breakdown,
                        top_interest           = EXCLUDED.top_interest,
                        geo_distribution       = EXCLUDED.geo_distribution,
                        female_pct             = EXCLUDED.female_pct,
                        male_pct               = EXCLUDED.male_pct,
                        gender_known_pct       = EXCLUDED.gender_known_pct,
                        audience_quality_tier  = EXCLUDED.audience_quality_tier,
                        interest_top           = EXCLUDED.interest_top,
                        interest_source        = EXCLUDED.interest_source,
                        age_gender_breakdown   = EXCLUDED.age_gender_breakdown,
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
                       OR {tabel.split('.')[1]}.female_pct
                              IS DISTINCT FROM EXCLUDED.female_pct
                       OR {tabel.split('.')[1]}.gender_known_pct
                              IS DISTINCT FROM EXCLUDED.gender_known_pct
                       OR {tabel.split('.')[1]}.audience_quality_tier
                              IS DISTINCT FROM EXCLUDED.audience_quality_tier
                       OR {tabel.split('.')[1]}.interest_top
                              IS DISTINCT FROM EXCLUDED.interest_top
                       OR {tabel.split('.')[1]}.interest_source
                              IS DISTINCT FROM EXCLUDED.interest_source
                       OR {tabel.split('.')[1]}.age_gender_breakdown
                              IS DISTINCT FROM EXCLUDED.age_gender_breakdown
                    """,
                    (sid, skor["audience_quality_score"], skor["authenticity_score"],
                     skor["follower_quality_score"],
                     json.dumps(agg["gender"], ensure_ascii=False),
                     json.dumps(top_json, ensure_ascii=False),
                     json.dumps({"country": agg["negara"], "city": agg["kota"]},
                                ensure_ascii=False),
                     female_pct, male_pct, known_pct,
                     tier_kualitas, interest_top, interest_source,
                     json.dumps(age_gender_breakdown(agg), ensure_ascii=False)),
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

    sebaran_umur: Counter = Counter()
    for a in ringkas.values():
        for k, v in (a.get("umur") or {}).items():
            sebaran_umur[k] += v
    umur_tahu = sum(v for k, v in sebaran_umur.items() if k != UMUR_UNKNOWN)
    akun_punya_umur = sum(
        1 for a in ringkas.values()
        if any(v for k, v in (a.get("umur") or {}).items() if k != UMUR_UNKNOWN))

    return Output(
        n_ig + n_tt,
        metadata={
            "akun_diproses": len(ringkas),
            "follower_dianalisis": total_follower,
            "baris_ig_audience_analysis": n_ig,
            "baris_tt_audience_analysis": n_tt,
            "gender_terdeteksi": total_gender_known,
            "gender_unknown": total_follower - total_gender_known,
            "umur_terdeteksi": umur_tahu,
            "umur_unknown": sebaran_umur.get(UMUR_UNKNOWN, 0),
            "umur_coverage_pct": (round(umur_tahu / total_follower * 100, 2)
                                  if total_follower else None),
            "akun_punya_minimal_satu_umur": akun_punya_umur,
            "sebaran_umur_semua_akun": MetadataValue.json(dict(sebaran_umur)),
            "tahun_acuan": tahun_acuan,
            "catatan_umur": MetadataValue.text(
                "age_gender_breakdown kini TERISI untuk tiap akun, tapi hampir "
                "seluruh isinya bucket `unknown` — dan itu hasil yang benar, "
                "bukan bug. Umur hanya diambil dari pernyataan eksplisit di "
                "bio follower ('umur 24', 'lahir 1998'); tahun telanjang dan "
                "angka di belakang username SENGAJA ditolak karena terbukti "
                "hampir selalu bukan umur. `coverage_pct` di tiap baris "
                "jsonb-nya menerbitkan seberapa besar penyebut yang tidak "
                "diketahui itu."),
            "kolom_sengaja_null": MetadataValue.text(
                "active_hours_heatmap (tidak ada waktu aktivitas); "
                "avg_reach, cpe, emv (butuh reach/biaya kampanye)."),
        },
    )


# ---------------------------------------------------------------------------
# L2 Gold
# ---------------------------------------------------------------------------
def _tulis_gold(postgres: PostgresResource, tahun_acuan: int) -> Output:
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

            n_demo = n_geo = n_int = n_age = 0
            n_basi = 0
            n_age_tahu = 0

            for (sid, plat, tgl), baris in per_akun.items():
                agg = _hitung_per_akun(baris, tahun_acuan)

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
                # Tingkat geo DIPISAH menurut `tingkat_geo`, tidak lagi
                # semuanya 'city'. Sebelum ini "Bali" dan "Lampung" ditulis
                # sebagai kota dan berdiri sejajar dengan "Bandung" -- dua
                # tingkat administratif tercampur di satu daftar filter.
                _per_tingkat: dict = {}
                for _k in agg["kota"]:
                    _per_tingkat.setdefault(tingkat_geo(_k), []).append(_k)
                for level, kunci in ([("country", list(agg["negara"].keys()))]
                                     + sorted(_per_tingkat.items())):
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

                # --- umur (audience_type='age') ---------------------------
                #
                # BARIS `measured` TIDAK PERNAH DISENTUH JALUR INI.
                #
                # Tabelnya dipakai bersama dua jalur yang tidak setara:
                #
                #     jalur A  Instagram Insights   confidence='measured'
                #     jalur B  bio follower (ini)   confidence='inferred_*'
                #
                # `uq_audience_demographics_daily` tidak memuat `confidence`,
                # jadi untuk satu (akun, platform, tanggal, 'age', bucket)
                # hanya ADA SATU baris -- keduanya tidak bisa hidup
                # berdampingan. Aturannya karena itu dibuat eksplisit dan
                # searah: angka yang dilaporkan platform selalu menang atas
                # angka yang diturunkan dari teks bio.
                #
                # Hari ini jalur A masih 0 baris, jadi tidak ada yang bertabrakan.
                # Penjagaan ini dipasang sekarang justru karena hari ketika
                # Insights menyala adalah hari yang paling buruk untuk
                # menemukan bahwa materialisasi rutin menimpanya.
                kunci_umur = [k for k, v in agg["umur"].items() if v]
                cur.execute("""
                    DELETE FROM l2_gold.audience_demographics_daily
                    WHERE social_account_id=%s AND platform=%s AND audience_date=%s
                      AND audience_type='age'
                      AND confidence IS DISTINCT FROM %s
                      AND dimension_key <> ALL(%s)""",
                    (sid, plat, tgl, CONF_TERUKUR, kunci_umur or [""]))
                n_basi += cur.rowcount or 0

                for kunci, jml in agg["umur"].items():
                    # Bucket kosong tidak ditulis sebagai baris nol: L2 di sini
                    # bergrain "satu baris per dimensi yang teramati", dan lima
                    # baris nol per akun per hari hanya menggelembungkan tabel
                    # tanpa menambah informasi. Penyebut lengkapnya sudah ada
                    # di `age_gender_breakdown` milik layer feature.
                    if not jml:
                        continue
                    conf = _kunci_confidence(
                        _modus_confidence(agg["umur_conf"].get(kunci, [])))
                    cur.execute("""
                        INSERT INTO l2_gold.audience_demographics_daily (
                            social_account_id, platform, audience_date,
                            audience_type, dimension_key, audience_count,
                            confidence, created_at, updated_at)
                        VALUES (%s,%s,%s,'age',%s,%s,%s,now(),now())
                        ON CONFLICT (social_account_id, platform, audience_date,
                                     audience_type, dimension_key)
                        DO UPDATE SET audience_count = EXCLUDED.audience_count,
                                      confidence     = EXCLUDED.confidence,
                                      updated_at     = now()
                        WHERE audience_demographics_daily.confidence
                                  IS DISTINCT FROM %s
                          AND (audience_demographics_daily.audience_count
                                  IS DISTINCT FROM EXCLUDED.audience_count
                            OR audience_demographics_daily.confidence
                                  IS DISTINCT FROM EXCLUDED.confidence)
                    """, (sid, plat, tgl, kunci, jml, conf, CONF_TERUKUR))
                    n_age += 1
                    if kunci != UMUR_UNKNOWN:
                        n_age_tahu += jml

                # --- geo: negara lalu kota, dua geo_level di tabel yang sama ---
                for level, sumber, conf_src in (
                    ("country", agg["negara"], agg["negara_conf"]),
                    # `None` berarti "tingkatnya ditentukan per kunci" -- lihat
                    # `tingkat_geo` di bawah. Leksikonnya sudah membedakan kota
                    # dari provinsi saat menebak; yang hilang selama ini hanya
                    # penerusan informasi itu ke L2.
                    (None, agg["kota"], agg["kota_conf"]),
                ):
                    for kunci, jml in sumber.items():
                        # Variabel BARU, bukan menimpa `level`: menimpanya
                        # akan menghapus penanda None pada iterasi pertama
                        # sehingga kunci berikutnya ikut memakai tingkat
                        # kunci pertama.
                        tingkat = level if level is not None else tingkat_geo(kunci)
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
                        """, (sid, plat, tgl, tingkat, kunci, jml, conf))
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
            "baris_disentuh_umur": n_age,
            "follower_ber_umur_diketahui": n_age_tahu,
            "baris_disentuh_geo": n_geo,
            "baris_disentuh_interest": n_int,
            "baris_basi_dihapus": n_basi,
            "tahun_acuan": tahun_acuan,
            "umur": MetadataValue.text(
                "Baris audience_type='age' kini ditulis jalur ini dari bio "
                "follower, berawalan `inferred_`. Baris `dimension_key="
                "'unknown'` adalah PENYEBUT, bukan kelompok umur, dan "
                "dikeluarkan dari perhitungan bucket dominan di "
                "`sql_filter_audience_age_band`. Baris bersumber 'measured' "
                "(Instagram Insights) TIDAK PERNAH ditimpa jalur ini."),
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
        "diturunkan dari l1_silver.unified_follower (harmonisasi dari "
        "l0_raw.{ig,tt}_followers_apify) memakai aturan deterministik di "
        "audience_inference.py. Gender/lokasi/interest TIDAK ada di data "
        "follower; ketiganya hasil inferensi dari full_name dan bio, dan "
        "`unknown` ikut disimpan supaya penyebutnya terlihat. "
        "age_gender_breakdown DIISI dari bio follower memakai extractor yang "
        "sama dengan Age Kreator (creator_age_inference.ekstrak_umur) — "
        "hanya pernyataan eksplisit yang diterima, jadi mayoritas isinya "
        "bucket `unknown`, dan penyebutnya ikut diterbitkan di jsonb-nya. "
        "active_hours_heatmap, avg_reach, cpe, emv sengaja dibiarkan NULL."
    ),
)
def audience_feature(postgres: PostgresResource) -> Output:
    # Dibekukan SEKALI di sini, lalu dioper ke bawah. Lihat
    # `bucket_umur_follower` untuk alasannya.
    return _jalankan_feature(postgres, date.today().year)


@asset(
    name="audience_gold",
    group_name=GROUP,
    deps=[AssetKey("audience_feature")],
    kinds={"postgres", "python"},
    description=(
        "l2_gold.audience_{demographics,geo,interest}_daily — hasil inferensi "
        "audiens dipekarkan jadi baris, grain per (akun, platform, tanggal, "
        "dimensi). Menulis audience_type 'gender' DAN 'age'; baris umur "
        "diturunkan dari bio follower dan hanya memuat pernyataan eksplisit. "
        "Kolom `confidence` SELALU berawalan `inferred_` supaya bisa "
        "dibedakan dari demografi terukur Instagram Insights yang masuk lewat "
        "l1_silver.unified_audience — dan baris `measured` milik jalur itu "
        "TIDAK PERNAH ditimpa asset ini."
    ),
)
def audience_gold(postgres: PostgresResource) -> Output:
    return _tulis_gold(postgres, date.today().year)


# ===========================================================================
# JALUR A -- AGE AUDIENCE TERUKUR
# ===========================================================================
#
# Semua di atas adalah jalur B (inferensi dari daftar follower). Bagian ini
# jalur A, dan ia menjawab satu-satunya dimensi yang jalur B TIDAK BISA jawab:
# UMUR. Tidak ada sinyal umur di data follower -- itu sebabnya
# `age_gender_breakdown` dibiarkan NULL sejak awal.
#
# YANG SEBENARNYA HILANG, DAN BARU KETAHUAN SAAT INI DITULIS
# ----------------------------------------------------------
# Rantai jalur A didokumentasikan lengkap di header file ini:
#
#     ig_profile_official.demographics_age
#         -> sp_sync_instagram_audience()      (ada, di luar repo ini)
#         -> l0_harmonization.instagram_audience
#         -> l1_silver.unified_audience        (audience_type='age')
#         -> l2_gold.audience_demographics_daily
#
# Langkah TERAKHIR tidak pernah dibangun. Sebelum asset ini ada, pencarian
# `unified_audience` di seluruh orchestration/ hanya menemukan KOMENTAR --
# tidak satu baris kode pun membacanya. Artinya meskipun Insights API besok
# menyala dan L1 terisi, datanya tetap berhenti di L1 dan filter Age Audience
# di Discovery tetap kosong. Asset ini yang menyambungkannya.
#
# HARI INI ASSET INI MEMPROSES NOL BARIS, dan itu bukan kegagalan: sumbernya
# memang masih kosong sampai ada Instagram Business Account + token. Yang
# berubah adalah begitu sumber itu menyala, tidak ada development lagi yang
# perlu dikerjakan.
#
# KENAPA NAMA KOLOM SUMBER DIRESOLUSI SAAT RUNTIME
# ------------------------------------------------
# `unified_audience` dibangun `l1_silver.sp_build_unified_audience()`, yang
# TIDAK ada di repo ini, dan tabelnya 0 baris sehingga bentuknya tidak bisa
# diperiksa dari data. Tiga kolom yang pasti karena dipakai migration 023
# adalah `audience_type`, `dimension_key`, dan `value`; nama kolom platform
# dan tanggal TIDAK pasti.
#
# Menebaknya lalu menuliskannya sebagai SQL tetap berarti asset ini akan
# meledak pada hari pertama data sungguhan masuk -- hari yang justru paling
# buruk untuk menemukan salah ketik. Karena itu keduanya dicari di
# information_schema saat dijalankan, dan kalau tidak ketemu asset ini
# BERHENTI DENGAN PESAN YANG MENYEBUT KOLOM APA SAJA YANG ADA, bukan menebak
# padanan terdekat.
# ===========================================================================

#: Kandidat nama kolom, berurutan dari yang paling mungkin. Dipakai
#: `_resolusi_kolom`; lihat komentar di atas.
_KANDIDAT_PLATFORM = ("platform", "platform_id", "platform_key")
_KANDIDAT_TANGGAL = ("audience_date", "date", "snapshot_date", "metric_date",
                     "processed_at")

def agregasi_bucket_age(
        mentah: list[tuple],
) -> tuple[dict[tuple, float], Counter]:
    """Bucket mentah platform -> bucket Discovery, DIJUMLAHKAN per akun/tanggal.

    `mentah` berisi tuple `(social_account_id, platform, tanggal,
    dimension_key, value)` apa adanya dari `l1_silver.unified_audience`.

    Fungsi ini dipisah dari asset supaya bisa diuji tanpa database -- dan itu
    perlu, karena ini satu-satunya tempat di jalur A yang mengubah angka.

    DUA HAL YANG DIJAGA DI SINI, DAN KEDUANYA PERNAH JADI BUG DI TEMPAT LAIN:

      1. `55-64` DAN `65+` DIJUMLAHKAN jadi `55+`, tidak saling menimpa.
         Kalau keduanya di-INSERT terpisah dengan ON CONFLICT DO UPDATE, yang
         kedua akan MENIMPA yang pertama dan seluruh audiens 65+ hilang tanpa
         jejak -- totalnya lalu tidak lagi sama dengan yang dilaporkan
         platform, dan tidak ada yang bisa menjelaskan selisihnya.

      2. BUCKET TAK DIKENAL DILEWATI DAN DIHITUNG, bukan dipetakan ke yang
         terdekat. Bucket asing berarti platform mengubah skemanya; menebak
         padanannya memindahkan audiens ke kelompok umur yang salah. Jumlahnya
         dikembalikan supaya bisa dilaporkan di metadata run.
    """
    terkumpul: dict[tuple, float] = {}
    tak_dikenal: Counter = Counter()
    for sid, plat, tgl, kunci_mentah, nilai in mentah:
        bucket = normalisasi_bucket_platform(kunci_mentah)
        if bucket is None:
            tak_dikenal[str(kunci_mentah)] += 1
            continue
        if nilai is None:
            continue
        k = (sid, plat, tgl, bucket)
        terkumpul[k] = terkumpul.get(k, 0) + float(nilai)
    return terkumpul, tak_dikenal


def _resolusi_kolom(cur, tabel: str, skema: str,
                    kandidat: tuple[str, ...]) -> str | None:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_schema = %s AND table_name = %s""", (skema, tabel))
    ada = {r[0] for r in cur.fetchall()}
    for nama in kandidat:
        if nama in ada:
            return nama
    return None


def _tulis_age_terukur(postgres: PostgresResource) -> Output:
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('l1_silver.unified_audience')")
            if cur.fetchone()[0] is None:
                conn.rollback()
                return Output(0, metadata={
                    "baris_ditulis": 0,
                    "status": "BLOCKED",
                    "catatan": MetadataValue.text(
                        "l1_silver.unified_audience tidak ada. Jalur A belum "
                        "terpasang di database ini."),
                })

            cur.execute("""
                SELECT count(*) FROM l1_silver.unified_audience
                 WHERE audience_type = 'age'""")
            n_sumber = cur.fetchone()[0]

            # Tidak ada sumber -> tidak menulis apa pun. TIDAK membuat baris
            # placeholder, tidak menulis nol, tidak menyalin sebaran dari
            # jalur inferensi. Tabel yang kosong dengan jujur lebih berguna
            # daripada tabel berisi angka yang tidak diukur siapa pun.
            if n_sumber == 0:
                conn.rollback()
                return Output(0, metadata={
                    "baris_ditulis": 0,
                    "baris_sumber": 0,
                    "status": "MENUNGGU SUMBER",
                    "blocker": MetadataValue.text(
                        "l1_silver.unified_audience audience_type='age' masih "
                        "0 baris. Hulunya l0_raw.ig_profile_official, yang "
                        "butuh Instagram Business Account + token Insights "
                        "API. Tidak ada data yang dibuat-buat sebagai "
                        "pengganti."),
                    "siap_saat_sumber_ada": MetadataValue.text(
                        "Mapping bucket dan penulisan L2 sudah lengkap dan "
                        "diuji (tests/test_audience_age.py). Begitu sumbernya "
                        "terisi, asset ini cukup dimaterialisasi ulang — "
                        "tidak ada development tersisa."),
                })

            kol_platform = _resolusi_kolom(cur, "unified_audience", "l1_silver",
                                           _KANDIDAT_PLATFORM)
            kol_tanggal = _resolusi_kolom(cur, "unified_audience", "l1_silver",
                                          _KANDIDAT_TANGGAL)
            if not kol_platform or not kol_tanggal:
                cur.execute("""
                    SELECT string_agg(column_name, ', ' ORDER BY ordinal_position)
                      FROM information_schema.columns
                     WHERE table_schema='l1_silver' AND table_name='unified_audience'""")
                daftar = cur.fetchone()[0]
                raise ValueError(
                    "Tidak bisa menentukan kolom "
                    f"{'platform' if not kol_platform else 'tanggal'} di "
                    f"l1_silver.unified_audience. Kolom yang ada: {daftar}. "
                    "Tambahkan nama yang benar ke _KANDIDAT_PLATFORM / "
                    "_KANDIDAT_TANGGAL di assets/audience.py.")

            # Platform bisa berupa id (uuid/int) atau key teks. Kalau id,
            # di-join ke public.platforms supaya yang tertulis di L2 tetap
            # 'instagram'/'tiktok' -- sama dengan yang ditulis jalur B, supaya
            # satu filter bisa membaca keduanya.
            if kol_platform.endswith("_id"):
                pilih_platform = "pl.key"
                join = f"JOIN public.platforms pl ON pl.id = ua.{kol_platform}"
            else:
                pilih_platform = f"ua.{kol_platform}"
                join = ""

            cur.execute(f"""
                SELECT ua.social_account_id,
                       {pilih_platform}      AS platform,
                       ua.{kol_tanggal}::date AS tgl,
                       ua.dimension_key,
                       ua.value
                  FROM l1_silver.unified_audience ua
                  {join}
                 WHERE ua.audience_type = 'age'
                   AND ua.social_account_id IS NOT NULL
            """)
            mentah = cur.fetchall()

            terkumpul, tak_dikenal = agregasi_bucket_age(mentah)

            # Buang baris L2 yang tidak lagi dihasilkan untuk (akun, platform,
            # tanggal) yang sama -- alasannya sama dengan `_tulis_gold`.
            # DIBATASI audience_type='age' supaya baris gender milik jalur B
            # di tabel yang sama tidak ikut terhapus.
            per_akun: dict[tuple, list] = {}
            for (sid, plat, tgl, bucket) in terkumpul:
                per_akun.setdefault((sid, plat, tgl), []).append(bucket)

            # Penghapusan ini SENGAJA tidak menyaring `confidence`: untuk
            # (akun, platform, tanggal) yang datanya memang diukur Insights,
            # sebaran terukur itulah yang berlaku utuh, dan bucket turunan
            # yang tersisa dari jalur B hanya akan menambahkan audiens yang
            # sudah ikut terhitung di sana. Arahnya searah dan disengaja:
            # measured menang atas inferred, tidak pernah sebaliknya.
            n_basi = 0
            for (sid, plat, tgl), buckets in per_akun.items():
                cur.execute("""
                    DELETE FROM l2_gold.audience_demographics_daily
                     WHERE social_account_id=%s AND platform=%s
                       AND audience_date=%s AND audience_type='age'
                       AND dimension_key <> ALL(%s)""",
                    (sid, plat, tgl, buckets))
                n_basi += cur.rowcount or 0

            ditulis = 0
            for (sid, plat, tgl, bucket), jml in sorted(terkumpul.items()):
                cur.execute("""
                    INSERT INTO l2_gold.audience_demographics_daily (
                        social_account_id, platform, audience_date,
                        audience_type, dimension_key, audience_count,
                        confidence, created_at, updated_at)
                    VALUES (%s,%s,%s,'age',%s,%s,%s,now(),now())
                    ON CONFLICT (social_account_id, platform, audience_date,
                                 audience_type, dimension_key)
                    DO UPDATE SET audience_count = EXCLUDED.audience_count,
                                  confidence     = EXCLUDED.confidence,
                                  updated_at     = now()
                    WHERE audience_demographics_daily.audience_count
                              IS DISTINCT FROM EXCLUDED.audience_count
                       OR audience_demographics_daily.confidence
                              IS DISTINCT FROM EXCLUDED.confidence
                """, (sid, plat, tgl, bucket, jml, CONF_TERUKUR))
                ditulis += 1

            cur.execute("""
                SELECT count(*) FROM l2_gold.audience_demographics_daily
                 WHERE audience_type = 'age'""")
            total_age = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return Output(
        ditulis,
        metadata={
            "baris_sumber": n_sumber,
            "baris_ditulis": ditulis,
            "baris_basi_dihapus": n_basi,
            "total_baris_age_di_l2": total_age,
            "akun": len(per_akun),
            "kolom_platform_terpakai": kol_platform,
            "kolom_tanggal_terpakai": kol_tanggal,
            "bucket_discovery": MetadataValue.text(" / ".join(BUCKET_AGE)),
            "bucket_tak_dikenal": MetadataValue.json(dict(tak_dikenal)),
            "catatan_55plus": MetadataValue.text(
                "Bucket 55-64 dan 65+ dari Instagram DIJUMLAHKAN jadi '55+', "
                "bukan diambil salah satu, supaya total per akun tetap utuh."),
            "confidence": MetadataValue.text(
                f"'{CONF_TERUKUR}' — tanpa awalan 'inferred_', karena angka "
                "ini dilaporkan platform. Baris gender di tabel yang sama "
                "berawalan 'inferred_' dan berasal dari jalur B."),
        },
    )


@asset(
    name="audience_age_measured",
    group_name=GROUP,
    deps=[AssetKey("audience_gold")],
    kinds={"postgres", "python"},
    description=(
        "l2_gold.audience_demographics_daily (audience_type='age') — umur "
        "AUDIENS terukur dari l1_silver.unified_audience (jalur A, Instagram "
        "Insights). Menyambung langkah L1→L2 yang selama ini tidak pernah "
        "dibangun: tanpa asset ini, data Insights berhenti di L1 meskipun "
        "sumbernya menyala. Bucket platform dipetakan ke enam bucket "
        "Discovery, 55-64 dan 65+ DIJUMLAHKAN jadi '55+'. confidence="
        "'measured', tanpa awalan 'inferred_'. Hari ini memproses 0 baris "
        "karena sumbernya masih kosong — dan TIDAK membuat data pengganti."
    ),
)
def audience_age_measured(postgres: PostgresResource) -> Output:
    return _tulis_age_terukur(postgres)


audience_assets = [audience_feature, audience_gold, audience_age_measured]
