# KOL Discovery – Filter Requirements

**Subtask:** 1 — List Kebutuhan Filter
**Sumber tunggal:** `app/AUTOME_2.html` (883 KB, 5.736 baris)
**Tanggal:** 2026-09-02
**Ruang lingkup:** UI saja. Tidak ada pengecekan database, coverage, atau mapping ke tabel.

> ### Status dokumen — direvisi 2026-09-06
>
> Dokumen ini **masih berlaku sebagai audit prototype**, tapi **bukan lagi baseline kebutuhan
> filter.** `AUTOME_2.html` berjalan di **8 KOL mock dengan 0 network call** — ia tidak pernah
> menyentuh database. Baseline yang berlaku sekarang adalah **app produksi** `autometric` @
> `discover/data-terukur-kol`.
>
> Lima temuan di sini sudah tidak akurat, termasuk **§4 yang mencoret 7 field sebagai "legacy"
> padahal ketujuhnya hidup di app**. Lihat **§Revisi 2026-09-06** di akhir dokumen.
>
> Baseline final: `docs/KOL_DISCOVERY_TASK5_DESIGN.md` §2 — **40 filter**, bukan 32.

---

## 1. Tujuan

Dokumen ini berisi daftar kebutuhan filter untuk KOL Discovery, disusun murni dari
UI yang **benar-benar dirender** oleh prototype `AUTOME_2.html`.

Tujuannya menetapkan satu daftar acuan yang disepakati sebelum masuk ke Subtask 2
(mapping ke database). Karena itu dokumen ini **tidak** menyebut tabel, kolom,
jumlah baris, atau ketersediaan data — semua itu urusan subtask berikutnya.

### Halaman yang diaudit

`AUTOME_2.html` adalah bundle dari 40 modul dalam satu shared scope. Halaman yang
menjadi acuan KOL Discovery adalah:

| | |
|---|---|
| Route | `state.section='kol'` → `V.list` |
| Judul di UI | **KOL Directory** — "Creator Intelligence Workspace — discover, evaluate, shortlist, compare, decide." |
| Definisi live | baris **3454**, modul `pages/directory-intel.js` |
| Engine filter | `filterKols2()` baris **3652**, modul `components/directory-filters2.js` |
| Panel filter | `filterPanelHTML()` baris **3632**, sidebar kanan, **6 grup** collapsible |

> **Catatan ruang lingkup.** Ada halaman terpisah `A.discover` ("Discover", baris 2279)
> dengan tab sendiri (`profiling`, `profile`, `db`, `roster`, `tracked`, `smart`).
> Halaman itu **bukan** KOL Directory dan tidak termasuk dalam dokumen ini.

### Kenapa ada dua versi di file yang sama

File ini memuat definisi lama dan baru sekaligus. Karena shared scope, **definisi
yang belakangan menimpa yang duluan**:

| Komponen | Versi lama (tertimpa) | Versi live |
|---|---|---|
| Route directory | `V.list` baris 1064 | **`V.list` baris 3454** |
| Engine filter | `filterKols2()` baris 3258 | **`filterKols2()` baris 3652** |
| UI filter | `filterModalHTML()` baris 1008 — modal | **`filterPanelHTML()` baris 3632 — sidebar** |

Baris 1006 di file itu sendiri menandai versi lama:
`/* advanced filter drawer (legacy — replaced by the persistent panel) */`

### Perubahan dari `AUTOME_1.html`

Satu modul baru: **`components/dir-freshness.js`** (baris 3670–3763). Dampaknya ke filter:

| Perubahan | Dampak |
|---|---|
| Grup panel baru: **Data Freshness & Monitoring** | **+5 filter aktif** (§2.1 No. 23–27) |
| Bar **Database Health** dirender di `V.list` baris 3480 | +4 tombol pintas ke filter Data Status (§2.3) |
| 5 kolom tabel baru di `COLDEFS` | Non-filter — lihat §3 |
| Modal **Data Status** per kreator | Non-filter — lihat §3 |

Grup 1–5 dan seluruh kontrol di luar panel **tidak berubah** dari `AUTOME_1.html`.
Daftar legacy juga tidak berubah.

---

## 2. Filter Aktif

Filter = kontrol yang **mengurangi jumlah hasil**. Semua yang ada di bagian ini
dieksekusi di dalam `filterKols2()` (baris 3652).

### 2.1 Panel Filter — 6 grup

Dirender oleh `filterPanelHTML()` (baris 3632); isi tiap grup dari `fpBody(g)`
(baris 3585); definisi grup di `FPG` (baris 3554).

| No | Group | Filter | Control Type | Options / Values | Keterangan |
|---:|---|---|---|---|---|
| 1 | Creator Profile | Platform | Chips (single-select, klik ulang = reset) | Instagram · TikTok · YouTube | Dari `APPS` (baris 599). Cocok bila platform kreator memuat nilai terpilih |
| 2 | Creator Profile | Kategori KOL | Chips (single-select, toggle) | Fitness · Lifestyle · Beauty · Food · Tech | Hardcoded 5 nilai. Menulis ke `state.cat` — **kontrol kembar** dengan chip kategori di header (No. 28) |
| 3 | Creator Profile | KOL Tier | Chips (single-select, toggle) | Nano · Micro · Mid-tier · Macro · Mega | Tooltip menyebut batas follower: Nano 1K–10K, Micro 10K–50K, Mid-tier 50K–500K, Macro 500K–1M, Mega >1M (Celebrity) |
| 4 | Creator Profile | Gender skew | Chips (toggle, dua chip terpisah) | Female-skewed · Male-skewed | **Threshold:** Female-skewed = female ≥ 60%. Male-skewed = male ≥ 55% (setara female ≤ 45%) |
| 5 | Creator Profile | Verified only | Chip (toggle on/off) | Verified only | Boolean |
| 6 | Creator Profile | Age | Select | All ages · 18-24 · 25-34 · 35-44 | Hanya 3 bucket. Mengacu ke kelompok umur audiens dominan |
| 7 | Creator Profile | Location | Select | All locations + daftar domisili kreator | Opsi digenerate dari data, bukan daftar tetap |
| 8 | Audience | Audience location | Select | All audience locations + daftar lokasi audiens | Opsi digenerate dari data |
| 9 | Audience | Audience interest | Select | All audience interests + daftar minat | Opsi digenerate dari data, **dipotong maksimal 12 item** |
| 10 | Audience | Audience Quality | Chips (multi-select) | High (85+) · Good (75+) · Below 75 | **Threshold:** skor kualitas audiens ≥85 / ≥75 / <75 |
| 11 | Content | Content Category / Topic | Chips (multi-select) | Digenerate dari topik utama tiap kreator | Daftar opsi mengikuti data, bukan daftar tetap |
| 12 | Content | Content Format | Select | All formats · Reels · Carousel · Story · Feed · Video · Photo | **Video** dan **Photo** adalah pengelompokan, bukan format tersendiri: Video → Reels; Photo → Feed + Carousel |
| 13 | Content | Content Style & Creator Personality | Chips (multi-select) | educational · entertaining · inspirational · relatable · storytelling · tutorial · review · aesthetic · minimalist · cinematic | 10 nilai hardcoded |
| 14 | Performance | Engagement Rate | Chips (multi-select) | Good ER (≥3%) · High ER (≥5,5%) | **Threshold:** 3% dan 5,5% |
| 15 | Performance | Save Rate | Chip (toggle) | High Save Rate | **Threshold:** ≥5%. Tooltip: "strong purchase-consideration signal" |
| 16 | Performance | Share Rate | Chip (toggle) | High Share Rate | **Threshold:** ≥1,8% |
| 17 | Performance | Views | Chips (multi-select) | 150K+ avg views · 300K+ avg views | **Threshold:** 150.000 dan 300.000 |
| 18 | Performance | Reliability | Chips (multi-select) | Consistent · Very Consistent | **Threshold:** ≥78 dan ≥88 |
| 19 | Performance | Performance Stability | Chips (multi-select) | Stable · Volatile | Stable = volatilitas <28; Volatile = selain itu |
| 20 | Performance | Viral Frequency | Chip (toggle) | Viral: frequent | **Threshold:** ketergantungan viral ≥55. Nilai `occasional` (≥35) dan `rare` ada di logika tapi **tidak dirender** — lihat §4 |
| 21 | Growth | Growth Classification | Chips (multi-select) | Exploding · Rising · Stable · Declining | **Threshold** (pertumbuhan 30 hari): Exploding ≥8% · Rising ≥4,5% · Stable ≥1% · Declining <1% |
| 22 | Growth | Signals — Rising Creator | Chip (toggle) | 🚀 Rising Creator | **Rule:** growth ≥5,5% DAN engagement ≥4,5% DAN follower <1 juta DAN tren tidak menurun. Tooltip: "Recent growth + momentum, independent of KOL Tier" |
| 23 | Data Freshness & Monitoring | Data Status | Chips (multi-select) | 🟢 Fresh · 🟡 Aging · 🟠 Due for Update · 🔴 Outdated · 🔵 Updating · ⚫ Update Failed | **Rule:** dihitung dari rasio umur data terhadap interval update kreator itu sendiri. Fresh <0,5 · Aging <0,85 · Due <1,2 · Outdated ≥1,2. Updating & Update Failed ditentukan oleh tingkat keyakinan data, bukan rasio |
| 24 | Data Freshness & Monitoring | Last Updated | Chips (multi-select) | Last 24 Hours · Last 3 Days · Last 7 Days · Last 30 Days · Older than 30 Days | **Threshold:** ≤24 jam · ≤72 jam · ≤168 jam · ≤720 jam · >720 jam |
| 25 | Data Freshness & Monitoring | Update Frequency | Chips (multi-select) | Every 6 Hours · Daily · Weekly · Monthly | Interval = 6 / 24 / 168 / 720 jam. **Turunan dari Monitoring Priority (No. 27), bukan field terpisah** |
| 26 | Data Freshness & Monitoring | Next Update | Chips (multi-select) | Today · Within 24 Hours · Within 3 Days · Not Scheduled | **Threshold:** ≤9 jam · ≤24 jam · ≤72 jam. "Not Scheduled" = status Update Failed. Kreator berstatus Updating/Failed dikecualikan dari tiga opsi pertama |
| 27 | Data Freshness & Monitoring | Monitoring Priority | Chips (multi-select) | High Priority · Active Monitoring · Standard · Low Priority | **Rule:** High = sedang dalam campaign/negosiasi ATAU growth exploding ATAU viral frequent. Active = growth rising ATAU sedang di-track ATAU ≥8 campaign. Low = growth declining DAN ≤5 campaign. Sisanya Standard |

**Perilaku panel:** tiap grup punya badge jumlah filter aktif dan tombol reset per
grup. Ada tombol **Clear All** dan **Save**. Filter aktif tampil sebagai chip yang
bisa dihapus satu-satu di bagian atas panel.

### 2.2 Filter di luar panel

Dirender langsung di `V.list` (baris 3454), ikut dieksekusi `filterKols2()`.

| No | Group | Filter | Control Type | Options / Values | Keterangan |
|---:|---|---|---|---|---|
| 28 | Header | Kategori | Chips | All · Fitness · Lifestyle · Beauty · Food · Tech | **Kontrol kembar** dengan No. 2 — keduanya menulis `state.cat` |
| 29 | Header | Keyword search | Search input | Teks bebas | Placeholder: *"Search names, topics, DNA, brands… or describe: 'rising skincare creators with Gen Z audience'"*. Mencari di: nama, handle, kategori, niche, lokasi, topik utama, sub-topik, topik tren, minat, atribut gaya konten, dan brand yang pernah dikerjakan |
| 30 | Header | Smart criteria (NL) | Tombol "Interpret" → chip | 29 aturan pencocokan pola | Aktif hanya bila query ≥3 kata. Hasil interpretasi jadi chip yang bisa dihapus. Daftar lengkap di §5.4 |
| 31 | Header | Section tabs | Chips (single-select, toggle) | 🎯 High Match · 📈 Trending · 💎 Hidden Gems · ⚡ High ROI · 🆕 Newly Added · 🔄 Recently Updated · 🕘 Recently Viewed | Tiap chip menampilkan jumlah hasil. "Recently Viewed" hanya muncul bila ada riwayat. **Rule:** High Match = skor kecocokan ≥85; Trending = growth exploding/rising ATAU viral frequent; High ROI juga lolos bila efisiensi komersial ≥70 |
| 32 | Header | Exclude | Pill → menu (multi-select) | Exclude already-selected creators · existing brand partners · competitor-heavy creators · high-risk creators · low-quality audiences · declining creators · sponsored-heavy creators | **Threshold:** low-quality audience = skor <75; sponsored-heavy = rasio sponsored >35%; competitor-heavy = saturasi kompetitor "high"; high-risk = level risiko "high" |
| 33 | Header | Collections | Pill → menu (single-select) | All creators + daftar shortlist tersimpan | Membatasi hasil ke anggota satu koleksi |

### 2.3 Tombol pintas — tidak menambah kebutuhan filter baru

Bar **Database Health** (`dfHealthHTML()`, dirender di `V.list` baris 3480) memuat
4 chip yang langsung menyetel filter **Data Status** (No. 23) lalu membuka panel:

| Chip | Menyetel Data Status ke |
|---|---|
| 🟢 N Fresh | `fresh` |
| 🔵 N Updating | `updating` |
| 🟡 N Aging | `aging` |
| 🔴 N Need Update | `due` + `outdated` + `failed` sekaligus |

Keempatnya **pintasan ke filter yang sudah ada**, bukan filter baru. Tidak dihitung
sebagai kebutuhan data tambahan.

---

## 3. Non-Filter Controls

Terlihat seperti filter tapi **tidak mengurangi jumlah hasil**. Tidak perlu
dicarikan datanya sebagai kebutuhan filter — tapi beberapa tetap butuh field
tersendiri, dan itu dicatat di kolom terakhir.

| Kontrol | Jenis | Isi | Butuh field sendiri? |
|---|---|---|---|
| **Sort** (pill kanan atas) | Pengurutan | **8 grup, 35 opsi:** Best Match (1) · Performance (8) · Growth (4) · Audience (4) · Commercial (5) · Intelligence (4) · Discovery (5) · Basic (4) | **Ya** — sebagian tidak dipakai filter mana pun: CPV, CPE, CPM, EMV, estimated ROI, opportunity score, competitor saturation, content relevance |
| **Columns** | Pemilihan kolom tabel + preset | Termasuk 5 kolom baru dari `dir-freshness.js`: Last Updated · Next Update · Update Frequency · Freshness Score · Update Status | Tidak — memakai field yang sama dengan filter No. 23–27, kecuali **Freshness Score** (0–100) yang tidak punya padanan filter |
| **Card / Table toggle** | Mode tampilan | Card · Table | Tidak |
| **Recent content** | Toggle tampilan | Menampilkan post terbaru tiap kreator secara inline | Tidak |
| **Saved searches** | Simpan & muat | Menyimpan kombinasi filter, sort, kolom, dan view | Tidak |
| **Database Health — angka & persentase** | Ringkasan | Jumlah per status + "Database Freshness: N%" | Tidak — agregat dari filter No. 23 |
| **Data Status modal** (klik chip di kartu kreator) | Detail per kreator | Last Updated (absolut + relatif) · Next Scheduled Update · Update Frequency · Monitoring Level · Freshness Score · tombol "Request Update Now" | Tidak — field sama dengan No. 23–27 |
| **Compare / Add KOL** | Aksi | — | Tidak |

> **Catatan.** Section tabs (No. 31) dan Exclude (No. 32) **bukan** non-filter.
> Meski tampil sebagai tab dan menu, keduanya dieksekusi di dalam `filterKols2()`
> lewat `dirSectionPass()` dan `dirExclPass()` dan benar-benar mengurangi hasil.

---

## 4. Filter Legacy / Tidak Aktif

Semua item di bawah **ada di kode tapi tidak dirender oleh UI live**, jadi tidak
bisa diklik dan tidak mempengaruhi hasil. **Jangan dihitung sebagai kebutuhan
filter, dan jangan dicarikan datanya di Subtask 2.**

| # | Item | Baris | Kenapa tidak aktif |
|---:|---|---|---|
| 1 | **12 field filter:** `rateMax`, `estReachMin`, `brandFitMin`, `campMin`, `postFreqMin`, `follMin`, `erMin`, `viewsMin`, `authMin`, `paidMax`, `follMax`, `reachMin` | `ADV_DEFAULT` 864 | Satu-satunya generator kontrolnya tidak pernah dipanggil (lihat #2). Field-nya masih hidup dan sebagian punya label siap pakai di `FP_ADV_LBL`, tapi nilainya tetap default netral sehingga kondisi di `filterKols()` selalu lolos |
| 2 | `fpAdvRange()`, `fpAdvMax()` — generator slider panel | 3574, 3577 | Didefinisikan tapi **nol call site**; `fpBody()` tidak pernah memanggilnya |
| 3 | **Modal Advanced Filters:** `chipRow()`, `filterModalHTML()`, `wireFilterModal()`, `renderFilterModal()`, `clearFilters()` | 1007–1050 | Hanya bisa dibuka dari `V.list` versi lama (#4). Sisanya lingkaran tertutup — `renderFilterModal()` cuma dipanggil dari dalam modal itu sendiri |
| 4 | `V.list` versi lama | 1064 | Ditimpa `V.list` baris 3454 |
| 5 | `filterKols2()` versi lama | 3258 | Ditimpa versi baris 3652 |
| 6 | `filterPanelHTML()` versi lama | 988 | Ditimpa versi baris 3632. Komentar baris 3631: "overrides filterPanelHTML" |
| 7 | `advS()`, `advPass()`, `advDnaPass()` | — | Memakai `state.dvAdv` — milik halaman `A.discover`, bukan KOL Directory. Registry `F2`/`M2` dipakai bersama, tapi KOL Directory mengaksesnya lewat `dirFxPass()` dengan state sendiri (`state.dirFx`) |
| 8 | Viral Frequency: nilai `occasional` (≥35) dan `rare` | — | Logikanya ada, chip-nya tidak dirender. Hanya `frequent` yang punya tombol (§2.1 No. 20) |
| 9 | Metric slider `medViewsK`, `avgLikesK`, `avgCmtK`, `affMin` | 3527–3530 | Didaftarkan ke `M2` khusus untuk panel ini, tapi semua grup di `FPG` punya `rngKeys` kosong sehingga tidak ada yang merendernya |

> **Yang perlu ditindaklanjuti — satu hal saja.**
> Baris #1 berarti **Rate Card, Est. Reach, Brand Fit, Campaigns Run, dan Posting
> Frequency tidak lagi menjadi filter di UI KOL Discovery.** Di prototype sebelum
> `AUTOME_1.html` kelimanya punya slider. Perlu dikonfirmasi ke pemilik desain:
> **sengaja dihapus, atau belum sempat dirender?** Jawabannya menentukan apakah
> kelimanya dicoret dari scope atau UI-nya yang harus dilengkapi dulu. Tidak ada
> jejak di kode yang bisa menjawab ini.

> **✅ TERJAWAB 2026-09-06 — dan jawabannya membatalkan §4 baris #1.**
> Tidak perlu dikonfirmasi ke pemilik desain: **ketujuh field itu hidup di app produksi.**
> `deliv.xlsx` sheet DELIVERABLES baris 75–77 dan 84 mencatat Minimum Followers, Minimum
> Engagement Rate, dan Max Rate Card berstatus **DONE**, sementara Min Authenticity, Min
> Brand Fit, Max Paid Ratio, dan Min Campaigns **dirender dalam keadaan `disabled`**
> (`KolDirectoryFilters.tsx:411–414`). Yang tidak dirender adalah **prototype**-nya, bukan
> produknya. Ketujuhnya masuk kembali ke scope — lihat §Revisi R2.

---

## 5. Catatan

### 5.1 Sebagian besar filter membaca lapisan turunan client-side, bukan field mentah

Filter di grup **Performance**, **Growth**, **Data Freshness**, **Audience Quality**,
dan **Content Category/Topic** tidak membaca field kreator secara langsung. Semuanya
lewat `intel2()` (baris 2725), `intel()` (baris 2311), dan `dfInfo()` (baris 3701)
yang menghitung di browser.

Penting untuk Subtask 2: yang perlu dicari di database adalah **field dasarnya**,
bukan nama yang muncul di UI. Contoh rantai turunan:

```
Save Rate         = (audience affinity × 0,5) + (engagement rate × 0,3)
Share Rate        = engagement rate × 0,35
Avg Likes         = avg views × engagement rate / 100 × 0,85
Audience Quality  = (authenticity + quality score) / 2
Growth Class      = bucketing dari pertumbuhan 30 hari
Perf. Stability   = dihitung dari deret tren 6 titik bulanan
Viral Frequency   = dihitung dari lonjakan terbesar pada deret tren
Data Status       = umur data ÷ interval update, lalu dibucket
Update Frequency  = turunan dari Monitoring Priority
Freshness Score   = 100 − min(1,6; rasio) × 50 − penalti status
```

### 5.2 Ada nilai yang dihasilkan dari hash ID, bukan dari data

Beberapa nilai di `intel2()` memakai `hsh(k.id)` — hash deterministik dari ID
kreator — sehingga terlihat realistis di prototype padahal bukan data:

```
idPct      = 80 + h%15     (Indonesia audience %)
jbPct      = 45 + h%20     (Jabodetabek audience %)
genZPct    = 52 + h%12     (Gen Z audience %)
millPct    = 55 + h%10     (Millennial audience %)
formatCons = 80 + h%12     (format consistency)
posSent    = authenticity × 0,85 + h%8
```

Empat di antaranya (`idPct`, `jbPct`, `genZPct`, `millPct`) dipakai aturan Smart
Criteria (§5.4). **Jangan diperlakukan sebagai kebutuhan data yang sudah tervalidasi**
sebelum dikonfirmasi ke pemilik desain.

### 5.3 Grup Data Freshness bertumpu pada dua input, bukan lima

Meski ada 5 filter (No. 23–27), seluruh grup ini diturunkan dari **dua** input saja:

| Input | Dipakai untuk |
|---|---|
| **Umur data** (kapan terakhir di-scrape) | Data Status, Last Updated, Next Update, Freshness Score |
| **Monitoring Priority** (diturunkan dari status campaign, growth class, virality, jumlah campaign) | Update Frequency, Next Update, Data Status |

Konsekuensinya untuk Subtask 2: **Update Frequency bukan field yang perlu disimpan** —
ia sepenuhnya ditentukan Monitoring Priority (High → 6 jam, Active → harian,
Standard → mingguan, Low → bulanan).

Perlu diperhatikan juga: `dfInfo()` memakai tanggal acuan **hardcoded**
`2026-09-02T15:00:00` (baris 3706) untuk menghitung timestamp absolut.

### 5.4 Daftar lengkap Smart Criteria (29 aturan)

Dipicu dari kotak pencarian bila query ≥3 kata, lalu jadi chip filter. Pola cocok
bahasa Inggris dan Indonesia.

| Pola | Label chip | Threshold |
|---|---|---|
| female / wanita / cewek | Female audience ≥60% | ≥60% |
| male audience / pria | Male-skewed audience | ≤45% female |
| gen z | Gen Z audience | ≥45% |
| millennial | Millennial audience | ≥50% |
| indonesia | Indonesia audience ≥80% | ≥80% |
| jakarta / jabodetabek | Jabodetabek audience | ≥40% |
| skincare | Skincare content | — |
| makeup | Makeup content | — |
| beauty | Beauty | — |
| fitness / workout / olahraga | Fitness | — |
| food / kuliner / recipe | Food | — |
| tech / gadget | Tech | — |
| travel | Travel content | — |
| lifestyle | Lifestyle | — |
| tiktok | TikTok | — |
| instagram / ig | Instagram | — |
| youtube | YouTube | — |
| high save / save rate / banyak disave | High Save Rate | ≥5% |
| high share / share rate | High Share Rate | ≥1,8% |
| growing / rising / tumbuh / naik | Growing | gClass rising atau exploding |
| exploding / viral growth | Exploding growth | gClass exploding |
| low competitor / competitor-free | Low Competitor Saturation | saturasi "low" |
| brand safe / safe / aman | Brand Safe | risiko "low" |
| high engagement / engaging | High Engagement | ≥5,5% |
| strong community / active audience | Active community | tipe audiens "active" |
| cheap / affordable / low cost / murah | Cost efficient | efisiensi ≥65 |
| hidden gem | Hidden Gem | klasifikasi peluang |
| micro / small creator | Under 1M followers | <1.000.000 |
| verified | Verified | boolean |

### 5.5 Nilai hardcoded di UI

| Filter | Nilai hardcoded |
|---|---|
| Platform | 3 platform: Instagram, TikTok, YouTube |
| Kategori KOL | 5 kategori: Fitness, Lifestyle, Beauty, Food, Tech |
| KOL Tier | 5 tier + batas follower di tooltip |
| Age | 3 bucket: 18-24, 25-34, 35-44 |
| Content Format | 6 opsi termasuk Video & Photo sebagai grup |
| Content Style & Personality | 10 nilai gaya konten |
| Audience Quality | 3 bucket, ambang 85 dan 75 |
| Data Status | 6 status + ambang rasio 0,5 / 0,85 / 1,2 |
| Last Updated · Update Frequency · Next Update · Monitoring Priority | Seluruh bucket dan intervalnya |
| Semua threshold Performance & Growth | Angka tetap di dalam fungsi filter |

Opsi yang **digenerate dari data**: Location, Audience location, Audience interest,
dan Content Category/Topic.

### 5.6 Urutan eksekusi filter

Untuk referensi Subtask 2, `filterKols2()` menerapkan penyaring dalam urutan:

```
1. filterKols()        — kategori, tier, format, gender, age, lokasi kreator,
                         lokasi audiens, minat, verified, platform
                         (pencarian teks dilewati di tahap ini)
2. dirQMatch()         — pencarian teks
3. dirFxPass()         — seluruh chip panel: Audience Quality, Content,
                         Performance, Growth, Data Freshness
4. dirExclPass()       — exclusions
5. dirSectionPass()    — section tab
6. nlPass()            — smart criteria
7. collection filter   — koleksi terpilih
```

### 5.7 Dua kontrol untuk satu filter

Kategori punya dua kontrol yang menulis ke state yang sama (`state.cat`): chip di
header (No. 28) dan chip "Kategori KOL" di panel (No. 2). Bukan dua kebutuhan
terpisah — cukup dihitung satu.

---

## Ringkasan

| Group | Jumlah filter aktif |
|---|---:|
| Creator Profile | 7 |
| Audience | 3 |
| Content | 3 |
| Performance | 7 |
| Growth | 2 |
| Data Freshness & Monitoring | 5 |
| **Subtotal panel** | **27** |
| Di luar panel | 6 |
| **Total kontrol filter** | **33** |

Setelah dikurangi satu kontrol kembar (Kategori — No. 2 dan No. 28 menulis state
yang sama), jumlah **kebutuhan filter unik = 32**.

**Non-filter controls: 8 kelompok** (§3). Dua di antaranya tetap butuh field
tersendiri di Subtask 2: **Sort** (35 opsi, sebagian pakai metrik yang tidak dipakai
filter mana pun) dan **Freshness Score** (0–100, tidak punya padanan filter).

**Legacy / tidak aktif: 9 baris di §4**, mencakup 12 field filter tanpa kontrol UI,
5 fungsi modal lama, 3 definisi yang tertimpa, 2 generator slider tanpa call site,
3 fungsi milik halaman lain, serta beberapa nilai filter yang tidak punya chip.

Dari seluruh isi §4, **hanya satu yang perlu ditindaklanjuti**: konfirmasi ke pemilik
desain apakah hilangnya Rate Card, Est. Reach, Brand Fit, Campaigns Run, dan Posting
Frequency dari UI itu disengaja. *(Sudah terjawab — lihat §Revisi R2.)*

---

# Revisi — 2026-09-06

Sumber: audit ulang Task 1–4 terhadap **app produksi** (`deliv.xlsx` sheet DELIVERABLES
baris 71–117), `docs/KOL_DISCOVERY_AUDIT.md` §3, dan migration `029`.

> §1–§5 di atas **sengaja dibiarkan apa adanya** sebagai audit trail prototype.
> Kalau ada pertentangan, **section ini yang berlaku**.

## R1 — Baseline berpindah: prototype bukan produk

`AUTOME_2.html` adalah mock: **8 KOL hardcode** (`const KOLS` baris 608) dan **0 network call**
(`fetch|XMLHttpRequest|axios` = 0). Ia tidak pernah membaca database, jadi daftar filternya adalah
*rancangan*, bukan *kebutuhan yang berjalan*. Implementasi nyatanya di repo `autometric` branch
`discover/data-terukur-kol` — dan daftar filternya berbeda.

Konsekuensinya: dokumen ini tetap sah sebagai **inventaris rancangan**, tapi Task 2–5 harus
memakai daftar app sebagai baseline dan memperlakukan sisa prototype sebagai **roadmap**.

## R2 — §4 baris #1 DICABUT: 7 field "legacy" hidup di app

| Field di `ADV_DEFAULT` | Status di app produksi | Bukti |
|---|---|---|
| `follMin` → Minimum Followers | **DONE** — slider 0–10M | `deliv.xlsx` baris 75 |
| `erMin` → Minimum Engagement Rate | **DONE** — slider 0–10%, step 0,1% | baris 76 |
| `rateMax` → Max Rate Card | **DONE** — slider 500rb–1M | baris 77 |
| `authMin` → Min Authenticity | Dirender, `disabled` | baris 84 · `KolDirectoryFilters.tsx:411–414` |
| `brandFitMin` → Min Brand Fit | Dirender, `disabled` | idem |
| `paidMax` → Max Paid Ratio | Dirender, `disabled` | idem |
| `campMin` → Min Campaigns | Dirender, `disabled` | idem |

Kalimat §4 *"tidak lagi menjadi filter di UI KOL Discovery"* **hanya benar untuk prototype**.
Ketujuhnya masuk kembali ke scope sebagai `CD-05`, `CD-06`, `CD-07`, `CD-14`, `CD-15`, `CD-16`,
`CD-17` di `KOL_DISCOVERY_TASK5_DESIGN.md`.

Sisa §4 (modal lama, definisi yang tertimpa, generator slider tanpa call site) **tetap berlaku** —
itu memang kode mati di dalam prototype.

## R3 — Dua filter yang tidak ada di prototype sama sekali

| Filter | Surface | Sumber | Catatan |
|---|---|---|---|
| **Profiling Status** | My Creators | `kol_directory.scrape_status` | Dropdown Ready / Profiling / Failed (`deliv.xlsx` baris 93) |
| **Lower Price than Reference** | Smart Discovery | `unified_rate_card.fee` | Toggle perbandingan relatif terhadap creator referensi (baris 116) |

Keduanya tidak punya padanan di `filterKols2()`, jadi tidak mungkin ditemukan lewat audit prototype.

## R4 — Kategori: 5 chip hardcode sudah usang

§2.1 No. 2 dan §5.5 menulis Kategori KOL sebagai **5 nilai hardcode** (Fitness, Lifestyle, Beauty,
Food, Tech). Sejak commit `8f5cad4` (migration `029`, 2026-09-03 — **sesudah** dokumen ini ditulis),
taxonomy resminya **9 Discovery Category**: Lifestyle, Beauty, Fashion, Food, Fitness, Entertainment,
Moms, Gen Z, Tech — dipetakan dari 22 dari 28 kategori mentah lewat `kol_categories.taxonomy_key`.

App sendiri sudah tidak memakai 5 chip: `deliv.xlsx` baris 74 menyebut *"6 kategori teratas di
toolbar dan daftar lengkap di Filter Panel"*.

## R5 — Platform: tiga daftar yang berbeda

| Sumber | Nilai |
|---|---|
| Prototype (§2.1 No. 1) | Instagram · TikTok · **YouTube** |
| App produksi | Instagram · TikTok · **Facebook** (`deliv.xlsx` baris 87, 113) |
| Database (`public.platforms`) | instagram 3.409 · tiktok 4.087 — **tidak ada YouTube maupun Facebook** |

Ketiganya tidak pernah sama. Ini keputusan produk (`D-10` di Task 5), bukan temuan data.

## Dampak ke hitungan

| | Dokumen ini | Setelah revisi |
|---|---:|---:|
| Kontrol filter | 33 | — |
| Kebutuhan filter unik | **32** | **40** |
| Filter yang dicoret sebagai legacy | 12 field | **5** *(7 dikembalikan — R2)* |
| Filter yang tidak tertangkap sama sekali | — | **2** *(R3)* |

Inventaris final ada di `docs/KOL_DISCOVERY_TASK5_DESIGN.md` §2, dipecah menjadi
**app Creator Database (18)** · **app baru (2)** · **roadmap prototype (20)**.
