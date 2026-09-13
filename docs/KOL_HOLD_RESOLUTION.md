# RESOLUSI HOLD — EMV/CPE/CPV · Style & Personality · What Matters Most

**Lanjutan** `KOL_DESIGN_EMV_STYLE_WHATMATTERS.md`.
**Tanggal:** 13 September 2026 · DB `kol` @ `10.100.14.216` · `transaction_read_only = on`.
**Sifat:** read-only + desain. Nol `INSERT/UPDATE/DELETE`, nol `CREATE/ALTER/DROP`, nol migration.

---

## 0. DUA KOREKSI ATAS DOKUMEN SEBELUMNYA

Keduanya material, jadi gue taruh di depan.

### 0.1 Frontend TERNYATA ADA di repo ini

Di dokumen sebelumnya gue menulis *"kode frontend tidak ada di repo ini"* dan
menyimpulkan fungsi 7 item tidak bisa dipastikan. **Itu salah.** Ada direktori
`app/` yang gue lewatkan:

| File | Ukuran | Isi |
|---|---:|---|
| `app/AUTOME_2.html` | 883 KB | Prototype Discovery + Smart Discovery, lengkap dengan `IQ_GROUPS`, `dirBadges()`, `intel()`/`intel2()`, registry filter |
| `app/Autometric-KOL-Module.html` | 689 KB | Prototype lebih lama, termasuk tabel campaign tracking |

Keduanya prototype statis: **tidak ada `fetch()`, tidak ada `/api/`**, hanya 2
pemakaian `localStorage`, dan seluruh data creator berupa literal hardcoded.
Jadi ia bukan aplikasi yang tersambung backend — tapi ia **spesifikasi UI yang
bisa dibaca**, dan itu yang membuat Bagian 4 sekarang bisa dijawab.

### 0.2 Angka handle lintas-platform: 216, bukan 439

Di dokumen sebelumnya gue menulis 439. Itu hasil `7.432 − 6.993`, dan keliru
karena 223 baris ber-`username_normalized` NULL ikut mengempis jadi satu grup.
Hitungan yang benar:

| | Jumlah |
|---|---:|
| Handle hanya di 1 platform | 6.777 |
| **Handle di 2 platform** | **216** |
| Baris kelebihan akibat itu | **216** |
| Maks baris per handle | 2 |
| Baris ber-handle kosong/NULL | 223 |

Jadi dampak duplikasi lintas-platform **2,9% roster**, bukan 5,9%. Kesimpulan
desainnya tidak berubah, tapi angkanya harus benar.

---

# 1. EMV

## 1.1 Semua bukti yang ditemukan, dipisah: TERTULIS vs KANDIDAT

### Yang benar-benar TERTULIS sebagai formula

Hanya **satu**, dan sumbernya konsisten di tiga tempat:

| # | Sumber | Kutipan persis | Jenis |
|---:|---|---|---|
| **T1** | `migrations/FEATURE_METRICS_BACKLOG.md:249` | `Formula \| reach × CPM ÷ 1000 × multiplier` · Sumber: `avg_reach` + konstanta CPM · Status: **BLOCKED + NEED CONFIRMATION** · "Perlu migration ❌ kolom sudah ada" | **FORMULA TERTULIS** |
| T1b | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md:336` | `emv \| numeric \| reach × CPM ÷ 1000 × multiplier — konstanta CPM tidak ada di DB \| UI k.emv` | kutipan T1 |
| T1c | `docs/AUTOMETRIC_METRICS_DATA_DICTIONARY.md:862` | idem, + "pencarian `%cpm%`, `%benchmark%`, `%multiplier%`, `%coefficient%`, `%formula%` di 7 schema: 0 hasil" | kutipan T1 |

### Yang hanya KANDIDAT (tersirat, bukan dinyatakan)

| # | Kandidat | Dari mana | Kenapa hanya kandidat |
|---:|---|---|---|
| **K1** | `EMV = engagement × CAL_VALUE_PER_ENG (9.000 IDR)` | `KOL_Database.AS` Estimated ROI = `Estimated Reach × ER% ÷ 100 × 9.000 ÷ Rate`. Bagian `... × 9.000` adalah "earned value" | Excel **tidak pernah menamainya EMV.** Gue yang mengenali bentuknya. Dan 9.000 IDR tidak punya sumber |
| **K2** | `EMV = f(reach)` tanpa CPM | `Discovery_Filters` r42 & `CMP_Hard_vs_Soft_Filter` r54: Estimated ROI = "EMV ÷ rate" | Memakai EMV sebagai input **tanpa mendefinisikannya**. Ini melingkar: ROI butuh EMV, EMV tidak pernah dijelaskan |

### Bukti dari KODE — dan ini yang paling menentukan

| # | Sumber | Temuan |
|---:|---|---|
| **C1** | `orchestration/kol_orchestration/assets/audience.py:65, 476, 580, 855` | Pipeline **sengaja tidak menulis** `avg_reach`, `cpe`, `emv`: *"butuh reach/biaya kampanye, di luar jalur ini. Semuanya dibiarkan NULL, mengikuti pola kolom blocked"*. Ada `-- SENGAJA tidak disebut (tetap NULL)` di dalam `INSERT` |
| **C2** | `tests/test_calculated_metrics.py:372` | **Test guard aktif**: `terlarang = ("brand_fit", "brand_fit_score", "partnership_score", "emv", "cpe", "cpv", "estimated_media_value")` — gagal kalau nama itu muncul sebagai kolom di `l2_gold.kol_profile_card` |
| **C3** | `tests/test_calculated_metrics.py:385` | `test_db_emv_cpe_tetap_null_selama_rate_card_kosong` — assert `count(cpe)+count(emv) == 0` di kedua `feature.*_audience_analysis` selama `unified_rate_card` kosong |
| **C4** | `app/AUTOME_2.html:609–616` | EMV di prototype = **literal hardcoded** (`emv:'$184K'`, `'$132K'`, …). **Nol formula client-side** |
| **C5** | `app/AUTOME_2.html:862, 704` | EMV dipakai sebagai **opsi sort** (`['emv','EMV']`) dan **kolom tabel** (`dirCols.emv=true`) |
| **C6** | `app/Autometric-KOL-Module.html:1796–1809` | Tabel campaign tracking: `alloc`, `pay`, `sched`, `appr`, `stage`, `reach`, `impr`, `eng`, **`emv`**, `roas`, `score` — seluruh nilai `emv` = `'—'`. Pemetaan 1:1 ke `campaign_kols` |

**C2 dan C3 mengubah status rekomendasi gue dari "saran" jadi "aturan yang sudah
ditegakkan":** repo ini sudah punya test yang **gagal** kalau ada yang menambah
kolom `emv`/`cpe`/`cpv` ke kartu L2. Jadi "jangan bikin kolom baru" bukan
pendapat gue — itu kontrak yang sudah hidup di test suite.

**C4 menutup satu pertanyaan:** UI **tidak** menghitung EMV. Ia menampilkan
apa pun yang backend kirim. Jadi definisi EMV **wajib** datang dari backend, dan
satu-satunya yang tertulis adalah T1.

## 1.2 Data yang masih kurang

| # | Kurang | Bukti ketiadaannya |
|---:|---|---|
| 1 | **Konstanta CPM** | Sapuan `information_schema.columns` 101 tabel untuk `(emv\|cpm\|cpv\|cpe\|multiplier\|benchmark\|coefficient\|earned)` → **cpm: 0 kolom**. Backlog:255 juga mencatat 0 hasil |
| 2 | **Nilai `multiplier`** | Tidak ada kolom, tidak ada nilai di Excel maupun dokumen mana pun |
| 3 | **`reach` aktual** | `l1_silver.unified_post.reach` = **0 terisi dari 503**. `feature.*_audience_analysis.avg_reach` = **0 dari 27**. Butuh Insights API |
| 4 | **Granularitas CPM** | Backlog:257 eksplisit: *"CPM per platform, per tier, atau global"* — belum diputuskan |
| 5 | **Mata uang** | Prototype pakai **$** (`emv:'$184K'`, `cpe:'$0.42'`). Excel pakai **IDR** (`CAL_VALUE_PER_ENG` 9.000, slider rate "500rb–1M"). `campaign_kols.currency` dan `campaign_orders.currency` ada, tapi 0 baris |
| 6 | Aturan agregasi `snapshot_date` → `campaign_kols` | `campaign_content_performance` punya `snapshot_date` + `delta_*` + `is_final`; tanpa aturan, `SUM` akan double-count |

## 1.3 Kesimpulan EMV

**Gue tidak memilih formula.** Yang bisa gue nyatakan:

- Ada **satu formula tertulis** (T1: `reach × CPM ÷ 1000 × multiplier`), dan ia
  bersumber dari backlog repo ini — bukan dari Excel. Statusnya sendiri
  **BLOCKED + NEED CONFIRMATION** sejak ditulis.
- Ada **dua kandidat tersirat** (K1, K2) yang **tidak pernah dinamai EMV** oleh
  penulisnya. Memakai salah satunya berarti gue mengarang penamaan.
- Dari 3 input T1, **nol** tersedia: `reach` 0 terisi, CPM tidak ada, multiplier
  tidak ada.
- **Kolomnya sudah ada di 4 tempat** dan ada test yang melarang menambah lagi.

**Status: HOLD — NEED PRODUCT DECISION.** Yang harus dijawab, berurutan:
(1) T1 dipakai atau tidak; (2) kalau ya — CPM berapa dan per apa (platform/tier/global);
(3) multiplier berapa; (4) mata uang $ atau IDR; (5) aturan agregasi snapshot.

---

# 2. CPE dan CPV

## 2.1 Definisi yang tersedia — dan ternyata ada TIGA sumber, bukan dua

| Sumber | CPE | CPV |
|---|---|---|
| **Excel** `KOL_Database.AP` / `.AO` | `Rate Card ÷ (Average Views × ER% ÷ 100)` | `Rate Card ÷ Average Views` — **per 1 view** |
| **Backlog** `FEATURE_METRICS_BACKLOG.md:266` | `fee ÷ total_engagement` · penyebut "total engagement per post" | **tidak disebut sama sekali** |
| **Frontend** `app/AUTOME_2.html:2781–2784` | `cpe = iqNum(k.cpe)` — **dibaca apa adanya dari field backend** | `cpv = rate / views × 1000` — **per 1.000 views** |

### Dua konflik baru yang belum pernah tercatat

**Konflik CPV — beda faktor 1.000.**
Excel: `Rate ÷ Avg Views` (biaya per satu view).
UI: `rate / views * 1000` dengan label **`'CPV / 1K views ≤ ($)'`** (biaya per
seribu view). Angka yang sama akan berbeda 1.000×. **NEED PRODUCT DECISION.**

**Konflik CPM — beda penyebut.**
Excel `KOL_Database.AQ`: `Rate Card ÷ Followers × 1000`.
UI: `cpm = rate / reach * 1000` — **berbasis reach, bukan followers**.
Dua metrik berbeda dengan nama sama. **NEED PRODUCT DECISION.**

**CPE tidak konflik** — dan itu kabar baik. UI **tidak** mendefinisikan CPE, ia
cuma membacanya (`iqNum(k.cpe)`). Jadi definisi backend yang berlaku, dan
satu-satunya yang tertulis adalah backlog: `fee ÷ total_engagement`.

### Yang juga baru: CPV dan CPM MEMANG requirement UI

Di dokumen sebelumnya gue menyimpulkan CPV mungkin bukan kebutuhan UI karena
tidak ada `k.cpv`. Registry slider prototype membuktikan sebaliknya
(`app/AUTOME_2.html:2842`):

```
rateMax : 'Est. Rate ≤ ($)'          → k.rate
cpmMax  : 'CPM ≤ ($)'                → intel2(k).cpm
cpvMax  : 'CPV / 1K views ≤ ($)'     → intel2(k).cpv
cpeMax  : 'CPE ≤ ($)'                → intel2(k).cpe
commEff : 'Commercial Efficiency'    → intel2(k).commEff
```

Dan di `IQ_GROUPS` grup `eff` (`:2446`) ada opsi
`['cpe','Low Cost per Engagement']` dan `['cpv','Low Cost per View']`.
Jadi ketiganya — CPE, CPV, CPM — adalah filter UI yang nyata.

## 2.2 Perbandingan kandidat cost, per grain

Semua kolom di bawah **terverifikasi ada** lewat `information_schema`; seluruh
tabelnya **0 baris**, jadi tidak ada nilai yang bisa gue bandingkan secara data.

| Kandidat cost | Tabel.kolom | Tipe | Grain kolom itu | Artinya | Cocok jadi cost untuk |
|---|---|---|---|---|---|
| **A** | `campaign_kols.deal_price` (+ `currency`) | numeric | **campaign × KOL** | harga nego bersih ke kreator | **CPE & CPV per campaign × KOL** |
| **B** | `campaign_kol_deliverables.unit_price` | numeric | **deliverable** | harga satu unit deliverable | CPV/CPE per konten |
| **C** | `campaign_kol_deliverables.subtotal` | numeric | **deliverable** | `unit_price × quantity` (nama & tetangga `quantity` menyiratkan itu — **tidak bisa gue buktikan, 0 baris**) | CPE/CPV per deliverable |
| **D** | `campaign_orders.subtotal` | numeric | **order** | total sebelum fee & pajak | CPE/CPV level order |
| **E** | `campaign_orders.total_amount` | numeric | **order** | `subtotal + platform_fee_amount + tax_amount − discount_amount` | CPE/CPV "biaya sebenarnya bagi brand" |
| **F** | `campaign_kol_deliverables.rate_card_snapshot` | jsonb | deliverable | rate card yang dibekukan saat order | versi Discovery, **tanpa menunggu `unified_rate_card`** |
| **G** | `l1_silver.unified_rate_card.fee` | numeric | **KOL × post_type** | harga rate card | versi Discovery — **0 baris** |
| **H** | `l2_gold.kol_profile_card.rate_card_min_fee` / `_max_fee` | numeric | KOL | ringkasan rate card | versi Discovery — **0 dari 1.978** |
| **I** | `campaign_kol_payments.allocation` | numeric | payment | alokasi pembayaran | akuntansi, bukan CPE |

### Cost per grain — rekomendasi teknis

| Grain | Cost yang gue rekomendasikan | Alasan teknis |
|---|---|---|
| **campaign × KOL** | **A · `campaign_kols.deal_price`** | Satu-satunya kandidat yang **bergrain persis sama** dengan tempat hasilnya dibaca (`total_engagement`, `emv`, `roas` ada di baris yang sama). Nol join, nol risiko salah alokasi |
| **deliverable / konten** | **C · `deliverables.subtotal`** | Sudah teragregasi dari `unit_price × quantity`; grain-nya sama dengan `campaign_content_performance.campaign_kol_deliverable_id` |
| **order** | **E · `campaign_orders.total_amount`** | Satu-satunya yang memuat fee + pajak |
| **Discovery (pra-campaign)** | **G · `unified_rate_card.fee`**, sementara pakai **F · `rate_card_snapshot`** | G adalah yang disebut backlog. F memungkinkan jalan lebih dulu |

**Ini rekomendasi TEKNIS soal grain, bukan keputusan bisnis.** Yang **bukan**
wewenang gue: apakah CPE yang dilaporkan ke brand memakai **A** (bersih ke
kreator) atau **E** (termasuk fee + pajak). Selisihnya adalah `platform_fee_pct`
+ `tax_pct`, dan itu angka komersial. **NEED PRODUCT DECISION.**

## 2.3 Formula yang bisa dipastikan vs yang tidak

| Metrik | Grain | Formula | Status |
|---|---|---|---|
| CPE | campaign × KOL | `campaign_kols.deal_price ÷ campaign_kols.total_engagement` | **BISA DIPASTIKAN** — tidak ada definisi lain yang bertabrakan, UI cuma membaca |
| CPE | Discovery / per KOL | `unified_rate_card.fee ÷ total_engagement` (backlog) **vs** `Rate ÷ (AvgViews × ER÷100)` (Excel) | **NEED PRODUCT DECISION** — Excel memakai engagement **estimasi**, backlog memakai **terukur** |
| CPV | campaign × KOL | `cost ÷ SUM(campaign_content_performance.views)` — **wajib agregasi**, `campaign_kols` tidak punya `views` | **NEED PRODUCT DECISION** — per 1 view (Excel) atau per 1K view (UI)? |
| CPV | Discovery | `Rate ÷ Average Views` (Excel) **vs** `rate ÷ views × 1000` (UI) | **NEED PRODUCT DECISION** — beda 1.000× |
| CPM | keduanya | `Rate ÷ Followers × 1000` (Excel) **vs** `rate ÷ reach × 1000` (UI) | **NEED PRODUCT DECISION** — penyebut beda; dan `reach` 0 terisi |

Satu hal tambahan yang harus diputuskan sebelum CPE mana pun dihitung:
**definisi `total_engagement`.** `taksonomi_kol` memakai `likes+comments+shares`;
`kol_directory.engagement_rate` dihitung `AVG(likes+comments)` **tanpa shares**.
`campaign_kols.total_engagement` 0 baris jadi tidak bisa diperiksa. Ini H4 lama
yang sekarang juga menentukan penyebut CPE.

## 2.4 Kesimpulan CPE/CPV

**Nol tabel baru. Nol kolom baru.** Diperkuat oleh C2: ada test yang gagal kalau
kolom `cpe`/`cpv` muncul di kartu L2.

- **CPE campaign** adalah satu-satunya dari tiga yang **formula-nya bisa
  dipastikan** — dua kolom, satu baris, tanpa join, tanpa konflik definisi.
- **CPV** punya **dua definisi yang berbeda 1.000×** antara Excel dan UI →
  tidak boleh gue pilih.
- **CPM** punya **dua penyebut berbeda** (followers vs reach) → tidak boleh gue
  pilih, dan versi UI-nya butuh `reach` yang 0 terisi.

---

# 3. STYLE & PERSONALITY — kunci mapping

Requirement tetap: data kurasi manual · 1 KOL banyak Style · 1 KOL banyak
Personality · nilai dari Excel · Brand Personality & Brand Tone **bukan** atribut
KOL.

## 3.1 Semua kandidat canonical identity di DB — hasil penelusuran

| Kandidat | Baris | Grain sebenarnya | Dipakai siapa | PK/FK |
|---|---:|---|---|---|
| **`public.kol_directory`** | **7.432** | **(platform, akun)** | layer serving. Memegang `category_ids uuid[]`, `followers_count`, `engagement_rate`, `bio`, `creator_city` | PK `id uuid` |
| `public.social_account` | 7.208 | akun platform (+ OAuth: `oauth_token`, `connected`, `data_source`) | **seluruh layer L1/L2/feature** | PK `id uuid` |
| `public.kol_social_account` | 7.208 | jembatan | penghubung dua di atas | PK `id`; FK `kol_id → kol_directory(id)`, `social_account_id → social_account(id)`, `platform_id → platforms(id)` |
| `public.agency_kol_accounts` | 7.431 | (agency, akun) | layer kurasi. Memegang `category_id`, `tier_id`, `label`, `campaign_tag`, `notes` | FK `kol_account_id → kol_directory(id)` |
| `public.user` | **1** | user aplikasi (`email`, `password_hash`, `google_id`, `role`, `agency_id`) | auth | — |
| `public.agencies` | **1** | agency | — | — |

### Temuan pokok: **tidak ada entity "orang" di DB**

`kol_social_account` **terlihat** seperti jembatan "satu orang → banyak akun" —
nama kolomnya `kol_id`, seolah menunjuk tabel `kol`. Tapi FK-nya:

```
kol_social_account_kol_id_fkey  FOREIGN KEY (kol_id) REFERENCES kol_directory(id)
```

`kol_id` menunjuk **`kol_directory`**, yang bergrain (platform, akun). Dan
kardinalitasnya **1:1:1**:

| | Jumlah |
|---|---:|
| Baris `kol_social_account` | 7.208 |
| `kol_id` distinct | **7.208** |
| `social_account_id` distinct | **7.208** |
| KOL dengan >1 akun | **0** — distribusi: 7.208 kol_id × 1 akun |

Jadi tabel ini **bukan** jembatan person→accounts; ia link 1:1 antara
`kol_directory` dan `social_account`. **Tidak ada satu tabel pun di 101 tabel
yang menyatakan "dua akun ini orang yang sama".**

### Bukti konkret duplikasi lintas-platform

```
handle        platform    kol_directory_id                      followers
a.ci.pa       instagram   44be0d9f-41f0-4472-a6aa-7419cd51081f    375.972
a.ci.pa       tiktok      80252a56-7ece-4aff-bdc2-84966988276f  1.200.000
adeliaazzahra97 instagram cea2f3b7-18a4-4b0a-a07d-96ed574ccff6     71.416
adeliaazzahra97 tiktok    6534cadc-61b5-43ac-ab1b-f1e712caece7    668.700
```

Dua UUID berbeda, handle sama. **216 handle** seperti ini (2,9% roster).

⚠️ Dan perhatikan: **handle sama ≠ terbukti orang yang sama.** DB tidak
menyatakan apa pun soal itu. Jadi "gabungkan berdasarkan handle" adalah heuristik,
bukan fakta — dan tidak boleh dipakai sebagai dasar penggabungan otomatis.

### Celah antar-tabel yang penting untuk keputusan ini

| Ukuran | Jumlah |
|---|---:|
| `kol_directory` tanpa baris di `kol_social_account` | **224** → tidak bisa dijangkau metrik L1/L2 sama sekali |
| `kol_directory` tanpa baris di `agency_kol_accounts` | **1** |
| `kol_profile_card` tanpa jembatan ke `kol_directory` | **0** → setiap kartu L2 bisa dijangkau dari directory |

## 3.2 Risiko kalau mapping langsung ke `kol_directory`

| # | Risiko | Besarnya | Bisa dimitigasi? |
|---:|---|---|---|
| 1 | **Kurasi ganda** untuk kreator lintas-platform | **216 handle** harus dilabeli 2× | Ya, di UI: saat menyimpan label, tawarkan "terapkan juga ke akun TikTok/IG dengan handle sama". **Jangan** otomatis — handle sama belum tentu orang sama |
| 2 | **Label bisa berbeda antar platform tanpa terdeteksi** | 216 handle | Bisa dijadikan laporan QA ("handle sama, style beda"), bukan constraint |
| 3 | **223 baris ber-handle NULL/kosong** tidak punya cara dikaitkan ke sibling | 223 | Tidak ada mitigasi; baris itu memang tidak bisa dicocokkan |
| 4 | Kalau nanti ada entity "orang", mapping harus dimigrasi | seluruh baris | Mitigasi murah: **simpan `kol_directory_id` sebagai FK terpisah**, jadi menambah `person_id` nanti tidak merusak yang ada |
| 5 | 224 KOL tanpa jembatan ke L2 tetap bisa dilabeli tapi tidak bisa dikorelasikan dengan metrik | 224 | Diterima — label kurasi tidak butuh metrik |

## 3.3 Perbandingan kunci mapping

| Kunci | Cakupan | Kelebihan | Kekurangan |
|---|---:|---|---|
| **`kol_directory.id`** | **7.432** (terluas) | Preseden langsung: `category_ids uuid[]` — atribut multi-nilai berkurasi — **sudah ada di tabel ini**. Bisa di-join ke L2 untuk 7.208 (97%) dan ke roster untuk 7.431 | Duplikasi 216 handle |
| `agency_kol_accounts.id` | 7.431 | Preseden: `category_id`/`tier_id` (atribut kurasi) ada di sini, dan **`brand_fit_analysis` memakai `agency_kol_account_id`** | Bergrain **per-agency**. Hari ini 1 agency / 1:1, tapi agency ke-2 berarti kurasi diulang dari nol. Tetap kena duplikasi 216 handle (karena FK-nya ke `kol_directory`) |
| `social_account.id` | 7.208 | Kunci yang dipakai seluruh L1/L2/feature | **Kehilangan 224 KOL.** Dan `social_account` berisi OAuth token — tabel identitas teknis, bukan tempat atribut editorial |
| entity "orang" baru | — | Satu-satunya yang menyelesaikan masalah 216 handle | **Tidak ada di DB.** Membuatnya = keputusan arsitektur besar, dan penggabungannya cuma bisa berbasis heuristik handle |

## 3.4 REKOMENDASI: `kol_directory.id`

Alasan, diurutkan:

1. **Preseden paling dekat.** `kol_directory.category_ids uuid[]` adalah atribut
   **multi-nilai, berkurasi, merujuk master** — persis kelas yang sama dengan
   Style/Personality. Ia sudah ada di tabel ini, dan mengikutinya berarti nol
   pola baru.
2. **Cakupan terluas** (7.432) dan **bisa dijangkau dari mana-mana**: ke L2 lewat
   `kol_social_account` (97%), ke roster lewat `agency_kol_accounts` (99,99%).
3. **Bukan per-agency.** Style/personality adalah sifat akun, bukan sifat
   hubungan agency dengan akun. `agency_kol_accounts` akan mengulang kurasi tiap
   agency baru.
4. **Bukan `social_account`** karena tabel itu memegang OAuth token — tempat
   identitas teknis, bukan atribut editorial — dan kehilangan 224 KOL.
5. Masalah 216 handle **tidak bisa dihindari oleh kunci mana pun yang ada**,
   karena tidak ada entity orang. Jadi ia bukan alasan memilih kunci lain —
   ia alasan untuk mitigasi di UI.

**Bentuknya tetap seperti desain sebelumnya** (master `kol_attribute` 30 baris +
junction `kol_attribute_map`), dengan junction ber-FK ke `kol_directory(id)`.
**Gue tidak membuat tabelnya.**

Satu catatan: gue **tidak** merekomendasikan pola `uuid[]` seperti `category_ids`
meski itu preseden terdekat — karena array tidak bisa membawa `assigned_by` /
`assigned_at`, dan ini data kurasi manual di mana jejak itu justru yang penting.
Masternya ikut pola DB; mappingnya tidak.

---

# 4. WHAT MATTERS MOST

## 4.1 Penelusuran ulang — sekarang dengan frontend

Karena `app/` ternyata ada, gue bisa menelusuri sampai lapis UI.

| Lapis | Yang diperiksa | Hasil |
|---|---|---|
| **Frontend** | `app/AUTOME_2.html` (883 KB) + `app/Autometric-KOL-Module.html` (689 KB) | Ketujuh item **tidak ada sebagai satu daftar bernama.** Pencarian `matters` di kedua file → **1 hit**, dan itu copy marketing |
| Frontend — persistence | grep `fetch(` · `/api/` · `XMLHttpRequest` | **0 hit.** Hanya 2 `localStorage`. Prototype statis, data creator hardcoded |
| Excel | 51 sheet | 0 hit untuk 5 dari 7 label (sudah dilaporkan di audit sebelumnya) |
| Katalog UI | `deliv.xlsx` 132 baris fitur + 3 workbook lain | 0 hit |
| DB | 101 tabel, sapuan `criteri\|prefer\|weight\|priorit` | Tidak ada tabel/kolom preference atau criteria |

### Satu-satunya kemunculan "matters" — dan ia menjawab pertanyaan fungsi

`app/AUTOME_2.html:2208`:

> **Smart Discovery** — "Pick **any** creator from the complete database as your
> reference, **tell us what matters**, and we'll rank similar creators for you."

Ini callout di atas panel Smart Discovery. Kalimat *"tell us what matters"*
merujuk ke picker kriteria yang ada persis di bawahnya — dan picker itu adalah
`IQ_GROUPS` (`:2432`).

### `IQ_GROUPS` — struktur kriteria yang sebenarnya dipakai UI

13 grup, masing-masing `{key, label, icon, opts:[[key,label],…]}`, sebagian
dengan `ranges` (slider) dan `sub` (sub-grup):

| key | label | jml opsi |
|---|---|---:|
| `opp` | Opportunity | 7 |
| `roles` | Campaign Fit | 8 |
| `pfit` | Portfolio Fit | 7 |
| `audopp` | Audience Opportunity | 6 + 2 slider |
| `ws` | Market White Space | 5 |
| `pos` | Content Position | 8 + sub + 1 slider |
| `behav` | Performance Behavior | 6 + 3 slider |
| `mom` | Creator Momentum | 6 |
| `dep` | Creator Dependency | 5 |
| `risk` | Campaign Risk | 3 |
| `sat` | Sponsored Saturation | 3 + 1 slider |
| `expo` | Creator Exposure | 3 |
| `arch` | Creator Archetype | 9 |
| `eff` | **Efficiency** | 6 — termasuk `['cpe','Low Cost per Engagement']`, `['cpv','Low Cost per View']`, `['reach','High Reach Efficiency']` |
| `collab` | Collaboration Opportunity | 6 |

Plus `IQ_MODES` (5 mode: Best Match, Find Opportunities, Find Missing Pieces,
Explore New Markets, Unexpected Matches) dan `IQ_PRESETS` (shortcut, mis.
`['gems','🔥','Hidden Gems',{mode:'oppo',sel:{opp:['untapped','underutilized'],sat:['lowsat']}}]`).

Bentuk pilihan: `sel = { <group_key>: [<option_key>, …] }` — **map grup → array
opsi**, disimpan di state klien, **tidak dipersist ke mana pun**.

### Ketujuh item ada di UI — tapi tersebar, bukan sebagai satu grup

| # | Item lo | Di UI ditemukan sebagai | Lokasi |
|---:|---|---|---|
| 1 | Strong Engagement | badge **`'High Engagement'`** bila `t.er >= 5.5` | `dirBadges()` :3179 |
| 2 | High Audience Quality | badge **`'High Audience Quality'`** bila `t.audQ >= 85` | :3188 |
| 3 | Consistent Performance | badge **`'Consistent Performer'`** bila `q.reliability >= 82` · opsi `behav.consistent` · sort `'Most Consistent Performance'` | :3181, :2439, :3225 |
| 4 | Strong Company/Community | badge **`'Strong Community'`** bila `t.community >= 72` · slider `community:'Community Strength'` | :3187, :2846 |
| 5 | High Reach | opsi `eff.reach` = **`'High Reach Efficiency'`** | :2446 |
| 6 | Content Quality | **TIDAK ADA** — 0 hit di kedua prototype | — |
| 7 | Brand Safety | slider `safety:'Brand Safety Score'` · kolom tabel `'Brand Safety'` · badge risk level | :2847, :3371, :3089 |

Jadi 6 dari 7 ada di UI, **dengan nama yang berbeda**, dan **tersebar di tiga
mekanisme berbeda** (badge, opsi kriteria, slider). `Content Quality` tidak ada
sama sekali — bahkan di frontend.

### Formula UI untuk yang relevan — dan tiga di antaranya bertumpu pada mock

`intel2()` (`:2725`), dikutip apa adanya:

```js
audQ      = (k.auth + k.q) / 2                          // keduanya ADA di DB (27 baris)
community = min(100, round(er*9 + k.aff*3))             // k.aff = MOCK
safety    = round((k.auth + posSent) / 2)               // posSent butuh sentiment = 0 baris
riskLevel = safety>=85 ? 'low' : safety>=72 ? 'medium' : 'high'
postCons  = k.cons                                       // k.cons = MOCK (hash dari ID)
cpm       = rate / reach * 1000
cpv       = rate / views * 1000
cpe       = iqNum(k.cpe)                                 // dibaca dari backend
commEff   = clamp(100 - cpv*6 + er*2, 0, 100)
```

Dan `intel2` memakai `hsh(k.id)` — **hash dari creator id** — untuk mensintesis
`idPct`, `jbPct`, `genZPct`, `millPct`, `eduPct`, `revPct`, `tutPct`,
`topicCons`, `formatCons`.

Ini mengonfirmasi dua temuan dokumen internal:
- `docs/FILTER_DB_MAPPING 2.md:82` — *"Performance Stability | dari `k.cons`,
  yaitu **hasil acak dari ID**"*
- `docs/AUTOME_2_READINESS_AUDIT.md:196` (F-5) — *"Quality score, brand affinity,
  audience quality, brand fit, opportunity score, match % — **6 skor menonjol di
  UI tanpa definisi komponen**. `k.aff` saja menopang 6 metrik turunan"*

**Konsekuensi untuk item #4 (Strong Community):** formulanya `er*9 + aff*3`, dan
`k.aff` tidak punya sumber DB. Jadi bukan cuma kolomnya tidak ada di DB —
**definisinya pun bertumpu pada field mock**. Item #3 (Consistent Performance)
sama: `k.cons` adalah hash ID.

## 4.2 Kesimpulan fungsi — dan apa yang masih tidak bisa dipastikan

**Yang bisa gue pastikan dari repo:**

1. Frontend **ada** dan bisa dibaca, tapi **statis** — tanpa `fetch`, tanpa API,
   tanpa persistence. Jadi ia menunjukkan *bentuk* UI, bukan kontrak backend.
2. Frasa "what matters" di UI merujuk **picker kriteria Smart Discovery**
   (`IQ_GROUPS`) — dan itu **preference/filter**, bukan skor per KOL.
3. Pilihannya berbentuk `{group: [options]}`, **tidak dipersist**.
4. Ketujuh item **bukan** `IQ_GROUPS`. Enam di antaranya ada di UI dengan nama
   berbeda dan tersebar di badge/slider/opsi; satu (`Content Quality`) tidak ada.

**Yang TIDAK bisa gue pastikan:** apakah daftar 7-item lo adalah **redesain**
picker itu (jadi: preference), atau **komponen skor baru** yang belum masuk
prototype. Prototype ini bertanggal 2 September 2026 dan tidak memuat daftar itu.
Keputusannya ada di spec/desain di luar repo — **NEED PRODUCT DECISION.**

## 4.3 DESAIN A — kalau ini preference / filter criteria

**Grain: (siapa yang memilih) × (kriteria).** Bukan per KOL.

| Lapis | Bentuk | Grain | Tabel baru? |
|---|---|---|---|
| Daftar 7 kriteria | **vocabulary di config/kode** — pola `IQ_GROUPS` yang sudah dipakai UI | — | **TIDAK** |
| Pilihan user saat mencari | **parameter query** (`?matters=engagement,audience_quality`) | per-request | **TIDAK** |
| Efek | menggeser bobot / urutan ranking, seperti `audience_priority` menggeser 12 poin di Excel | — | **TIDAK** |

**Tabel yang diperlukan: NOL.** Buktinya: prototype tidak mempersist pilihan
apa pun, dan 30 ranking preset di `Lookup_Lists` juga hidup sebagai vocabulary,
bukan tabel.

**Tabel baru hanya perlu kalau** salah satu ini benar — dan keduanya belum
terbukti:

| Kalau… | Maka perlu | Grain |
|---|---|---|
| Daftar 7 harus bisa diedit tanpa redeploy | `what_matters_criteria` — **7 baris** (`criteria_key`, `label`, `sort_order`, `is_active`, `source_column`) | per kriteria |
| Pilihan harus tersimpan & dipakai ulang per brand/campaign | `brand_evaluation_preference` (`brand_id`, `criteria_key`, `rank`/`weight`) | **brand × kriteria** — diblokir: `public.brand` **0 baris** |

## 4.4 DESAIN B — kalau ini score per KOL

**Grain: KOL × kriteria** (atau 7 kolom pada satu baris KOL).

| Opsi | Bentuk | Grain | Penilaian |
|---|---|---|---|
| **B1 — hitung saat query, jangan simpan** | tiap kriteria menunjuk kolom sumber existing; dinormalisasi di API | per request | ✅ **Rekomendasi.** Mengikuti aturan yang sudah berlaku: `Final Match Score` "Computed, not stored" |
| B2 — 7 kolom di `kol_profile_card` | 7 kolom numeric | KOL | ❌ Tabel ini **di-regenerate asset Dagster**, dan 2 dari 7 permanen NULL |
| B3 — master + mapping skor | `what_matters_criteria` (7) + `kol_what_matters_score` (KOL × kriteria) | **KOL × kriteria** = 7 × 7.432 = **52.024 baris** | ❌ Menyimpan turunan kolom yang sudah ada; 14.864 baris NULL selamanya |

**Kalau B3 tetap dipilih Product**, grain-nya harus:
`(kol_directory_id, criteria_key, score numeric, basis varchar, computed_at)` —
dengan `basis` wajib, mengikuti pola `confidence` / `interest_source` /
`content_topic_source` yang sudah ada di DB, karena 5 dari 7 nilainya akan
berupa proksi.

### Kesiapan sumber untuk kedua desain

| # | Item | Kolom sumber | Terisi | Catatan |
|---:|---|---|---:|---|
| 1 | Strong Engagement | `kol_directory.engagement_rate` | **1.736** | ⚠️ outlier sampai 223,41% (H20) |
| 2 | High Audience Quality | `kol_profile_card.audience_quality_score` + `authenticity_score` | **27** | UI: `(auth+q)/2` — **kedua input ada** |
| 3 | Consistent Performance | `performance_stability` (11) · `post_frequency_reliability` (49) | 11–49 | UI memakai `k.cons` = **hash ID** |
| 4 | Strong Community | — | **0** | UI: `er*9 + aff*3`; `k.aff` **mock** |
| 5 | High Reach | `avg_views` (30) · `view_to_follower_ratio` (22); `reach` **0/503** | 0–30 | `reach ≠ views` |
| 6 | Content Quality | — | **0** | Tidak ada di DB, Excel (bobot 0), **maupun frontend** |
| 7 | Brand Safety | UI butuh `posSent` (sentiment **0 baris**). Proksi 4-input Excel: `authenticity` 27 + `follower_quality` 27 + `verified_status` 931 + `paid_ratio` 48 | 27 | **Definisi UI ≠ definisi Excel** |

**2 siap · 3 proksi · 2 kosong**, dan **3 dari 7 formula UI-nya bertumpu pada
field mock atau sumber 0 baris**.

---

# 5. FINAL DECISION MATRIX

Hanya keputusan yang berdiri di atas bukti yang sudah ditemukan.

| Feature | Existing DB Source | New Table Needed? | New Column Needed? | Business Decision Needed? | Technical Decision Needed? | Recommendation | Confidence |
|---|---|---|---|---|---|---|---|
| **EMV** | `campaign_kols.emv` · `campaign_content_performance.emv` · `feature.ig/tt_audience_analysis.emv` — **4 kolom, semua 0 terisi**. Input: `total_engagement` ✅ ada · `reach` **0/503** · **CPM & multiplier: 0 kolom di 101 tabel** | **TIDAK** | **TIDAK** — dan ada test guard (`test_calculated_metrics.py:372`) yang gagal kalau kolom `emv` ditambah ke kartu L2 | **YA** — pakai T1 (`reach × CPM ÷ 1000 × multiplier`)? CPM berapa & per platform/tier/global? multiplier berapa? mata uang $ atau IDR? | **YA** — aturan agregasi `snapshot_date` → `campaign_kols` supaya tidak double-count | Pakai 4 kolom existing. Hitung per baris di `campaign_content_performance`, lalu agregasi ke `campaign_kols.emv`. **Jangan isi apa pun sebelum T1 dikonfirmasi** | **Tinggi** untuk "tidak perlu struktur baru" · **Nol** untuk formula |
| **CPE** | Campaign: `campaign_kols.deal_price` + `total_engagement` — **keduanya ada, satu baris, tanpa join**. Discovery: `feature.*_audience_analysis.cpe` (0 terisi) + `unified_rate_card.fee` (**0 baris**) atau `deliverables.rate_card_snapshot` | **TIDAK** | **TIDAK** — kolom `cpe` sudah ada; test guard juga melarang tambahan | **YA** — cost pakai `deal_price` (bersih ke kreator) atau `campaign_orders.total_amount` (termasuk fee+pajak)? Dan definisi `total_engagement` (dengan/tanpa `shares`) | **TIDAK** untuk grain campaign — tidak ada definisi yang bertabrakan; UI hanya membaca `k.cpe` | **Campaign: `deal_price ÷ total_engagement`** — satu-satunya dari ketiga metrik biaya yang formulanya bisa dipastikan. Discovery: tunggu rate card | **Tinggi** (campaign) · **Rendah** (discovery) |
| **CPV** | **Tidak ada kolom `cpv`** di 101 tabel. Views: `campaign_content_performance.views` · `avg_views` (30 terisi). `campaign_kols` **tidak punya** `views` → wajib agregasi | **TIDAK** | **TIDAK** — turunan murni, dan test guard melarang nama `cpv` | **YA — konflik 1.000×**: Excel `Rate ÷ Avg Views` (per 1 view) vs UI `rate/views*1000` label `'CPV / 1K views'` (per 1K view) | **YA** — agregasi views per `campaign_kol` (semua snapshot? `is_final`? `delta_*`?) | **Calculated murni, jangan bikin kolom.** Tapi **jangan hitung sebelum satuan diputuskan** — salah satuan = salah 1.000× | **Tinggi** untuk struktur · **Nol** untuk satuan |
| **Style** | **NOL** — `%style%` di 101 tabel = 0 tabel, 0 kolom. Preseden pola: `kol_categories` (master) + `kol_directory.category_ids uuid[]` (multi-nilai berkurasi) | **YA — 1 master + 1 junction** (dibagi dengan Personality) | **TIDAK** | **YA** — style itu sifat **akun** atau **orang**? (216 handle lintas-platform) | **TIDAK** — kunci mapping sudah terjawab bukti: `kol_directory.id` | Master `kol_attribute` **30 baris** (`kind`+`attribute_group`+`attribute_key`, unik bertiga) + junction `kol_attribute_map` ber-FK `kol_directory(id)`, dengan `assigned_by`/`assigned_at` | **Tinggi** |
| **Personality** | **NOL** — `%personality%` = 0 tabel, 0 kolom | **TIDAK** — pakai 2 tabel yang sama | **TIDAK** | **YA** — sama dengan Style · dan **di mana Brand Personality + Brand Tone (18 baris) disimpan**, diblokir `public.brand` 0 baris | **TIDAK** | Sisi KOL: `kind='personality'`, **12 baris** (Creator Personality). **Brand Personality + Brand Tone JANGAN masuk tabel KOL** | **Tinggi** (sisi KOL) · **Nol** (sisi brand) |
| **What Matters Most** | 6 dari 7 ada di UI dengan nama lain (badge/slider/opsi), tersebar di `dirBadges()`, `IQ_GROUPS.eff`, registry slider. `Content Quality` **tidak ada bahkan di frontend**. Sumber: ER 1.736 · AQ 27 · proksi 11–30 · Community & Content Quality **0** | **TIDAK** untuk Desain A. **TIDAK** untuk Desain B1 | **TIDAK** | **YA — paling memblokir**: ini preference (Desain A) atau score per KOL (Desain B)? Prototype menunjukkan "tell us what matters" = picker kriteria = **preference**, tapi daftar 7-item lo bukan `IQ_GROUPS` | **TIDAK** sampai fungsi diputuskan | **Desain A + B1: nol tabel.** Vocabulary di config (pola `IQ_GROUPS`), pilihan sebagai query param, nilai dihitung dari kolom existing. Master 7 baris **hanya kalau** daftarnya harus editable runtime | **Sedang** untuk fungsi (bukti kuat mengarah ke preference) · **Tinggi** untuk "nol tabel" |

### Yang berubah dari dokumen sebelumnya

| Sebelumnya | Sekarang | Penyebab |
|---|---|---|
| "Frontend tidak ada di repo → fungsi 7 item tidak bisa dipastikan" | Frontend **ada** (`app/*.html`); fungsi **terarah kuat ke preference** | Gue melewatkan direktori `app/` |
| "CPV mungkin bukan requirement UI (tidak ada `k.cpv`)" | CPV **memang** requirement UI — slider `cpvMax` + opsi `eff.cpv` | Registry slider `:2842` |
| "Rekomendasi: master `what_matters_criteria` 7 baris" | **Nol tabel** untuk Desain A & B1; master hanya kalau perlu editable runtime | Prototype tidak mempersist pilihan apa pun |
| "439 handle lintas-platform" | **216 handle** | Koreksi hitungan |
| "Konflik CPE Excel-vs-DB (H5)" | **Bukan konflik** untuk grain campaign (UI cuma membaca `k.cpe`); **konflik baru** muncul di CPV (1.000×) dan CPM (penyebut) | `intel2()` `:2781–2784` |
| "Rekomendasi gue: jangan bikin kolom EMV/CPE/CPV" | Sama, **tapi bukan lagi pendapat** — sudah ditegakkan test guard | `test_calculated_metrics.py:372` |

---

# 6. IMPLEMENTATION BLOCKERS

## 6.1 READY setelah approval — nol keputusan tambahan

| # | Pekerjaan | Kenapa siap |
|---:|---|---|
| R1 | **Master `kol_attribute` (30 baris) + junction `kol_attribute_map`**, FK ke `kol_directory(id)` | Nilai dari Excel sudah lengkap & terverifikasi (18 style + 12 creator personality). Kunci mapping sudah terjawab bukti. Dua tabel baru yang tidak direferensikan siapa pun dan tidak disentuh asset Dagster |
| R2 | **Endpoint filter Style/Personality** (`EXISTS` + `attribute_group`) | 7.432 baris, seq scan murah; tidak butuh index |
| R3 | **CPE campaign sebagai query/API**: `deal_price ÷ total_engagement` | Dua kolom, satu baris, tanpa join, tanpa konflik definisi — **satu-satunya metrik biaya yang begini** |
| R4 | **Vocabulary 7 kriteria + pemetaan ke kolom sumber, sebagai config di kode** | Berguna untuk Desain A maupun B1; kalau fungsinya berubah, yang diubah cuma satu file |
| R5 | Guard "input kosong → NULL, bukan 0" di semua metrik biaya | Aturan Excel & backlog yang konsisten; paling mahal kalau salah |
| R6 | Laporan QA "handle sama, label Style/Personality beda" | Mitigasi risiko 216 handle, tanpa constraint DB |

## 6.2 HOLD karena Product/mentor

| # | Keputusan | Memblokir |
|---:|---|---|
| P1 | **Fungsi 7 item: preference atau score per KOL?** | Seluruh Bagian 4. Bukti mengarah ke preference, tapi daftarnya bukan `IQ_GROUPS` |
| P2 | **Formula EMV** — T1 dipakai atau tidak | 4 kolom `emv`; sorting EMV di UI; kolom `emv` di tabel campaign tracking |
| P3 | **Konstanta CPM** + granularitasnya (platform/tier/global) | EMV kandidat T1; CPM sebagai filter UI |
| P4 | **Nilai multiplier** EMV | idem |
| P5 | **Satuan CPV**: per 1 view (Excel) atau per 1K view (UI) | Angka CPV — **salah pilih = salah 1.000×** |
| P6 | **Penyebut CPM**: followers (Excel) atau reach (UI) | Angka CPM; versi UI butuh `reach` yang 0 terisi |
| P7 | **Cost mana** untuk CPE/CPV: `deal_price` vs `campaign_orders.total_amount` | Angka yang dilaporkan ke brand. Selisihnya `platform_fee_pct` + `tax_pct` |
| P8 | **Definisi `total_engagement`** — dengan atau tanpa `shares` | Penyebut CPE; konsistensi dengan `kol_directory.engagement_rate` yang **tanpa** shares |
| P9 | **Mata uang**: UI `$`, Excel IDR | Semua metrik biaya |
| P10 | **Style/personality: sifat akun atau orang?** | Bentuk final junction. Kalau "orang", DB belum punya entity-nya |
| P11 | **Brand Personality + Brand Tone (18 baris) disimpan di mana** | Brand Personality Fit (10% skor) |
| P12 | **`Content Quality` (#6) benar-benar dibutuhkan?** | Tidak ada di DB, Excel (bobot 0), **maupun frontend** |
| P13 | **`Consistent Performance` = `performance_stability` atau cadence?** | Kriteria #3. UI memakai `k.cons` yang hash ID |
| P14 | **`Brand Safety`: definisi UI (`auth+posSent`) atau Excel (4-input integrity screen)?** | Kriteria #7 — dua definisi berbeda |
| P15 | **Daftar 7 harus editable runtime?** | Menentukan apakah master `what_matters_criteria` perlu ada |

## 6.3 HOLD karena data/source belum ada

| # | Blocker | Angka | Memblokir |
|---:|---|---|---|
| D1 | `l1_silver.unified_rate_card` | **0 baris** (juga 0 di L0 — bukan gap ETL) | CPE/CPV/CPM versi Discovery; `feature.*.cpe` |
| D2 | `unified_post.reach` | **0 dari 503** | EMV T1; `avg_reach`; CPM versi UI; High Reach yang jujur |
| D3 | `feature.*_comments_analysis` + `unified_comment` | **0 baris** | `posSent` → Brand Safety versi UI; Sentiment Archetype |
| D4 | `public.brand` | **0 baris** | `brand_fit_analysis` ber-**FK** ke `brand(id)` → nol baris bisa ditulis; tempat Brand Personality/Tone |
| D5 | Seluruh tabel campaign (13 dari 14) | **0 baris** | Semua EMV/CPE/CPV versi campaign — struktur siap, isi belum |
| D6 | `k.aff` (sumber `community`, `purchase`, `topicCons`, …) | **mock, tidak ada kolom DB** | Strong Community (#4) dan 5 metrik turunan lain di UI |
| D7 | `k.cons` | **hash dari creator id** | Consistent Performance (#3) versi UI |
| D8 | `feature.*_audience_analysis` cakupan | **27 dari 7.432** (0,36%) | High Audience Quality (#2), Brand Safety proksi |
| D9 | Umur audiens | 29 baris, **2.567 dari 2.568 `unknown`** | Age Match (25% dari komponen terberat) |

## 6.4 HOLD karena repo frontend/backend tidak tersedia

Jauh lebih kecil daripada dugaan gue sebelumnya — tapi tidak nol:

| # | Yang tidak ada | Akibat |
|---:|---|---|
| F1 | **Backend/API layer** — tidak ada `package.json`, `scripts/`, `.mjs`, `lib/` di repo ini | Kontrak field (`k.emv`, `k.cpe`, `k.aff`, `k.cons`) **dikonsumsi** prototype tapi **diproduksi** di tempat lain. Gue tidak bisa melihat produsen aslinya |
| F2 | `scripts/brand-match/vocabulary.mjs` · `scoring.mjs` · `taxonomy.mjs` · `@/lib/discover/vocab` · `creatorMatch` | Sumber 48 nilai Style/Personality dan implementasi scoring — dirujuk Excel, **tidak ada di sini** |
| F3 | Seri migration aplikasi (`discover_creator_links` = **migrasi 053**; repo ini sampai 044) | Tabel state Discovery ada di DB lain |
| F4 | **Versi UI terbaru** yang memuat daftar 7-item persisnya | `app/AUTOME_2.html` bertanggal 2 Sep 2026 dan memuat `IQ_GROUPS` (13 grup), bukan daftar 7. Jadi daftar itu **lebih baru atau dari spec lain** — dan itulah kenapa P1 tidak bisa gue tutup sendiri |

⚠️ Catatan penting soal `app/*.html`: keduanya **prototype statis** — nol
`fetch()`, nol `/api/`, data creator hardcoded. Jadi ia sah dipakai sebagai
**spesifikasi UI** (label, formula client-side, bentuk pilihan), **tidak** sebagai
bukti kontrak backend.

---

## 7. STATUS SESI

| | |
|---|---|
| Query DB | ~12 `SELECT` tambahan (FK, kardinalitas, struktur), read-only |
| INSERT / UPDATE / DELETE | **0** |
| CREATE / ALTER / DROP | **0** |
| Migration | **0** |
| Perubahan DB | **0** |
| Database disentuh | **`kol` saja** |
| File ditulis | `docs/KOL_HOLD_RESOLUTION.md` (dokumen ini) |
| Formula yang gue tetapkan sendiri | **Nol.** Satu-satunya yang gue nyatakan "bisa dipastikan" adalah CPE campaign — dan itu karena tidak ada definisi lain yang bertabrakan, bukan karena gue memilih |
| Keputusan diserahkan | **15 Product (P1–P15)** · 9 data blocker · 4 repo blocker |

**HOLD yang berhasil ditutup sesi ini:** kunci mapping Style/Personality
(terjawab bukti FK + kardinalitas) · status "perlu kolom baru" untuk EMV/CPE/CPV
(terjawab test guard) · arah fungsi What Matters Most (terjawab prototype,
meski belum final).

**Menunggu review lo. Nol tabel dibuat.**
