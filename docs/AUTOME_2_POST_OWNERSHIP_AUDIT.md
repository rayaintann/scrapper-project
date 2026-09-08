# AUTOME_2 — Audit Jumlah & Kepemilikan Post Hasil Scraping

**Read-only · 8 September 2026 · scraping DIHENTIKAN**

Requirement yang diuji: **setiap KOL → maksimal 10 postingan terakhir MILIK KOL tersebut.**

Run TikTok dihentikan di tengah jalan (batch 1) dan **tidak menulis satu baris pun** ke `l0_raw.tt_video_apify` — insert baru terjadi setelah semua batch selesai. Tidak ada retry, tidak ada batch tambahan, tidak ada migration, tidak ada perubahan pipeline.

---

# Ringkasan: requirement TIDAK terpenuhi, dan tidak pernah terpenuhi

| Requirement | Kenyataan |
|---|---|
| 10 post **milik KOL** | Actor dibatasi **10 hasil per URL**, bukan 10 post milik profil. Sisanya milik akun yang di-tag/kolaborasi |
| Terbukti di run terbaik (20 Agu) | Tiap URL mengembalikan **tepat 10 item**, tapi yang benar-benar milik profil **1–10** (rata-rata 6,8). `irwansyah_15`: 10 item, **1** miliknya |
| Terbukti di pilot (8 Sep) | Tiap URL mengembalikan 1–6 item (rata-rata 2,48), dan **tepat 1** miliknya di **seluruh 25 URL** |
| Filter kepemilikan di pipeline | **Tidak ada di titik mana pun** |

---

# 1. Apakah `InstagramPostScraper` meminta 10 post terakhir per profil?

**Tidak — ia meminta 10 HASIL per URL, dan hasil itu tidak dijamin milik profil tersebut.**

`apify_posts.py:50–75`

```python
class InstagramPostScraper(ProfileScraper):
    empty_is_failure = False
    retry_missing = False
    seconds_per_username = 20

    def __init__(self, cfg: ApifyConfig, results_limit: int = 10, **kwargs):
        actor_id = kwargs.pop("actor_id", None) or DEFAULT_IG_POST_ACTOR
        super().__init__(cfg, actor_id=actor_id, **kwargs)
        self._results_limit = results_limit

    def build_input(self, usernames: Sequence[str]) -> dict:
        return {
            "directUrls": [f"https://www.instagram.com/{u}/" for u in usernames],
            "resultsType": "posts",
            "resultsLimit": self._results_limit,
            "searchType": "user",
            "addParentData": False,
        }
```

Tidak ada satu pun parameter yang membatasi hasil ke pemilik profil. `resultsLimit` adalah plafon jumlah, bukan plafon kepemilikan.

---

# 2. Parameter Apify yang menentukan jumlah post

| Parameter | Nilai | Asal |
|---|---|---|
| `resultsLimit` | **10** | `--results` (default 10) → `_build_scraper()` (`post_pipeline.py:90–94`) → `InstagramPostScraper(results_limit=...)` → `self._results_limit` (`apify_posts.py:65`) → `build_input()` (`apify_posts.py:71`) |
| `resultsType` | `"posts"` | hardcoded `apify_posts.py:70` |
| `searchType` | `"user"` | hardcoded `apify_posts.py:72` |
| `addParentData` | `false` | hardcoded `apify_posts.py:73` |

TikTok, pembanding — `apify_posts.py:188–204`: `resultsPerPage` = `--results`, `profileScrapeSections: ["videos"]`, `profiles: [...]`.

---

# 3. Apakah 25 username dikirim sebagai 25 target profil terpisah?

**Ya sebagai `directUrls`, tapi dipecah jadi 3 run.**

`post_pipeline.py:279` → `chunked(usernames, max(1, args.batch_size))` dengan `--batch-size 10` → run berisi 10, 10, dan 5 URL.

Contoh input run pertama pilot:

```json
{
  "directUrls": [
    "https://www.instagram.com/ahquote/",
    "https://www.instagram.com/alyssadaguise/",
    "... 8 URL lainnya ..."
  ],
  "resultsType": "posts",
  "resultsLimit": 10,
  "searchType": "user",
  "addParentData": false
}
```

**`resultsLimit` berlaku per URL, bukan per run** — dibuktikan run 20 Agu: 13 URL × tepat 10 item = 130 baris, `min_per_url = max_per_url = 10`.

---

# 4. Apakah actor mengembalikan post dari akun yang di-tag/mention/kolaborasi?

**Ya. Terbukti di kedua run.**

| Run | Baris | Owner = profil diminta | Owner = akun lain |
|---|---:|---:|---:|
| 20 Agu | 130 | 89 (68%) | **41 (32%)** |
| 8 Sep (pilot) | 62 | 25 (40%) | **37 (60%)** |

### Contoh output yang owner-nya BENAR

| `inputUrl` | `ownerUsername` | `type` | Tertaut |
|---|---|---|---|
| `instagram.com/ahquote/` | `ahquote` | Image / feed | ✅ |
| `instagram.com/folkative/` | `folkative` | Image / feed | ✅ |
| `instagram.com/bobonsantoso/` | `bobonsantoso` | Sidecar / carousel_container | ✅ |

### Contoh output yang owner-nya SALAH

| `inputUrl` | `ownerUsername` | `type` | Tertaut |
|---|---|---|---|
| `instagram.com/andreastaulany/` | `andretaulanyandfriends` | Video / clips | ❌ NULL |
| `instagram.com/andreastaulany/` | **`neorheumacyl`** (merek obat) | Video / clips | ❌ NULL |
| `instagram.com/andreastaulany/` | `taulany_tv` | Sidecar | ❌ NULL |
| `instagram.com/dahliachr/` | `priveeclinic.id` | Video / clips | ❌ NULL |
| `instagram.com/chicco.jerikho/` | **`bodrex`** (merek obat) | Video / clips | ❌ NULL |
| `instagram.com/leomessi/` *(20 Agu)* | `adidasfootball` | — | ⚠ **tertaut ke `leomessi`** |
| `instagram.com/leomessi/` *(20 Agu)* | `mls` | — | ⚠ **tertaut ke `leomessi`** |

---

# 5. Apakah pipeline memfilter berdasarkan `ownerUsername`?

## **TIDAK. Tidak ada filter kepemilikan di titik mana pun.**

Jalurnya, dengan baris kode:

```
post_pipeline.py:330  _insert(platform, conn, items_all, scraper.item_username, ...)
                      └─ username_of = ownerUsername (apify_posts.py:76–88)
post_raw_store.py:284 usable = _partition(items, username_of, stats)
                      └─ hanya membuang: item error, tanpa username, tanpa content_id
                         TIDAK membandingkan dengan daftar username yang diminta
post_raw_store.py:290 account_ids = _account_ids(conn, stats, usable, "instagram", None)
                      └─ fetch_social_account_ids() — cocokkan username ke social_account
post_raw_store.py:294 social_account_id = account_ids.get(username)
post_raw_store.py:295     if social_account_id: stats.linked += 1
post_raw_store.py:297     else:                 stats.unlinked += 1   ← TETAP DI-INSERT
```

Item yang owner-nya tidak ada di `social_account` **tetap masuk L0** dengan `social_account_id = NULL`.

Akibatnya di pilot: **36 dari 62 baris** adalah post milik brand/akun lain (`neorheumacyl`, `bodrex`, `priveeclinic.id`, `elleindonesia`, …) yang:

- sudah dibayar ke Apify,
- tersimpan permanen di tabel append-only,
- tidak akan pernah bisa mengalir ke L1 (harmonisasi butuh `social_account_id`).

---

# 6. Apakah filter itu seharusnya sebelum insert ke L0?

**Sebagian ya — tapi filter "owner == username yang diminta" akan membuang data yang sebenarnya berharga.**

Buktinya dari run 20 Agu: sebagian owner yang berbeda **ternyata KOL roster juga** — `bazaarindonesia`, `elleindonesia`, `rans.entertainment`, `juansennnnn`, `zaskiasungkar15`. Post mereka memang benar-benar milik mereka, dan menyimpannya di bawah akun mereka sendiri adalah perilaku yang benar.

Jadi pemisahannya tiga, bukan dua:

| Kategori | Contoh | Perlakuan yang tepat |
|---|---|---|
| Owner = profil yang diminta | `folkative` ← `instagram.com/folkative/` | Simpan, tautkan ke profil itu |
| Owner ≠ profil, **tapi ada di roster** | `zaskiasungkar15` ← `instagram.com/irwansyah_15/` | Simpan, tautkan ke **pemilik sebenarnya** |
| Owner ≠ profil, **tidak ada di roster** | `neorheumacyl` ← `instagram.com/andreastaulany/` | **Buang sebelum insert** — inilah 36 baris sampah itu |

**Keputusan produk, bukan keputusan teknis.** Saya tidak mengubahnya.

---

# 7. Kenapa 20 Agustus menghasilkan 130 post dari 13 akun, pilot hanya 26 valid dari 25?

**Dua efek berbeda dan independen. Keduanya terukur.**

## Efek A — hasil per URL runtuh (bukan karena kode kita)

| Run | URL | Item | **Item per URL** | Min | Maks |
|---|---:|---:|---:|---:|---:|
| 20 Agu | 13 | 130 | **10,00** | 10 | 10 |
| 27 Agu | 2 | 38 | 19,00 | 0 | 9 |
| 28 Agu | 1 | 20 | 20,00 | 0 | 10 |
| **8 Sep (pilot)** | 25 | 62 | **2,48** | 1 | 6 |

Parameter identik (`resultsLimit: 10`), actor identik (`apify/instagram-scraper`), jalur kode identik. 20 Agu memenuhi plafon dengan sempurna; 8 Sep hanya 25% dari plafon. **Penyebabnya di sisi Instagram/actor, bukan di repo ini.**

## Efek B — porsi milik sendiri juga turun

| Run | Owner = profil | Persen |
|---|---:|---:|
| 20 Agu | 89 / 130 | 68% |
| 8 Sep | 25 / 62 | **40%** |

Pola pilot sangat khas: **tepat 1 post milik sendiri di setiap satu dari 25 URL** — tidak ada satu pun yang dapat 2 atau lebih.

## Efek C — atribusi 20 Agu ternyata SALAH, jadi angkanya tidak sebanding

| Run | Baris | `social_account_id` NULL | Owner **cocok** dgn akun tertaut | Owner **SALAH** |
|---|---:|---:|---:|---:|
| 20 Agu | 130 | 0 | 89 | **41** |
| 27 Agu | 38 | 0 | 36 | **2** |
| 28 Agu | 20 | 2 | 18 | 0 |
| 8 Sep | 62 | 36 | 26 | **0** |

Bukti langsung — `abd72737…` adalah `social_account` milik **`leomessi`**:

| `ownerUsername` | `inputUrl` | `social_account_id` |
|---|---|---|
| **`adidasfootball`** | `instagram.com/leomessi/` | `abd72737…` (leomessi) |
| `leomessi` ×8 | `instagram.com/leomessi/` | `abd72737…` |
| **`mls`** | `instagram.com/leomessi/` | `abd72737…` |

`adidasfootball` dan `mls` **tidak ada** di `public.social_account` (diperiksa: 0 baris), jadi tidak mungkin ter-resolve lewat `fetch_social_account_ids`. Kode hari ini (`post_pipeline.py:330` + `post_raw_store.py:294`) menautkan per `ownerUsername`, jadi mereka akan jadi NULL — persis yang terjadi 8 Sep.

Data 20 Agu **mendahului commit pertama repo** (`494f977`, 27 Agu), jadi versi kode yang membuatnya tidak ada di git history dan tidak bisa saya periksa.

### Dampaknya masih hidup sampai sekarang

**43 dari 503 baris `l1_silver.unified_post` punya `username` yang berbeda dari pemilik `social_account` yang ditautkan.** Artinya likes/comments milik `adidasfootball` dan `mls` ikut dihitung ke ER `leomessi`. Ini isu integritas data terpisah yang belum pernah tercatat.

### Kesimpulan Q7

"130 post dari 13 akun" **bukan 130 post milik 13 akun itu.** Sebenarnya 89 milik mereka + 41 milik akun lain yang salah dilekatkan. Perbandingan yang jujur:

| | 20 Agu | 8 Sep |
|---|---:|---:|
| Post benar-benar milik KOL yang diminta | **89** dari 13 akun (6,8/akun) | **25** dari 25 akun (1,0/akun) |

---

# 8. Apakah perubahan 1 baris provenance mempengaruhi scraping?

## **Tidak. Diverifikasi lima cara.**

| # | Bukti |
|---|---|
| 1 | `git diff --stat` = **1 file, 1 insertion, 3 deletions**. Tidak ada file lain tersentuh |
| 2 | Baris yang diubah hanya menghitung string `actor`, yang dipakai untuk kolom `source_actor` dan log. Tidak masuk ke `build_input()` |
| 3 | `build_input()` di `apify_posts.py` **tidak disentuh sama sekali** — `directUrls`, `resultsType`, `resultsLimit`, `searchType`, `addParentData` identik |
| 4 | Scraper yang dipakai `scrape_batch()` dibangun terpisah di `post_pipeline.py:245/254`. Instance pada baris yang diubah hanya dibaca `._actor_id`-nya lalu dibuang. `ProfileScraper.__init__` (`apify_runner.py:111–127`) tidak melakukan I/O jaringan — hanya membuat objek `ApifyClient` |
| 5 | `source_actor` yang tercatat di 62 baris pilot = **`apify/instagram-scraper`** — nilai yang sama persis dengan 188 baris lama. Perbaikannya bekerja, dan tidak lebih dari itu |

Efek A (hasil per URL 10 → 2,48) **tidak mungkin** disebabkan perubahan ini: input actor byte-for-byte sama.

---

# Hasil pilot yang terlanjur berjalan

Data pilot mengalir sendiri sampai L2 (ada job/asset yang berjalan otomatis, tanpa saya materialisasi apa pun).

## Funnel 50 KOL

| Tahap | Instagram | TikTok | Total |
|---|---:|---:|---:|
| KOL pilot | 25 | 25 | 50 |
| Ada L0 post | **25** | **0** | 25 |
| Harmonized | 25 | 0 | 25 |
| L1 `unified_post` | 25 | 0 | 25 |
| Punya denominator | 19 | 0 | 19 |
| Feature ER | 16 | 0 | 16 |
| **L2 ER** | **16** | **0** | **16** |

## Post pilot per layer

| Layer | Post |
|---|---:|
| L0 (62 masuk, 36 tanpa `social_account_id`) | **25** tertaut |
| Harmonization | 25 |
| L1 `unified_post` | 25 |
| L2 `post_metric` | 25 |
| Punya denominator | 19 |
| **Masuk hitungan ER** | **16** |

## Post gagal / tidak usable

| Sebab | Post |
|---|---:|
| Tanpa denominator (terbit sebelum snapshot akun) | 6 |
| `likes_hidden` | 4 |
| `is_collaboration` | 0 |
| **Total tidak dapat ER** | **9 dari 25** |

Rentang tanggal post pilot: 2026-04-28 s.d. 2026-09-08; **19 dari 25** jatuh di jendela snapshot.

## ER coverage sebelum vs sesudah

| | KOL ber-ER L2 |
|---|---:|
| Sebelum pilot | **22** |
| Sesudah pilot | **38** |
| Selisih | **+16 (+73%)** |

## ⚠ Tapi seluruh 16 ER baru bertumpu pada SATU post

| Username | `n_post` | `n_sampel` | ER L2 |
|---|---:|---:|---:|
| `bobonsantoso` | 1 | 1 | **7,3993%** |
| `folkative` | 1 | 1 | 3,7810% |
| `cakecaine` | 1 | 1 | 3,7751% |
| `ahquote` | 1 | 1 | 2,0961% |
| `tasyakamila` | 1 | 1 | 1,1875% |
| `kikysaputrii` | 1 | 1 | 0,2529% |
| `syakirdaulay` | 1 | 1 | 0,2225% |
| `wulanguritno` | 1 | 1 | 0,1639% |
| `andreastaulany` | 1 | 1 | 0,1558% |
| `tasyafarasya` | 1 | 1 | 0,1423% |
| `indrowarkop_asli` | 1 | 1 | 0,1254% |
| `jakarta.terkini` | 1 | 1 | 0,1163% |
| `instagram` | 1 | 1 | 0,0899% |
| `andreadianbimo` | 1 | 1 | 0,0859% |
| `indozone.id` | 1 | 1 | 0,0563% |
| `desta80s` | 1 | 1 | 0,0166% |

Rentangnya **445×** (0,0166% – 7,3993%) — sebaran yang wajar untuk satu post tunggal, dan tidak layak disebut "engagement rate kreator".

## Biaya

| Platform | Batch | Item | Biaya |
|---|---|---:|---|
| Instagram | 3 (10/10/5) | 62 | **$0,5382** |
| TikTok | 1 sukses + 2 gagal, dihentikan | 3 (tidak ditulis) | **$0,1230** |
| **Total** | | | **≈ $0,66** |

TikTok juga menghabiskan biaya pada run yang `SUCCEEDED tapi 0 item` (diblokir platform) — tidak tercatat karena run dihentikan sebelum ringkasan.

---

# Apakah existing scraper menjamin 10 post terakhir per KOL?

## **Tidak, dan secara desain memang tidak bisa.**

| Syarat requirement | Terpenuhi? | Alasan |
|---|---|---|
| Maksimal 10 | ✅ | `resultsLimit: 10` |
| Tepat/hingga 10 **milik KOL** | ❌ | `resultsLimit` membatasi total hasil, bukan hasil milik profil |
| Post terbaru | ⚠ | Urutan dari actor, tidak diverifikasi pipeline |
| Hanya milik KOL | ❌ | Tidak ada filter kepemilikan di seluruh jalur |

Terbaik yang pernah tercapai (20 Agu): **6,8 post milik KOL** dari plafon 10 — dan satu akun (`irwansyah_15`) cuma dapat **1**.

---

# Perubahan minimum yang diperlukan

**Belum saya kerjakan.** Butuh persetujuan, dan sebagian butuh keputusan produk.

| # | Perubahan | File | Sifat | Kenapa |
|---|---|---|---|---|
| **A** | Buang item yang owner-nya **tidak ada di roster** sebelum insert L0 | `post_pipeline.py` (sebelum `_insert`, baris 330) **atau** `post_raw_store._partition` | ~5 baris | Mencegah 36 baris sampah/25 akun. **Jangan** filter ke "owner == yang diminta" — akan membuang post KOL roster yang sah (bukti §6) |
| **B** | Naikkan `--results` supaya hasil milik-sendiri mendekati 10 | tidak ada perubahan kode — hanya argumen CLI | 0 baris | Rata-rata milik-sendiri 68% (20 Agu). Untuk 10 milik sendiri butuh ±15. **Menaikkan biaya**, dan tidak menjamin |
| **C** | Batasi per owner setelah filter (ambil 10 terbaru tiap owner) | sama dengan A | ~5 baris | Supaya "maksimal 10 per KOL" benar-benar dijamin, bukan diharapkan |
| **D** | Perbaiki 43 baris L1 yang salah atribusi | butuh keputusan | — | Isu integritas data terpisah. Menyentuh data produksi — **tidak boleh dikerjakan tanpa keputusan eksplisit** |

**A + C bersama** adalah perubahan minimum yang benar-benar memenuhi requirement. B sendirian tidak cukup — tanpa filter, menaikkan `resultsLimit` hanya menambah post milik orang lain.

## Yang perlu diputuskan sebelum kode disentuh

1. Post milik **KOL roster lain** yang ikut terbawa: disimpan (ditautkan ke pemilik sebenarnya) atau dibuang?
2. Berapa `--results` yang sepadan biayanya untuk mengejar 10 post milik sendiri?
3. 43 baris L1 salah atribusi: dibiarkan, ditandai, atau dibersihkan?
4. Efek A (hasil per URL 10 → 2,48) — tunggu dan ukur ulang, atau naikkan `--results` sebagai kompensasi?

---

*Audit read-only. Perubahan kode dalam sesi ini hanya satu baris provenance actor di `post_pipeline.py` yang sudah disetujui sebelumnya. Tidak ada scraping tambahan, retry, batch baru, scaling, migration, maupun perubahan pipeline. Tidak ada commit atau push.*
