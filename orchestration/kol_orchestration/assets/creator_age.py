"""Asset Age KREATOR: bio profil -> kolom `creator_age*` di kartu profil.

    l0_raw.ig_profile_apify.biography       -> l0_harmonization.instagram_profile
    l0_raw.tt_profile_apify.bio_description -> l0_harmonization.tiktok_profile
        -> l1_silver.unified_profile.bio
        -> l2_gold.kol_profile_card.bio   (+ cadangan langsung dari L0)
        -> creator_age_inference.ekstrak_umur()
        -> l2_gold.kol_profile_card.creator_age{,_birth_year,_band,_source,_confidence}

Bio kartu dipakai lebih dulu; bio L0 non-kosong terbaru hanya menambal akun
yang bio kartunya kosong. Lihat komentar di atas `SQL_BACA`.

Sejak 12 September 2026 ada sumber KEDUA, sebagai cadangan:

    l0_raw.kol_roster_import.influencer_no_ktp
        -> creator_age_nik.umur_per_akun()      (SELECT-nya di modul itu)
        -> kolom yang sama, creator_age_source = 'roster_ktp'

============================================================================
URUTAN PRIORITAS
============================================================================

    manual              diisi manusia. TIDAK PERNAH ditimpa; disaring keluar
                        sejak SQL_BACA, jadi bio-nya pun tidak ikut diproses.
    bio_self_declared   menang kapan pun bio menghasilkan umur.
    roster_ktp          hanya kalau bio tidak menghasilkan apa-apa.
    NULL                sisanya, dan itu tetap mayoritas.

Bio menang atas NIK BUKAN karena lebih akurat. NIK justru lebih tepat --
tanggal lahir sungguhan, bukan tebakan dari teks bebas. Yang membedakan
adalah ASALNYA: umur di bio adalah pernyataan yang kreatornya sendiri
terbitkan ke publik, sedangkan NIK diserahkan untuk keperluan administratif.
Kalau keduanya ada, yang pantas tampil di etalase adalah yang pertama.

Konsekuensi yang enak: jalur NIK tidak bisa MENGURANGI apa pun. Satu-satunya
baris yang disentuhnya adalah baris yang tanpa dia akan NULL.

============================================================================
NOMOR KTP TIDAK PERNAH MASUK KE FILE INI
============================================================================

`umur_per_akun()` melakukan query-nya SENDIRI di `creator_age_nik.py` dan
mengembalikan `{social_account_id: HasilNIK}`. Tidak ada satu pun nomor yang
melewati batas itu -- bukan sekadar "tidak ditulis ke tabel", tapi tidak
pernah hidup sebagai variabel di sini, sehingga tidak bisa ikut tercetak
lewat stack trace maupun metadata run.

Yang ditulis ke kartu hanya lima kolom umur yang sudah ada. Tidak ada kolom
untuk nomornya, dan migration 044 memverifikasi bahwa memang tidak ada.

============================================================================
KENAPA FILE SENDIRI, BUKAN DITUMPANGKAN KE audience.py ATAU gold_profile.py
============================================================================

Dua alasan, dan keduanya praktis.

  1. INI BUKAN FITUR AUDIENS. `audience.py` mengurus umur/gender/lokasi
     PENGIKUT. File ini mengurus umur ORANG KOL-nya. Menaruh keduanya di satu
     file adalah cara tercepat membuat orang berikutnya menyambungkan kolom
     yang salah -- persis kesalahan yang sudah pernah terjadi di proyek ini,
     saat satu filter UI bernama "Age" dibaca sebagai dua hal berbeda oleh dua
     dokumen audit.

  2. `gold_profile.py` SATU UPSERT SQL BESAR. Ekstraksi umur butuh Python
     (regex + VETO kontekstual), jadi ia tidak bisa ikut jadi ekspresi di CTE
     itu. Menyisipkannya akan memaksa asset kartu profil berhenti jadi murni
     SQL, dan itu harga yang tidak perlu dibayar untuk kolom yang mayoritas
     barisnya NULL.

Asset ini karena itu berjalan SETELAH `kol_profile_card` dan hanya
meng-UPDATE lima kolom miliknya sendiri. Ia tidak pernah INSERT baris, tidak
pernah menyentuh kolom lain, dan tidak pernah menyentuh tabel audiens.

============================================================================
BARIS `manual` TIDAK PERNAH DITIMPA
============================================================================

`WHERE creator_age_source IS DISTINCT FROM 'manual'` bukan kehati-hatian
berlebihan, melainkan syarat supaya fitur ini tidak merusak data.

Ekstraksi dari bio hampir selalu mengembalikan `unknown` -- 902 bio asli yang
diuji menghasilkan NOL umur. Kalau asset ini menulis apa adanya ke semua
baris, maka tiap kali dijalankan ia akan menimpa umur yang sudah diisi dan
diverifikasi manusia dengan NULL. Satu materialisasi rutin akan menghapus
seluruh pekerjaan manual tim.

============================================================================
`tahun_acuan` DICATAT, BUKAN DIBIARKAN IMPLISIT
============================================================================

Umur yang diturunkan dari tahun lahir bergantung pada tahun berapa asset ini
dijalankan. Tahun itu ikut dilaporkan di metadata run supaya angka di kolom
bisa ditelusuri ke run yang menghasilkannya, dan supaya jelas kapan
materialisasi ulang diperlukan (tiap pergantian tahun).
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

from dagster import AssetKey, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

# `creator_age_inference.py` ada di root project, satu level di atas folder
# orchestration/. Pola yang sama dipakai audience.py terhadap
# audience_inference.py -- aturannya hidup di satu tempat, bukan disalin ke
# dalam paket Dagster.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from creator_age_inference import SUMBER_MANUAL, ekstrak_umur  # noqa: E402
# Jalur NIK. Modul ini melakukan SELECT-nya SENDIRI dan hanya mengembalikan
# hasil yang sudah diurai -- nomor KTP tidak pernah sampai ke file ini, dan
# itu memang syaratnya. Lihat docstring `creator_age_nik`.
from creator_age_nik import SUMBER_NIK, nik_aktif, umur_per_akun  # noqa: E402

GROUP = "gold_profile"
_KARTU = AssetKey("kol_profile_card")

# Baris yang PUNYA bio perlu dibaca karena bisa menghasilkan umur. Baris yang
# bio-nya kosong TAPI sudah pernah menghasilkan umur juga perlu dibaca -- dan
# ini bukan kehalusan teoretis:
#
#   kreator mengganti bio-nya, kalimat "umur 24" hilang
#     -> tanpa cabang kedua, barisnya tidak pernah dibaca lagi
#     -> `creator_age` lama tetap berdiri selamanya, tanpa sumber yang
#        mendukungnya, dan ikut menyaring hasil Discovery
#
# Ini masalah yang sama dengan "baris basi" di `audience._tulis_gold`, dan
# jawabannya sama: yang sudah tidak lagi dihasilkan harus DICABUT, bukan
# dibiarkan.
#
# Baris bersumber `manual` disaring di sini juga, bukan cuma di UPDATE, supaya
# bio-nya tidak ikut diproses percuma.
# BIO L0 DIPAKAI SEBAGAI CADANGAN, BUKAN PENGGANTI
# ------------------------------------------------
# `kol_profile_card.bio` sudah merupakan bio L0 yang diturunkan lewat rantai
# yang utuh:
#
#     l0_raw.ig_profile_apify.biography      -> l0_harmonization.instagram_profile
#     l0_raw.tt_profile_apify.bio_description -> l0_harmonization.tiktok_profile
#         -> l1_silver.unified_profile.bio -> l2_gold.kol_profile_card.bio
#
# Jadi membaca kartu BUKAN sumber yang berbeda; ia sumber yang sama, sesudah
# dibersihkan dan dideduplikasi.
#
# Yang HILANG di kartu cuma satu hal, dan itu nyata: kartu memakai `DISTINCT ON
# ... ORDER BY p.date DESC` -- snapshot TERBARU per akun. Kalau kreator
# mengosongkan bio-nya di snapshot terakhir, kartu menyimpan NULL meskipun
# snapshot sebelumnya memuat "umur 24". Audit mencatat 1.873 bio dari 1.978
# profil; selisih 105 itu justru kelompok yang paling mungkin terdampak.
#
# Karena itu bio L0 non-kosong TERBARU ikut dibaca sebagai CADANGAN, dan hanya
# dipakai saat bio kartu kosong. Urutannya sengaja begitu, bukan sebaliknya:
# bio kartu adalah yang dipakai seluruh Discovery, dan umur yang ditampilkan di
# kartu harus bisa ditelusuri ke teks yang juga ada di kartu itu. L0 hanya
# menambal kasus di mana kartu memang tidak punya teks apa pun.
#
# `DISTINCT ON` + `btrim(...) <> ''` di dalam turunan: yang dicari adalah
# snapshot terbaru yang bio-nya BERISI, bukan snapshot terbaru yang kebetulan
# bio-nya kosong.
SQL_BACA = """
    WITH bio_l0_ig AS (
        SELECT DISTINCT ON (r.social_account_id)
               r.social_account_id, r.biography AS bio
          FROM l0_raw.ig_profile_apify r
         WHERE r.social_account_id IS NOT NULL
           AND r.biography IS NOT NULL AND btrim(r.biography) <> ''
         ORDER BY r.social_account_id, r.fetched_at DESC NULLS LAST, r.id DESC
    ),
    bio_l0_tt AS (
        SELECT DISTINCT ON (r.social_account_id)
               r.social_account_id, r.bio_description AS bio
          FROM l0_raw.tt_profile_apify r
         WHERE r.social_account_id IS NOT NULL
           AND r.bio_description IS NOT NULL AND btrim(r.bio_description) <> ''
         ORDER BY r.social_account_id, r.fetched_at DESC NULLS LAST, r.id DESC
    )
    SELECT k.social_account_id,
           coalesce(nullif(btrim(k.bio), ''),
                    nullif(btrim(ig.bio), ''),
                    nullif(btrim(tt.bio), '')) AS bio,
           CASE WHEN nullif(btrim(k.bio), '') IS NOT NULL THEN 'kartu'
                WHEN nullif(btrim(ig.bio), '') IS NOT NULL THEN 'l0_ig'
                WHEN nullif(btrim(tt.bio), '') IS NOT NULL THEN 'l0_tt'
           END AS asal_bio
      FROM l2_gold.kol_profile_card k
      LEFT JOIN bio_l0_ig ig ON ig.social_account_id = k.social_account_id
      LEFT JOIN bio_l0_tt tt ON tt.social_account_id = k.social_account_id
     WHERE k.creator_age_source IS DISTINCT FROM %(manual)s
       AND (coalesce(nullif(btrim(k.bio), ''),
                     nullif(btrim(ig.bio), ''),
                     nullif(btrim(tt.bio), '')) IS NOT NULL
         OR k.creator_age IS NOT NULL
         OR k.creator_age_source IS NOT NULL
         -- Kartu yang TIDAK punya bio sama sekali tapi punya umur dari NIK
         -- harus ikut terbaca, kalau tidak jalur NIK tidak pernah sampai ke
         -- mereka. Daftar akunnya dioper sebagai parameter, BUKAN dicari
         -- lewat subquery ke kolom NIK: satu-satunya SELECT yang menyentuh
         -- kolom itu ada di `creator_age_nik.umur_per_akun`, dan menambah
         -- yang kedua di sini akan menghapus jaminan itu tanpa alasan.
         OR k.social_account_id = ANY(%(sid_nik)s::uuid[]))
"""

# `IS DISTINCT FROM` di WHERE menjaga idempotensi: baris yang hasilnya tidak
# berubah tidak ikut ditulis, jadi `updated_at` tidak bergerak tanpa alasan.
# Pola yang sama dipakai seluruh L2.
SQL_UPDATE = """
    UPDATE l2_gold.kol_profile_card
       SET creator_age            = %(umur)s,
           creator_birth_year     = %(tahun_lahir)s,
           creator_age_band       = %(band)s,
           creator_age_source     = %(source)s,
           creator_age_confidence = %(confidence)s,
           updated_at             = now()
     WHERE social_account_id  = %(sid)s
       AND creator_age_source IS DISTINCT FROM %(manual)s
       AND (creator_age            IS DISTINCT FROM %(umur)s
         OR creator_birth_year     IS DISTINCT FROM %(tahun_lahir)s
         OR creator_age_band       IS DISTINCT FROM %(band)s
         OR creator_age_source     IS DISTINCT FROM %(source)s
         OR creator_age_confidence IS DISTINCT FROM %(confidence)s)
"""


def _jalankan(postgres: PostgresResource) -> Output:
    tahun_acuan = date.today().year
    aktif_nik = nik_aktif()
    conn = postgres.get_conn()
    try:
        with conn.cursor() as cur:
            # NIK dibaca LEBIH DULU, dan oleh modulnya sendiri. Yang kembali
            # ke sini hanya `{social_account_id: HasilNIK}` -- tidak ada satu
            # pun nomor. Daftar akunnya juga dipakai memperluas SQL_BACA
            # supaya kartu tanpa bio tetap terbaca.
            if aktif_nik:
                umur_nik, stat_nik = umur_per_akun(conn, tahun_acuan=tahun_acuan)
            else:
                umur_nik, stat_nik = {}, {"status": "dimatikan lewat "
                                                    "CREATOR_AGE_NIK_ENABLED"}

            cur.execute(SQL_BACA, {"manual": SUMBER_MANUAL,
                                   "sid_nik": list(umur_nik)})
            baris = cur.fetchall()

            diperiksa = len(baris)
            ditulis = 0
            per_band: Counter = Counter()
            per_confidence: Counter = Counter()
            per_source: Counter = Counter()
            per_asal_bio: Counter = Counter()
            asal_bio_yang_berhasil: Counter = Counter()
            diketahui = 0
            n_dari_bio = 0
            n_dari_nik = 0
            n_nik_kalah_dari_bio = 0
            n_ada_bio = 0
            contoh: list[str] = []

            for sid, bio, asal_bio in baris:
                if asal_bio:
                    per_asal_bio[asal_bio] += 1
                    n_ada_bio += 1

                # ----- URUTAN PRIORITAS, DITEGAKKAN DI SINI ----------------
                #
                #   manual             disaring di SQL; tidak pernah sampai ke sini
                #   bio_self_declared  menang kapan pun ia menghasilkan umur
                #   roster_ktp         hanya kalau bio tidak menghasilkan apa-apa
                #   NULL               sisanya
                #
                # Urutan bio-di-atas-NIK bukan soal akurasi -- NIK justru lebih
                # tepat, sampai ke tanggal. Ia soal ASAL: umur di bio adalah
                # pernyataan yang kreatornya sendiri terbitkan ke publik,
                # sedangkan NIK diserahkan untuk keperluan administratif.
                # Kalau keduanya ada, yang pantas tampil di etalase adalah yang
                # pertama.
                #
                # Praktisnya ini juga yang membuat jalur NIK tidak bisa
                # MENGURANGI apa pun: satu-satunya baris yang disentuhnya
                # adalah baris yang tanpa dia akan NULL.
                hasil = ekstrak_umur(bio, tahun_acuan=tahun_acuan)
                hasil_nik = umur_nik.get(sid)

                if hasil.diketahui:
                    if hasil_nik is not None:
                        n_nik_kalah_dari_bio += 1
                    n_dari_bio += 1
                    asal_bio_yang_berhasil[asal_bio or "?"] += 1
                    if len(contoh) < 5:
                        contoh.append(f"{hasil.umur} th ({hasil.confidence}, "
                                      f"bio dari {asal_bio}) — {hasil.alasan}")
                elif hasil_nik is not None:
                    hasil = hasil_nik
                    n_dari_nik += 1

                if hasil.diketahui:
                    diketahui += 1
                    per_band[hasil.band] += 1
                    per_confidence[hasil.confidence] += 1
                    per_source[hasil.source] += 1

                cur.execute(SQL_UPDATE, {
                    "sid": sid,
                    "umur": hasil.umur,
                    "tahun_lahir": hasil.tahun_lahir,
                    "band": hasil.band,
                    "source": hasil.source,
                    "confidence": hasil.confidence,
                    "manual": SUMBER_MANUAL,
                })
                ditulis += cur.rowcount or 0

            # Baris `manual` dihitung terpisah supaya metadata menunjukkan
            # bahwa kolom ini punya dua pengisi, dan berapa banyak yang datang
            # dari jalur yang TIDAK disentuh asset ini.
            cur.execute(
                "SELECT count(*) FROM l2_gold.kol_profile_card "
                "WHERE creator_age_source = %s", (SUMBER_MANUAL,))
            n_manual = cur.fetchone()[0]

            cur.execute(
                "SELECT count(*) FROM l2_gold.kol_profile_card "
                "WHERE creator_age IS NOT NULL")
            n_terisi = cur.fetchone()[0]

            # Sebaran akhir dibaca dari TABEL, bukan dari hitungan di memori.
            # Keduanya harus sama; kalau suatu saat berbeda, yang benar adalah
            # tabel, dan selisihnya berarti ada baris yang tidak tertulis.
            cur.execute(
                "SELECT creator_age_source, count(*) "
                "FROM l2_gold.kol_profile_card "
                "WHERE creator_age IS NOT NULL GROUP BY 1")
            source_di_tabel = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute(
                "SELECT creator_age_band, count(*) "
                "FROM l2_gold.kol_profile_card "
                "WHERE creator_age_band IS NOT NULL GROUP BY 1")
            band_di_tabel = {r[0]: r[1] for r in cur.fetchall()}
        conn.commit()
    finally:
        conn.close()

    unknown = diperiksa - diketahui
    return Output(
        n_terisi,
        metadata={
            "baris_diperiksa": diperiksa,
            "punya_bio": n_ada_bio,
            "tanpa_bio": diperiksa - n_ada_bio,
            "umur_ditemukan": diketahui,
            "unknown": unknown,
            "unknown_pct": round(unknown / diperiksa * 100, 2) if diperiksa else None,
            "baris_diupdate": ditulis,
            "umur_dari_bio": n_dari_bio,
            "umur_dari_nik": n_dari_nik,
            "nik_kalah_dari_bio": n_nik_kalah_dari_bio,
            "nik_aktif": aktif_nik,
            "nik_statistik": MetadataValue.json(stat_nik),
            "sebaran_source": MetadataValue.json(dict(per_source)),
            "sebaran_source_di_tabel": MetadataValue.json(source_di_tabel),
            "sebaran_band_di_tabel": MetadataValue.json(band_di_tabel),
            "asal_bio": MetadataValue.json(dict(per_asal_bio)),
            "asal_bio_yang_menghasilkan_umur": MetadataValue.json(
                dict(asal_bio_yang_berhasil)),
            "total_terisi_di_kartu": n_terisi,
            "bersumber_manual_tidak_disentuh": n_manual,
            "tahun_acuan": tahun_acuan,
            "sebaran_band": MetadataValue.json(dict(per_band)),
            "sebaran_confidence": MetadataValue.json(dict(per_confidence)),
            "contoh": MetadataValue.text(
                "\n".join(contoh) if contoh else "tidak ada satu pun umur ditemukan"),
            "nomor_ktp_tidak_pernah_disimpan": MetadataValue.text(
                "Jalur `roster_ktp` menulis HANYA umur, tahun lahir, band, "
                "source, dan confidence. Nomor KTP-nya berhenti di "
                "creator_age_nik.umur_per_akun(), yang melakukan SELECT-nya "
                "sendiri dan hanya mengembalikan hasil terurai — file asset "
                "ini tidak pernah memegang satu pun nomor, jadi ia juga tidak "
                "bisa bocor lewat stack trace maupun metadata run. Tidak ada "
                "kolom KTP/NIK di kol_profile_card, dan migration 044 "
                "memverifikasi bahwa memang tidak ada."),
            "urutan_prioritas": MetadataValue.text(
                "manual (tidak pernah ditimpa) > bio_self_declared > "
                "roster_ktp > NULL. NIK hanya mengisi baris yang tanpa dia "
                "akan NULL, jadi ia tidak bisa mengurangi apa pun. "
                "`nik_kalah_dari_bio` menghitung akun yang punya KEDUANYA dan "
                "bio-nya yang dipakai."),
            "kenapa_unknown_itu_normal": MetadataValue.text(
                "Platform tidak mengekspos umur kreator, jadi satu-satunya "
                "sumber otomatis adalah teks bio. Terhadap 902 bio asli yang "
                "diuji, extractor ini mengembalikan NOL umur — dan itu "
                "jawaban yang benar: 'ada tahun di bio' hanya ~3% benar "
                "sebagai tahun lahir (sisanya tahun penghargaan, tahun "
                "berdiri brand, nomor telepon, dan tanggal lahir ANAK si "
                "kreator). Pengisian nyata diharapkan datang dari jalur "
                "'manual' atau sumber baru yang memang memuat tanggal lahir."
            ),
            "bukan_age_audience": MetadataValue.text(
                "Asset ini TIDAK menyentuh l2_gold.audience_demographics_daily. "
                "Umur AUDIENS diisi asset `audience_age_measured` dari "
                "l1_silver.unified_audience — fitur terpisah, tabel terpisah."
            ),
        },
    )


@asset(
    name="creator_age",
    group_name=GROUP,
    deps=[_KARTU],
    kinds={"postgres", "python"},
    description=(
        "l2_gold.kol_profile_card.creator_age* — umur KREATOR (bukan audiens), "
        "diekstrak dari bio profil (kartu, dengan cadangan bio L0 terbaru dari "
        "ig_profile_apify.biography / tt_profile_apify.bio_description) "
        "memakai aturan ketat di "
        "creator_age_inference.py. Hanya pernyataan eksplisit yang diterima "
        "('umur 24', 'lahir 1998'); tahun telanjang di bio SENGAJA ditolak "
        "karena hanya ~3% benar sebagai tahun lahir. Mayoritas baris "
        "menghasilkan NULL, dan itu hasil yang benar. Baris bersumber "
        "'manual' tidak pernah ditimpa. Sejak migration 044, "
        "l0_raw.kol_roster_import.influencer_no_ktp dipakai sebagai sumber "
        "CADANGAN (creator_age_source='roster_ktp') hanya untuk baris yang "
        "bio-nya tidak menghasilkan umur — bio selalu menang. Nomor KTP-nya "
        "tidak pernah disimpan, di-log, maupun keluar dari creator_age_nik.py."
    ),
)
def creator_age(postgres: PostgresResource) -> Output:
    return _jalankan(postgres)


creator_age_assets = [creator_age]
