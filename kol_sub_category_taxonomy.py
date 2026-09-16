"""42 Sub Category resmi — disimpan di public.kol_categories sebagai child.

============================================================================
KEPUTUSAN (Mba Yunita, 16 Sep 2026)
============================================================================

  * Creator Sub Category boleh dibuat.
  * Pakai / extend tabel kategori yang sudah ada — BUKAN source production
    baru. Maka Sub Category tinggal di `public.kol_categories`, dibedakan
    lewat kolom `level` dan ditautkan ke induknya lewat `parent_id`
    (migration 047).
  * 42 Sub Category resmi dari `docs/brand_match_master.xlsx` adalah source
    of record.
  * Category existing tidak diubah atau dihapus.
  * Mapping KOL -> Sub Category TIDAK dikarang.

============================================================================
SUMBER: SATU FILE, DUA SHEET YANG HARUS SEPAKAT
============================================================================

    docs/brand_match_master.xlsx

        sheet `Taxonomy`, bagian C   baris 21-163
            Baris ber-`Level` **L2 Sub Category** persis 42 buah, masing-masing
            membawa kode (`BEA.SKN`), kode induk (`BEA`), label EN dan label ID.

        sheet `Lookup_Lists`, bagian 2   baris 51-92
            "SUB CATEGORY -> PARENT CATEGORY" — 42 baris `label -> label induk`.

Keduanya identik. `tests/` membandingkan modul ini terhadap KEDUANYA.
Label disalin apa adanya — `&` tidak dijadikan `and`, tidak ada normalisasi.

============================================================================
PARENT CATEGORY: BARIS EXISTING DULU, BARU BARIS BARU
============================================================================

Excel punya 14 Parent Category (L1). Aturannya, disetujui user:

    nama PERSIS sama dengan baris kol_categories existing
        -> baris itu yang jadi induk; hanya kolom baru `code` yang diisi.
           id, name, taxonomy_key, created_at, updated_at tidak disentuh.
           Beauty, Fashion, Food, Fitness, Lifestyle, Travel,
           Entertainment, Gaming                                    (8)

    tidak ada baris bernama persis sama
        -> ditambahkan sebagai baris Category baru, label dari Excel.
           Tech, Finance, Education, Parenting, Automotive,
           Home & Living                                            (6)

TIDAK ada alias nama-mirip. `Technology and gadgets`, `Parenting and family`,
`Automotive and motorsports`, `Home Decor`, dan `Business and
entrepreneurship` TIDAK dijadikan induk: Excel bagian F hanya memetakan 5 dari
28 baris dan menulis "23 more | not read — left blank rather than guessed".

Catatan yang harus dibaca apa adanya: `Gaming` existing punya `taxonomy_key =
Tech` (migration 029), sedangkan di Excel ia L1 tersendiri (`GAM`). Keduanya
dibiarkan — `taxonomy_key` adalah Discovery Category, `code` adalah node Excel.

============================================================================
YANG SENGAJA TIDAK ADA DI SINI: MAPPING KOL -> SUB CATEGORY
============================================================================

Field mapping-nya BELUM DITETAPKAN, dan datanya pun belum ada.

`kol_directory.category_ids` BUKAN field itu. Audit 16 Sep 2026 atas DB `kol`:

    * 5.172 id di 4.002 KOL, SEMUANYA menunjuk baris `level = 'category'`;
      `category_id` (satu-satunya yang ber-FK) selalu ada di dalam array.
    * Array-nya tanpa FK, jadi DB tidak menolak id Sub Category — tapi
      pembacanya menganggap setiap elemen sebuah Category. Endpoint Discovery
      di app mengagregasi `kol_categories` per `id = ANY(category_ids)` tanpa
      saringan level; id Sub Category di sana akan muncul sebagai chip
      Category dan mengubah hitungan facet.
    * Excel sendiri memisahkannya: sheet `Taxonomy` menulis `category_ids ->
      kol_categories (L1 only, today)` dan meminta field L2 tersendiri.

Karena itu modul ini tidak menyediakan filter atau query mapping sama sekali.
Tidak ada assignment yang ditulis dari `category_ids`, `content_topic`, kata
kunci, atau alias `Moms -> PAR.MOM` di bagian F (itu alias kategori, bukan
assignment per KOL). Selama field dan datanya belum ada, Sub Category Match
berstatus UNAVAILABLE dan bobot 20%-nya dinormalisasi keluar — BUKAN diskor 0.
"""

from __future__ import annotations

# ===========================================================================
# BOBOT — dari Excel, bukan dipilih di sini
# ===========================================================================
#: `Lookup_Lists` bagian 4, konstanta `W_CC_SUBCATEGORY` = 20.
#: Tiga saudaranya: W_CC_CATEGORY 30, W_CC_TOPIC 30, W_CC_STYLE 20.
SUB_CATEGORY_MATCH_BOBOT = 20

#: Apakah input creator Sub Category sudah ada di produksi.
#: False selama field mapping KOL -> Sub Category belum ditetapkan dan belum
#: berisi data resmi. Konsumen WAJIB membaca ini dan mengeluarkan bobot 20%
#: dari penyebut — BUKAN menskor 0.
SUB_CATEGORY_INPUT_TERSEDIA = False

#: Alasan yang wajib ikut ditampilkan UI saat komponennya nonaktif.
SUB_CATEGORY_ALASAN_UNAVAILABLE = (
    "Master 42 Sub Category dan parent mapping-nya sudah tersedia, tetapi "
    "field mapping KOL -> Sub Category belum ditetapkan dan belum ada data "
    "assignment resmi."
)

# ===========================================================================
# TAXONOMY  ->  (code, parent_code, label, parent_label, label_id, sort_order)
# ===========================================================================
# Digenerate dari sheet `Taxonomy` baris 21-163, disaring `Level == 'L2 Sub
# Category'`. Urutannya urutan Excel. `label_id` dan `sort_order` hanya untuk
# tampilan dan TIDAK disimpan di DB — perubahan skema dibuat seminimal mungkin.

TAXONOMY: tuple[dict[str, object], ...] = tuple(
    {
        "code": code,
        "parent_code": parent_code,
        "label": label,
        "parent_label": parent_label,
        "label_id": label_id,
        "sort_order": sort_order,
    }
    for code, parent_code, label, parent_label, label_id, sort_order in (
        # Beauty
        ('BEA.SKN',  'BEA', 'Skincare',                   'Beauty',        'Perawatan Kulit',                   1),
        ('BEA.MKP',  'BEA', 'Makeup',                     'Beauty',        'Riasan',                            2),
        ('BEA.HAR',  'BEA', 'Haircare',                   'Beauty',        'Perawatan Rambut',                  3),
        # Fashion
        ('FAS.STR',  'FAS', 'Streetwear',                 'Fashion',       'Streetwear',                        4),
        ('FAS.HJB',  'FAS', 'Hijab Fashion',              'Fashion',       'Fashion Hijab',                     5),
        ('FAS.LOC',  'FAS', 'Local Brand',                'Fashion',       'Brand Lokal',                       6),
        # Food
        ('FOD.CUL',  'FOD', 'Culinary Review',            'Food',          'Review Kuliner',                    7),
        ('FOD.HCK',  'FOD', 'Home Cooking',               'Food',          'Masak Rumahan',                     8),
        ('FOD.BEV',  'FOD', 'Coffee & Beverage',          'Food',          'Kopi & Minuman',                    9),
        # Fitness
        ('FIT.HOM',  'FIT', 'Home Workout',               'Fitness',       'Olahraga di Rumah',                 10),
        ('FIT.GYM',  'FIT', 'Gym & Strength',             'Fitness',       'Gym & Latihan Beban',               11),
        ('FIT.RUN',  'FIT', 'Running',                    'Fitness',       'Lari',                              12),
        # Tech
        ('TEC.GDG',  'TEC', 'Gadget Review',              'Tech',          'Review Gadget',                     13),
        ('TEC.SAAS', 'TEC', 'Software & SaaS',            'Tech',          'Software & SaaS',                   14),
        ('TEC.AIP',  'TEC', 'AI & Productivity',          'Tech',          'AI & Produktivitas',                15),
        # Finance
        ('FIN.PFN',  'FIN', 'Personal Finance',           'Finance',       'Keuangan Pribadi',                  16),
        ('FIN.INV',  'FIN', 'Investing',                  'Finance',       'Investasi',                         17),
        ('FIN.BIZ',  'FIN', 'Business',                   'Finance',       'Bisnis',                            18),
        # Education
        ('EDU.STU',  'EDU', 'Study Tips',                 'Education',     'Tips Belajar',                      19),
        ('EDU.LNG',  'EDU', 'Language',                   'Education',     'Bahasa',                            20),
        ('EDU.CAR',  'EDU', 'Career',                     'Education',     'Karier',                            21),
        # Lifestyle
        ('LIF.VLG',  'LIF', 'Daily Vlog',                 'Lifestyle',     'Vlog Harian',                       22),
        ('LIF.SLF',  'LIF', 'Self Improvement',           'Lifestyle',     'Pengembangan Diri',                 23),
        ('LIF.MIN',  'LIF', 'Minimalism',                 'Lifestyle',     'Minimalis',                         24),
        # Travel
        ('TRV.DOM',  'TRV', 'Domestic Travel',            'Travel',        'Wisata Domestik',                   25),
        ('TRV.BGT',  'TRV', 'Budget Travel',              'Travel',        'Wisata Hemat',                      26),
        ('TRV.STY',  'TRV', 'Staycation & Hotel',         'Travel',        'Staycation & Hotel',                27),
        # Parenting
        ('PAR.MOM',  'PAR', 'Momlife',                    'Parenting',     'Kehidupan Ibu',                     28),
        ('PAR.KID',  'PAR', 'Kids & Family',              'Parenting',     'Anak & Keluarga',                   29),
        ('PAR.PRG',  'PAR', 'Pregnancy & Newborn',        'Parenting',     'Kehamilan & Bayi',                  30),
        # Entertainment
        ('ENT.COM',  'ENT', 'Comedy',                     'Entertainment', 'Komedi',                            31),
        ('ENT.MUS',  'ENT', 'Music',                      'Entertainment', 'Musik',                             32),
        ('ENT.FLM',  'ENT', 'Film & Series',              'Entertainment', 'Film & Serial',                     33),
        # Gaming
        ('GAM.MOB',  'GAM', 'Mobile Gaming',              'Gaming',        'Gim Mobile',                        34),
        ('GAM.PCC',  'GAM', 'PC & Console',               'Gaming',        'PC & Konsol',                       35),
        ('GAM.ESP',  'GAM', 'Esports',                    'Gaming',        'Esports',                           36),
        # Automotive
        ('AUT.MTR',  'AUT', 'Motorcycle',                 'Automotive',    'Motor',                             37),
        ('AUT.CAR',  'AUT', 'Car Review',                 'Automotive',    'Review Mobil',                      38),
        ('AUT.MOD',  'AUT', 'Modification & Aftermarket', 'Automotive',    'Modifikasi & Aftermarket',          39),
        # Home & Living
        ('HNL.INT',  'HNL', 'Interior',                   'Home & Living', 'Interior',                          40),
        ('HNL.ORG',  'HNL', 'Home Organization',          'Home & Living', 'Beberes Rumah',                     41),
        ('HNL.IMP',  'HNL', 'Home Improvement',           'Home & Living', 'Renovasi Rumah',                    42),
    )
)


# ===========================================================================
# TURUNAN — dihitung, tidak diketik ulang
# ===========================================================================

#: 14 Parent Category (code, label), urutan kemunculan pertama di Excel.
PARENT_CATEGORIES: tuple[tuple[str, str], ...] = tuple(
    dict.fromkeys((r["parent_code"], r["parent_label"]) for r in TAXONOMY)
)

#: Induk yang memakai baris kol_categories existing (nama persis sama, dicek
#: ke DB `kol` 16 Sep 2026). Dicatat di sini supaya test dan verifikasi
#: migration bisa menegakkannya; migration sendiri menentukannya dari nama.
PARENT_BARIS_EXISTING: tuple[str, ...] = (
    "BEA", "FAS", "FOD", "FIT", "LIF", "TRV", "ENT", "GAM")

#: Induk yang ditambahkan sebagai baris Category baru.
PARENT_BARIS_BARU: tuple[str, ...] = tuple(
    c for c, _ in PARENT_CATEGORIES if c not in PARENT_BARIS_EXISTING)

_PER_CODE = {r["code"]: r for r in TAXONOMY}
_PER_LABEL = {r["label"]: r for r in TAXONOMY}


def parent_dari_code(code: str) -> str | None:
    """`'BEA.SKN'` -> `'BEA'`. Kode tak dikenal -> None, bukan exception.

    Sengaja tidak diturunkan dari `code.split('.')[0]`: yang dibaca selalu
    kolom Parent Excel, supaya tidak ada induk yang dikarang.
    """
    baris = _PER_CODE.get(code)
    return baris["parent_code"] if baris else None


def parent_dari_label(label: str) -> str | None:
    """`'Skincare'` -> `'Beauty'`. Label tak dikenal -> None."""
    baris = _PER_LABEL.get(label)
    return baris["parent_label"] if baris else None


def sekode_induk(a: str, b: str) -> bool:
    """Apakah dua Sub Category berbagi Parent Category yang sama."""
    pa, pb = parent_dari_code(a), parent_dari_code(b)
    return pa is not None and pa == pb


def ringkasan() -> dict[str, int]:
    """Jumlah Sub Category per Parent — dipakai test dan verifikasi migration."""
    hasil: dict[str, int] = {}
    for r in TAXONOMY:
        hasil[r["parent_label"]] = hasil.get(r["parent_label"], 0) + 1
    hasil["TOTAL"] = len(TAXONOMY)
    return hasil


# ===========================================================================
# BENTUK KEDUA: literal SQL untuk migration
# ===========================================================================

def _q(nilai: object) -> str:
    return "'" + str(nilai).replace("'", "''") + "'"


def baris_parent_sql() -> str:
    """Literal `VALUES (code, name)` untuk 14 Parent Category — migration 047."""
    return ",\n".join(f"    ({_q(c)}, {_q(l)})" for c, l in PARENT_CATEGORIES)


def baris_seed_sql() -> str:
    """Literal `VALUES (code, parent_code, name)` untuk 42 Sub Category.

    Dipakai migration 047. Digenerate dari TAXONOMY yang sama dengan yang
    dibaca kode aplikasi, jadi seed dan kode tidak mungkin bergeser diam-diam.
    """
    return ",\n".join(
        f"    ({_q(r['code'])}, {_q(r['parent_code'])}, {_q(r['label'])})"
        for r in TAXONOMY)


# ===========================================================================
# FILTER / MATCH
# ===========================================================================

def parse_sub_category_codes(param: str | list[str] | tuple[str, ...] | None
                             ) -> list[str]:
    """`'BEA.SKN,FAS.HJB'` -> daftar kode sah, duplikat dibuang.

    Menerima KODE, bukan label: kode stabil, label bisa diterjemahkan. Kode
    tak dikenal diabaikan, bukan menggagalkan request.
    """
    if not param:
        return []
    bagian = param.split(",") if isinstance(param, str) else list(param)
    hasil: list[str] = []
    for b in bagian:
        kode = str(b).strip()
        if kode in _PER_CODE and kode not in hasil:
            hasil.append(kode)
    return hasil


# Filter SQL "KOL ber-Sub Category X" SENGAJA belum ada: field mapping KOL ->
# Sub Category belum ditetapkan (lihat docstring modul). Menulisnya sekarang
# berarti memilih field itu diam-diam.
