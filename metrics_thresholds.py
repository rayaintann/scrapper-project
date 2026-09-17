"""Ambang KERJA untuk metric turunan — SATU tempat, dua bentuk.

============================================================================
KENAPA FILE INI ADA
============================================================================

Lima metric di bawah bukan pengukuran, melainkan PELABELAN atas angka yang
sudah diukur: Growth Classification melabeli `followers_growth`, Monitoring
Priority melabeli engagement rate, dan seterusnya. Rumusnya sepele; yang
tidak sepele adalah ANGKA AMBANGNYA.

Dan angka-angka itu **sementara**. Semuanya ditandai sebagai *working
threshold*, bukan kesepakatan bisnis final — jadi pertanyaan yang menentukan
desain file ini bukan "bagaimana menghitungnya" melainkan "berapa tempat yang
harus disentuh saat angkanya berubah". Jawabannya harus: satu.

Karena itu tiap ambang hidup SEKALI di sini, dan dari sini diturunkan ke dua
bentuk yang dibutuhkan:

    klasifikasi_*()   fungsi Python   -- dipakai test, dan sebagai acuan
    sql_*()           ekspresi SQL    -- dipakai gold_profile.py mengisi L2,
                                         dan jalur baca db.py

Keduanya digenerate dari konstanta yang SAMA, jadi tidak mungkin bergeser
diam-diam. `tests/test_metrics_thresholds.py` menguji keduanya atas nilai
batas yang identik; kalau seseorang mengubah salah satu saja, test itu gagal.

============================================================================
KENAPA HASILNYA DISIMPAN DI L2, PADAHAL AMBANGNYA SEMENTARA
============================================================================

Menyimpan label ke `l2_gold.kol_profile_card` berarti mengubah ambang menuntut
materialisasi ulang asset. Itu biaya yang nyata, dan alternatifnya —
menghitung label saat dibaca — terdengar lebih murah.

Alternatif itu ditolak karena UI (Next.js) query Postgres LANGSUNG. Kalau
label hanya ada saat-baca di db.py, satu-satunya cara UI bisa MEMFILTER dan
MENGURUTKAN berdasarkan label adalah menyalin CASE-nya ke repo lain. Ambangnya
lalu hidup di dua repo, dan syarat "centralized, easy to change" langsung
hilang. Satu perintah materialisasi jauh lebih murah daripada itu.

============================================================================
NULL BUKAN KATEGORI
============================================================================

Seluruh fungsi mengembalikan None kalau masukannya None. Tidak ada label
"Unknown", tidak ada jatuh ke kategori terendah. `growth_pct` NULL berarti
akun itu belum punya dua snapshot — bukan berarti pertumbuhannya buruk, dan
melabelinya "Negative Growth" akan mengubah ketiadaan data menjadi tuduhan.
Aturan yang sama berlaku untuk keempat lainnya.
"""

from __future__ import annotations

# ===========================================================================
# 1. GROWTH CLASSIFICATION  <- l2_gold.kol_profile_card.followers_growth (%)
# ===========================================================================
# >= 10%       High Growth        (10 tepat masuk High, sesuai spesifikasi)
# 5% .. < 10%  Medium Growth
# 0% .. < 5%   Low Growth
# < 0%         Negative Growth
GROWTH_HIGH_MIN = 10.0
GROWTH_MEDIUM_MIN = 5.0
GROWTH_LOW_MIN = 0.0

GROWTH_HIGH = "High Growth"
GROWTH_MEDIUM = "Medium Growth"
GROWTH_LOW = "Low Growth"
GROWTH_NEGATIVE = "Negative Growth"


def klasifikasi_growth(growth_pct: float | None) -> str | None:
    """Label pertumbuhan dari Growth %, atau None kalau belum bisa dihitung."""
    if growth_pct is None:
        return None
    if growth_pct >= GROWTH_HIGH_MIN:
        return GROWTH_HIGH
    if growth_pct >= GROWTH_MEDIUM_MIN:
        return GROWTH_MEDIUM
    if growth_pct >= GROWTH_LOW_MIN:
        return GROWTH_LOW
    return GROWTH_NEGATIVE


def sql_growth_class(kolom: str = "followers_growth") -> str:
    return f"""CASE
        WHEN {kolom} IS NULL                    THEN NULL
        WHEN {kolom} >= {GROWTH_HIGH_MIN}       THEN '{GROWTH_HIGH}'
        WHEN {kolom} >= {GROWTH_MEDIUM_MIN}     THEN '{GROWTH_MEDIUM}'
        WHEN {kolom} >= {GROWTH_LOW_MIN}        THEN '{GROWTH_LOW}'
        ELSE '{GROWTH_NEGATIVE}'
    END"""


# ===========================================================================
# 2. GENDER RELIABILITY  <- gender_known_pct (%)
# ===========================================================================
# Ini BUKAN penilaian atas creator-nya, melainkan atas DATA-nya: seberapa
# besar bagian audiens yang gendernya berhasil diketahui. Female %/Male %
# tetap dihitung apa adanya (unknown dikeluarkan dari penyebut); kolom ini
# yang memberi tahu seberapa jauh angka itu boleh dipercaya.
GENDER_HIGH_MIN = 70.0
GENDER_MEDIUM_MIN = 40.0

TINGKAT_HIGH = "High"
TINGKAT_MEDIUM = "Medium"
TINGKAT_LOW = "Low"


def klasifikasi_gender(gender_known_pct: float | None) -> str | None:
    if gender_known_pct is None:
        return None
    if gender_known_pct >= GENDER_HIGH_MIN:
        return TINGKAT_HIGH
    if gender_known_pct >= GENDER_MEDIUM_MIN:
        return TINGKAT_MEDIUM
    return TINGKAT_LOW


def sql_gender_reliability(kolom: str = "gender_known_pct") -> str:
    return f"""CASE
        WHEN {kolom} IS NULL                 THEN NULL
        WHEN {kolom} >= {GENDER_HIGH_MIN}    THEN '{TINGKAT_HIGH}'
        WHEN {kolom} >= {GENDER_MEDIUM_MIN}  THEN '{TINGKAT_MEDIUM}'
        ELSE '{TINGKAT_LOW}'
    END"""


# ===========================================================================
# 3. POST FREQUENCY RELIABILITY  <- observation_days + valid_post_count
# ===========================================================================
# Dua syarat, bukan satu. Alasannya konkret: satu akun di data sekarang
# menghasilkan 150 post/bulan dari 10 post dalam 2 HARI. Aritmetikanya benar,
# tapi mengekstrapolasi dua hari menjadi sebulan adalah tebakan. Ambang
# `observation_days` yang menangkapnya; ambang `valid_post_count` menangkap
# kebalikannya — rentang panjang dengan sampel terlalu sedikit.
FREQ_HIGH_HARI = 30
FREQ_HIGH_POST = 10
FREQ_MEDIUM_HARI = 14
FREQ_MEDIUM_POST = 5


def klasifikasi_post_frequency(observation_days: int | None,
                               valid_post_count: int | None) -> str | None:
    """None kalau tidak ada data post sama sekali.

    `Low` BUKAN nilai bawaan: ia hanya diberikan kalau memang ADA post yang
    terhitung. Akun tanpa satu pun post valid mendapat None -- "belum bisa
    dinilai", bukan "tidak bisa diandalkan".
    """
    if valid_post_count is None or valid_post_count <= 0:
        return None
    hari = observation_days if observation_days is not None else 0
    if hari >= FREQ_HIGH_HARI and valid_post_count >= FREQ_HIGH_POST:
        return TINGKAT_HIGH
    if hari >= FREQ_MEDIUM_HARI and valid_post_count >= FREQ_MEDIUM_POST:
        return TINGKAT_MEDIUM
    return TINGKAT_LOW


def sql_post_frequency_reliability(kol_hari: str = "observation_days",
                                   kol_post: str = "post_frequency_count") -> str:
    return f"""CASE
        WHEN {kol_post} IS NULL OR {kol_post} <= 0 THEN NULL
        WHEN COALESCE({kol_hari}, 0) >= {FREQ_HIGH_HARI}
         AND {kol_post} >= {FREQ_HIGH_POST}        THEN '{TINGKAT_HIGH}'
        WHEN COALESCE({kol_hari}, 0) >= {FREQ_MEDIUM_HARI}
         AND {kol_post} >= {FREQ_MEDIUM_POST}      THEN '{TINGKAT_MEDIUM}'
        ELSE '{TINGKAT_LOW}'
    END"""


# ===========================================================================
# 4. MONITORING PRIORITY  <- engagement rate (%)
# ===========================================================================
# SEMENTARA memakai ER sebagai satu-satunya sinyal. Rule produk yang
# sebenarnya (campaign aktif, monitoring aktif, akses terakhir) diuji di
# docs/KOL_DISCOVERY_MONITORING_PRIORITY_AUDIT.md dan nol dari enam sinyalnya
# punya data — jadi ER dipakai sebagai pengganti sadar, bukan sebagai
# penafsiran ulang rule-nya.
#
# ER yang dipakai adalah ER yang SUDAH ADA di feature.*_engagement_analysis.
# Tidak ada ER kedua yang dihitung di sini.
PRIORITY_HIGH_MIN = 5.0
PRIORITY_MEDIUM_MIN = 2.0


def klasifikasi_monitoring(er_pct: float | None) -> str | None:
    """None kalau ER belum diketahui. NULL TIDAK sama dengan Low."""
    if er_pct is None:
        return None
    if er_pct >= PRIORITY_HIGH_MIN:
        return TINGKAT_HIGH
    if er_pct >= PRIORITY_MEDIUM_MIN:
        return TINGKAT_MEDIUM
    return TINGKAT_LOW


def sql_monitoring_priority(kolom: str = "engagement_rate") -> str:
    return f"""CASE
        WHEN {kolom} IS NULL                    THEN NULL
        WHEN {kolom} >= {PRIORITY_HIGH_MIN}     THEN '{TINGKAT_HIGH}'
        WHEN {kolom} >= {PRIORITY_MEDIUM_MIN}   THEN '{TINGKAT_MEDIUM}'
        ELSE '{TINGKAT_LOW}'
    END"""


# ===========================================================================
# Daftar nilai sah — dipakai UI untuk membangun pilihan filter kategori,
# supaya daftar pilihannya tidak diketik ulang di sana.
# ===========================================================================
NILAI_GROWTH_CLASS = (GROWTH_HIGH, GROWTH_MEDIUM, GROWTH_LOW, GROWTH_NEGATIVE)
NILAI_TINGKAT = (TINGKAT_HIGH, TINGKAT_MEDIUM, TINGKAT_LOW)

#: Ringkasan seluruh ambang, untuk dilaporkan di metadata asset supaya nilai
#: yang BENAR-BENAR dipakai satu run terlihat tanpa membuka kode.
RINGKASAN_AMBANG = {
    "growth_class": f">={GROWTH_HIGH_MIN} High / >={GROWTH_MEDIUM_MIN} Medium / "
                    f">={GROWTH_LOW_MIN} Low / sisanya Negative",
    "gender_reliability": f">={GENDER_HIGH_MIN} High / >={GENDER_MEDIUM_MIN} Medium / sisanya Low",
    "post_frequency_reliability":
        f"High: hari>={FREQ_HIGH_HARI} & post>={FREQ_HIGH_POST}; "
        f"Medium: hari>={FREQ_MEDIUM_HARI} & post>={FREQ_MEDIUM_POST}; sisanya Low",
    "monitoring_priority": f">={PRIORITY_HIGH_MIN} High / >={PRIORITY_MEDIUM_MIN} Medium / sisanya Low",
}


# ===========================================================================
# 5. AUDIENCE QUALITY  <- feature.*_audience_analysis.audience_quality_score
# ===========================================================================
# Skornya SUDAH ADA dan sudah terisi untuk seluruh 27 akun yang punya data
# follower (`audience_inference.skor_kualitas`); yang belum ada hanyalah
# pelabelannya. Rentang nyata pada data sekarang 54..94.
#
# ASUMSI YANG DIPAKAI, karena ambangnya belum pernah ditetapkan bisnis:
# skornya berskala 0..100, jadi ambang dipasang di sepertiga atas dan tengah
# skala (>=75, >=50). Itu pembagian yang bisa dipertahankan tanpa mengarang
# angka "ajaib", dan sengaja TIDAK dikalibrasi ke sebaran 27 akun yang ada --
# mengambang ambang mengikuti sampel sekecil itu akan berubah tiap kali satu
# akun baru masuk.
QUALITY_HIGH_MIN = 75.0
QUALITY_MEDIUM_MIN = 50.0


def klasifikasi_audience_quality(skor: float | None) -> str | None:
    if skor is None:
        return None
    if skor >= QUALITY_HIGH_MIN:
        return TINGKAT_HIGH
    if skor >= QUALITY_MEDIUM_MIN:
        return TINGKAT_MEDIUM
    return TINGKAT_LOW


def sql_audience_quality_tier(kolom: str = "audience_quality_score") -> str:
    return f"""CASE
        WHEN {kolom} IS NULL                  THEN NULL
        WHEN {kolom} >= {QUALITY_HIGH_MIN}    THEN '{TINGKAT_HIGH}'
        WHEN {kolom} >= {QUALITY_MEDIUM_MIN}  THEN '{TINGKAT_MEDIUM}'
        ELSE '{TINGKAT_LOW}'
    END"""


# ===========================================================================
# 6. PERFORMANCE STABILITY  <- simpangan baku ER historis
# ===========================================================================
# SATUANNYA POIN PERSEN, dan ini bukan detail sepele.
# `l2_gold.kol_metric_daily.er_followers_daily` disimpan sebagai FRAKSI
# (0,0000164 .. 0,1615), sedangkan `feature.*_engagement_analysis.engagement_rate`
# disimpan sebagai PERSEN (0,00 .. 16,15) -- data yang sama, beda 100x.
# Menghitung simpangan baku atas fraksi lalu membandingkannya dengan ambang
# "1%" akan menyatakan SEMUA akun stabil, karena 0,01 fraksi = 1 poin persen.
# Karena itu ER harian DIKALI 100 lebih dulu, dan ambang di bawah dibaca
# sebagai poin persen.
STABILITY_HIGH_MAX = 1.0     # SD <= 1 poin persen
STABILITY_MEDIUM_MAX = 3.0   # 1 < SD <= 3
STABILITY_MIN_PERIODE = 3    # < 3 periode -> NULL, bukan "stabil"

STABIL_HIGH = "High Stability"
STABIL_MEDIUM = "Medium Stability"
STABIL_LOW = "Low Stability"


def klasifikasi_stability(sd_poin_persen: float | None,
                          jumlah_periode: int | None) -> str | None:
    """None kalau periodenya kurang dari tiga.

    Dua titik selalu punya simpangan baku, dan angkanya selalu terlihat kecil
    -- melabelinya "High Stability" akan menjual kekurangan data sebagai
    konsistensi. Tiga adalah minimum yang disepakati.
    """
    if jumlah_periode is None or jumlah_periode < STABILITY_MIN_PERIODE:
        return None
    if sd_poin_persen is None:
        return None
    if sd_poin_persen <= STABILITY_HIGH_MAX:
        return STABIL_HIGH
    if sd_poin_persen <= STABILITY_MEDIUM_MAX:
        return STABIL_MEDIUM
    return STABIL_LOW


def sql_stability(kol_sd: str = "er_stddev_pp",
                  kol_n: str = "er_periods") -> str:
    return f"""CASE
        WHEN {kol_n} IS NULL OR {kol_n} < {STABILITY_MIN_PERIODE} THEN NULL
        WHEN {kol_sd} IS NULL                    THEN NULL
        WHEN {kol_sd} <= {STABILITY_HIGH_MAX}    THEN '{STABIL_HIGH}'
        WHEN {kol_sd} <= {STABILITY_MEDIUM_MAX}  THEN '{STABIL_MEDIUM}'
        ELSE '{STABIL_LOW}'
    END"""


# ===========================================================================
# 7. VIRAL FREQUENCY  <- views post vs median views creator
# ===========================================================================
# Pengali RELATIF, bukan ambang views absolut: 100.000 views luar biasa untuk
# akun nano dan biasa saja untuk akun mega, jadi angka absolut hanya akan
# menemukan akun besar. Median dipakai sebagai acuan, bukan rata-rata --
# rata-rata sudah tertarik oleh post viral yang justru sedang dicari.
VIRAL_MULTIPLIER = 3.0


# ===========================================================================
# 8. RISING CREATOR  <- Growth %
# ===========================================================================
# Memakai batas Medium Growth yang SUDAH ada di atas, bukan angka sendiri.
# Ambang lama 5,5% dari prototype sengaja tidak dipakai lagi.
RISING_MIN = GROWTH_MEDIUM_MIN   # 5.0


def rising_creator(growth_pct: float | None) -> bool | None:
    """None kalau Growth belum terukur -- bukan False.

    False berarti "diukur, dan tidak naik cukup". None berarti "belum bisa
    dijawab". Filter yang menyamakan keduanya akan menyembunyikan creator
    yang belum pernah di-scrape dua kali seolah mereka gagal tumbuh.
    """
    if growth_pct is None:
        return None
    return growth_pct >= RISING_MIN


def sql_rising_creator(kolom: str = "followers_growth") -> str:
    return f"""CASE WHEN {kolom} IS NULL THEN NULL
                    ELSE ({kolom} >= {RISING_MIN}) END"""


NILAI_STABILITAS = (STABIL_HIGH, STABIL_MEDIUM, STABIL_LOW)

RINGKASAN_AMBANG.update({
    "audience_quality": f">={QUALITY_HIGH_MIN} High / >={QUALITY_MEDIUM_MIN} Medium / sisanya Low",
    "performance_stability":
        f"SD<={STABILITY_HIGH_MAX}pp High / <={STABILITY_MEDIUM_MAX}pp Medium / "
        f"sisanya Low; <{STABILITY_MIN_PERIODE} periode -> NULL",
    "viral_frequency": f"post viral = views >= {VIRAL_MULTIPLIER}x median views creator",
    "rising_creator": f"Growth >= {RISING_MIN}%",
})


# ===========================================================================
# 9. BUCKET UMUR  <- dipakai DUA fitur yang berbeda
# ===========================================================================
# Ini SATU-SATUNYA hal yang dipakai bersama oleh Age Kreator dan Age Audience.
# Keduanya tetap fitur terpisah -- sumber berbeda, tabel berbeda, asset
# berbeda, test berbeda -- tapi DAFTAR BUCKET-nya wajib sama, karena Discovery
# merender satu baris chip yang sama untuk keduanya. Kalau daftarnya diketik
# dua kali, cepat atau lambat salah satu bergeser dan chip "45+" di satu
# filter berarti hal yang berbeda dari chip "45+" di filter sebelahnya.
#
# KENAPA 45+ DIGABUNG, DAN KENAPA DULU BUKAN BEGITU
# -------------------------------------------------
# Versi pertama daftar ini punya ENAM bucket, dengan `45-54` dan `55+`
# terpisah, karena itu bentuk mentah yang dikirim Instagram Insights. Spesifikasi
# Discovery yang final hanya memakai LIMA chip, dan bucket teratasnya `45+`.
#
# Instagram Insights tetap mengirim TUJUH bucket: 13-17, 18-24, 25-34, 35-44,
# 45-54, 55-64, 65+. Tiga bucket teratas karena itu DIJUMLAHKAN jadi `45+` --
# dijumlahkan, bukan diambil salah satu. Mengambil salah satu akan membuang
# audiens 55+ diam-diam dan membuat total per akun tidak lagi sama dengan
# jumlah follower yang dilaporkan platform.
#
# Penggabungan hanya terjadi ke ATAS dan hanya di bucket paling atas, jadi
# tidak ada audiens yang berpindah kelompok umur: siapa pun yang dulu masuk
# `45-54` atau `55+` memang berumur 45 tahun ke atas.
BUCKET_AGE = ("13-17", "18-24", "25-34", "35-44", "45+")

#: Batas bawah tiap bucket, dipakai `bucket_age`. Batas atas bucket ke-n
#: adalah batas bawah bucket ke-(n+1) dikurangi satu; ditulis sebagai batas
#: bawah saja supaya tidak ada celah maupun tumpang tindih yang bisa muncul
#: dari dua angka yang diketik terpisah.
BATAS_BAWAH_AGE = (13, 18, 25, 35, 45)

#: Kunci untuk audiens yang umurnya TIDAK diketahui. Bukan anggota
#: `BUCKET_AGE` -- ia bukan kelompok umur, melainkan penyebut yang membuat
#: kelima bucket lain bisa dibaca dengan jujur. Disimpan sebagai baris
#: tersendiri di `audience_demographics_daily`, dan DIKELUARKAN dari setiap
#: perhitungan "bucket dominan" (lihat `sql_filter_audience_age_band`).
AGE_UNKNOWN = "unknown"

#: Umur di luar rentang ini ditolak. 13 adalah umur minimum akun Instagram dan
#: TikTok, jadi umur di bawahnya hampir pasti salah baca (tanggal lahir anak,
#: nomor rumah, ukuran baju). 80 dipilih sebagai batas atas yang longgar:
#: bukan mustahil, tapi di atasnya jauh lebih mungkin salah baca daripada
#: benar.
AGE_MIN = 13
AGE_MAX = 80

#: Bucket mentah platform -> bucket Discovery. Hanya dua yang perlu dipetakan;
#: sisanya identik dan sengaja ikut ditulis supaya tabel ini bisa dibaca
#: sebagai daftar lengkap tanpa pembaca harus menebak mana yang hilang.
PETA_BUCKET_PLATFORM = {
    "13-17": "13-17",
    "18-24": "18-24",
    "25-34": "25-34",
    "35-44": "35-44",
    # Tiga teratas runtuh jadi satu. Nilainya DIJUMLAHKAN oleh pemanggil
    # (`agregasi_bucket_age`), tidak saling menimpa -- lihat komentar di sana.
    "45-54": "45+",
    "55-64": "45+",
    "65+": "45+",
}


def bucket_age(umur: int | None) -> str | None:
    """Umur (tahun) -> salah satu `BUCKET_AGE`. None kalau di luar `AGE_MIN..AGE_MAX`.

    None BUKAN "umur tidak diketahui berarti muda". Pemanggil yang menerima
    None harus menyimpan `unknown`/NULL, bukan menjatuhkannya ke bucket mana
    pun.
    """
    if umur is None:
        return None
    try:
        umur = int(umur)
    except (TypeError, ValueError):
        return None
    if umur < AGE_MIN or umur > AGE_MAX:
        return None
    hasil = BUCKET_AGE[0]
    for batas, nama in zip(BATAS_BAWAH_AGE, BUCKET_AGE):
        if umur >= batas:
            hasil = nama
    return hasil


def normalisasi_bucket_platform(label: str | None) -> str | None:
    """Bucket mentah Insights -> bucket Discovery. None kalau tidak dikenal.

    None sengaja TIDAK jatuh ke bucket terdekat. Bucket yang tidak dikenal
    berarti platform mengubah skemanya, dan menebak padanannya akan
    memindahkan audiens ke kelompok umur yang salah tanpa jejak. Pemanggil
    menghitung yang tak dikenal sebagai baris yang dilewati, dan melaporkannya.
    """
    if not label:
        return None
    return PETA_BUCKET_PLATFORM.get(str(label).strip().lower().replace(" ", ""))


def sql_creator_age_band(kolom: str = "creator_age") -> str:
    """Versi SQL `bucket_age`, untuk mengisi kolom di L2 tanpa menyalin batas."""
    cabang = "\n        ".join(
        f"WHEN {kolom} >= {batas} THEN '{nama}'"
        for batas, nama in reversed(list(zip(BATAS_BAWAH_AGE, BUCKET_AGE)))
    )
    return f"""CASE
        WHEN {kolom} IS NULL THEN NULL
        WHEN {kolom} < {AGE_MIN} OR {kolom} > {AGE_MAX} THEN NULL
        {cabang}
    END"""


RINGKASAN_AMBANG.update({
    "bucket_age": " / ".join(BUCKET_AGE) + f" (sah {AGE_MIN}..{AGE_MAX} tahun)",
})


# ===========================================================================
# 10. PREDIKAT FILTER DISCOVERY UNTUK KEDUA FITUR UMUR
# ===========================================================================
# Dua fungsi, karena Age Kreator dan Age Audience adalah dua filter berbeda
# yang kebetulan memakai daftar chip yang sama. Keduanya ditulis di sini
# supaya definisinya tidak disalin ke repo UI -- alasan yang sama dengan
# `sql_growth_class` dan kawan-kawan (lihat header file).
#
# KENAPA AGE AUDIENS MEMAKAI BUCKET DOMINAN, BUKAN "PUNYA SEDIKIT"
# ----------------------------------------------------------------
# Spesifikasi UI menyebut filter ini sebagai "satu bucket umur DOMINAN per
# kreator". Bedanya besar: hampir setiap akun punya SEBAGIAN audiens di tiap
# bucket, jadi predikat "punya audiens 18-24" akan meloloskan hampir semua
# akun dan filternya tidak menyaring apa pun. Yang dicari brand adalah akun
# yang audiens TERBESARNYA ada di bucket itu.
#
# Mode `any` tetap disediakan karena ada pertanyaan sah yang berbentuk begitu
# ("akun mana saja yang punya audiens 13-17"), tapi bukan default.
#
# KENAPA HANYA TANGGAL TERBARU
# ----------------------------
# `audience_demographics_daily` bergrain harian. Tanpa pembatasan tanggal,
# satu akun dengan 30 snapshot akan diuji terhadap 30 sebaran sekaligus dan
# bisa lolos lewat sebaran lama yang sudah tidak berlaku. Bucket dominan
# dihitung pada `audience_date` TERBARU milik akun itu sendiri -- bukan
# tanggal terbaru global, yang akan menyingkirkan akun yang belum di-refresh
# hari itu.


def sql_filter_creator_age_band(param: str = "%(creator_age_band)s",
                                kolom: str = "pc.creator_age_band") -> str:
    """Predikat filter Age KREATOR. NULL pada param berarti "jangan saring".

    Sengaja sesederhana ini: umurnya sudah dihitung dan dibekukan jadi band
    di `l2_gold.kol_profile_card` oleh asset `creator_age`, jadi saat baca
    tidak ada lagi yang perlu dihitung.

    Akun tanpa umur (mayoritas) TIDAK lolos saat sebuah band dipilih, dan itu
    disengaja: "tidak diketahui" bukan berarti "cocok dengan apa pun".
    """
    return f"({param}::text IS NULL OR {kolom} = {param})"


def sql_filter_audience_age_band(param: str = "%(audience_age_band)s",
                                 kolom_akun: str = "ksa.social_account_id",
                                 mode: str = "dominant") -> str:
    """Predikat filter Age AUDIENS terhadap l2_gold.audience_demographics_daily.

    `mode='dominant'` (default) -- bucket TERBESAR milik akun pada tanggal
    audiens terbarunya sendiri harus sama dengan band yang dipilih.
    `mode='any'` -- akun punya audiens di band itu, berapa pun jumlahnya.

    Pola EXISTS mengikuti filter Agency, Connected, dan Audience Location yang
    sudah ada, jadi tidak ada tabel yang perlu di-JOIN ke query utama.

    BARIS `unknown` DIKELUARKAN DARI PERHITUNGAN DOMINAN
    ----------------------------------------------------
    Sejak jalur bio-follower mengisi tabel ini, tiap akun juga punya baris
    `dimension_key='unknown'` yang memuat follower yang bio-nya tidak
    menyatakan umur. Baris itu hampir selalu JAUH terbesar (liputan nyata: 1
    dari 934). Tanpa pengecualian di bawah, "bucket dominan" setiap akun
    adalah `unknown`, dan filter band apa pun mengembalikan NOL baris --
    terbaca oleh pengguna sebagai "tidak ada KOL yang cocok", padahal artinya
    "mayoritas audiensnya tidak diketahui umurnya".

    Yang benar adalah membandingkan bucket umur terhadap sesama bucket umur:
    dominan = bucket TERBESAR di antara yang umurnya diketahui. Akun yang
    tidak punya satu pun follower ber-umur otomatis tidak lolos band apa pun,
    dan itu memang jawaban yang benar untuk akun seperti itu.

    CATATAN: predikat ini benar tapi hari ini SELALU kosong hasilnya --
    `audience_type='age'` masih 0 baris sampai Instagram Insights API
    tersedia. Kontrol UI-nya harus tetap disabled sampai saat itu; filter yang
    aktif di atas data kosong terbaca sebagai "tidak ada KOL yang cocok",
    padahal artinya "datanya belum ada".
    """
    if mode not in ("dominant", "any"):
        raise ValueError(f"mode harus 'dominant' atau 'any', bukan {mode!r}")

    if mode == "any":
        # `dimension_key = {param}` sudah menjamin barisnya bukan `unknown`:
        # param selalu salah satu dari BUCKET_AGE, dan `unknown` bukan
        # anggotanya. Tidak ada penyaringan tambahan yang perlu.
        return f"""({param}::text IS NULL OR EXISTS (
            SELECT 1 FROM l2_gold.audience_demographics_daily ad
             WHERE ad.social_account_id = {kolom_akun}
               AND ad.audience_type = 'age'
               AND ad.dimension_key = {param}
               AND ad.audience_count > 0))"""

    # Subquery bersarang, BUKAN ORDER BY/LIMIT langsung di dalam EXISTS:
    # `EXISTS (SELECT ... LIMIT 1)` selalu benar begitu ada satu baris, jadi
    # pembatasannya harus terjadi di dalam turunan dulu, baru hasilnya
    # dibandingkan. Urutan kedua (`dimension_key`) memecah seri supaya akun
    # dengan dua bucket berjumlah sama selalu jatuh ke bucket yang sama tiap
    # query -- tanpa itu hasil filter bisa berubah antar pemanggilan.
    return f"""({param}::text IS NULL OR EXISTS (
        SELECT 1 FROM (
            SELECT ad.dimension_key
              FROM l2_gold.audience_demographics_daily ad
             WHERE ad.social_account_id = {kolom_akun}
               AND ad.audience_type = 'age'
               AND ad.dimension_key <> '{AGE_UNKNOWN}'
               AND ad.audience_count > 0
               AND ad.audience_date = (
                     SELECT max(ad2.audience_date)
                       FROM l2_gold.audience_demographics_daily ad2
                      WHERE ad2.social_account_id = {kolom_akun}
                        AND ad2.audience_type = 'age')
             ORDER BY ad.audience_count DESC NULLS LAST, ad.dimension_key
             LIMIT 1
        ) teratas
         WHERE teratas.dimension_key = {param}))"""


def sql_audience_age_siap() -> str:
    """Query kesiapan: apakah filter Age Audiens layak diaktifkan di UI.

    Dipakai backend untuk memutuskan `disabled` pada kontrol, supaya
    keputusannya mengikuti DATA dan bukan flag yang harus diingat seseorang
    untuk dimatikan lagi nanti.

    "ADA BARIS" BUKAN "SIAP DIPAKAI"
    --------------------------------
    Versi pertama query ini cuma menghitung baris `audience_type='age'`. Itu
    benar selama satu-satunya pengisi tabel adalah Instagram Insights: kalau
    ada barisnya, datanya memang ada.

    Sejak jalur bio-follower ikut mengisi, itu tidak lagi benar. Jalur itu
    menulis satu baris `unknown` untuk HAMPIR SETIAP akun -- penyebut yang
    memang harus ada, tapi yang tidak bisa dicocokkan dengan chip mana pun.
    Query lama karena itu akan melaporkan "siap" untuk tabel yang, dari sudut
    pandang filter, masih kosong: kontrolnya menyala, lalu band apa pun yang
    dipilih pengguna mengembalikan nol KOL.

    Yang menentukan kesiapan adalah adanya baris yang BISA cocok: bucket umur
    sungguhan, dengan cacah di atas nol.
    """
    return (f"SELECT count(*) > 0 AS siap "
            f"FROM l2_gold.audience_demographics_daily "
            f"WHERE audience_type = 'age' "
            f"  AND dimension_key <> '{AGE_UNKNOWN}' "
            f"  AND audience_count > 0")


RINGKASAN_AMBANG.update({
    "filter_age_kreator": "kol_profile_card.creator_age_band = band terpilih",
    "filter_age_audiens": "bucket DOMINAN pada audience_date terbaru akun",
})
