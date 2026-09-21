"""Leksikon Creator Classification -- kosakata, BUKAN taxonomy.

Setiap target di file ini adalah baris yang SUDAH ADA di database `kol`, dan
selalu dirujuk lewat identifier yang stabil -- BUKAN lewat nama tampilan:

    kategori      public.kol_categories.code         (level = 'category', parent_id NULL)
    subkategori   public.kol_categories.code         (level = 'sub_category')
    style         public.kol_attribute.attribute_key (kind = 'style')
    personality   public.kol_attribute.attribute_key (kind = 'personality')

Nama kategori/subkategori TIDAK diketik di sini: nama tampilan selalu diambil
dari `kol_categories.name` oleh `creator_classification.Taxonomy`, dan relasi
induk-anak selalu dari `kol_categories.parent_id` -- bukan dari prefix kode.

`creator_classification.Taxonomy` memvalidasi SELURUH target di sini terhadap
taxonomy yang dibaca dari DB. Satu target yang tidak ada di DB -> error saat
classifier dibuat, bukan label karangan yang lolos diam-diam.

============================================================================
ASAL KOSAKATA
============================================================================
Titik awalnya `audience_inference.INTEREST` (kosakata ID/EN yang sudah dipakai
`content_topic`). Kata yang di kamus itu GENERIK untuk bio kreator sengaja
tidak dibawa: `endorse`, `promo`, `order`, `brand`, `produk`, `tiktok`,
`youtube`, `enak`, `makan`, `sehat`, `digital`, `data`, `edit`, `photo`
muncul di bio hampir semua kreator dan akan membuat kategori menyala tanpa
bukti. Sisanya diperluas dengan frasa khas kreator (`beauty enthusiast`,
`food vlogger`, `motovlog`, ...) dan nama subkategori resminya sendiri.

Konsep dari repo riset (pratamasuherman/Autometric_research) yang dipakai:
  * urutan declared category: category -> category_name -> business_category_name
    (`fetch-profiles`). Di data kita padanannya satu field: businessCategoryName.
  * account_type + is_business -> sinyal PERAN akun (`compute-analysis`).
  * label persona (`run-t2-enrichment`) hanya sebagai ROLE perantara -- bukan
    taxonomy, dan di riset label itu dipakai untuk FOLLOWER, jadi di sini
    diturunkan ulang dari bukti milik kreator sendiri, tanpa LLM.
Logic gender/umur/minat riset adalah milik AUDIENS dan tidak dipakai.
"""

from __future__ import annotations

# ===========================================================================
# ROLE -- label perantara, bukan kolom dan bukan taxonomy
# ===========================================================================
ROLE_CREATOR = "Creator"
ROLE_MEDIA = "Media"
ROLE_PUBLIC_OFFICIAL = "Politician/Public Official"
ROLE_BUSINESS = "Business/Brand"
ROLE_ENTREPRENEUR = "Entrepreneur"
ROLE_PROFESSIONAL = "Professional"
ROLE_COMMUNITY = "Community"
ROLE_RELIGIOUS = "Religious"
ROLES = (ROLE_CREATOR, ROLE_MEDIA, ROLE_PUBLIC_OFFICIAL, ROLE_BUSINESS,
         ROLE_ENTREPRENEUR, ROLE_PROFESSIONAL, ROLE_COMMUNITY, ROLE_RELIGIOUS)

#: Peran yang boleh hidup berdampingan dengan Creator. Seri Creator vs salah
#: satunya -> peran yang lebih spesifik ini yang dipilih (dokter yang juga
#: kreator tetap Professional). Seri Creator vs Media/Business/Public Official
#: -> Unknown, karena itu memang dua jenis akun yang berbeda.
ROLES_SPECIFIC_OVER_CREATOR = (ROLE_PROFESSIONAL, ROLE_ENTREPRENEUR, ROLE_RELIGIOUS)

# ===========================================================================
# DECLARED CATEGORY (Instagram businessCategoryName) -> role / kategori
# ===========================================================================
# Setiap nilai yang benar-benar ada di data (57 nilai, 21 Sep 2026) ada di
# salah satu daftar, atau sengaja tidak dipetakan (lihat BUSINESS_CATEGORY_IGNORED).
# "Public figure" SENGAJA bukan Politician: di Instagram itu label generik
# untuk selebritas, atlet, dan kreator.
BUSINESS_CATEGORY_ROLE: dict[str, str] = {
    "Digital creator": ROLE_CREATOR, "Personal blog": ROLE_CREATOR,
    "Reel creator": ROLE_CREATOR, "Blogger": ROLE_CREATOR,
    "Creators & Celebrities": ROLE_CREATOR, "Gaming video creator": ROLE_CREATOR,
    "Public figure": ROLE_CREATOR, "Artist": ROLE_CREATOR, "Actor": ROLE_CREATOR,
    "Comedian": ROLE_CREATOR, "Musician": ROLE_CREATOR, "Musician/band": ROLE_CREATOR,
    "Singer": ROLE_CREATOR, "Bass Guitarist": ROLE_CREATOR, "Athlete": ROLE_CREATOR,
    "Fashion Model": ROLE_CREATOR, "Model": ROLE_CREATOR, "Makeup Artist": ROLE_CREATOR,
    "Writer": ROLE_CREATOR, "Author": ROLE_CREATOR, "Podcast": ROLE_CREATOR,
    "Chef": ROLE_CREATOR, "Coach": ROLE_CREATOR,
    "Media": ROLE_MEDIA, "Media/news company": ROLE_MEDIA,
    "News & media website": ROLE_MEDIA,
    "Politician": ROLE_PUBLIC_OFFICIAL, "Government official": ROLE_PUBLIC_OFFICIAL,
    "Government organization": ROLE_PUBLIC_OFFICIAL, "Political candidate": ROLE_PUBLIC_OFFICIAL,
    "Entrepreneur": ROLE_ENTREPRENEUR,
    "Doctor": ROLE_PROFESSIONAL, "Dentist & Dental Office": ROLE_PROFESSIONAL,
    "Obstetrician-Gynecologist (OBGYN)": ROLE_PROFESSIONAL, "Dermatologist": ROLE_PROFESSIONAL,
    "Nutritionist": ROLE_PROFESSIONAL, "Psychologist": ROLE_PROFESSIONAL,
    "Lawyer & Law Firm": ROLE_PROFESSIONAL, "Medical & health": ROLE_PROFESSIONAL,
    "Community": ROLE_COMMUNITY, "Community Garden": ROLE_COMMUNITY,
    "Social Service": ROLE_COMMUNITY,
    "Non-Profits & Religious Organizations": ROLE_RELIGIOUS,
    "Barber Shop": ROLE_BUSINESS, "Donut Shop": ROLE_BUSINESS, "Product/service": ROLE_BUSINESS,
    "Food & beverage": ROLE_BUSINESS, "Home Services": ROLE_BUSINESS,
    "Gym/Physical Fitness Center": ROLE_BUSINESS, "Automotive Body Shop": ROLE_BUSINESS,
    "Zoo": ROLE_BUSINESS, "Event": ROLE_BUSINESS,
}

#: Nilai yang ada di data tapi tidak membawa informasi ROLE (sebagian tetap
#: membawa kategori, lihat BUSINESS_CATEGORY_TO_CATEGORY). Tiap nilai yang
#: ada di data ada di BUSINESS_CATEGORY_ROLE atau di sini.
BUSINESS_CATEGORY_IGNORED = frozenset({
    "None", "Just for fun", "People", "Reference Website",
    "Design & fashion", "Education", "Children & Parenting",
    "Beauty, cosmetic & personal care", "Health/beauty",
})

#: Declared category -> KODE kategori canonical (`kol_categories.code`).
BUSINESS_CATEGORY_TO_CATEGORY: dict[str, str] = {
    "Beauty, cosmetic & personal care": "BEA", "Health/beauty": "BEA",
    "Makeup Artist": "BEA", "Dermatologist": "BEA",
    "Fashion Model": "FAS", "Model": "FAS", "Design & fashion": "FAS",
    "Athlete": "FIT", "Coach": "FIT", "Gym/Physical Fitness Center": "FIT",
    "Chef": "FOD", "Food & beverage": "FOD", "Donut Shop": "FOD",
    "Gaming video creator": "GAM",
    "Actor": "ENT", "Comedian": "ENT", "Musician": "ENT", "Musician/band": "ENT",
    "Singer": "ENT", "Bass Guitarist": "ENT", "Artist": "ENT",
    "Education": "EDU", "Children & Parenting": "PAR",
    "Home Services": "HNL", "Automotive Body Shop": "AUT",
    # Doctor / Dentist / Nutritionist / OBGYN / "Medical & health" / Zoo sengaja
    # TIDAK dipetakan ke kategori: Medical dan Animal Lovers bukan kategori
    # canonical. Peran Professional/Business-nya tetap dibaca BUSINESS_CATEGORY_ROLE.
}

# ===========================================================================
# KATEGORI -- target = nama baris kol_categories (level 'category')
# ===========================================================================
#: Kategori yang boleh jadi hasil classifier: HANYA 14 kategori canonical --
#: baris `level='category'`, `parent_id IS NULL`, dengan `code`. `Taxonomy`
#: memverifikasi ke DB bahwa ke-14 kode ini ada dan berbentuk demikian.
#: Label legacy roster (Foodies, Medical, ...) dan segmen audiens (Gen Z, Moms)
#: TIDAK PERNAH menjadi hasil.
CATEGORY_TARGETS = (
    "BEA", "ENT", "FAS", "FIT", "FOD", "LIF", "TRV",
    "GAM", "AUT", "EDU", "FIN", "HNL", "PAR", "TEC",
)

#: Segmen audiens yang tidak boleh menjadi kategori kreator.
AUDIENCE_SEGMENT_CATEGORIES = frozenset({"Gen Z", "Moms"})

#: Label roster LEGACY (baris `kol_categories` tanpa `code`) -> kode canonical.
#: Kompatibilitas saja, dan SENGAJA tidak diperluas: isinya sama persis dengan
#: crosswalk sebelumnya. Keputusan pemetaan resminya belum ada (lihat audit
#: taxonomy); dua baris di bawah bertanda AMBIGUOUS di audit itu.
#: Baris roster yang SUDAH canonical (Beauty, Food, ...) tidak perlu di sini --
#: dikenali langsung dari `code`-nya di DB.
ROSTER_LEGACY_TO_CODE: dict[str, str] = {
    "Dance": "ENT", "Humor": "ENT", "Musicians": "ENT", "Story Teller": "ENT",
    "Cyclist": "FIT", "Gym Enthusiast": "FIT", "Sports": "FIT",
    "Cooking": "FOD", "Foodies": "FOD",
    "Home Decor": "HNL",                       # AMBIGUOUS (taxonomy_key = Lifestyle)
    "Parenting and family": "PAR",
    "Technology and gadgets": "TEC",
    "Automotive and motorsports": "AUT",
    "Business and entrepreneurship": "FIN",    # AMBIGUOUS
}

#: Label legacy tanpa padanan canonical: diabaikan sebagai kategori (UNMAPPED).
ROSTER_UNMAPPED = frozenset({"Medical", "Spirituality and religion", "Animal Lovers",
                             "Environmentalism and sustainability"})

CATEGORY_LEXICON: dict[str, tuple[str, ...]] = {
    "BEA": ("makeup", "make up", "skincare", "skin care", "kosmetik", "cosmetics",
               "mua", "beauty", "kecantikan", "lipstik", "lipstick", "serum",
               "sunscreen", "haircare", "hair care", "beauty enthusiast", "beautyvlogger",
               "beauty vlogger", "beauty creator", "perawatan wajah", "glowing skin"),
    "FAS": ("fashion", "ootd", "outfit", "hijab style", "hijabers", "modest fashion",
                "streetwear", "lookbook", "fashion stylist", "stylist", "busana",
                "fashion blogger", "thrift", "thrifting", "mix and match", "fashion enthusiast"),
    "FIT": ("fitness", "gym", "workout", "personal trainer", "bodybuilding", "yoga",
                "pilates", "running", "runner", "marathon", "lari", "athlete", "atlet",
                "calisthenics", "cycling", "gowes", "crossfit", "zumba", "fitness coach",
                "olahraga", "sepakbola", "futsal", "badminton", "basket", "basketball"),
    "FOD": ("food", "foodie", "foodies", "kuliner", "culinary", "masak", "cooking", "chef",
             "resep", "recipe", "food vlogger", "food review", "kulineran", "food blogger",
             "baking", "pastry", "homemade", "jajanan"),
    "LIF": ("lifestyle", "daily life", "dailyvlog", "daily vlog", "lifestyle blogger",
                  "lifestyle creator", "self improvement", "minimalism", "minimalist living"),
    "TRV": ("travel", "traveler", "traveller", "traveling", "travelling", "wisata",
               "jalan jalan", "backpacker", "staycation", "hotel review", "travel vlogger",
               "trip", "explore indonesia", "liburan"),
    "GAM": ("gaming", "gamer", "esports", "esport", "mobile legends", "mlbb", "pubg",
               "free fire", "valorant", "pro player", "game streamer", "caster", "roblox",
               "minecraft", "genshin"),
    "TEC": ("tech", "teknologi", "gadget", "smartphone", "laptop", "programmer", "developer",
             "coding", "software", "artificial intelligence", "saas", "tech reviewer",
             "techie", "unboxing gadget"),
    # "motor"/"mobil" sendirian SENGAJA tidak ada: "naik motor", "di mobil" adalah
    # cerita harian, bukan konten otomotif.
    "AUT": ("otomotif", "automotive", "review mobil", "sepeda motor", "car review", "modifikasi",
                   "motovlog", "motovlogger", "bikers", "touring", "racing", "pembalap",
                   "car enthusiast"),
    "EDU": ("education", "edukasi", "pendidikan", "guru", "teacher", "dosen",
                  "tips belajar", "studygram", "study tips", "english teacher", "bahasa inggris",
                  "tutor", "bimbel", "beasiswa", "scholarship", "career coach", "karier"),
    "FIN": ("finance", "keuangan", "finansial", "investasi", "investing", "investor",
                "saham", "reksadana", "crypto", "trader", "trading", "financial planner",
                "perencana keuangan", "personal finance", "umkm", "pengusaha", "entrepreneur",
                # "business"/"bisnis" sendirian SENGAJA tidak ada: "for business
                # inquiries" ada di bio ratusan kreator (dry-run 21 Sep: 112 dari 117
                # Finance palsu). Hanya frasa yang memang bertopik bisnis.
                "tips bisnis", "belajar bisnis", "mentor bisnis", "bisnis online",
                "business coach", "business mentor"),
    "HNL": ("interior", "desain interior", "interior design", "home decor",
                      "dekorasi rumah", "home improvement", "renovasi", "home organization",
                      "beberes", "decluttering", "home living", "homedecor"),
    "PAR": ("parenting", "momlife", "mom life", "mom of", "ibu dari", "dad of",
                  "ayah dari", "toddler", "newborn", "hamil", "pregnancy", "busui", "bumil",
                  "family vlog", "mamah muda", "ibu anak", "parenting tips"),
    "ENT": ("actor", "aktor", "aktris", "actress", "komedian", "comedian", "comedy",
                      "stand up comedy", "standup", "musisi", "musician", "singer", "penyanyi",
                      "band", "cover lagu", "dancer", "penari", "dance", "film", "movie",
                      "prank", "sketsa komedi", "entertainer", "presenter", "host",
                      "podcast", "podcaster"),
}

# ===========================================================================
# SUBKATEGORI -- target = kode kol_categories (level 'sub_category')
# ===========================================================================
SUBCATEGORY_LEXICON: dict[str, tuple[str, ...]] = {
    "BEA.SKN": ("skincare", "skin care", "sunscreen", "serum", "moisturizer", "jerawat",
                "acne", "kulit wajah", "skincare routine"),
    "BEA.MKP": ("makeup", "make up", "mua", "makeup artist", "lipstik", "lipstick",
                "foundation", "eyeshadow", "makeup tutorial"),
    "BEA.HAR": ("haircare", "hair care", "rambut", "hairstyle", "hair stylist", "catok",
                "shampoo", "hair treatment"),
    "ENT.COM": ("comedy", "komedi", "komedian", "comedian", "stand up comedy", "standup",
                "lucu", "prank", "sketsa komedi"),
    "ENT.FLM": ("film", "movie", "series", "drakor", "review film", "movie review",
                "netflix", "sinema", "aktor", "aktris", "actor", "actress"),
    "ENT.MUS": ("music", "musik", "musisi", "musician", "singer", "penyanyi", "band",
                "cover lagu", "gitaris", "guitarist", "vocalist"),
    "FAS.HJB": ("hijab", "hijabers", "hijab style", "modest fashion", "jilbab", "kerudung",
                "hijab tutorial"),
    "FAS.LOC": ("local brand", "brand lokal", "produk lokal", "bangga buatan indonesia",
                "localbrand"),
    "FAS.STR": ("streetwear", "street style", "sneakers", "sneakerhead", "hypebeast"),
    "FIT.GYM": ("gym", "bodybuilding", "angkat beban", "weightlifting", "strength training",
                "personal trainer", "powerlifting"),
    "FIT.HOM": ("home workout", "workout di rumah", "olahraga di rumah", "hiit", "pilates",
                "yoga"),
    "FIT.RUN": ("running", "runner", "marathon", "half marathon", "trail run", "fun run",
                "lari pagi"),
    "FOD.BEV": ("coffee", "kopi", "barista", "kafe", "cafe", "minuman", "boba"),
    "FOD.CUL": ("food review", "kuliner", "kulineran", "culinary", "food vlogger",
                "food blogger", "review makanan", "tempat makan", "jajanan"),
    "FOD.HCK": ("resep", "recipe", "masak", "cooking", "home cooking", "masakan rumahan",
                "baking", "homemade"),
    "GAM.ESP": ("esports", "esport", "pro player", "turnamen", "tournament", "caster",
                "rrq", "evos", "onic"),
    "GAM.MOB": ("mobile legends", "mlbb", "pubg mobile", "free fire", "genshin",
                "mobile game", "codm", "honor of kings"),
    "GAM.PCC": ("pc gaming", "console", "playstation", "ps5", "xbox", "nintendo", "steam",
                "valorant", "dota", "pc build"),
    "LIF.MIN": ("minimalism", "minimalis", "minimalist", "decluttering", "slow living"),
    "LIF.SLF": ("self improvement", "self development", "pengembangan diri", "mindset",
                "produktif", "productivity", "journaling", "self love"),
    "LIF.VLG": ("daily vlog", "dailyvlog", "vlog harian", "day in my life", "a day in my life",
                "vlogger", "vlog"),
    "TRV.BGT": ("budget travel", "backpacker", "backpacking", "traveling hemat",
                "liburan hemat", "low budget"),
    "TRV.DOM": ("wisata indonesia", "explore indonesia", "wonderful indonesia", "bali", "lombok",
                "labuan bajo", "jogja", "bromo", "raja ampat", "domestic travel"),
    "TRV.STY": ("staycation", "hotel review", "review hotel", "resort", "villa", "glamping"),
    "AUT.CAR": ("car review", "review mobil", "car enthusiast", "test drive"),
    "AUT.MOD": ("modifikasi", "modif", "aftermarket", "custom", "velg", "knalpot"),
    "AUT.MTR": ("motovlog", "motovlogger", "bikers", "sepeda motor", "riding",
                "moge", "vespa", "touring"),
    "EDU.CAR": ("career", "karier", "karir", "career coach", "hrd", "lowongan",
                "interview kerja", "fresh graduate"),
    "EDU.LNG": ("english", "bahasa inggris", "english teacher", "belajar bahasa", "toefl",
                "ielts", "japanese", "bahasa korea", "language"),
    "EDU.STU": ("study tips", "studygram", "tips belajar", "ujian", "utbk",
                "skripsi", "beasiswa", "scholarship"),
    "FIN.BIZ": ("umkm", "entrepreneur", "pengusaha", "startup", "digital marketing",
                "tips bisnis", "belajar bisnis", "mentor bisnis", "bisnis online",
                "business coach", "business mentor"),
    "FIN.INV": ("investasi", "investing", "investor", "saham", "reksadana", "crypto",
                "trading", "trader", "obligasi"),
    "FIN.PFN": ("personal finance", "keuangan pribadi", "financial planner",
                "perencana keuangan", "atur keuangan", "budgeting", "dana darurat",
                "financial literacy"),
    "HNL.IMP": ("home improvement", "renovasi", "renovasi rumah", "diy rumah", "tukang"),
    "HNL.INT": ("interior", "desain interior", "interior design", "home decor",
                "dekorasi rumah", "homedecor"),
    "HNL.ORG": ("home organization", "beberes", "beberes rumah", "decluttering", "organizing",
                "rapi rapi"),
    "PAR.KID": ("kids", "anak anak", "toddler", "mpasi", "tumbuh kembang", "family vlog",
                "kids activity"),
    "PAR.MOM": ("momlife", "mom life", "mom of", "ibu dari", "busui", "working mom",
                "ibu rumah tangga", "mamah muda"),
    "PAR.PRG": ("hamil", "pregnancy", "pregnant", "bumil", "newborn", "persalinan",
                "melahirkan", "maternity"),
    "TEC.AIP": ("artificial intelligence", "chatgpt", "produktivitas", "productivity tools",
                "ai tools", "notion"),
    "TEC.GDG": ("gadget", "review gadget", "unboxing", "smartphone", "laptop",
                "tech reviewer", "iphone", "android"),
    "TEC.SAAS": ("software", "saas", "aplikasi", "developer", "programmer", "coding", "web app"),
}

# ===========================================================================
# ROLE dari bio -- pola kata (sudah dinormalisasi: huruf kecil, tanpa tanda baca)
# ===========================================================================
ROLE_BIO_LEXICON: dict[str, tuple[str, ...]] = {
    ROLE_CREATOR: ("content creator", "kreator konten", "digital creator", "influencer",
                   "kol", "selebgram", "youtuber", "tiktoker", "vlogger", "blogger",
                   "for endorsement", "endorsement", "business inquiries", "business inquiry",
                   "collab", "kolaborasi", "for business", "dm for", "managed by", "mgmt"),
    ROLE_MEDIA: ("portal berita", "media online", "berita terkini", "news portal",
                 "official media", "redaksi", "media partner resmi", "kanal berita",
                 "breaking news", "jurnalis", "journalist", "wartawan", "news anchor"),
    ROLE_PUBLIC_OFFICIAL: ("anggota dpr", "anggota dprd", "dpr ri", "dprd", "bupati",
                           "wakil bupati", "walikota", "wali kota", "gubernur", "menteri",
                           "caleg", "calon legislatif", "wakil rakyat", "senator",
                           "member of parliament", "kepala desa", "pejabat publik",
                           "akun resmi pemerintah", "pemerintah kabupaten", "pemerintah kota",
                           "pemprov", "pemkab", "pemkot"),
    ROLE_BUSINESS: ("official store", "official account", "official shop", "online shop",
                    "olshop", "toko online", "order via", "pemesanan", "reseller",
                    "dropship", "grosir", "supplier", "open order", "katalog"),
    ROLE_ENTREPRENEUR: ("founder", "co founder", "cofounder", "ceo", "owner of", "owner",
                        "pengusaha", "entrepreneur", "business owner"),
    ROLE_PROFESSIONAL: ("dokter", "doctor", "drg", "dentist", "apoteker", "pharmacist",
                        "perawat", "nurse", "bidan", "psikolog", "psychologist", "ahli gizi",
                        "nutritionist", "pengacara", "lawyer", "notaris", "arsitek", "architect",
                        "dosen", "lecturer", "financial planner", "konsultan", "consultant"),
    ROLE_COMMUNITY: ("komunitas", "community", "paguyuban", "relawan", "volunteer",
                     "yayasan", "foundation"),
    ROLE_RELIGIOUS: ("ustadz", "ustadzah", "ustad", "pendeta", "pastor", "habib", "kyai",
                     "dai", "pendakwah", "kajian rutin", "majelis"),
}

# ===========================================================================
# STYLE -- target = kol_attribute.attribute_key (kind 'style')
# ===========================================================================
#: Style yang bisa dikenali dari teks caption. Duplikat label lintas grup
#: (Educational/Storytelling ada di content_style DAN communication_style)
#: selalu dipetakan ke content_style supaya satu konsep = satu key.
STYLE_CUES: dict[str, tuple[str, ...]] = {
    "content_style.tutorial": ("tutorial", "cara", "how to", "step by step", "langkah",
                               "diy", "tips and trick", "tutor"),
    "content_style.review": ("review", "ulasan", "honest review", "unboxing", "first impression",
                             "worth it", "rekomendasi", "rating"),
    "content_style.vlog": ("vlog", "day in my life", "a day in my life", "daily vlog",
                           "dailyvlog", "weekly vlog", "grwm", "get ready with me"),
    "content_style.storytelling": ("storytime", "story time", "cerita", "kisah", "pengalaman aku",
                                   "pengalamanku", "true story"),
    "content_style.educational": ("tips", "fakta", "edukasi", "belajar", "tahukah kamu",
                                  "did you know", "penjelasan", "explained", "infografis"),
    "content_style.comedy": ("komedi", "comedy", "lucu", "ngakak", "prank", "sketsa", "parodi",
                             "wkwk", "wkwkwk", "funny"),
    "content_style.demo": ("demo", "demonstrasi", "percobaan", "eksperimen", "trial"),
    "content_style.commentary": ("opini", "pendapat", "reaksi", "react", "reacting",
                                 "komentar", "hot take", "menurut aku"),
    "communication_style.testimonial": ("testimoni", "testimonial", "sudah pakai", "udah pakai",
                                        "hasil pemakaian", "before after", "before and after"),
    "communication_style.data_driven": ("data", "statistik", "riset", "research", "survei",
                                        "persen", "grafik", "angka"),
}

#: Style yang ADA di taxonomy tapi TIDAK PERNAH dihasilkan: butuh bukti visual
#: (gambar/video) yang tidak tersedia, atau bukan pola teks yang bisa dihitung.
STYLE_NOT_INFERABLE = frozenset({
    "visual_style.aesthetic", "visual_style.casual", "visual_style.professional",
    "visual_style.cinematic", "visual_style.colorful", "visual_style.lifestyle",
    "visual_style.minimalist", "content_style.aesthetic", "content_style.talking_head",
    "content_style.entertaining", "communication_style.visual_first",
    "communication_style.conversational", "communication_style.demonstrative",
    "communication_style.demonstration", "communication_style.humorous",
    "communication_style.educational", "communication_style.storytelling",
})

# ===========================================================================
# PERSONALITY -- target = kol_attribute.attribute_key (kind 'personality')
# ===========================================================================
#: Personality diturunkan dari POLA caption, bukan dari satu kata. Tiap aturan
#: menunjuk style/cue yang harus mendominasi (lihat PERSONALITY_MIN_*).
PERSONALITY_FROM_STYLE: dict[str, tuple[str, ...]] = {
    "creator_personality.reviewer": ("content_style.review",),
    "creator_personality.educational": ("content_style.educational", "content_style.tutorial"),
    "creator_personality.humorous": ("content_style.comedy",),
}
INSPIRATIONAL_CUES = ("motivasi", "inspirasi", "semangat", "mindset", "never give up",
                      "jangan menyerah", "bersyukur", "percaya diri", "self love", "inspirational")
TECH_CUES = ("gadget", "teknologi", "tech", "smartphone", "laptop", "aplikasi", "software",
             "coding", "update", "fitur")

#: Personality yang ADA di taxonomy tapi TIDAK PERNAH dihasilkan.
#: Premium/Luxury = positioning brand, bukan kepribadian. Sisanya tidak punya
#: pola teks yang bisa dibedakan secara deterministik dari caption.
PERSONALITY_NOT_INFERABLE = frozenset({
    "creator_personality.premium", "creator_personality.luxury",
    "creator_personality.relatable", "creator_personality.casual",
    "creator_personality.creative", "creator_personality.professional",
    "creator_personality.entertaining",
})
