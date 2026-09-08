# AUTOME_2 Readiness Audit

**Read-only · 8 September 2026 · tidak ada perubahan kode / DB / pipeline / endpoint / commit**

| Sumber kebenaran | Detail |
|---|---|
| UI (requirement) | `app/AUTOME_2.html` — 5.736 baris, 41 modul JS |
| Pipeline | `scrapper-project` @ `4903965` — 34 migration, 19 Dagster asset |
| API | `D:/intern/autometric` branch `engkol_v1` @ `19e2616` — 108 route |
| Database | `kol` — `l0_raw`, `l0_harmonization`, `l1_silver`, `feature`, `l2_gold`, `public` |

## ⚠ Batas pembuktian

DB produksi **tidak bisa dihubungi dari mesin ini** (`.env` → `PG_HOST=localhost`, `PG_PASSWORD` kosong, gagal `fe_sendauth: no password supplied`). **Tidak ada angka jumlah baris di dokumen ini yang diukur hari ini.**

- **Definitif:** schema & logic — dibaca langsung dari 34 migration, 19 asset, 10.665 baris query layer app.
- **Perlu verifikasi ulang:** angka baris & coverage — dikutip dari pengukuran bertanggal di dalam sumber itu sendiri (migration 023 @21 Agu, `kolGold.ts`/`kolMeasured.ts` @1 Sep, `docs/KOL_DISCOVERY_AUDIT.md` @3–7 Sep).

## Tiga temuan yang mengubah premis

1. **Prototype punya dua panel filter, yang kedua menang.** `directory-filters2.js` mendefinisikan ulang `filterPanelHTML()` di atas `directory-filters.js`. Yang dirender = 6 grup / 28 filter (`FPG`). Panel lama (slider EMV, authenticity, brand fit, paid ratio, campaigns) masih di file tapi **tidak pernah tampil** — jangan dihitung sebagai requirement.
2. **Tier bukan lagi mismatch.** `TIER_TIP` di panel aktif (Mid-tier 50K–500K, Macro 500K–1M) sudah cocok dengan `public.kol_tiers` sesudah migration 033/034. Yang bercabang adalah panel lama yang mati.
3. **Endpoint bukan nol, tapi bukan di repo ini.** `scrapper-project` tidak punya framework web (`requirements.txt` = apify-client, psycopg2, python-dotenv). Seluruh API ada di repo `autometric`. Filter KOL Directory ter-expose: **10 dari 28** (`q, platform, category, tier, follMin, minEr, maxRate, growthMin, growthMax, connected`).

---

# Matriks

Status: **A** ready · **B** data ada belum diolah · **C** sudah diolah belum ada endpoint · **D** filter gap · **E** source gap · **F** ambigu

## 1. Identitas & profil

| Prototype element | Data source | DB table.column | Join | Calculation | Pipeline | Endpoint | Filter logic | Data ada? | Gap | Action | St |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Username | roster | `kol_directory.username` | — | — | roster | ada | `ILIKE %q%` | 97,1% | — | — | A |
| Display name | L2 | `kol_profile_card.display_name` | `kol_directory→kol_social_account→kol_profile_card` | — | `kol_profile_card` | detail saja | ikut search di `db.py` | 25,4% | list endpoint tak mengembalikannya | tambah ke `KolDirectoryRow` + BASE | C |
| Avatar | roster | `kol_directory.avatar_url` | — | — | roster | ada | — | 12,1% | 87,9% kosong, fallback inisial jalan | backfill dari `profilePicUrl` raw | A |
| Verified badge | ambigu, 3 definisi | L1/L2 `is_verified`=Connected · `kol_directory.verified_status`=badge (454) · `tt_profile_apify.is_verified` | `social_account` | `platform_user_id IS NOT NULL AND oauth_token IS NOT NULL` | `unified_profile` | `?connected=1` | EXISTS | Connected = **0 KOL** | mismatch semantik: prototype gambar centang platform | keputusan **F-1** | F |
| Platform | roster | `platforms.key` | `kol_directory.platform_id` | — | roster | `?platform=` | equality | 97,1% | prototype multi-platform per kreator, DB 1:1; YouTube tak ada baris | definisikan grouping / kunci ke IG+TikTok | D |
| Kategori | roster | `kol_categories.name` (28) / `.taxonomy_key` (9) | `EXISTS c.id = ANY(category_ids)` | — | roster | `?category=` pakai `name` | equality | 54,1% | app pakai `name`, `db.py` pakai `taxonomy_key`; prototype cuma kenal 5 | samakan ke `taxonomy_key` **F-2** | D |
| Niche | — | — | — | — | — | — | ikut search | ✗ | tidak ada kolom | turunkan dari hashtag / kurasi | E |
| Domisili kreator | roster | `kol_directory.creator_city` | — | — | tidak diisi | diambil sbg `city` | belum | kolom ada, **isi 0%** | UI app sudah men-*disable* kontrolnya | butuh source | E |
| Agency | roster | `agency_kol_accounts` + `agencies.name` | LATERAL, attach sesudah paging | — | roster | ada | belum | 7.684 / 7.718 | — | — | A |
| Followers | roster | `kol_directory.followers_count` | — | — | roster | `?follMin=` | `>=` | 97,1% | — | — | A |
| Tier | lookup | `kol_tiers.name` (band min/max) | `followers BETWEEN min AND max` | band lookup | `unified_profile.tier`, `kol_profile_card.tier` | `?tier=a,b` | `IN` | 93,2% | sudah ditutup migration 033/034 | jalankan ulang `transform_chain_job` | A |
| Data confidence badge | roster | `last_refreshed_at` + `scrape_status` | — | `≤7hr→Live · success→Calculated · else Estimated` | roster | ada (`status`) | belum | timpang: Estimated 77,3%, Live 1 | rumus benar, populasi belum di-refresh | butuh scheduler rutin | D |
| Last synced | roster | `kol_directory.last_refreshed_at` | — | format relatif di client | roster | ada | **belum** (`dfLast`) | ✓ | data ada, filter belum | tambah `?refreshedAfter=` | D |
| Bio | roster | `kol_directory.bio` | — | — | roster | ada | ikut search di `db.py`, **tidak** di app | 11,7% | search app hanya `username` | port search berjenjang `db.py` | D |
| Profile URL | roster | `kol_directory.profile_url` | — | — | roster | ada | — | 97,1% | — | — | A |

## 2. Metrik performa

| Prototype element | Data source | DB table.column | Join | Calculation | Pipeline | Endpoint | Filter logic | Data ada? | Gap | Action | St |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Engagement rate | **3 sumber paralel** | `kol_directory.engagement_rate` · `feature.{ig,tt}_engagement_analysis.engagement_rate` · `kol_metric_daily.er_followers_daily` | `kol_social_account` | Σeng ÷ (followers × posts_in_sample); sampel `likes_hidden IS NOT TRUE AND is_collaboration IS NOT TRUE` | `kol_metric_daily` | `?minEr=` baca **roster** | `>=` | roster 22,7% · L2 26% baris | 3 angka ER per kreator tak dijamin sama; roster punya 83 nilai mustahil (maks 223%); **L2 fraksi 0..1 vs roster poin persen** | pilih 1 ER kanonik + konversi satuan | D |
| Avg views | L2 | `kol_metric_daily.views_sum`, `.posts_in_sample` | `kol_social_account` | `views_sum ÷ posts_in_sample` — belum ditulis | `kol_metric_daily` | ✗ | belum (`viewsHi`) | 30 kreator | agregat per akun belum ada | agregasi + endpoint | B |
| Median views | L2 | `post_metric.views` | `social_account_id` | prototype pakai `views × 0,82`, **bukan median** | `post_metric` | ✗ | belum | 477 baris | median asli bisa dihitung | `percentile_cont(0.5)` | B |
| Avg likes / comments | L1+L2 | `post_metric.likes/.comments` · `feature.*_engagement_analysis.total_*` + `posts_analyzed_count` | `social_account_id` | `total ÷ posts_analyzed_count` | feature + `post_metric` | ✗ | belum | ✓ sudah dihitung | tak pernah dikembalikan ke UI | **endpoint saja** | C |
| Avg shares / saves | actor | `post_metric.shares/.saves` | `social_account_id` | Σ per akun | `post_metric` | ✗ | belum (`saveHi`,`shareHi`) | **TikTok saja; IG NULL 0/130** | actor IG tak menyediakannya → filter Save/Share Rate membuang seluruh KOL Instagram | Insights API, atau batasi filter ke TikTok | E |
| Reach / Est. reach | — | `reach_sum`, `er_reach_daily`, `post_metric.reach` | — | *blocked column*, sengaja NULL | — | ✗ | belum | **NULL di setiap baris** | reach hanya dari Insights API | source baru | E |
| Impressions | — | — | — | — | — | ✗ | — | ✗ | metrik owned-account | Insights API | E |
| Posting frequency | L2 | `kol_metric_monthly.post_count`, `.active_days` | `social_account_id` | `post_count ÷ (hari ÷ 7)` — belum ada | `kol_metric_monthly` | ✗ | belum | 68 baris | rumus belum ada di layer mana pun | kalkulasi; hati-hati penyebut periode | B |
| Paid / sponsored ratio | actor | `post_metric.is_sponsored` | `social_account_id` | `COUNT(sponsored) ÷ COUNT(*)` — belum ada | `post_metric` | ✗ | belum | 30 kreator | flag `paidPartnership` asli platform, tinggal diagregasi | agregat + endpoint | B |
| Performance consistency | turunan | butuh ≥4 titik `kol_metric_monthly` | `social_account_id` | `100 − volatilitas tr[]` | blocked | ✗ | belum (`consHi`,`perfStab`) | **~5 KOL** punya ≥4 titik | terblokir **volume time-series**, bukan schema | scheduler rutin dulu | E |
| Trend 6 bulan `tr[]` | L2 | `kol_metric_monthly.followers_eom` | `social_account_id` | deret 6 titik | `kol_metric_monthly` | ✗ | — | 68 baris, ~5 KOL | **satu kekurangan ini memblokir 6 filter**: momentum, vol, viralDep, gClass, perfStab, consistency | akumulasi waktu | E |
| Quality score `k.q` | — | — | — | prototype tak mendefinisikan rumus | *sample* | ✗ | — | ✗ | app membangkitkannya deterministik dari id | definisikan **F-5** | F |
| Authenticity `k.auth` | — | — | — | `suspPct = 100 − auth` | *sample* | ✗ | belum | ✗ | **tapi `l1_silver.unified_follower` ada** dan belum dipakai untuk skor keaslian | bangun dari data follower | B |
| Brand affinity `k.aff` | — | — | — | menopang 6 metrik turunan `intel2()` | *sample* | ✗ | belum | ✗ | 1 field mock → 6 turunan | definisikan atau buang | F |
| Success rate `k.succ` | campaign | `public.campaigns`, `campaign_kols` | `kol_id` | — | **0 baris** | ✗ | — | ✗ | riwayat kampanye belum pernah diisi | data operasional | E |

## 3. Audiens

> **Dua jalur, jangan dicampur.** **A (terukur):** `ig_profile_official.demographics_*` → `unified_audience` = **0 baris**, butuh business account + token. **B (aktif hari ini):** `unified_follower` → `audience_inference.py` → `feature.*_audience_analysis` → `l2_gold.audience_*_daily`. Gender/lokasi/interest **tidak ada** di data follower — ketiganya ditebak dari `full_name` + `bio`, ditandai prefix `inferred_`. Pipeline menyimpan `unknown` sebagai baris tersendiri: tercatat **1.086 dari 1.300 follower tidak terdeteksi gendernya**. Menampilkan "59% pria" tanpa coverage = salah baca yang tak bisa diperbaiki di hilir.

| Prototype element | Data source | DB table.column | Join | Calculation | Pipeline | Endpoint | Filter logic | Data ada? | Gap | Action | St |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Gender split | inferensi | `audience_demographics_daily` (`audience_type='gender'`) | `social_account_id`+`audience_date` | share, **tanpa** unknown → wajib dibaca dgn coverage | `audience_gold` | ✗ | belum | 69 baris, inferred | filter "Female-skewed ≥60%" tak menyebut coverage | endpoint + tampilkan `confidence` & coverage | C |
| Age band | — | `audience_demographics_daily` (`='age'`) | — | — | **0 baris** | ✗ | belum | ✗ | **tidak ada sinyal umur** di data follower — bukan "belum diproses" | Insights API; matikan filter Age | E |
| Generasi (Gen Z / Millennial) | turunan age | — | — | map age→gen | — | ✗ | NL rule | ✗ | terblokir age | ikut age | E |
| Audience location | inferensi | `audience_geo_daily` (`geo_level='country'\|'city'`) | `social_account_id`+`audience_date` | share per `geo_key` | `audience_gold` | ✗ | belum | 181 baris, inferred | bukti terkuat hanya emoji bendera; "Jabodetabek" belum jadi konsep DB | endpoint + definisikan Jabodetabek | C |
| Audience interest | inferensi | `audience_interest_daily.interest_key` | `social_account_id`+`audience_date` | share | `audience_gold` | ✗ | belum | 214 baris, inferred | **ambigu**: prototype pakai `k.interests` untuk topik kreator *dan* minat audiens | pisahkan **F-4** | F |
| Audience quality `audQ` | turunan sample | — | — | `(auth + q) ÷ 2` | *sample* | ✗ | belum | ✗ | turunan dari 2 angka mock | ikut `auth` | B |
| Audience overlap | turunan | butuh ageTop+audLoc+interests | — | `40(age)+30(loc)+30×share interest` | — | ✗ | — | ✗ | butuh age yang tak ada — **tapi overlap follower bisa dihitung eksak** dari irisan `unified_follower` | ganti pendekatan | B |
| Purchase / brand / category affinity | turunan sample | — | — | semua fungsi dari `k.aff` | *sample* | ✗ | belum | ✗ | 3 metrik, 1 input mock | definisikan atau buang | F |
| Active hours heatmap | feature | `feature.*_engagement_analysis.best_posting_time_heatmap` | `social_account_id` | distribusi `posted_at` hari×jam | `feature_engagement` | ✗ | — | ✓ sudah dihitung | tak pernah di-expose; **ini jam posting kreator, bukan jam aktif audiens** seperti judul prototype | endpoint + perbaiki label | C |
| Geographic map top-6 | inferensi | `audience_geo_daily` (`city`) | `social_account_id` | top-N share | `audience_gold` | ✗ | — | ✓ inferred | data ada, endpoint tidak | endpoint saja | C |

## 4. Konten & post

| Prototype element | Data source | DB table.column | Join | Calculation | Pipeline | Endpoint | Filter logic | Data ada? | Gap | Action | St |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Post likes/comments/views | actor | `post_metric.likes/.comments/.views` | `social_account_id` | disalin dari L1 | L0→L1→`post_metric` | ✗ | — | 477 baris / 30 kreator | rantai lengkap, tak ada route | endpoint | C |
| Post shares/saves | actor | `post_metric.shares/.saves` | `social_account_id` | disalin dari L1 | `post_metric` | ✗ | — | TikTok saja | actor IG tak menyediakan; NULL ≠ 0 (pipeline benar) | Insights API | E |
| Post ER + rank | feature | `post_metric.er_followers`, `.rank_in_account` | `feature.*_post_analysis` | `engagement ÷ followers_at_post_date` (carry-forward snapshot ≤ post_date) | `feature_post`+`post_metric` | ✗ | — | **NULL 71% post** | risiko denominator sudah ditangani benar (NULL bukan 0) | endpoint; jangan render 0 untuk NULL | C |
| Format konten | actor | `post_metric.media_type` · `content_format_daily.media_type` | `social_account_id`+`metric_date` | agregat (akun,hari,format) | `content_format_daily` | ✗ | belum | 300 baris | **nilainya kata mentah**: `clips`,`carousel_container`,`feed`,`VIDEO`,`CAROUSEL`,`unknown`. Prototype minta Reels/Feed/Story/Carousel/Content + TikTok Video/Photo. **Story tak pernah di-scrape** | tetapkan mapping **F-6** | F |
| Hashtag / keyword | actor | `post_metric.top_hashtags` (jsonb) | `feature.*_post_analysis` | ekstraksi caption | `feature_post` | ✗ | — | 78 / 221 post | sudah dihitung, belum di-expose | endpoint | C |
| Sponsored / organic | actor | `post_metric.is_sponsored` | — | `paidPartnership` asli platform | `post_metric` | ✗ | belum | ✓ | flag resmi, bukan tebakan `#ad` | endpoint + filter | C |
| Cover image / permalink | actor | `post_metric.permalink` · `unified_post.cover_image` | — | — | `unified_post` | ada (proxy cover) | — | link CDN **sudah kedaluwarsa** semua | sudah ditangani app | — | A |
| Sentiment | **belum diolah** | `feature.*_post_analysis.sentiment_breakdown` — *blocked* | — | — | blocked | ✗ | belum (`repRisk`) | **bahan mentah ADA** | `latestComments` ikut di `raw_payload` scrape post IG, belum pernah dibaca | asset sentimen — **kandidat B paling bernilai** | B |
| Content category / topic | belum diolah | `feature.*_post_analysis.content_category` — *blocked* | — | — | blocked | ✗ | belum | bahan ada | caption+hashtag tersedia | klasifikasi topik | B |
| Content style / persona | — | — | — | prototype menulisnya tangan per kreator (`DNA2`) | — | ✗ | belum | ✗ | 10 nilai persona tanpa definisi cara menurunkan | otomatis atau manual? **F-7** | F |
| AI recommendation per post | — | `feature.*_post_analysis.ai_recommendation` — *blocked* | — | — | blocked | ✗ | — | ✗ | kolom siap, isi belum ada | layer LLM | E |
| Watch time / completion | — | `post_metric.avg_watch_time_seconds`, `.completion_rate` — *blocked* | — | — | blocked | ✗ | — | ✗ | metrik owned-account | Insights API | E |

## 5. Growth, komersial & brand fit

> **⚠ Mismatch penyebut.** Prototype menampilkan growth **"+6,4% / mo"** dengan ambang `gClass`: exploding ≥8%, rising ≥4,5%, stable ≥1%. Backend (`sp_build_unified_profile`, migration 031/034) menghitung **% perubahan terhadap snapshot sebelumnya** — jaraknya apa pun yang dihasilkan scraper, tercatat 10–13 hari, rentang **−0,051% s.d. +0,917%**. Akibatnya: **setiap KOL jatuh ke bucket `declining`**; 3 dari 4 chip Growth Classification selalu nol, dan "🚀 Rising Creator" (≥5,5%) meminta angka **6× nilai tertinggi** yang pernah ada. Bukan bug filter — dua definisi metrik berbeda dengan nama sama.

| Prototype element | Data source | DB table.column | Join | Calculation | Pipeline | Endpoint | Filter logic | Data ada? | Gap | Action | St |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Followers growth | L1 snapshot | `kol_profile_card.followers_growth` ← `unified_profile` | `kol_social_account` | `(now−prev)÷prev×100`, prev = `date` terdekat lebih kecil; NULL kalau prev NULL/0 | `sp_build_unified_profile` | `?growthMin=`,`?growthMax=` | range | NULL untuk mayoritas (di-scrape sekali) | **jarak snapshot bukan 30 hari**; label "/mo" salah | normalisasi per-30-hari **atau** ubah label UI | D |
| Growth classification | turunan | `followers_growth` | — | ambang 8 / 4,5 / 1 | `unified_profile` | ✗ | chip multi-select | efektif ✗ | 3 dari 4 bucket selalu kosong | kalibrasi ulang **sesudah** penyebut diperbaiki | D |
| Rising Creator | turunan | `followers_growth`+`er`+`tr[]` | — | growth ≥5,5% ∧ ER ≥4,5% ∧ foll <1M | blocked | ✗ | boolean | ✗ | ambang 6× maksimum; momentum butuh ≥3 snapshot, 0 akun punya | ikut perbaikan growth | D |
| Growth accel / stability / g7 / g90 | turunan | butuh deret snapshot | — | fungsi `tr[]` | blocked | ✗ | — | ✗ | terblokir volume time-series | waktu + scheduler | E |
| Rate card | platform KOL | `l1_silver.unified_rate_card.fee`, `.currency` | `kol_social_account` | `base × multiplier` per deliverable | `unified_rate_card` | `?maxRate=` + `/discover/rates` | `<=`; KOL tanpa rate card dibuang | **9.210 deliverable / 7.230 KOL — angka bertentangan** | prototype USD vs DB IDR; `kol_profile_card.rate_card*` sengaja NULL (1 sumber harga) | verifikasi **F-3**; kunci ke IDR | F |
| EMV | — | — | — | butuh reach + benchmark CPM | *sample* | ✗ | — | ✗ | terblokir reach; tak ada tabel benchmark | Insights API + benchmark | E |
| CPE / CPM / CPV | sebagian | `unified_rate_card.fee` + `post_metric.views` | `kol_social_account` | `CPV = rate ÷ views × 1000`; CPM butuh reach | `unified_rate_card` | ✗ | belum | CPV mungkin (30 kreator) | CPM butuh reach, CPE butuh biaya kampanye | hitung CPV dulu | B |
| Brand Fit / match | tabel ada, kosong | `feature.brand_fit_analysis.partnership_score`, `.sub_scores`, `.audience_overlap_pct`, `.category_fit_tags`, `.recommendations` | `agency_kol_account_id`+`brand_id` | rata-rata 6 komponen × matriks relevansi kategori | **tak ada asset** | ✗ | belum | tabel dibuat migration 014, **0 baris** | schema persis sesuai bentuk UI; hilang: asset pengisi + 4 dari 6 input masih mock | bangun asset sesudah audience quality nyata | E |
| Opportunity score & `oc` | turunan | — | — | komposit momentum+saturasi+camps+audQ+commEff | — | ✗ | belum | ✗ | setiap input blocked/mock | kerjakan paling belakang | E |
| Competitor saturation | — | — | — | prototype menyimpan daftar brand sebagai literal | — | ✗ | belum | ✗ | tak ada tabel riwayat kolaborasi brand–KOL | turunkan dari `taggedUsers`+`mentions` raw | B |
| Worked with my brand / repeat | workspace | tabel order + negotiation di app | `org→order→kol` | `EXISTS` order/nego selesai | app | ada | belum | ✓ | data internal, sudah ada tabelnya | filter query saja | D |

## 6. Data freshness, monitoring & modul lain

> **⚠ Seluruh grup Data Freshness berdiri di atas penyebut yang tidak ada.** Prototype menghitung `ratio = umur_data ÷ frekuensi_jadwal`, frekuensi dari prioritas (High 6 jam / Active harian / Standard mingguan / Low bulanan). Di DB **tidak ada frekuensi, prioritas, maupun jadwal berikutnya per KOL**. `scheduler_engine.py` eksplisit one-shot ("tidak ada loop, tidak ada cron, tidak ada retry", `MAX_RETRIES = 0`); `scheduler_logs` mencatat yang *sudah* jalan. `/admin/scheduler/config` mengatur jam sinkronisasi akun brand global, bukan monitoring per KOL. Tombol "Request Update Now" juga tanpa backend — route `/discover/creators/[id]/refresh` melayani entitas lain (`discover_creators` milik org), bukan roster KOL.

| Prototype element | DB table.column | Calculation | Endpoint | Data ada? | Gap | Action | St |
|---|---|---|---|---|---|---|---|
| Last Updated (5 bucket) | `kol_directory.last_refreshed_at` | `now() − last_refreshed_at` | field ada, filter tidak | ✓ | satu-satunya filter di grup ini yang punya kolom | tambah param filter — **paling murah** | D |
| Data Status (6 status) | butuh frekuensi per KOL | `ratio` <0,5 fresh / <0,85 aging / <1,2 due / else outdated | ✗ | ✗ | `updating`/`failed` juga butuh state job per KOL | tabel jadwal/monitoring | E |
| Update Frequency | — | — | ✗ | ✗ | tak ada konsep frekuensi per KOL | tabel `kol_monitoring` baru | E |
| Next Update | — | `last + frekuensi` | ✗ | ✗ | turunan frekuensi | ikut tabel monitoring | E |
| Monitoring Priority | — | dari: kampanye aktif, gClass exploding, viralFreq, camps ≥8 | ✗ | ✗ | semua input turunan blocked — **tapi "ada di order/nego aktif" bisa dijawab hari ini** | mulai dari aturan sederhana | E |
| Database Health bar | — | rata-rata freshness score | ✗ | ✗ | ikut Data Status | ikut tabel monitoring | E |
| Request Update Now | — | — | ✗ | ✗ | tak ada antrian scrape on-demand untuk roster | job queue + endpoint trigger | E |
| Compare multi-KOL | `kol_directory` | — | `?ids=` (maks 50, UUID-validated) | ✓ | — | — | A |
| Ordering / Cart / Checkout | tabel order app + Midtrans | subtotal→promo→fee 8%→pajak 11%, integer rupiah | 7 route `/discover/orders/*` + webhook | ✓ | prototype USD vs implementasi IDR | verifikasi field-by-field | A |
| Negotiation | tabel negotiation app | guaranteed fee + performance fee | ada (`negotiation.ts`, 785 baris) | ✓ | halaman prototype 1.237 baris, belum dibandingkan per field | audit terpisah | A |
| Discovery Content | `unified_post` + `unified_competitor_post` — post **brand & kompetitor** | ER diturunkan dari raw count | `/discover/content` | ✓ untuk korpus brand | **mismatch korpus**: prototype menampilkan konten para KOL | keputusan **F-8** | F |
| Audience Insights (halaman) | agregat korpus brand | — | `/discover/summary` | ✓ untuk korpus brand | mismatch korpus sama | **F-8** | F |
| AI Assistant | agregat performa org | konsep dari pillar & format yang perform | `/discover/assistant` | ✓ | — | — | A |
| Reports / export | template & export app | — | 8 route `/reports/*` | untuk laporan brand | laporan **per kreator** (`genRpt`) belum ada | tambah template per kreator | C |
| Saved List / Search / Collection / Favorite | — | — | ✗ | **tak ada tabel** | 4 collection bawaan + saved search + Favorite, semua state lokal | tabel + CRUD endpoint | E |
| Natural-language search (29 rule) | — | regex → predikat filter | ✗ | ~8 dari 29 rule datanya ada | sisanya menunggu data | implementasikan subset, sembunyikan sisanya | D |
| Similar creators | `kol_directory`+kategori+tier+ER | aturan bernama | `/discover/creators/similar` | ✓ | ada di app, tak eksplisit di prototype | — | A |

---

# A. READY

Username · profile URL · avatar (12,1%) · bio · followers · platform · `last_refreshed_at` · **tier** (sudah cocok sesudah migration 033/034) · agency (7.684/7.718) · kategori (dgn catatan F-2) · ER versi roster (dgn catatan 3 sumber) · rate card & filter Max rate (IDR) · Connected · search/sort/paging/facets/otorisasi org (sort di-whitelist, aman injection) · Compare · Ordering/Checkout · Negotiation · AI Assistant · Similar creators.

# B. DATA ADA, BELUM DIOLAH

| Prioritas | Item | Kenapa |
|---|---|---|
| **Tinggi** | Sentimen komentar | `latestComments` ada di `raw_payload` post IG; kolom `sentiment_breakdown` sudah ada & blocked. **Nol biaya Apify tambahan** |
| **Tinggi** | Badge verified Instagram | `verified` ada di payload actor, tak diangkat jadi kolom. Harmonisasi IG bahkan tak punya kolom `is_verified` (TikTok punya sejak L0) |
| | Agregat per akun | avg views, median views, avg likes/comments, posting freq, paid ratio — bahan lengkap di `post_metric`/`kol_metric_*`, hilang 1 langkah agregasi |
| | Topik & kategori konten | caption + hashtag ada di L1; kolom `content_category` blocked |
| | Riwayat kolaborasi brand | `taggedUsers` + `mentions` + `is_sponsored` ada di payload post → `compN` / competitor saturation |
| | Kualitas & keaslian audiens | `unified_follower` berisi daftar follower lengkap (bio, verified, private, following) → skor keaslian nyata menggantikan `auth` mock; **overlap antar-KOL juga bisa dihitung eksak** |

# C. SUDAH DIOLAH, BELUM ADA ENDPOINT

9 kelompok, semuanya sudah benar & rekonsiliasi — tinggal di-expose:

`kol_metric_daily` (280) · `kol_metric_monthly` (68) · `post_metric` (477: likes, comments, views, ER, rank, hashtag, sponsored, permalink) · `content_format_daily` (300, dijamin rekonsiliasi dgn daily) · `audience_demographics_daily` (69) · `audience_geo_daily` (181) · `audience_interest_daily` (214) · `best_posting_time_heatmap` · `format_performance` · total likes/comments/views/shares/saves per akun di layer feature · `display_name` (ada di detail, hilang di list) · `kol_profile_card.profile_snapshot_date`.

# D. FILTER GAP

- **18 dari 28 filter sidebar tanpa param endpoint.**
- Growth Classification & Rising Creator — data ada, ambang tak cocok skala data.
- Last Updated — kolom ada, filter tidak. **Paling murah.**
- Gender-skewed / audience location / interest / quality — tabel L2 terisi, tak ada join dari roster.
- Content Format — data ada, nilainya kata mentah, mapping belum ditetapkan.
- Save Rate / Share Rate / Views threshold — kolom ada, kosong untuk seluruh Instagram.
- Search — app hanya `username`; logic berjenjang di `db.py` (username→display_name→bio + ranking relevansi) belum diport.
- Kategori — app pakai `name`, `db.py` pakai `taxonomy_key`. Dua perilaku untuk filter yang sama.
- Worked with my brand / repeat — data workspace ada, filter belum.

# E. SOURCE / SCRAPING GAP

| Butuh Insights API | Butuh akumulasi waktu | Butuh data operasional | Kolom/tabel belum pernah diisi |
|---|---|---|---|
| reach & est. reach · impressions · shares/saves IG · watch time & completion · Story · demografi umur · demografi terukur (jalur A) | trend `tr[]` · performance consistency & stability · viral frequency · momentum · growth acceleration & stability — *semua terblokir hal yang sama: baru ~5 KOL punya ≥4 titik bulanan* | riwayat kampanye & `camps` · success rate & ROAS · CPE (biaya kampanye) · EMV (reach + benchmark CPM) | domisili kreator (`creator_city` 0%) · niche/sub-kategori · jadwal & prioritas monitoring per KOL · saved list/collection · platform YouTube (tak ada baris di `platforms`) |

# F. AMBIGU / PERLU KLARIFIKASI

| # | Pertanyaan |
|---|---|
| **F-1** | **Arti ikon "verified".** Prototype gambar centang biru platform + toggle "Verified creators only". Backend memberi *Connected* (OAuth) = **0 KOL**. Badge platform ada di `verified_status` (454) tapi sudah dibuang dari Discovery lewat keputusan 7 Sep. Prototype minta yang mana? Kalau badge platform, keputusan itu perlu dibatalkan + badge IG diangkat dari raw payload |
| **F-2** | **Taksonomi kategori.** Prototype kenal 5 (Fitness, Lifestyle, Beauty, Food, Tech). DB punya 9 `taxonomy_key` + 28 nama mentah. Fashion, Entertainment, Moms, Gen Z tak punya tempat di UI — dipetakan ke mana? |
| **F-3** | **Jumlah baris `unified_rate_card`.** `docs/KOL_DISCOVERY_AUDIT.md` (3 Sep) = **0 baris**; `kolMeasured.ts` (1 Sep) = **9.210 / 7.230 KOL**. Filter Max rate + seluruh checkout bergantung padanya. **Satu query menyelesaikannya** |
| **F-4** | **Arti `interests`.** Prototype pakai field yang sama untuk minat *audiens* (filter) dan topik *kreator* (kartu). `audience_interest_daily` hanya menjawab yang pertama, itu pun inferensi |
| **F-5** | **Rumus skor komposit.** Quality score, brand affinity, audience quality, brand fit, opportunity score, match % — 6 skor menonjol di UI tanpa definisi komponen. `k.aff` saja menopang 6 metrik turunan |
| **F-6** | **Mapping format konten.** `clips`/`carousel_container`/`feed`/`VIDEO`/`CAROUSEL`/`unknown` → Reels/Feed/Story/Carousel/Content/Video/Photo. Pipeline sengaja tak menormalkannya (keputusan produk). Story tanpa sumber sama sekali |
| **F-7** | **Content style / persona.** 10 nilai yang di prototype ditulis tangan per kreator — diturunkan otomatis atau di-tag manual? |
| **F-8** | **Korpus Discovery Content & Audience Insights.** Prototype menampilkan konten para KOL; endpoint mengembalikan konten brand sendiri + kompetitor. Dua maksud, satu nama halaman |
| **F-9** | **Mata uang.** Prototype seluruhnya USD (`$0,42 CPE`, `$184K EMV`, rate `$3.200`); DB & checkout seluruhnya IDR. Spesifikasi visual atau spesifikasi nilai? |

---

# Ringkasan aksi

| Butuh coding saja | Butuh pipeline | Butuh scraping / source baru | Butuh endpoint / filter query saja |
|---|---|---|---|
| port search berjenjang `db.py`→`kolDirectory.ts` · `display_name` di list · filter `?refreshedAfter=` · endpoint metrik L2 per kreator · tabel+CRUD saved list · filter "pernah kerja dgn brand saya" · samakan kategori ke `taxonomy_key` | asset sentimen dari `raw_payload.latestComments` · angkat `verified` IG L0→L1→L2 · agregat per akun (avg/median views, likes, posting freq, paid ratio) · klasifikasi topik dari caption+hashtag · skor keaslian dari `unified_follower` · riwayat kolaborasi dari `taggedUsers`/`mentions` · asset `feature.brand_fit_analysis` · **scheduler berulang** | Insights API IG & TikTok (reach, impressions, shares/saves IG, watch time, demografi umur) · scraping Story · platform YouTube · kota kreator · data operasional kampanye · tabel benchmark CPM | seluruh kelompok **C** (9 kelompok L2) · join roster→`audience_*_daily` untuk 4 filter audiens · filter sponsored ratio & format (sesudah mapping) · filter Last Updated |

# Urutan prioritas

Diurutkan menurut berapa banyak elemen UI yang ikut terbuka dan apakah memblokir pekerjaan lain — **bukan** menurut kemudahan.

| # | Pekerjaan | Kenapa di posisi ini |
|---|---|---|
| **1** | **Selesaikan F-1…F-9** | Tak ada kode yang aman ditulis sebelum arti "verified", taksonomi, mapping format, dan mata uang disepakati. 4 dari 9 mengubah bentuk API, bukan cuma tampilan. Biaya: satu sesi |
| **2** | **Nyalakan scheduler berulang untuk roster** | Prasyarat tunggal terbesar. Trend 6 bulan, momentum, growth classification, rising creator, consistency, viral frequency, dan seluruh grup Data Freshness menunggu akumulasi snapshot. Selama `scheduler_engine.py` one-shot, semuanya tak akan pernah punya data. **Pekerjaan operasional, bukan kode besar.** Membuka 6 filter + 5 kolom + Database Health |
| **3** | **Expose kelompok C** | 9 kelompok sudah dihitung, sudah rekonsiliasi, tak dipakai siapa pun. Nilai per unit usaha tertinggi: tanpa pipeline baru, source baru, atau keputusan produk. Membuka tab Performance, Content, sebagian besar Audience |
| **4** | **Perbaiki penyebut growth, lalu kalibrasi ambang** | Normalisasi ke per-30-hari pakai jarak tanggal nyata, atau ubah label UI. **Paling berbahaya kalau dilewati: filternya *terlihat* jalan sambil selalu salah** |
| **5** | **Tutup filter murah di endpoint** | Last Updated, sponsored ratio, join `audience_*_daily`, search berjenjang, display name. Semua query, tanpa dependensi pipeline. Menaikkan filter ter-expose **10 → ~18 dari 28** |
| **6** | **Agregat per akun di L2** | Avg/median views, avg likes/comments, posting freq, paid ratio. Bahan lengkap, hilang 1 langkah. Menghapus 5 field dari yang sekarang di-*sample* app |
| **7** | **Asset sentimen & topik konten** | Komentar & caption sudah di `raw_payload`; 2 kolom blocked sudah bernama benar. **Nol panggilan actor tambahan = nol biaya Apify.** Membuka Content Category/Topic + reputation risk |
| **8** | **Skor keaslian & kualitas audiens dari `unified_follower`** | Menggantikan `auth` dan `q` yang mock — keduanya input untuk Audience Quality, Brand Fit, Opportunity Score. Overlap antar-KOL juga jadi eksak. **Satu pekerjaan, 4 skor komposit berhenti jadi tebakan** |
| **9** | **Ajukan akses Insights API** | Reach, impressions, shares/saves IG, demografi umur tak akan datang dari scraping publik. Lead time panjang — **mulai lebih awal, bukan dikerjakan lebih awal** |
| **10** | **Saved list / collection / shortlist** | Kecil, mandiri, tak memblokir apa pun. 1 tabel, 4 endpoint |

---

*Audit read-only. Tidak ada perubahan pada kode, database, schema, migration, pipeline, endpoint, atau UI. Tidak ada commit. Schema & logic dibaca langsung dari repo; angka baris & coverage dikutip dari pengukuran bertanggal di dalam sumber tersebut — verifikasi ulang sebelum dipakai untuk keputusan sizing.*
