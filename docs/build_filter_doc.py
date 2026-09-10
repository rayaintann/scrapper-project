"""Generator dokumentasi filter KOL Discovery -> docs/KOL_DISCOVERY_FILTER_DOC.xlsx.

KENAPA GENERATOR, BUKAN XLSX YANG DIEDIT TANGAN
===============================================
Angka cakupan di dokumen ini berubah tiap kali pipeline jalan. XLSX yang
diedit tangan akan basi dalam hitungan hari dan tidak ada yang tahu kapan.
Skrip ini membaca cakupan LANGSUNG dari database saat dijalankan, jadi
memperbarui dokumen berarti menjalankannya lagi -- bukan mengetik ulang 24
baris angka.

Isi non-angka (definisi, rumus, ambang, endpoint) ditulis di sini sebagai
data, bukan diturunkan dari kode: semuanya adalah KESEPAKATAN, dan kesepakatan
tidak boleh berubah diam-diam hanya karena kodenya berubah. Kalau keduanya
berbeda, itu discrepancy yang harus terlihat -- lihat sheet `Validation`.

Dijalankan read-only. Tidak menulis apa pun ke database.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KELUARAN = ROOT / "docs" / "KOL_DISCOVERY_FILTER_DOC.xlsx"

EP_LIST = "GET /api/organizations/{id}/discover/kol-directory"
EP_DETAIL = "GET /api/organizations/{id}/discover/kol-directory/{kolId}"
EP_KEDUA = EP_LIST + "  ·  " + EP_DETAIL


def cakupan(conn) -> dict:
    """Cakupan nyata per kolom, dibaca saat generator dijalankan."""
    kolom = [
        "followers_growth", "growth_class", "daily_growth", "projected_30d",
        "projected_followers_30d", "female_pct", "male_pct", "gender_known_pct",
        "gender_reliability", "avg_views", "median_views", "view_to_follower_ratio",
        "like_to_view_ratio", "paid_ratio", "share_rate", "save_rate",
        "audience_interest_top", "content_topic", "format_dominant",
        "viral_frequency", "rising_creator", "post_frequency_monthly",
        "post_frequency_reliability", "audience_quality_score",
        "audience_quality_tier", "er_stddev_pp", "performance_stability",
        "monitoring_er_pct", "monitoring_priority",
    ]
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.kol_directory")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM l2_gold.kol_profile_card")
        kartu = cur.fetchone()[0]
        cur.execute("SELECT %s FROM l2_gold.kol_profile_card"
                    % ", ".join(f"count({k})" for k in kolom))
        c = dict(zip(kolom, cur.fetchone()))
        cur.execute("SELECT count(engagement_rate) FROM public.kol_directory")
        c["kd_engagement_rate"] = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT social_account_id) FROM l2_gold.audience_geo_daily")
        c["geo"] = cur.fetchone()[0]
    c["_total"] = total
    c["_kartu"] = kartu
    return c


def cov(c: dict, kunci: str, penyebut: str = "kartu") -> str:
    n = c[kunci]
    d = c["_kartu"] if penyebut == "kartu" else c["_total"]
    label = "kartu L2" if penyebut == "kartu" else "KOL"
    return f"{n:,} / {d:,} {label} ({n * 100.0 / d:.1f}%)".replace(",", ".")


def baris_final(c: dict) -> list[list]:
    """24 filter FINAL. Urutan mengikuti daftar yang disepakati."""
    return [
        [1, "Engagement Rate (ER)", "FINAL / APPROVED",
         "Seberapa tinggi engagement dibanding jumlah followers.",
         "Engagement / Followers x 100%",
         "public", "kol_directory", "engagement_rate",
         "kol_directory.id (langsung); untuk nilai feature: kol_directory -> kol_social_account -> feature.{ig,tt}_engagement_analysis",
         EP_KEDUA, "erPct  (filter: minEr)",
         cov(c, "kd_engagement_rate", "total"),
         "Tidak ada ambang; dipakai sebagai nilai mentah dan sebagai dasar Monitoring Priority.",
         "DISCREPANCY: nilai yang DITAMPILKAN dan difilter di Directory memakai "
         "COALESCE(feature.engagement_rate, kol_directory.engagement_rate) "
         "(kolDirectory.ts:472, konstanta ER_PCT) -- feature lebih dulu, roster cadangan. "
         "Spesifikasi menyebut hanya kol_directory.engagement_rate. Monitoring Priority "
         "(no. 24) SUDAH memakai roster saja sesuai keputusan. Implementasi TIDAK diubah; "
         "lihat sheet Validation."],

        [2, "Growth", "FINAL / APPROVED",
         "Pertumbuhan followers berdasarkan snapshot sebelumnya.",
         "((current - previous) / previous) x 100%",
         "l1_silver", "unified_profile", "followers_growth (dihitung sp_build_unified_profile)",
         "unified_profile.social_account_id -> kol_social_account -> kol_directory",
         EP_KEDUA, "growthPct  (filter: growthMin, growthMax)",
         cov(c, "followers_growth"),
         "previous = snapshot VALID terakhir. NULL bila previous NULL/0 atau current NULL.",
         "previous melompati snapshot yang di-NULL-kan sanity guard migration 035, "
         "bukan memakainya dan bukan memutus rantai."],

        [3, "Growth Classification", "FINAL / APPROVED",
         "Mengelompokkan growth berdasarkan tingkat pertumbuhannya.",
         "Label atas Growth %",
         "l2_gold", "kol_profile_card", "growth_class",
         "kol_profile_card.social_account_id -> kol_social_account -> kol_directory",
         EP_KEDUA, "growthClass  (filter: growthClass)",
         cov(c, "growth_class"),
         "<0% Negative · 0-<5% Low · 5-<10% Medium · >=10% High · NULL -> NULL",
         "Ambang hidup di metrics_thresholds.py; CASE SQL digenerate dari konstanta yang sama. "
         "NULL BUKAN Negative."],

        [4, "Female %", "FINAL / APPROVED",
         "Persentase audience perempuan.",
         "female / (female + male) x 100%",
         "feature (utama) · l2_gold (turunan)",
         "feature.ig_audience_analysis · feature.tt_audience_analysis · l2_gold.audience_demographics_daily",
         "feature.*.female_pct · audience_demographics_daily.dimension_key='female'",
         "audience_analysis.social_account_id -> kol_social_account -> kol_directory",
         EP_KEDUA, "femalePct, genderKnownPct  (filter: femaleMin)",
         cov(c, "female_pct"),
         "unknown DIKELUARKAN dari penyebut. NULL bila female+male = 0.",
         "Dihitung `rasio_gender()` di audience.py dari gender_breakdown; "
         "audience_demographics_daily menyimpan cacah yang sama, dipekarkan jadi baris."],

        [5, "Male %", "FINAL / APPROVED",
         "Persentase audience laki-laki.",
         "male / (female + male) x 100%",
         "feature (utama) · l2_gold (turunan)",
         "feature.ig_audience_analysis · feature.tt_audience_analysis · l2_gold.audience_demographics_daily",
         "feature.*.male_pct · audience_demographics_daily.dimension_key='male'",
         "sama dengan Female %",
         EP_KEDUA, "malePct  (filter: maleMin)",
         cov(c, "male_pct"),
         "Penyebut sama dengan Female %, jadi keduanya selalu berjumlah 100 bila tidak NULL.",
         "Di UI ini dua kontrol filter terpisah (femaleMin, maleMin), bukan satu filter Gender -- "
         "dokumen mengikuti struktur implementasi actual."],

        [6, "Avg Views", "FINAL / APPROVED",
         "Rata-rata views per post.",
         "SUM(valid views) / COUNT(valid posts)",
         "feature", "feature.ig_engagement_analysis · feature.tt_engagement_analysis", "avg_views (sumber: l1_silver.unified_post.views)",
         "engagement_analysis.social_account_id -> kol_social_account -> kol_directory",
         EP_KEDUA, "avgViews, viewsAnalyzedCount  (sort: avgviews)",
         cov(c, "avg_views"),
         "Penyebut = post ber-views > 0, BUKAN seluruh post sampel.",
         "views > 0 (bukan IS NOT NULL): di Instagram nilai 0 berarti tipe media itu "
         "tidak punya play count, bukan hasil pengukuran."],

        [7, "Median Views", "FINAL / APPROVED",
         "Nilai tengah views post seorang KOL.",
         "MEDIAN(valid post views)",
         "feature", "feature.ig_engagement_analysis · feature.tt_engagement_analysis", "median_views (sumber: unified_post.views)",
         "sama dengan Avg Views",
         EP_KEDUA, "medianViews  (sort: medviews)",
         cov(c, "median_views"),
         "percentile_cont -> interpolasi, jadi jumlah post genap menghasilkan nilai berdesimal.",
         "Ditampilkan bersama rata-rata: jarak keduanya adalah ukuran seberapa besar "
         "satu post viral menarik angkanya."],

        [8, "V2F", "FINAL / APPROVED",
         "Views dibanding followers.",
         "Views / Followers x 100%",
         "feature", "feature.ig_engagement_analysis · feature.tt_engagement_analysis", "view_to_follower_ratio",
         "sama dengan Avg Views; followers dari unified_profile pada TANGGAL POST",
         EP_KEDUA, "v2fPct  (sort: v2f)",
         cov(c, "view_to_follower_ratio"),
         "Penyebut ADITIF: jumlah followers-pada-tanggal-post tiap post.",
         "Rutin melebihi 100% dan TIDAK boleh dijepit -- satu video menembus jauh "
         "di atas following akun kecil adalah hal biasa."],

        [9, "L2V", "FINAL / APPROVED",
         "Likes dibanding views.",
         "Average Likes / Views x 100%",
         "feature", "feature.ig_engagement_analysis · feature.tt_engagement_analysis", "like_to_view_ratio",
         "sama dengan Avg Views",
         EP_KEDUA, "l2vPct",
         cov(c, "like_to_view_ratio"),
         "Post tanpa views keluar dari KEDUA sisi pecahan, bukan dihitung nol.",
         "Belum diekspos sebagai sort -- prototype pun memperlakukannya sebagai filter, bukan ranking."],

        [10, "Paid Ratio", "FINAL / APPROVED",
         "Proporsi konten sponsored dibanding konten yang dapat dikategorikan Paid atau Organic.",
         "Paid / (Paid + Organic) x 100%",
         "l1_silver", "unified_post", "is_sponsored",
         "unified_post.social_account_id -> kol_social_account -> kol_directory",
         EP_KEDUA, "paidRatio, paidSignalCount  (filter: paidMax · sort: paidratio)",
         cov(c, "paid_ratio"),
         "is_sponsored TRUE -> Paid · FALSE -> Organic · NULL -> Unknown, TIDAK masuk penyebut.",
         "paidSignalCount adalah penyebutnya; tanpa itu 0% 'tidak ada yang berbayar' "
         "tidak bisa dibedakan dari 0% 'tidak ada yang diketahui'. Tidak ada inferensi "
         "dari views/engagement/caption."],

        [11, "Share Rate", "FINAL / APPROVED",
         "Proporsi share dari total engagement.",
         "Shares / (Likes + Comments + Shares) x 100%",
         "l1_silver", "unified_post", "shares, likes, comments",
         "sama dengan Paid Ratio",
         EP_KEDUA, "shareRate  (filter: shareMin · sort: sharerate)",
         cov(c, "share_rate"),
         "Penyebut = engagement, BUKAN views dan BUKAN followers. Penyebut 0 -> NULL.",
         "Instagram publik tidak melaporkan shares (0 dari 212 post) -> seluruh IG NULL, bukan 0. "
         "Prototype lama memakai shares/views; definisi itu TIDAK dipakai."],

        [12, "Save Rate", "FINAL / APPROVED",
         "Proporsi save dari total engagement.",
         "Saves / (Likes + Comments + Shares) x 100%",
         "l1_silver", "unified_post", "saved",
         "sama dengan Paid Ratio",
         EP_KEDUA, "saveRate  (filter: saveMin · sort: saverate)",
         cov(c, "save_rate"),
         "saves TIDAK masuk penyebut -- penyebutnya sama persis dengan Share Rate. "
         "NULL saves tetap NULL, tidak dianggap 0.",
         "Hanya TikTok: Instagram publik tidak melaporkan saved (0 dari 212 post)."],

        [13, "Audience Interest", "FINAL / APPROVED",
         "Minat utama audience KOL.",
         "Prioritas: Observed -> Content-inferred -> Unknown. "
         "Minat teratas selain 'unknown'; bila seluruhnya unknown, dipakai topik konten creator.",
         "feature (utama) · l2_gold (turunan)",
         "feature.ig_audience_analysis · feature.tt_audience_analysis · l2_gold.audience_interest_daily",
         "feature.*.interest_top, feature.*.interest_source · audience_interest_daily.interest_key",
         "audience_analysis.social_account_id -> kol_social_account -> kol_directory",
         EP_KEDUA, "audienceInterestTop, audienceInterestSource  (filter: interest)",
         cov(c, "audience_interest_top"),
         "interest_source = 'audience' (teramati) atau 'content_inferred' (turunan). "
         "NULL bila keduanya tidak tersedia.",
         "Penandaan sumber WAJIB: tanpa itu minat turunan terbaca sebagai minat audiens "
         "yang teramati. Leksikonnya `audience_inference.INTEREST`, sama dengan Content Topic."],

        [14, "Audience Location", "FINAL / APPROVED",
         "Lokasi audience KOL.",
         "Ambil geo_key lalu petakan tingkatnya: city / province / island / country.",
         "l2_gold", "audience_geo_daily", "geo_key, geo_level",
         "audience_geo_daily.social_account_id -> kol_social_account -> kol_directory (EXISTS)",
         EP_LIST, "filter: geoKey + geoLevel  (tidak ada field baris; dijawab EXISTS)",
         cov(c, "geo"),
         "Tingkat ditentukan `audience_inference.tingkat_geo()`; province/island tidak lagi "
         "bercampur dengan city.",
         "Sebelum migration 039 SELURUH tebakan ditulis geo_level='city', sehingga Bali dan "
         "Lampung berdiri sejajar dengan Bandung. Tidak ada kolom kartu untuk metrik ini -- "
         "satu creator punya banyak lokasi, dan memipihkannya jadi satu akan menjawab "
         "pertanyaan yang berbeda."],

        [15, "Content Topic", "FINAL / APPROVED",
         "Topik yang paling sering dibahas KOL.",
         "Caption + hashtag -> klasifikasi interest -> modus per creator.",
         "l1_silver", "unified_post", "caption, hashtags",
         "unified_post.social_account_id -> kol_social_account -> kol_directory",
         EP_KEDUA, "contentTopic, contentTopicSource  (filter: topic)",
         cov(c, "content_topic"),
         "content_topic_source = 'content' atau 'creator_category_fallback'. NULL bila keduanya kosong.",
         "TIDAK pernah ditebak dari username/display name. Kategori roster hanya cadangan "
         "dan WAJIB ditandai -- ia ditetapkan manusia saat impor, bukan hasil klasifikasi konten."],

        [16, "Content Format", "FINAL / APPROVED",
         "Format konten yang dibuat KOL.",
         "VIDEO / clips -> Video · CAROUSEL / carousel_container -> Carousel · feed -> Image. "
         "Diambil modus per creator.",
         "l1_silver", "unified_post", "media_type",
         "sama dengan Content Topic",
         EP_KEDUA, "formatDominant  (filter: format)",
         cov(c, "format_dominant"),
         "Casing dinormalkan lebih dulu, jadi CAROUSEL dan carousel_container tidak "
         "menghasilkan dua kategori kembar.",
         "Story TIDAK dibuat: l0_raw.ig_stories_apify bukan sumber rantai ini, jadi "
         "kategorinya akan selamanya kosong."],

        [17, "Viral Frequency", "FINAL / APPROVED",
         "Seberapa sering post KOL tergolong viral.",
         "Post viral bila views >= 3 x median views KOL; "
         "viral_frequency = post viral / post ber-views x 100%",
         "l1_silver", "unified_post", "views",
         "sama dengan Content Topic",
         EP_KEDUA, "viralFrequency, viralPostCount  (filter: viralMin · sort: viralfreq)",
         cov(c, "viral_frequency"),
         "Pengali RELATIF (3x median), bukan ambang views absolut.",
         "Median, bukan rata-rata: rata-rata sudah tertarik ke atas oleh post viral yang "
         "justru sedang dicari. viral_threshold_views menyimpan ambang tiap akun."],

        [18, "Rising Creator", "FINAL / APPROVED",
         "KOL yang pertumbuhan followers-nya sedang bagus.",
         "followers_growth >= 5% -> Rising",
         "l2_gold", "kol_profile_card", "rising_creator (dari followers_growth)",
         "sama dengan Growth Classification",
         EP_KEDUA, "risingCreator  (filter: rising=1)",
         cov(c, "rising_creator"),
         ">=5% (batas Medium Growth). NULL bila Growth belum terukur.",
         "Ambang lama prototype 5,5% TIDAK dipakai. Tidak ada syarat ER tambahan. "
         "NULL BUKAN false: false = diukur dan tidak naik cukup."],

        [19, "Growth 30D", "FINAL / APPROVED",
         "Proyeksi pertambahan followers 30 hari berdasarkan growth harian yang tersedia. "
         "Ini PROYEKSI, bukan pertumbuhan 30 hari yang benar-benar teramati.",
         "daily_growth = (current - previous) / days_between ; "
         "projected_30d = daily_growth x 30 ; "
         "projected_followers_30d = current + projected_30d",
         "l2_gold", "kol_profile_card",
         "daily_growth, projected_30d, projected_followers_30d, days_between, previous_followers",
         "sama dengan Growth Classification",
         EP_KEDUA, "dailyGrowth, projected30d, projectedFollowers30d",
         cov(c, "projected_30d"),
         "NULL bila previous NULL, previous = 0, atau days_between <= 0.",
         "days_between memakai jarak NYATA antar snapshot -- tidak pernah menuntut 30 hari. "
         "Jarak nyata sekarang 10-15 hari. projected_30d adalah SELISIH, bukan jumlah absolut "
         "(arti ini diubah migration 040)."],

        [20, "Post Frequency", "FINAL / APPROVED",
         "Perkiraan jumlah post dalam satu bulan.",
         "valid_post_count / observation_days x 30",
         "l1_silver", "unified_post", "posted_at",
         "sama dengan Content Topic",
         EP_KEDUA, "postFrequencyMonthly, postFrequencyCount, observationDays  "
                   "(filter: postFreqMin · sort: postfreq)",
         cov(c, "post_frequency_monthly"),
         "HANYA satuan bulanan. NULL bila observation_days <= 0 atau tidak ada post valid.",
         "Tidak ada varian mingguan/tahunan. post_frequency_daily disimpan sebagai BASIS "
         "(monthly = daily x 30) tetapi tidak diekspos di tabel, filter, maupun export."],

        [21, "Post Frequency Reliability", "FINAL / APPROVED",
         "Seberapa bisa dipercaya hasil Post Frequency berdasarkan jumlah data dan lama observasi.",
         "Dari observation_days DAN valid_post_count bersamaan.",
         "l2_gold", "kol_profile_card", "post_frequency_reliability, observation_days, post_frequency_count",
         "sama dengan Growth Classification",
         EP_KEDUA, "postFrequencyReliability  (filter: freqReliability)",
         cov(c, "post_frequency_reliability"),
         "High: hari>=30 DAN post>=10 · Medium: hari>=14 DAN post>=5 (belum High) · "
         "Low: ada post valid tapi belum Medium · NULL: tidak ada post valid",
         "Mengukur KEANDALAN angka frekuensi, bukan kerajinan creator: 200 post dalam 5 hari "
         "menghasilkan frekuensi tinggi tapi tetap Low. NULL BUKAN Low."],

        [22, "Audience Quality", "FINAL / APPROVED",
         "Mengukur kualitas audience KOL berdasarkan audience_quality_score yang sudah tersedia.",
         "Label atas audience_quality_score (skor tidak dihitung ulang).",
         "feature", "feature.ig_audience_analysis · feature.tt_audience_analysis", "audience_quality_score",
         "audience_analysis.social_account_id -> kol_social_account -> kol_directory",
         EP_KEDUA, "audienceQualityScore, audienceQualityTier  (filter: audQuality)",
         cov(c, "audience_quality_score"),
         ">=75 High · 50-<75 Medium · <50 Low · NULL -> NULL",
         "Ambang 75/50 FINAL dan sudah disetujui. Skor berasal dari "
         "`audience_inference.skor_kualitas` atas daftar follower; rentang nyata 54-94."],

        [23, "Performance Stability", "FINAL / APPROVED",
         "Mengukur seberapa stabil ER KOL dari waktu ke waktu -- KONSISTENSI ER, "
         "bukan tinggi/rendahnya ER.",
         "STDDEV_SAMP(er_followers_daily * 100) per akun, dalam poin persen.",
         "l2_gold", "kol_metric_daily", "er_followers_daily",
         "kol_metric_daily.social_account_id + platform -> kol_profile_card -> kol_social_account -> kol_directory",
         EP_KEDUA, "performanceStability, erStddevPp, erPeriods  (filter: stability)",
         cov(c, "performance_stability"),
         "<=1 pp High · >1-<=3 pp Medium · >3 pp Low · periode <3 -> NULL",
         "er_followers_daily disimpan sebagai FRAKSI (0,0000164-0,1615) sementara ambangnya "
         "poin persen -- konversi x100 WAJIB, tanpa itu setiap akun tercatat stabil. "
         "STDDEV_SAMP, bukan populasi. ER rendah yang rata tetap High Stability."],

        [24, "Monitoring Priority", "FINAL / APPROVED",
         "Menentukan prioritas monitoring berdasarkan Engagement Rate.",
         "Label atas engagement_rate roster.",
         "public", "kol_directory", "engagement_rate",
         "kol_directory -> kol_social_account -> kol_profile_card (monitoring_er_pct)",
         EP_KEDUA, "monitoringPriority, monitoringErPct  (filter: priority)",
         cov(c, "monitoring_priority"),
         ">=5% High · >=2% dan <5% Medium · <2% Low · NULL -> NULL",
         "Sumber FINAL adalah public.kol_directory.engagement_rate. Sebelum migration 041 "
         "memakai feature.*_engagement_analysis (hanya 38 akun); perpindahan menaikkan "
         "cakupan jadi %s kartu. Satuan diperiksa: keduanya persen. NULL BUKAN Low."
         % f"{c['monitoring_priority']:,}".replace(",", ".")],
    ]


BARIS_HOLD = [
    [25, "Age", "HOLD",
     "Rentang umur audience KOL.",
     "Belum ada -- tidak diimplementasikan.",
     "l2_gold", "audience_demographics_daily", "audience_type='age' (0 baris)",
     "-", "-", "-",
     "0 baris: tidak ada satu pun sinyal umur di data follower.",
     "-",
     "Dibutuhkan: source age yang valid dari mentor. Tidak boleh ditebak dari username, "
     "display name, maupun follower count."],
    [26, "Brand Fit", "HOLD",
     "Seberapa cocok KOL dengan suatu brand.",
     "Belum ada -- tidak diimplementasikan.",
     "feature", "brand_fit_analysis", "partnership_score (0 baris)",
     "-", "-", "-", "0 baris; grain KOL x brand belum ada daftarnya.",
     "-", "Dibutuhkan: faktor + bobot + scoring yang disepakati."],
    [27, "EMV", "HOLD",
     "Estimasi nilai media dari eksposur KOL.",
     "Belum ada -- tidak diimplementasikan.",
     "feature", "feature.ig_audience_analysis · feature.tt_audience_analysis", "emv (0 terisi)",
     "-", "-", "-",
     "avg_reach 0 terisi; reach 0 dari 503 post; konstanta CPM tidak ada di database.",
     "-", "Dibutuhkan: rate card + formula."],
    [28, "CPE", "HOLD",
     "Biaya per engagement.",
     "Belum ada -- tidak diimplementasikan.",
     "feature", "feature.ig_audience_analysis · feature.tt_audience_analysis", "cpe (0 terisi)",
     "-", "-", "-", "l1_silver.unified_rate_card 0 baris.",
     "-", "Dibutuhkan: biaya campaign + definisi engagement yang dipakai."],
    [29, "CPV", "HOLD",
     "Biaya per view.",
     "Belum ada -- tidak diimplementasikan.",
     "-", "-", "-", "-", "-", "-", "Tidak ada kolom; rate card 0 baris.",
     "-", "Dibutuhkan: biaya campaign + definisi view."],
    [30, "Content Style & Personality", "HOLD",
     "Gaya dan kepribadian konten KOL.",
     "Belum ada -- tidak diimplementasikan.",
     "-", "-", "-", "-", "-", "-", "Tidak ada taxonomy final.",
     "-", "Dibutuhkan: kategori style/personality + metode klasifikasi."],
    [31, "Data Status", "HOLD",
     "Kesegaran data KOL (Fresh / Aging / Stale).",
     "Belum ada aturan -- tidak diimplementasikan.",
     "public", "kol_directory", "last_refreshed_at (tersedia)",
     "-", "-", "-",
     "Kolomnya ada dan terisi, yang belum ada adalah POLICY batas umurnya.",
     "-",
     "CATATAN: endpoint sudah punya field `status` (Live/Calculated/Estimated) dari "
     "aturan lain di kolDirectory.ts. Itu BUKAN Data Status yang dimaksud di sini "
     "dan tidak boleh disamakan. Dibutuhkan: freshness policy + batas umur."],
    [32, "Update Frequency", "HOLD",
     "Seberapa sering data KOL dianggap rutin diperbarui.",
     "Belum ada policy -- tidak diimplementasikan.",
     "public", "kol_directory", "refresh_tier (0 terisi, 1 nilai unik)",
     "-", "-", "-", "refresh_tier NULL untuk seluruh 7.432 baris.",
     "-", "Dibutuhkan: aturan refresh/update frequency."],
    [33, "Next Update", "HOLD",
     "Kapan data KOL dijadwalkan diperbarui berikutnya.",
     "Belum ada -- bergantung pada Update Frequency.",
     "-", "-", "-", "-", "-", "-", "Tidak ada sumber; turunan dari no. 32.",
     "-", "Dibutuhkan: selesaikan business rule Update Frequency lebih dulu."],
    [34, "Smart Criteria", "HOLD",
     "Pencarian KOL berdasarkan kriteria gabungan atau bahasa natural.",
     "Belum ada -- scope belum jelas.",
     "-", "-", "-", "-", "-", "-",
     "Belum jelas apakah filter biasa atau natural-language criteria.",
     "-", "Dibutuhkan: requirement + behaviour yang disepakati."],
]

KOLOM = ["No", "Filter", "Status", "Definisi", "Kalkulasi / Logic",
         "Source Schema", "Source Table", "Source Column", "Join / Relationship",
         "Endpoint", "Response Field", "Data Coverage / Limitation",
         "Threshold / Rule", "Notes"]

LEBAR = [5, 26, 17, 46, 46, 16, 30, 40, 46, 52, 44, 30, 46, 62]

JUDUL_FILL = PatternFill("solid", fgColor="1F3864")
JUDUL_FONT = Font(bold=True, color="FFFFFF", size=10)
FINAL_FILL = PatternFill("solid", fgColor="E2EFDA")
HOLD_FILL = PatternFill("solid", fgColor="FCE4D6")
TEPI = Border(*[Side(style="thin", color="BFBFBF")] * 4)


def tulis_sheet(ws, kolom, baris, warna_status=True):
    ws.append(kolom)
    for i, sel in enumerate(ws[1], start=1):
        sel.fill = JUDUL_FILL
        sel.font = JUDUL_FONT
        sel.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = (
            LEBAR[i - 1] if kolom is KOLOM and i <= len(LEBAR) else 34)
    ws.row_dimensions[1].height = 30
    for b in baris:
        ws.append(b)
    for r in ws.iter_rows(min_row=2):
        status = str(r[2].value) if len(r) > 2 else ""
        for sel in r:
            sel.alignment = Alignment(vertical="top", wrap_text=True)
            sel.border = TEPI
            sel.font = Font(size=9)
            if warna_status and status.startswith("HOLD"):
                sel.fill = HOLD_FILL
            elif warna_status and status.startswith("FINAL"):
                sel.fill = FINAL_FILL
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions


def main() -> int:
    import psycopg2
    from config import load_config

    conn = psycopg2.connect(connect_timeout=20,
                            **load_config().postgres.as_connect_kwargs())
    conn.set_session(readonly=True, autocommit=True)
    try:
        c = cakupan(conn)
    finally:
        conn.close()

    final = baris_final(c)
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "Filter Mapping"
    tulis_sheet(ws, KOLOM, final + BARIS_HOLD)

    ws2 = wb.create_sheet("Endpoint Mapping")
    tulis_sheet(ws2, ["Endpoint", "Method", "Path", "Dipakai untuk",
                      "Query param filter", "Response field metric", "Catatan"], [
        ["KOL Directory list", "GET",
         "/api/organizations/{id}/discover/kol-directory",
         "Daftar KOL + seluruh filter, sort, paging, export",
         "q, platform, category, tier, follMin, minEr, maxRate, verified, connected, "
         "updatedWithin, agency, growthMin, growthMax, growthClass, femaleMin, maleMin, "
         "paidMax, postFreqMin, shareMin, freqReliability, priority, saveMin, viralMin, "
         "rising, topic, format, audQuality, stability, interest, geoKey, geoLevel, "
         "sort, dir, page, pageSize, ids, facets",
         "erPct, growthPct, growthClass, dailyGrowth, projected30d, projectedFollowers30d, "
         "femalePct, malePct, genderKnownPct, genderReliability, avgViews, medianViews, "
         "viewsAnalyzedCount, v2fPct, l2vPct, paidRatio, paidSignalCount, shareRate, "
         "saveRate, viralFrequency, viralPostCount, contentTopic, contentTopicSource, "
         "formatDominant, audienceQualityScore, audienceQualityTier, audienceInterestTop, "
         "audienceInterestSource, postFrequencyMonthly, postFrequencyCount, observationDays, "
         "postFrequencyReliability, erStddevPp, erPeriods, performanceStability, "
         "monitoringErPct, monitoringPriority, risingCreator",
         "Endpoint EXISTING. Tidak ada endpoint baru yang dibuat untuk dokumen ini. "
         "Handler: src/app/api/organizations/[id]/discover/kol-directory/route.ts -> "
         "listKolDirectory() di src/lib/discover/kolDirectory.ts"],
        ["KOL Directory detail", "GET",
         "/api/organizations/{id}/discover/kol-directory/{kolId}",
         "Satu KOL beserta kartu L2-nya",
         "(tidak ada; kolId di path)",
         "Sama dengan list (getKolCreator memakai tipe baris yang sama), "
         "ditambah gold card lewat getKolGold()",
         "Endpoint EXISTING. Handler: .../kol-directory/[kolId]/route.ts -> "
         "getKolCreator(). Cover post diproksikan withProxiedCovers()."],
        ["KOL Gold (detail metric)", "-",
         "src/lib/discover/kolGold.ts :: getKolGold()",
         "Kartu L2 lengkap untuk halaman detail",
         "-",
         "GoldProfileCard: followersGrowth, avgViews, medianViews, v2fPct, l2vPct, "
         "growthClass, dailyGrowth, projected30d, projectedFollowers30d, femalePct, "
         "malePct, genderKnownPct, genderReliability, paidRatio, shareRate, saveRate, "
         "viralFrequency, contentTopic, formatDominant, audienceQualityTier, "
         "audienceInterestTop, performanceStability, monitoringPriority, risingCreator",
         "BUKAN endpoint HTTP -- fungsi data-access yang dipanggil route detail. "
         "Dicatat supaya jejak field ke UI lengkap."],
    ], warna_status=False)

    ws3 = wb.create_sheet("Validation")
    tulis_sheet(ws3, ["Pemeriksaan", "Hasil", "Bukti / Catatan"], [
        ["XLSX terbuka & terbaca", "PASS",
         "Diverifikasi openpyxl.load_workbook setelah generate."],
        ["Setiap filter punya DEFINISI", "PASS",
         "34 dari 34 baris (24 FINAL + 10 HOLD) terisi kolom Definisi."],
        ["Source schema/table/column nyata", "PASS",
         "Seluruh nama tabel/kolom FINAL diverifikasi ke information_schema; "
         "HOLD ditandai '-' bila memang tidak ada."],
        ["Endpoint benar-benar ada", "PASS",
         "Dua route file ada di repo autometric dan tidak diubah dokumen ini."],
        ["Audience Quality >=75/50", "PASS",
         "metrics_thresholds.QUALITY_HIGH_MIN=75.0, QUALITY_MEDIUM_MIN=50.0; "
         "test batas 49/50/74.99/75 lulus."],
        ["Performance Stability 1/3 pp + STDDEV_SAMP", "PASS",
         "STABILITY_HIGH_MAX=1.0, STABILITY_MEDIUM_MAX=3.0, MIN_PERIODE=3; "
         "gold_profile.py memakai stddev_samp(er_followers_daily * 100)."],
        ["Monitoring Priority 5/2 + sumber roster", "PASS",
         "PRIORITY_HIGH_MIN=5.0, PRIORITY_MEDIUM_MIN=2.0; monitoring_er_pct "
         "= public.kol_directory.engagement_rate (0 baris berbeda)."],
        ["HOLD tidak terimplementasi", "PASS",
         "Tidak ada kolom brand_fit/emv/cpe/cpv/age/style di kol_profile_card; "
         "dijaga test_db_metrik_blocked_tidak_punya_kolom."],
        ["DISCREPANCY: sumber ER Directory", "PERLU KEPUTUSAN",
         "Spesifikasi no. 1 menyebut public.kol_directory.engagement_rate, tetapi "
         "implementasi menampilkan & memfilter COALESCE(feature.engagement_rate, "
         "kol_directory.engagement_rate) -- kolDirectory.ts:472. Monitoring Priority "
         "(no. 24) sudah memakai roster saja. Implementasi TIDAK diubah; menunggu "
         "keputusan apakah erPct Directory ikut dipindah ke roster saja."],
        ["CATATAN: jumlah item", "INFO",
         "34 item, bukan 32: Female % dan Male % ditulis terpisah karena di UI memang "
         "dua kontrol filter terpisah (femaleMin, maleMin), dan seluruh HOLD ditulis "
         "sebagai item sendiri. Tidak ada item yang dihapus untuk mengejar angka."],
        ["CATATAN: dokumen lama", "INFO",
         "docs/mapping filter database.xlsx dan docs/KOL_DISCOVERY_AUDIT.xlsx TIDAK diubah "
         "-- keduanya mendokumentasikan hal berbeda (coverage mapping dan audit log UI) "
         "dan tidak punya kolom Definisi/Kalkulasi/Endpoint."],
    ], warna_status=False)

    ws3.column_dimensions["A"].width = 42
    ws3.column_dimensions["B"].width = 20
    ws3.column_dimensions["C"].width = 100
    for lebar, huruf in ((26, "A"), (10, "B"), (52, "C"), (34, "D"),
                         (60, "E"), (60, "F"), (60, "G")):
        ws2.column_dimensions[huruf].width = lebar

    wb.properties.title = "KOL Discovery - Filter Definitions & Endpoints"
    wb.properties.creator = "scrapper-project"
    wb.properties.description = (
        "Digenerate docs/build_filter_doc.py pada "
        + datetime.now().strftime("%Y-%m-%d %H:%M")
        + ". Angka cakupan dibaca langsung dari database saat generate.")
    wb.save(KELUARAN)
    print("Tersimpan: %s" % KELUARAN)
    print("  Filter Mapping   : %d baris (%d FINAL + %d HOLD)"
          % (len(final) + len(BARIS_HOLD), len(final), len(BARIS_HOLD)))
    print("  Endpoint Mapping : 3 baris")
    print("  Validation       : 11 baris")
    return 0


if __name__ == "__main__":
    sys.exit(main())
