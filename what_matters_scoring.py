"""What Matters Most — 6 kriteria ranking, SATU definisi, dua bentuk.

============================================================================
APA INI
============================================================================

Tujuh kriteria preferensi user di Discovery. User memilih beberapa, sistem
merata-ratakan skor kriteria yang dipilih, lalu meranking.

Seluruh skor 0..100. Semua dihitung SAAT DIBACA -- tidak ada kolom baru, tidak
ada tabel baru, tidak ada nilai yang disimpan. Alasannya di bagian terakhir.

Pola dan alasannya sama dengan `metrics_thresholds.py` dan
`campaign_cost_metrics.py`: definisi hidup sekali di sini, lalu diturunkan ke
fungsi Python dan ekspresi SQL yang digenerate dari konstanta yang sama.

============================================================================
DUA JENIS SKOR, DAN KENAPA DIBEDAKAN
============================================================================

    REAL     dihitung dari metric yang memang mengukur hal itu
    PROXY    dihitung dari metric LAIN karena yang sebenarnya tidak ada

Perbedaan itu bukan basa-basi. `reach_proxy_score` dihitung dari VIEWS, dan
views bukan reach -- satu penayangan berulang dari orang yang sama dihitung
dua kali, sementara reach menghitung akun unik. Menampilkannya sebagai "reach"
tanpa kualifikasi akan membuat orang mengambil keputusan beli berdasarkan
angka yang bukan yang mereka kira.

`SIFAT` di bawah merekamnya per kriteria, dan API wajib meneruskannya.

============================================================================
CONTENT QUALITY  --  PROXY dari metric post, rumus yang disepakati
============================================================================

Dulu selalu NULL. Usulan awal (engagement 40% + content format 30% + content
topic 30%) ditolak karena tidak ada sumber yang menyatakan Carousel lebih
berkualitas daripada Image, atau topik `food` daripada `religion`. Alasan itu
masih berlaku: format dan topik TIDAK dipakai.

Rumus yang disepakati sekarang memakai performa post itu sendiri, dari
`l2_gold.post_metric`:

    Content Quality = 50% Engagement + 30% Views + 20% Consistency

    Engagement   ER akun ADITIF atas post yang punya `er_followers`:
                 sum(engagement_owned) / sum(followers_at_post_date) x 100.
                 Pola yang sama dengan `_ER_AKUN` di feature_engagement.py.
                 Dinormalisasi dengan `persentil_ke_skor`.
    Views        median `views` atas post lolos sampel (bukan likes_hidden,
                 bukan kolaborasi) yang `views > 0` -- definisi yang sama
                 dengan `median_views` di migration 036. `reach` 0/522 terisi
                 (butuh Insights), jadi views dipakai; ia BUKAN reach.
                 Dinormalisasi dengan `persentil_ke_skor`.
    Consistency  simpangan baku ER per post (poin persen) ->
                 `metrics_thresholds.klasifikasi_stability` (ambang dan
                 minimum 3 sampel yang sudah ditetapkan) -> 0 / 50 / 100.

Tanpa jendela tanggal: seluruh post yang ada, sama seperti metric post
lainnya (`median_views`, ER, stability) -- datanya ~10 post per akun yang
tersebar ratusan hari, jadi jendela pendek akan mengosongkan hampir semuanya.

Komponen yang tidak terukur keluar dari pembilang DAN penyebut, bobot sisanya
direnormalisasi -- pola yang sama dengan `community_strength_score`. Semua
komponen NULL -> NULL.

Sifatnya PROXY: ini performa konten, bukan penilaian kualitas kreatif. Dan
ia sengaja beririsan dengan Strong Engagement dan High Reach (sumbernya
berbeda: post_metric vs kol_directory / kol_profile_card). Memilih ketiganya
sekaligus memberi sinyal engagement dan views bobot lebih di rata-rata.

BRAND SAFETY DIHAPUS DARI SCOPE. Keputusan terbaru: Brand Safety tidak lagi
menjadi bagian Brand Match maupun What Matters. Kriterianya tidak terdaftar
di `KRITERIA`, jadi `?matters=brand_safety` diabaikan `parse_matters` seperti
kunci tak dikenal lainnya -- tidak ada skor, proxy, atau default pengganti.

============================================================================
KENAPA TIDAK ADA KOLOM, TABEL, ATAU VIEW BARU
============================================================================

Kolom  Seluruh skor di sini turunan murni kolom yang sudah ada. Menyimpannya
       berarti wajib menjaganya sinkron tiap kali sumbernya berubah. Dan
       `tests/test_calculated_metrics.py` memang melarang calculated metric
       baru di `l2_gold.kol_profile_card`.

Tabel  Tidak ada yang perlu disimpan. Preferensi user dikirim per-request,
       dan produk ini belum pernah mempersist pilihan user jenis apa pun.

View   Database `kol` sekarang punya NOL view. Memperkenalkan yang pertama
       adalah keputusan konvensi tim, bukan keputusan task ini.
"""

from __future__ import annotations

# ===========================================================================
# SIFAT SKOR
# ===========================================================================
REAL = "real"
PROXY = "proxy"
TIDAK_TERSEDIA = "tidak_tersedia"

SKALA_MIN = 0.0
SKALA_MAX = 100.0


# ===========================================================================
# 1. KRITERIA  --  kunci API, nama, sumber, sifat
# ===========================================================================
#
# `kunci` adalah yang dikirim UI:  ?matters=engagement,consistency,reach

KRITERIA: dict[str, dict] = {
    "engagement": {
        "nama": "Strong Engagement",
        "skor": "engagement_score",
        "sifat": REAL,
        "sumber": ("public.kol_directory.engagement_rate",),
        "catatan": "Peringkat persentil ER dalam populasi terukur.",
    },
    "audience_quality": {
        "nama": "High Audience Quality",
        "skor": "audience_quality_score",
        "sifat": REAL,
        "sumber": ("l2_gold.kol_profile_card.audience_quality_score",
                   "l2_gold.kol_profile_card.authenticity_score"),
        "catatan": "Rata-rata keduanya; kalau satu NULL, pakai yang ada.",
    },
    "consistency": {
        "nama": "Consistent Performance",
        "skor": "consistency_score",
        "sifat": REAL,
        "sumber": ("l2_gold.kol_profile_card.performance_stability",
                   "l2_gold.kol_profile_card.post_frequency_reliability"),
        "catatan": "Dua label ordinal dari metrics_thresholds, bukan k.cons "
                   "prototype yang merupakan hash creator id.",
    },
    "community": {
        "nama": "Strong Company/Community",
        "skor": "community_strength_score",
        "sifat": PROXY,
        "sumber": ("l2_gold.kol_profile_card.audience_quality_score",
                   "public.kol_directory.engagement_rate"),
        "catatan": "PROXY. Bukan ukuran komunitas sebenarnya -- tidak ada "
                   "kolom community di seluruh DB.",
    },
    "reach": {
        "nama": "High Reach",
        "skor": "reach_proxy_score",
        "sifat": PROXY,
        "sumber": ("l2_gold.kol_profile_card.median_views",),
        "catatan": "PROXY BERBASIS VIEWS, bukan reach Insights. "
                   "estimated_reach TIDAK dipakai.",
    },
    "content_quality": {
        "nama": "Content Quality",
        "skor": "content_quality_score",
        "sifat": PROXY,
        "sumber": ("l2_gold.post_metric.engagement_owned",
                   "l2_gold.post_metric.followers_at_post_date",
                   "l2_gold.post_metric.er_followers",
                   "l2_gold.post_metric.views"),
        "catatan": "PROXY performa konten: Engagement 50% + Views 30% + "
                   "Consistency 20%, dari post_metric. Views bukan reach. "
                   "Format dan topik TIDAK dipakai.",
    },
}

#: Urutan tampil di UI.
URUTAN_KRITERIA = ("engagement", "audience_quality", "consistency",
                   "community", "reach", "content_quality")

#: Kriteria yang benar-benar mengembalikan angka hari ini.
KRITERIA_AKTIF = tuple(k for k in URUTAN_KRITERIA
                       if KRITERIA[k]["sifat"] != TIDAK_TERSEDIA)


# ===========================================================================
# 2. NORMALISASI
# ===========================================================================

def klem(nilai: float | None) -> float | None:
    """Paksa ke 0..100. None tetap None."""
    if nilai is None:
        return None
    return max(SKALA_MIN, min(SKALA_MAX, float(nilai)))


def persentil_ke_skor(nilai: float | None,
                      populasi: list[float] | tuple[float, ...]) -> float | None:
    """Peringkat persentil `nilai` dalam `populasi`, sebagai 0..100.

    Dipakai untuk metric yang sebarannya sangat miring: ER punya ekor sampai
    223% dan median_views sampai 136 juta. Normalisasi linear terhadap nilai
    maksimum akan menempelkan hampir seluruh populasi ke nol.

    Persentil dipilih karena ia TIDAK memerlukan benchmark yang harus
    dikarang. Ia murni relatif terhadap populasi yang sedang dibandingkan, dan
    kebal outlier: ER 223% cuma menjadi peringkat teratas, tidak menggeser
    skala orang lain.

    Populasi yang dipakai adalah yang TERUKUR saja -- NULL tidak ikut, dan
    tidak diperlakukan sebagai nol.
    """
    if nilai is None:
        return None
    terukur = [float(x) for x in populasi if x is not None]
    if not terukur:
        return None
    if len(terukur) == 1:
        return SKALA_MAX if float(nilai) >= terukur[0] else SKALA_MIN
    # Dibatasi n-1 supaya nilai di LUAR populasi (mis. saat memberi skor satu
    # kreator terhadap populasi lain) tidak menghasilkan lebih dari 100.
    lebih_kecil = min(sum(1 for x in terukur if x < float(nilai)),
                      len(terukur) - 1)
    return round(lebih_kecil / (len(terukur) - 1) * SKALA_MAX, 4)


def _rata_rata_tersedia(*nilai: float | None) -> float | None:
    """Rata-rata yang mengabaikan None. Semua None -> None.

    NULL bukan nol. Kreator yang belum diukur tidak boleh dihukum seolah
    hasil pengukurannya buruk.
    """
    ada = [float(v) for v in nilai if v is not None]
    if not ada:
        return None
    return sum(ada) / len(ada)


# ===========================================================================
# 3. SKOR ORDINAL  --  label -> angka
# ===========================================================================
# Label stabilitas dan reliabilitas datang dari `metrics_thresholds`, yang
# ambangnya sudah ditetapkan. Yang belum ada adalah cara mengubah label jadi
# angka.
#
# Aturannya deterministik, bukan angka pilihan: posisi ordinal dinormalisasi
# ke 0..100. Tiga tingkat -> 0 / 50 / 100. Ini URUTAN, bukan pengukuran --
# "Medium" bukan berarti separuh sebaik "High", hanya berarti di tengah.

TINGKAT_STABILITAS = ("Low Stability", "Medium Stability", "High Stability")
TINGKAT_RELIABILITAS = ("Low", "Medium", "High")


def _ordinal_ke_skor(label: str | None,
                     tingkat: tuple[str, ...]) -> float | None:
    if label is None or label not in tingkat:
        return None
    return round(tingkat.index(label) / (len(tingkat) - 1) * SKALA_MAX, 4)


# ===========================================================================
# 4. TUJUH SKOR KRITERIA
# ===========================================================================

def engagement_score(engagement_rate: float | None,
                     populasi_er: list[float] | tuple[float, ...]) -> float | None:
    """Kriteria 1 -- REAL.  Peringkat persentil ER."""
    return persentil_ke_skor(engagement_rate, populasi_er)


def audience_quality_score(aq: float | None,
                           authenticity: float | None) -> float | None:
    """Kriteria 2 -- REAL.  Rata-rata dua skor yang sudah 0..100.

    Keduanya sudah berskala 0..100 di sumbernya, jadi tidak dinormalisasi
    ulang -- itu akan menghilangkan artinya. Kalau salah satu NULL, yang
    tersedia dipakai apa adanya.
    """
    return klem(_rata_rata_tersedia(aq, authenticity))


def consistency_score(performance_stability: str | None,
                      post_frequency_reliability: str | None) -> float | None:
    """Kriteria 3 -- REAL.  Rata-rata dua label ordinal.

    `performance_stability` sudah memperhitungkan arah yang benar: ia berasal
    dari `er_stddev_pp`, di mana simpangan baku KECIL berarti STABIL, dan
    `metrics_thresholds.klasifikasi_stability` sudah membalikkannya jadi
    High/Medium/Low. Memakai labelnya berarti memakai ambang yang sudah
    ditetapkan, bukan membuat definisi kedua atas angka mentahnya.
    """
    return _rata_rata_tersedia(
        _ordinal_ke_skor(performance_stability, TINGKAT_STABILITAS),
        _ordinal_ke_skor(post_frequency_reliability, TINGKAT_RELIABILITAS),
    )


# --- bobot community, dan kenapa berbeda dari usulan awal -------------------
#
# Usulan awal: audience quality 40% + authenticity 30% + engagement 30%.
# Audit `audience_inference.py:1102` menemukan:
#
#     aq = round((fq + au) / 2)
#
# `audience_quality_score` HARFIAH rata-rata `follower_quality_score` dan
# `authenticity_score`. Diverifikasi atas data nyata: 21 dari 27 baris cocok
# persis, 6 sisanya beda satu poin karena pembulatan.
#
# Jadi bobot usulan akan memberi authenticity 0,40x0,50 + 0,30 = 50% efektif,
# sementara follower quality cuma 20% -- authenticity dihitung dua kali.
#
# Perbaikannya: pakai `audience_quality_score` saja, yang sudah membawa
# keduanya dengan bobot setara.
BOBOT_COMMUNITY_KUALITAS = 0.70
BOBOT_COMMUNITY_ER = 0.30


def community_strength_score(aq: float | None,
                             engagement_rate: float | None,
                             populasi_er: list[float] | tuple[float, ...]
                             ) -> float | None:
    """Kriteria 4 -- PROXY.  Kualitas audiens 70% + engagement 30%.

    BUKAN ukuran komunitas. Tidak ada kolom community di seluruh 101 tabel.
    Ini gabungan dua sinyal yang ADA dan secara masuk akal berkorelasi dengan
    audiens yang hidup: audiens yang asli, dan audiens yang berinteraksi.
    """
    er_skor = persentil_ke_skor(engagement_rate, populasi_er)
    aq_klem = klem(aq)
    if aq_klem is None and er_skor is None:
        return None
    if aq_klem is None:
        return er_skor
    if er_skor is None:
        return aq_klem
    return aq_klem * BOBOT_COMMUNITY_KUALITAS + er_skor * BOBOT_COMMUNITY_ER


def reach_proxy_score(median_views: float | None,
                      populasi_views: list[float] | tuple[float, ...]
                      ) -> float | None:
    """Kriteria 5 -- PROXY BERBASIS VIEWS.

    `median_views` dipilih di atas `avg_views`: keduanya berkorelasi 0,957,
    tapi rata-rata tertarik post viral (p50 638 ribu vs median 345 ribu),
    sehingga akun dengan satu post meledak akan naik melewati akun yang
    konsisten.

    `l0_raw.kol_roster_import.estimated_reach` TIDAK dipakai sebagai fallback:
    2.164 barisnya punya reach lebih besar daripada jumlah follower -- indikasi
    pergeseran kolom CSV.

    Reach kanonik tetap Instagram/TikTok Insights. Seluruh tabel `*_official`
    saat ini 0 baris dan tidak ada satu pun akun yang tersambung OAuth.
    """
    return persentil_ke_skor(median_views, populasi_views)


# --- Content Quality: bobot yang disepakati ----------------------------------
BOBOT_CQ_ENGAGEMENT = 0.50
BOBOT_CQ_VIEWS = 0.30
BOBOT_CQ_KONSISTENSI = 0.20


def _rata_rata_berbobot(*pasangan: tuple[float | None, float]) -> float | None:
    """Rata-rata berbobot atas komponen yang ADA; bobotnya direnormalisasi.

    Komponen None keluar dari pembilang dan penyebut, persis seperti
    `community_strength_score`. Semua None -> None.
    """
    ada = [(nilai, bobot) for nilai, bobot in pasangan if nilai is not None]
    if not ada:
        return None
    total = sum(bobot for _, bobot in ada)
    return sum(float(nilai) * bobot for nilai, bobot in ada) / total


def ringkas_post_content_quality(posts) -> dict:
    """Satu akun: daftar baris `l2_gold.post_metric` -> tiga angka mentah.

    Bentuk Python dari CTE `SQL_CONTENT_QUALITY_CTE`; keduanya diuji
    berpasangan. Setiap post adalah mapping dengan kolom post_metric:
    `likes_hidden`, `is_collaboration`, `engagement_owned`,
    `followers_at_post_date`, `er_followers`, `views`.

        er_pct        ER aditif (%) atas post ber-`er_followers`; None kalau
                      tidak ada satu pun.
        median_views  median `views` post lolos sampel dengan `views > 0`.
        er_sd_pp      simpangan baku sampel ER per post, poin persen; None
                      kalau kurang dari dua post ber-ER.
        er_posts      jumlah post ber-ER -- penentu minimum 3 di stability.

    `er_followers` sudah NULL untuk post yang tidak lolos sampel atau yang
    followers-nya tidak diketahui (gold_post.py butir 4), jadi ia sekaligus
    menjadi syarat sampel untuk ER.
    """
    import statistics

    ber_er = [p for p in posts if p.get("er_followers") is not None]
    pembilang = sum(float(p["engagement_owned"]) for p in ber_er
                    if p.get("engagement_owned") is not None)
    penyebut = sum(float(p["followers_at_post_date"]) for p in ber_er
                   if p.get("followers_at_post_date") is not None)
    er_pct = pembilang / penyebut * 100 if ber_er and penyebut > 0 else None

    views = [float(p["views"]) for p in posts
             if p.get("likes_hidden") is not True
             and p.get("is_collaboration") is not True
             and p.get("views") is not None and float(p["views"]) > 0]
    median_views = statistics.median(views) if views else None

    er_per_post = [float(p["er_followers"]) * 100 for p in ber_er]
    er_sd_pp = statistics.stdev(er_per_post) if len(er_per_post) >= 2 else None

    return {"er_pct": er_pct, "median_views": median_views,
            "er_sd_pp": er_sd_pp, "er_posts": len(er_per_post)}


def content_quality_score(er_pct: float | None,
                          populasi_er: list[float] | tuple[float, ...],
                          median_views: float | None,
                          populasi_views: list[float] | tuple[float, ...],
                          er_sd_pp: float | None,
                          er_posts: int | None) -> float | None:
    """Kriteria 6 -- PROXY.  Engagement 50% + Views 30% + Consistency 20%.

    Tiap komponen 0..100 dengan helper yang sudah ada -- persentil untuk
    engagement dan views, label stability ordinal untuk consistency -- lalu
    dirata-rata berbobot atas komponen yang terukur saja. Lihat docstring
    modul untuk sumber dan alasannya.
    """
    import metrics_thresholds as mt

    engagement = persentil_ke_skor(er_pct, populasi_er)
    views = persentil_ke_skor(median_views, populasi_views)
    konsistensi = _ordinal_ke_skor(
        mt.klasifikasi_stability(er_sd_pp, er_posts), TINGKAT_STABILITAS)
    return _rata_rata_berbobot(
        (engagement, BOBOT_CQ_ENGAGEMENT),
        (views, BOBOT_CQ_VIEWS),
        (konsistensi, BOBOT_CQ_KONSISTENSI),
    )


# ===========================================================================
# 5. WHAT MATTERS SCORE
# ===========================================================================

def what_matters_score(skor: dict[str, float | None],
                       dipilih: list[str] | tuple[str, ...]) -> float | None:
    """Rata-rata skor kriteria yang DIPILIH dan PUNYA NILAI.

    Kriteria yang dipilih tapi nilainya NULL dikeluarkan dari penyebut, bukan
    dihitung nol. Kreator tidak boleh turun peringkat karena datanya memang
    belum ada.

    Seluruh kriteria terpilih NULL -> None, dan di ranking ia jatuh ke bawah
    lewat NULLS LAST -- bukan lewat skor nol yang akan menyamakannya dengan
    kreator yang benar-benar buruk.
    """
    if not dipilih:
        return None
    ada = [skor[k] for k in dipilih if skor.get(k) is not None]
    if not ada:
        return None
    return sum(ada) / len(ada)


def parse_matters(param: str | None) -> list[str]:
    """`"engagement,consistency,reach"` -> daftar kunci yang sah.

    Kunci tak dikenal diabaikan, bukan membuat request gagal: UI yang lebih
    baru boleh mengirim kriteria yang backend ini belum kenal.
    """
    if not param:
        return []
    hasil = []
    for bagian in param.split(","):
        kunci = bagian.strip().lower()
        if kunci in KRITERIA and kunci not in hasil:
            hasil.append(kunci)
    return hasil


# ===========================================================================
# 6. BENTUK KEDUA: SQL
# ===========================================================================
# Persentil di SQL memakai `percent_rank()`, yang definisinya identik dengan
# `persentil_ke_skor`: (jumlah baris yang nilainya lebih kecil) / (n - 1).
# Baris NULL otomatis keluar dari jendela, jadi tidak perlu filter tambahan.

def sql_ordinal(kolom: str, tingkat: tuple[str, ...]) -> str:
    bagian = "\n".join(
        f"        WHEN {kolom} = '{label}' THEN {round(i / (len(tingkat)-1) * SKALA_MAX, 4)}"
        for i, label in enumerate(tingkat))
    return f"CASE\n{bagian}\n        ELSE NULL\n    END"


def sql_persentil(kolom: str) -> str:
    """0..100 atas populasi TERUKUR saja. NULL tetap NULL.

    `PARTITION BY ({kolom} IS NULL)` bukan hiasan — tanpanya, baris NULL ikut
    masuk penyebut `percent_rank()` dan seluruh skor mengecil sebanding
    coverage. Dengan ER yang cuma terisi 23%, kreator ber-ER tertinggi di
    seluruh direktori mendapat 23 alih-alih 100.

    Partisi memisahkan baris NULL ke kelompoknya sendiri, jadi peringkat di
    kelompok non-NULL dihitung hanya terhadap sesama non-NULL — sepadan dengan
    `persentil_ke_skor()`, yang juga membuang None dari populasi.
    """
    return (f"CASE WHEN {kolom} IS NULL THEN NULL "
            f"ELSE percent_rank() OVER "
            f"(PARTITION BY ({kolom} IS NULL) ORDER BY {kolom}) * {SKALA_MAX} "
            f"END")


def sql_rata_rata_tersedia(*ekspresi: str) -> str:
    """Rata-rata yang mengabaikan NULL; semua NULL -> NULL."""
    pembilang = " + ".join(f"COALESCE({e}, 0)" for e in ekspresi)
    penyebut = " + ".join(f"(CASE WHEN {e} IS NULL THEN 0 ELSE 1 END)"
                          for e in ekspresi)
    return f"(({pembilang}) / NULLIF(({penyebut}), 0))"


def sql_what_matters(dipilih: list[str] | tuple[str, ...],
                     kolom_skor: dict[str, str]) -> str:
    """Rata-rata kolom skor kriteria terpilih, NULL dikeluarkan penyebut."""
    ekspresi = [kolom_skor[k] for k in dipilih
                if k in kolom_skor and KRITERIA[k]["sifat"] != TIDAK_TERSEDIA]
    if not ekspresi:
        return "NULL"
    return sql_rata_rata_tersedia(*ekspresi)


#: Klausa ranking. NULLS LAST supaya ketiadaan data tidak menyamar jadi skor
#: buruk, dan tidak pula naik ke atas.
SQL_ORDER_BY = "ORDER BY what_matters_score DESC NULLS LAST"


# ===========================================================================
# 7. EKSPRESI SKOR SIAP-PAKAI UNTUK JALUR BACA
# ===========================================================================
# Dipakai `db.py` membangun query Discovery. Ditaruh di sini, bukan di db.py,
# supaya rumusnya tetap hidup di satu tempat -- sama seperti fungsi Python di
# atas, dan diuji sepasang dengannya.

#: CTE Content Quality: tiga angka mentah per akun dari `l2_gold.post_metric`.
#: Bentuk SQL dari `ringkas_post_content_quality`. Di-JOIN ke jalur baca
#: sebagai alias `cq` (lihat `db._query_what_matters`).
SQL_CONTENT_QUALITY_CTE = """
    post_quality AS (
        SELECT social_account_id,
               sum(engagement_owned) FILTER (WHERE er_followers IS NOT NULL)::numeric
                 / NULLIF(sum(followers_at_post_date)
                            FILTER (WHERE er_followers IS NOT NULL), 0)
                 * 100                                          AS er_pct,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY views)
                 FILTER (WHERE likes_hidden IS NOT TRUE
                           AND is_collaboration IS NOT TRUE
                           AND views > 0)                       AS median_views,
               stddev_samp(er_followers * 100)                  AS er_sd_pp,
               count(er_followers)                              AS er_posts
          FROM l2_gold.post_metric
         GROUP BY social_account_id
    )"""

#: Kolom sumber default, sesuai alias di `_SEARCH_QUERY`.
KOLOM_SUMBER_DEFAULT = {
    "engagement_rate": "k.engagement_rate",
    "audience_quality_score": "pc.audience_quality_score",
    "authenticity_score": "pc.authenticity_score",
    "performance_stability": "pc.performance_stability",
    "post_frequency_reliability": "pc.post_frequency_reliability",
    "median_views": "pc.median_views",
    "cq_er_pct": "cq.er_pct",
    "cq_median_views": "cq.median_views",
    "cq_er_sd_pp": "cq.er_sd_pp",
    "cq_er_posts": "cq.er_posts",
}


def sql_rata_rata_berbobot(*pasangan: tuple[str, float]) -> str:
    """Bentuk SQL `_rata_rata_berbobot`: NULL keluar dari pembilang dan
    penyebut, bobot sisanya direnormalisasi; semua NULL -> NULL."""
    pembilang = " + ".join(f"COALESCE(({e}), 0) * {b}" for e, b in pasangan)
    penyebut = " + ".join(f"(CASE WHEN ({e}) IS NULL THEN 0 ELSE {b} END)"
                          for e, b in pasangan)
    return f"(({pembilang}) / NULLIF({penyebut}, 0))"


def sql_ekspresi_skor(kolom: dict[str, str] | None = None) -> dict[str, str]:
    """kunci kriteria -> ekspresi SQL bernilai 0..100 (atau NULL).

    Persentil memakai `percent_rank()`, jadi ekspresi ini WAJIB dievaluasi di
    subquery yang cakupannya seluruh populasi pembanding -- bukan setelah
    LIMIT. Menghitung persentil atas satu halaman akan memberi peringkat yang
    artinya berubah-ubah tiap kali orang menggeser halaman.

    `content_quality` membaca alias `cq` dari `SQL_CONTENT_QUALITY_CTE`, jadi
    query pemakainya wajib menyertakan CTE dan JOIN itu.
    """
    import metrics_thresholds as mt

    c = {**KOLOM_SUMBER_DEFAULT, **(kolom or {})}
    er = sql_persentil(c["engagement_rate"])
    aq = sql_rata_rata_tersedia(c["audience_quality_score"],
                                c["authenticity_score"])
    return {
        "engagement": er,
        "audience_quality": aq,
        "consistency": sql_rata_rata_tersedia(
            sql_ordinal(c["performance_stability"], TINGKAT_STABILITAS),
            sql_ordinal(c["post_frequency_reliability"], TINGKAT_RELIABILITAS),
        ),
        # Bobot 70/30 dengan renormalisasi kalau salah satu NULL -- sepadan
        # dengan `community_strength_score()`.
        "community": (
            f"((COALESCE({c['audience_quality_score']}, 0) * {BOBOT_COMMUNITY_KUALITAS}"
            f" + COALESCE(({er}), 0) * {BOBOT_COMMUNITY_ER})"
            f" / NULLIF("
            f"(CASE WHEN {c['audience_quality_score']} IS NULL THEN 0 ELSE {BOBOT_COMMUNITY_KUALITAS} END)"
            f" + (CASE WHEN ({er}) IS NULL THEN 0 ELSE {BOBOT_COMMUNITY_ER} END), 0))"
        ),
        "reach": sql_persentil(c["median_views"]),
        "content_quality": sql_rata_rata_berbobot(
            (sql_persentil(c["cq_er_pct"]), BOBOT_CQ_ENGAGEMENT),
            (sql_persentil(c["cq_median_views"]), BOBOT_CQ_VIEWS),
            (sql_ordinal("(" + mt.sql_stability(c["cq_er_sd_pp"],
                                                c["cq_er_posts"]) + ")",
                         TINGKAT_STABILITAS), BOBOT_CQ_KONSISTENSI),
        ),
    }


def sql_jumlah_kontributor(dipilih: list[str] | tuple[str, ...],
                           kolom_skor: dict[str, str]) -> str:
    """Berapa kriteria terpilih yang benar-benar punya nilai.

    Dibutuhkan UI: skor 100 dari satu kriteria tidak sebanding dengan skor 100
    dari lima. Tanpa angka ini, keduanya terlihat sama.
    """
    ekspresi = [kolom_skor[k] for k in dipilih if k in kolom_skor]
    if not ekspresi:
        return "0"
    return " + ".join(f"(CASE WHEN {e} IS NULL THEN 0 ELSE 1 END)"
                      for e in ekspresi)
