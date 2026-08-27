"""Menurunkan atribut audiens dari data follower, dengan aturan deterministik.

Dipakai layer Feature untuk mengisi `feature.{ig,tt}_audience_analysis`, lalu
diteruskan ke `l2_gold.audience_*`.

============================================================================
PRINSIP -- KENAPA MODUL INI BOLEH ADA
============================================================================

Follower TIDAK mengirim gender, lokasi, atau interest. Yang dikirim hanya
`username`, `full_name`, `bio`, dan beberapa flag. Jadi ketiga dimensi itu
DITURUNKAN, bukan diambil.

Supaya turunan tidak berubah jadi karangan, seluruh modul ini terikat lima
aturan:

  1. DETERMINISTIK. Input yang sama selalu menghasilkan output yang sama. Tidak
     ada acak, tidak ada model probabilistik, tidak ada panggilan jaringan.

  2. `unknown` ADALAH JAWABAN YANG SAH. Kalau tidak ada aturan yang cocok,
     hasilnya `unknown` -- BUKAN tebakan acak, dan bukan pula baris yang dibuang
     diam-diam. `unknown` ikut dihitung dan ikut disimpan, supaya pembaca tahu
     berapa besar yang tidak diketahui.

  3. SETIAP HASIL MEMBAWA `confidence`:
         high   -- tidak ambigu secara teknis (emoji bendera -> kode ISO,
                   simbol gender eksplisit)
         medium -- kecocokan leksikon kuat (nama depan persis, sufiks morfologi)
         low    -- kecocokan lemah (substring handle, kata kunci di username)

  4. BUKTI YANG BERTENTANGAN -> `unknown`. Kalau sinyal pria dan wanita
     sama-sama muncul pada kekuatan yang sama, hasilnya `unknown`, bukan
     "yang ketemu duluan". Lihat `_putuskan_gender`.

  5. TIDAK ADA NILAI YANG DIKETIK MANUAL PER AKUN. Modul ini hanya berisi ATURAN
     dan KAMUS umum. Tidak ada cabang "kalau akunnya X maka jawabannya Y".

Yang SENGAJA TIDAK dipakai sebagai sinyal: emoji dekoratif (bunga, hati, kupu-
kupu) untuk menebak gender. Itu stereotip, bukan bukti, dan akan menghasilkan
angka yang terlihat percaya diri tapi tidak berdasar.

============================================================================
BATAS DATA YANG SUDAH DIUKUR (2.300 follower)
============================================================================

    platform    baris   username   full_name   bio    followers_count
    instagram   1.300   1.300      1.003       0      0
    tiktok      1.000   1.000      1.000       410    1.000

`username` adalah satu-satunya field yang terisi 100%, dan sering justru
memuat nama asli ketika `full_name` berisi sampah (`"Bitch"`, `";)"`, `"k"`).
Karena itu gender dibaca dari KEDUANYA, bukan dari username hanya sebagai
cadangan.

`bio` adalah sumber utama interest. Instagram tidak mengirimnya sama sekali,
jadi interest Instagram akan tetap didominasi `unknown`. Itu batas DATA, bukan
batas aturan -- menaikkannya butuh scrape profil per follower.

============================================================================
KENAPA NORMALISASI DAN PEMECAHAN HANDLE PENTING
============================================================================

Nama asli di data banyak yang bergaya atau berupa handle yang dilekatkan:

    `𝔬𝔧𝔞𝔫`, `🌈almeera🌈`, `yayukprasetyaa`, `na.bilaaa09_`, `summmmmmm17`

`_normalisasi()` melipat unicode dekoratif ke ASCII; `_token()` membuang angka,
memecah di titik/garis bawah/strip, lalu MERUNTUHKAN huruf berulang
(`bilaaa` -> `bila`). Tanpa keduanya, `almeera`, `prasetya`, dan `nabila` tidak
akan pernah cocok dengan kamus mana pun padahal namanya jelas terbaca.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Kamus nama -> gender
# ---------------------------------------------------------------------------
# Nama depan umum Indonesia + internasional. Sengaja HANYA nama yang gendernya
# tidak diperdebatkan. Nama netral/ambigu (Sri, Ari, Eka, Dwi, Tri, Andrea,
# Alex, Kiki, Nur, Ayu Bagus, ...) TIDAK dimasukkan supaya tidak dipaksakan.
NAMA_PRIA = {
    "abdul","abdullah","abi","abil","aburizal","achmad","adam","ade putra","adi",
    "adit","aditya","adnan","afif","agung","agus","agusman","ahmad","ahmed","aji",
    "akbar","akmal","alan","albert","aldi","aldo","alfa","alfian","alfin","algi",
    "ali","alif","alvin","amar","amin","amir","ammar","anang","anas","andhika",
    "andi","andika","andre","andrew","andri","andrian","angga","anggara","anton",
    "antonius","ardi","ardian","ardiansyah","arfan","arga","argo","ari wibowo",
    "arief","arif","arifin","aris","arman","arnold","arya","aryo","asep","asep s",
    "aswin","aulia rahman","axel","ayub","azhar","azmi","bagas","bagus","bahtiar",
    "bambang","bara","barra","bayu","bekti","ben","benny","bima","bimo","bintang",
    "bobby","bondan","boy","brayen","brian","budi","bukhori","burhan","cahya",
    "cahyo","calvin","candra","cecep","chandra","charles","chris","christian",
    "daffa","dafa","dandi","dani","daniel","danu","darma","darmawan","david",
    "dedi","dedy","deni","denny","derry","dewa","dicky","didi","didik","dimas",
    "dio","diego","dodi","dody","doni","dony","dwiki","eden","edi","eddy","edo",
    "eduardo","edward","edwin","eka putra","eko","elang","eldi","elvin","emil",
    "eric","erik","erlangga","erwin","evan","fachri","fadhil","fadil","fahmi",
    "fahri","faisal","faiz","fajar","fandi","fandy","farhan","faris","farrel",
    "fauzan","fauzi","febri","febrian","ferdi","ferdinand","ferry","fikri","firda n",
    "firman","fitra","frans","fredy","gading","gagah","galang","galih","gani",
    "gary","gavin","george","gerald","gibran","gilang","gio","giovanni","gunawan",
    "guntur","hadi","hafiz","hafidz","haikal","hakim","hamdan","hamzah","handoko",
    "handy","hanif","hari","haris","harry","hartono","harun","hasan","hasbi",
    "hendra","hendri","hendrik","henry","heri","herman","hermawan","hidayat",
    "hilman","husein","husen","ibnu","ibrahim","idris","ikhsan","ikhwan","ilham",
    "ilyas","imam","imron","indra","irfan","irham","irsyad","irwan","irwansyah",
    "iqbal","isa","ismail","israel","ivan","iwan","jack","jaka","jamal","james",
    "jason","javier","jefri","jeffry","jeremy","jimmy","joel","johan","john",
    "johnny","jonathan","joko","jose","joseph","joshua","julian","julius","kaka",
    "kamal","kevin","khairul","khalid","kurnia","kusuma","lucas","luthfi","luqman",
    "mahdi","mahendra","maik","malik","manto","marcel","marco","mario","mark",
    "marko","martin","marwan","maulana","maulida n","michael","miftah","mikael",
    "misbah","mochamad","moh","mohamad","mohammad","mohammed","muh","muhamad",
    "muhammad","mukhlis","mulyadi","mulyono","munir","mursid","musa","mustofa",
    "nabil","nanda putra","nasir","nathan","naufal","nico","nicolas","novan",
    "nugroho","nur cholis","nurdin","oki","oscar","panca","pandu","patrick","paul",
    "peter","prabowo","pradana","pramana","prasetya","prasetyo","pratama","pria",
    "priyo","purnama","purnomo","putra","radit","raditya","rafi","raffi","rafli",
    "raden","rahmat","rahman","raka","rakha","ramadhan","ramdan","randi","rangga",
    "rasyid","ravi","reyhan","rendi","rendy","reno","reza","rezky","ricky","ridho",
    "ridwan","rifki","rifky","rio","riyan","rizal","rizki","rizky","robert",
    "robby","rohman","roni","rudi","rudy","rusdi","ryan","saeful","saiful","salman",
    "samsul","samuel","sandi","sandy","santoso","satria","sayid","sebastian",
    "setiawan","sigit","simon","slamet","sofyan","solihin","steven","sugeng",
    "suhendra","sukarno","sulaiman","suparno","supriyanto","surya","susanto",
    "sutrisno","syahrul","syaiful","syamsul","taufik","teguh","teddy","thomas",
    "tirta","tomi","tommy","tono","topan","tri anto","umar","usman","utomo",
    "vicky","victor","vincent","wahyu","wawan","widodo","wibowo","wildan",
    "william","willy","wisnu","yahya","yanto","yoga","yohanes","yosef","yoseph",
    "yudha","yudi","yudistira","yusuf","yusril","zaki","zainal","zainuddin","zidan",
    # --- perluasan leksikon: nama umum Indonesia ---
    "adhitya","aditia","afandi","ahsan","aidil","akhmad","alamsyah","aldian",
    "alfarizi","alghifari","amrullah","andreas","anggoro","anugrah","apriyanto",
    "ardiyanto","arhan","aripin","arjuna","arkan","arsyad","aryanto","asnawi",
    "asrul","athallah","awang","bachtiar","badru","bagja","bahrul","bakti",
    "baskoro","basuki","beni","bernard","bramantyo","bryan","budiman","bustomi",
    "cakra","chairul","choirul","cristian","dafi","dahlan","damar","danang",
    "danendra","darwis","dedik","deddy","dendi","dendy","depri","dhani","dhimas",
    "dimitri","dodit","eddie","edgar","efendi","eggy","elfan","endra","engkos",
    "erlan","ernest","fadli","faiq","fajri","fakhri","falah","farel","fatur",
    "fauzul","febrianto","feri","fernando","fikram","firdaus","fitrah","gerry",
    "ghani","ghozali","gunadi","gustav","habib","hafidh","haidar","hairul","halim",
    "hamdani","hanafi","handika","hanip","hardi","harjo","haryanto","hasyim",
    "hedi","hendrawan","herlambang","hermanto","hidayatullah","hisyam","huda",
    "idham","ifan","iksan","ilhamsyah","indrawan","irsan","ishak","iskandar",
    "isnan","jafar","jamil","jarwo","jauhari","jayadi","jefry","jibril","joni",
    "jufri","junaidi","juned","kahfi","kamaruddin","karim","kartono","kasim",
    "kelvin","khoirul","kholil","krisna","kurniawan","kusnadi","kusworo","latif",
    "lazuardi","lukman","luthfan","mahfud","makmur","mamat","mansyur","mardi",
    "masykur","mawardi","mikhael","mirza","muflih","mujahid","mukti","mulya",
    "munawir","murtadha","musthofa","nabhan","nafis","nanang","narendra","nasrul",
    "nazar","nizar","noval","novrizal","nugraha","nurhadi","oktavian","olan",
    "omar","opik","padli","pahlevi","pandji","parlin","pascal","perdana","permadi",
    "pieter","pramono","pranata","prayoga","prayogi","priyanto","puguh","rachmad",
    "rachman","radhitya","raffa","rahadian","rahardjo","raihan","rakhman","ramli",
    "rasyad","reyhan","refi","renaldi","ricardo","richard","ridha","rifai","rifat",
    "rinaldi","rizaldi","roberto","rochman","rofiq","romi","ronald","rosyid",
    "royhan","rusli","sabar","sadam","safar","sahrul","saldi","salim","samir",
    "saputra","sarwo","sasongko","satrio","sayuti","sidiq","sirojudin","sofian",
    "solehudin","subhan","sudarmono","sudirman","sugiarto","suhadi","sukri",
    "sulthan","sumanto","sunardi","supri","suryadi","sutanto","sutopo","syafiq",
    "syahril","syarif","tajudin","tarmizi","tegar","thoriq","tirto","tubagus",
    "umam","untung","usamah","vino","wafi","wahid","wardana","waskito","wiguna",
    "winarno","wiranto","yafi","yandi","yanuar","yayan","yogi","yoyok","yudianto",
    "yulianto","yunus","zacky","zahran","zulfikar","zulhilmi","zulkarnain",
    # --- perluasan leksikon: nama internasional ---
    "aaron","abraham","adrian","ahmet","alberto","aleksandr","alessandro","alfredo",
    "anders","andres","angelo","antonio","arjun","arnav","arthur","ashraf","aziz",
    "bilal","carlos","cesar","christopher","dario","dmitri","eduardo","emre","enzo",
    "esteban","fabio","farid","felipe","francisco","gabriel","giovanni","gustavo",
    "hakan","hamid","hassan","hector","hugo","igor","ismael","javed","jorge","juan",
    "julio","khaled","kumar","leonardo","lorenzo","luis","luiz","manuel","marcos",
    "mateo","matheus","mehmet","miguel","mustafa","nasser","nicolas","oleg","pablo",
    "pedro","philippe","rafael","ramesh","ricardo","rodrigo","salman","sanjay",
    "santiago","sergio","suresh","tariq","thiago","tomas","vijay","vladimir",
    "walid","yassin","youssef","zaid",
}

NAMA_WANITA = {
    "ade irma","adelia","adelina","adinda","afifah","aida","aisyah","aisha","alifia",
    "alisha","alisyah","aliya","almeera","alya","alyssa","amalia","amanda","amelia",
    "anastasia","andini","anggi","anggita","anggun","anisa","anita","anjani",
    "annisa","antika","anya","aprilia","apriliya","arini","arum","asih","asmara",
    "astri","astuti","aulia putri","aurel","aurelia","aurellia","ayu","ayudia",
    "ayunda","azizah","bela","bella","berta","bunga","cahaya","cantika","carla",
    "cathy","cecilia","chelsea","cherry","cindy","citra","clara","claudia",
    "cornelia","cut","dara","debby","dela","delia","della","denada","desi","dessy",
    "devi","dewi","diah","diana","dinda","dini","dita","dwi ayu","dyah","eka sari",
    "elisa","elizabeth","ella","elsa","elvira","emma","endah","erika","erna",
    "esther","eva","evi","fanny","farah","fadhilah","fatimah","fatma","febi",
    "felicia","fenny","fina","fira","firda","fitri","fitria","fitriani","gita",
    "grace","gracia","hana","hanna","hani","hasna","helen","helena","hesti","hilda",
    "ida","ika","ikke","indah","indira","intan","irma","isabella","isnaini",
    "isyana","jane","jasmine","jennifer","jenny","jessica","jihan","julia",
    "juliana","kartika","kayla","keisha","kesya","khofifah","kirana","kiran",
    "lala","laila","lailatul","larasati","latifah","laura","lestari","lidwina",
    "lilis","lina","linda","lisa","lulu","luna","lusi","maharani","maria","marina",
    "marissa","marlina","maya","megawati","melati","melisa","mila","mira","monica",
    "mutiara","nabila","nadia","nadine","nadya","nafisa","najwa","nanda sari",
    "natasha","nia","nida","nike","nila","nilam","ningsih","nisa","nita","nova",
    "novi","novita","nur aini","nurhayati","nurul","oktavia","olivia","patricia",
    "paula","permata","pipit","puji","puspita","putri","rachel","rahayu","rahma",
    "rahmawati","ratih","ratna","ratu","rena","reni","resti","ressy","retno","rina",
    "rini","risa","riska","rita","rosa","rosita","sabrina","safira","salma","salsa",
    "salsabila","sandra","santi","sari","sarah","sekar","selvi","septi","shinta",
    "sifa","silvia","sinta","siska","siti","sofia","sonya","stella","sulastri",
    "susi","syifa","tania","tari","tasya","tia","tiara","tika","tina","titi",
    "tri wahyuni","utami","vanessa","vania","vera","veronica","vina","violet",
    "wanda","widya","winda","wulan","yani","yanti","yayuk","yeni","yola","yulia",
    "yuni","yunita","yuli","yuliana","zahra","zaskia","zulfa","zulaikha",
    # --- perluasan leksikon: nama umum Indonesia ---
    "adhelia","adistya","afiqah","agustin","agustina","aini","aisha","alfiah",
    "aliyah","almira","alviana","amira","anastasya","andriani","anggraeni",
    "anggraini","anisah","apriani","ardelia","arifah","arinda","asmaul","asyifa",
    "aurora","azkia","balqis","berlian","bilqis","cahyani","callista","carissa",
    "charisa","chika","chintya","cinta","damayanti","darmawati","dea","deasy",
    "denisa","desiana","destiana","dhea","dhiya","diandra","dianti","dinar",
    "dinia","diva","dwita","elvina","emilia","enjelina","eriska","ervina",
    "fadhilah","fahira","faizah","fara","fardah","fauziah","febriana","febrianti",
    "fidya","fikriyah","fionna","gadis","gayatri","gina","hafizah","haliza",
    "hamidah","hanifah","hasanah","haura","hayati","herlina","hidayah","humaira",
    "ilma","imelda","inayah","irna","isnaeni","istiqomah","jamilah","janet",
    "jelita","juwita","kamila","karina","kartini","kesha","khadijah","khairunnisa",
    "khaleda","kholifah","lailatun","larasati","lativa","laurensia","lidya","lilik",
    "lintang","liza","luthfiah","maisyaroh","malika","manda","marfuah","mariam",
    "marlin","marsya","maulida","mawar","maylani","mega","meilani","melinda","meli",
    "mey","milea","miranda","mufidah","muslimah","nabilah","nadhira","nadila",
    "nafisah","naila","najma","nasywa","natalia","nayla","neira","nelly","niken",
    "nindy","ningrum","nirmala","nisrina","noviana","nurhaliza","nurjanah",
    "nurlaila","octavia","oktaviani","olla","priska","puspa","putriana","rachma",
    "radhiyah","rahmania","raisa","rani","rara","raudhatul","regina","renata",
    "reyna","riani","rika","rindu","risma","riyanti","rosalina","roslina","safitri",
    "sakinah","salsabil","samira","sania","santika","sarifah","sasa","sausan",
    "selvia","septiana","shafira","shalika","shania","sharon","shella","sherly",
    "shofia","sindi","sonia","suci","sulis","sumiati","susanti","syahira","syarifah",
    "tantri","triana","tuti","ulfa","umi","vanya","veny","vika","vivi","wahyuni",
    "wardah","wati","wenny","wilda","windi","wiwik","yasmin","yuliani","yulis",
    "yustika","zulfiana","zunita",
    # --- perluasan leksikon: nama internasional ---
    "alexandra","alice","amara","amina","angela","anika","anna","asma","aya",
    "ayesha","beatriz","bianca","camila","carmen","carolina","catalina","charlotte",
    "chloe","clarissa","daniela","elena","elif","emily","esra","fatima","fatma",
    "gabriela","hina","isabel","isabella","joana","josephine","kamala","karolina",
    "katarina","kumari","lara","leila","lucia","mariana","marta","meera","mona",
    "nour","olga","paola","pooja","priya","rania","rebecca","riya","sana","sara",
    "shreya","sophia","svetlana","valentina","valeria","victoria","yasmine",
    "zainab","zeynep",
}

# Gelar/sapaan yang menandakan gender tanpa perlu nama.
SAPAAN_PRIA = {"mr", "bang", "bung", "om", "pak", "bapak", "kang", "mas", "abang",
               "gus", "ust", "ustadz", "haji", "tuan"}
SAPAAN_WANITA = {"mrs", "ms", "miss", "bu", "ibu", "mbak", "teh", "neng", "tante",
                 "hajjah", "nyonya", "ummi", "bunda"}

# Sufiks morfologi Indonesia. Cukup andal untuk dipakai, TAPI hanya pada token
# yang panjangnya masuk akal sebagai nama (>= 6 huruf) supaya kata pendek acak
# tidak ikut tertangkap.
SUFIKS_WANITA = ("wati", "ningsih", "yanti", "asih", "arti", "anti", "iyah",
                 "awati", "ilah", "iyati",
                 # perluasan: sufiks pembentuk nama perempuan yang lazim
                 "sari", "ningrum", "ningtyas", "atun", "atin", "nisa",
                 "lestari", "wulandari", "damayanti")
SUFIKS_PRIA = ("uddin", "udin", "syah", "iyanto", "ianto", "anto", "wan",
               "man syah", "ullah", "urrahman",
               # perluasan: sufiks pembentuk nama laki-laki yang lazim
               "nugroho", "santoso", "kusumo", "wardana", "prasetyo", "purnomo",
               "susanto", "hartono", "budiono", "waluyo")

# Partikel patronimik Arab/Melayu -- penanda gender EKSPLISIT, bukan tafsiran.
# `bin` = "anak laki-laki dari", `binti`/`binte` = "anak perempuan dari".
# Dicek sebagai token utuh, jadi `bin` tidak ikut tertangkap di dalam `bintang`
# atau `robin`.
PARTIKEL_PRIA = {"bin"}
PARTIKEL_WANITA = {"binti", "binte", "bint"}

# Awalan nama Arab/Islami yang gendernya jelas.
AWALAN_PRIA = ("muhammad", "muhamad", "mohammad", "mohamad", "mochamad", "muh ",
               "abdul", "abdur", "abd ", "ahmad", "achmad", "syaikh")
AWALAN_WANITA = ("siti", "dewi ", "putri ", "sri ")

# Penanda akun toko/merek/instansi. Kalau salah satu muncul, gender TIDAK
# ditebak sama sekali -- entitas tidak punya gender, dan nama merek sering
# memuat kata yang kebetulan juga nama orang.
PENANDA_BISNIS = {
    "shop","store","toko","olshop","official","store id","jual","jualan","sewa",
    "rental","catering","catering","grosir","supplier","distributor","agen",
    "reseller","dropship","perumahan","properti","property","gold","diamond",
    "jewelry","boutique","butik","salon","clinic","klinik","apotek","hotel",
    "resto","restoran","cafe","kedai","warung","bakery","laundry","bengkel",
    "travel agent","tour travel","photography","studio","production","media",
    "channel","community","komunitas","group","grup","corp","company","pt",
    "cv","inc","ltd","id","promo","order","admin","cs","wa","gudang","brides",
    "wedding","event organizer","eo","percetakan","konveksi","pabrik",
}

# Simbol gender eksplisit -- ini SELF-IDENTIFICATION, bukan stereotip, jadi
# boleh dipakai dan diberi confidence tinggi.
SIMBOL_PRIA = "♂"     # ♂
SIMBOL_WANITA = "♀"   # ♀

# ---------------------------------------------------------------------------
# Lokasi
# ---------------------------------------------------------------------------
KOTA_ID = {
    "jakarta": "Jakarta", "jkt": "Jakarta", "jaksel": "Jakarta", "jaktim": "Jakarta",
    "jakbar": "Jakarta", "jakut": "Jakarta", "jakpus": "Jakarta",
    "depok": "Depok", "bekasi": "Bekasi", "tangerang": "Tangerang",
    "tangsel": "Tangerang Selatan", "bogor": "Bogor", "bandung": "Bandung",
    "cimahi": "Cimahi", "garut": "Garut", "cianjur": "Cianjur",
    "sukabumi": "Sukabumi", "tasikmalaya": "Tasikmalaya", "tasik": "Tasikmalaya",
    "cirebon": "Cirebon", "karawang": "Karawang", "purwakarta": "Purwakarta",
    "subang": "Subang", "sumedang": "Sumedang", "indramayu": "Indramayu",
    "kuningan": "Kuningan", "majalengka": "Majalengka", "banjar": "Banjar",
    "serang": "Serang", "cilegon": "Cilegon", "pandeglang": "Pandeglang",
    "lebak": "Lebak", "semarang": "Semarang", "solo": "Surakarta",
    "surakarta": "Surakarta", "salatiga": "Salatiga", "magelang": "Magelang",
    "klaten": "Klaten", "boyolali": "Boyolali", "sragen": "Sragen",
    "karanganyar": "Karanganyar", "wonogiri": "Wonogiri", "sukoharjo": "Sukoharjo",
    "tegal": "Tegal", "brebes": "Brebes", "pekalongan": "Pekalongan",
    "pemalang": "Pemalang", "purwokerto": "Purwokerto", "banyumas": "Banyumas",
    "cilacap": "Cilacap", "kebumen": "Kebumen", "purworejo": "Purworejo",
    "wonosobo": "Wonosobo", "temanggung": "Temanggung", "kendal": "Kendal",
    "demak": "Demak", "kudus": "Kudus", "jepara": "Jepara", "pati": "Pati",
    "rembang": "Rembang", "blora": "Blora", "grobogan": "Grobogan",
    "yogyakarta": "Yogyakarta", "jogja": "Yogyakarta", "jogjakarta": "Yogyakarta",
    "sleman": "Sleman", "bantul": "Bantul", "gunungkidul": "Gunungkidul",
    "kulonprogo": "Kulon Progo", "surabaya": "Surabaya", "sby": "Surabaya",
    "sidoarjo": "Sidoarjo", "gresik": "Gresik", "mojokerto": "Mojokerto",
    "malang": "Malang", "batu": "Batu", "kediri": "Kediri", "jember": "Jember",
    "madiun": "Madiun", "probolinggo": "Probolinggo", "pasuruan": "Pasuruan",
    "banyuwangi": "Banyuwangi", "blitar": "Blitar", "tuban": "Tuban",
    "lamongan": "Lamongan", "bojonegoro": "Bojonegoro", "jombang": "Jombang",
    "nganjuk": "Nganjuk", "ngawi": "Ngawi", "ponorogo": "Ponorogo",
    "trenggalek": "Trenggalek", "tulungagung": "Tulungagung", "situbondo": "Situbondo",
    "bondowoso": "Bondowoso", "lumajang": "Lumajang", "sumenep": "Sumenep",
    "pamekasan": "Pamekasan", "sampang": "Sampang", "bangkalan": "Bangkalan",
    "madura": "Madura", "bali": "Bali", "denpasar": "Denpasar", "ubud": "Ubud",
    "badung": "Badung", "gianyar": "Gianyar", "tabanan": "Tabanan",
    "singaraja": "Singaraja", "buleleng": "Buleleng", "lombok": "Lombok",
    "mataram": "Mataram", "sumbawa": "Sumbawa", "bima": "Bima", "kupang": "Kupang",
    "flores": "Flores", "maumere": "Maumere", "ende": "Ende", "labuan bajo": "Labuan Bajo",
    "medan": "Medan", "binjai": "Binjai", "pematangsiantar": "Pematangsiantar",
    "siantar": "Pematangsiantar", "tebingtinggi": "Tebing Tinggi",
    "tanjungbalai": "Tanjung Balai", "sibolga": "Sibolga", "padangsidimpuan": "Padang Sidimpuan",
    "toba": "Toba", "samosir": "Samosir", "karo": "Karo", "berastagi": "Berastagi",
    "padang": "Padang", "bukittinggi": "Bukittinggi", "payakumbuh": "Payakumbuh",
    "solok": "Solok", "pariaman": "Pariaman", "pekanbaru": "Pekanbaru",
    "dumai": "Dumai", "jambi": "Jambi", "palembang": "Palembang",
    "prabumulih": "Prabumulih", "lubuklinggau": "Lubuklinggau",
    "lampung": "Lampung", "bandarlampung": "Bandar Lampung", "metro": "Metro",
    "bengkulu": "Bengkulu", "batam": "Batam", "tanjungpinang": "Tanjung Pinang",
    "karimun": "Karimun", "bintan": "Bintan", "aceh": "Aceh",
    "banda aceh": "Banda Aceh", "lhokseumawe": "Lhokseumawe", "langsa": "Langsa",
    "sabang": "Sabang", "meulaboh": "Meulaboh", "pontianak": "Pontianak",
    "singkawang": "Singkawang", "ketapang": "Ketapang", "sintang": "Sintang",
    "banjarmasin": "Banjarmasin", "banjarbaru": "Banjarbaru",
    "martapura": "Martapura", "samarinda": "Samarinda", "balikpapan": "Balikpapan",
    "bontang": "Bontang", "tenggarong": "Tenggarong", "berau": "Berau",
    "tarakan": "Tarakan", "nunukan": "Nunukan", "palangkaraya": "Palangka Raya",
    "sampit": "Sampit", "pangkalanbun": "Pangkalan Bun", "makassar": "Makassar",
    "parepare": "Parepare", "palopo": "Palopo", "bone": "Bone", "gowa": "Gowa",
    "maros": "Maros", "bulukumba": "Bulukumba", "palu": "Palu", "poso": "Poso",
    "donggala": "Donggala", "kendari": "Kendari", "baubau": "Baubau",
    "kolaka": "Kolaka", "gorontalo": "Gorontalo", "manado": "Manado",
    "bitung": "Bitung", "tomohon": "Tomohon", "minahasa": "Minahasa",
    "ambon": "Ambon", "ternate": "Ternate", "tidore": "Tidore",
    "jayapura": "Jayapura", "sorong": "Sorong", "merauke": "Merauke",
    "manokwari": "Manokwari", "timika": "Timika", "biak": "Biak", "nabire": "Nabire",
    # --- singkatan kota yang lazim dipakai di bio ---
    # `sby`, `bdg`, `smg` dst. muncul nyata di data ("Visit our store 📍 Sby 📍 Malang").
    # Hanya singkatan yang tidak berbenturan dengan kata lain yang dimasukkan;
    # `mlg`/`plg` diambil karena bukan kata Indonesia maupun Inggris.
    "sby": "Surabaya", "bdg": "Bandung", "smg": "Semarang", "mlg": "Malang",
    "jgj": "Yogyakarta", "jog": "Yogyakarta", "plg": "Palembang",
    "mks": "Makassar", "bpn": "Balikpapan", "pnk": "Pontianak",
    "bjm": "Banjarmasin", "tng": "Tangerang", "bks": "Bekasi", "dpk": "Depok",
    "pku": "Pekanbaru", "mdn": "Medan", "pdg": "Padang",
}

# Nama kota yang JUGA kata umum atau nama orang. Tanpa penjaga, `bima` di
# "arya bima sakti wijanarko" tertebak kota Bima, dan `palu` (= martil) atau
# `batu` (= batu) tertangkap dari kalimat biasa.
#
# Untuk kunci-kunci ini, nama kota hanya diterima kalau teksnya JUGA memuat pin
# lokasi -- artinya orangnya memang sedang menyebut tempat, bukan kebetulan
# memakai kata itu. Kota berkunci panjang/khas (`surabaya`, `pekanbaru`) tidak
# butuh penjaga ini.
KOTA_AMBIGU = {
    "bima", "pati", "palu", "batu", "solo", "metro", "bone", "gowa", "karo",
    "toba", "ende", "banjar", "tuban", "blora", "demak", "kudus", "sabang",
    "jambi", "buleleng", "maros", "sampit", "berau", "langsa", "bitung",
}

# Provinsi Indonesia, nama Indonesia DAN Inggris. Ditaruh terpisah dari KOTA_ID
# karena hasilnya bukan kota: dipakai untuk menetapkan negara `ID` dan mengisi
# `city` dengan nama provinsinya, yang tetap lebih informatif daripada `unknown`.
#
# Ditambahkan setelah melihat data: "West Java", "Jawa Tengah", "Bandar Lampung"
# muncul di bio tapi tidak tertangkap karena kamus lama hanya berisi nama kota.
PROVINSI_ID = {
    "jawa barat": "Jawa Barat", "west java": "Jawa Barat",
    "jawa tengah": "Jawa Tengah", "central java": "Jawa Tengah",
    "jawa timur": "Jawa Timur", "east java": "Jawa Timur",
    "jawa": "Jawa", "java": "Jawa",
    "banten": "Banten", "lampung": "Lampung",
    "sumatera utara": "Sumatera Utara", "north sumatra": "Sumatera Utara",
    "sumatera barat": "Sumatera Barat", "west sumatra": "Sumatera Barat",
    "sumatera selatan": "Sumatera Selatan", "south sumatra": "Sumatera Selatan",
    "sumatra": "Sumatera", "sumatera": "Sumatera",
    "kalimantan timur": "Kalimantan Timur", "east kalimantan": "Kalimantan Timur",
    "kalimantan barat": "Kalimantan Barat", "west kalimantan": "Kalimantan Barat",
    "kalimantan selatan": "Kalimantan Selatan",
    "kalimantan tengah": "Kalimantan Tengah",
    "kalimantan utara": "Kalimantan Utara",
    "kalimantan": "Kalimantan", "borneo": "Kalimantan",
    "sulawesi selatan": "Sulawesi Selatan", "south sulawesi": "Sulawesi Selatan",
    "sulawesi utara": "Sulawesi Utara", "north sulawesi": "Sulawesi Utara",
    "sulawesi tengah": "Sulawesi Tengah", "sulawesi tenggara": "Sulawesi Tenggara",
    "sulawesi barat": "Sulawesi Barat", "sulawesi": "Sulawesi", "celebes": "Sulawesi",
    "nusa tenggara barat": "Nusa Tenggara Barat",
    "nusa tenggara timur": "Nusa Tenggara Timur",
    "papua barat": "Papua Barat", "west papua": "Papua Barat", "papua": "Papua",
    "maluku utara": "Maluku Utara", "maluku": "Maluku",
    "riau": "Riau", "kepulauan riau": "Kepulauan Riau",
    "bangka belitung": "Bangka Belitung", "babel": "Bangka Belitung",
}

# Nama negara / demonim -> kode ISO. Dicocokkan sebagai kata utuh.
NEGARA_KATA = {
    "indonesia": "ID", "indo": "ID", "nusantara": "ID",
    "malaysia": "MY", "kuala lumpur": "MY", "johor": "MY", "penang": "MY",
    "singapore": "SG", "singapura": "SG",
    "brunei": "BN", "thailand": "TH", "bangkok": "TH",
    "vietnam": "VN", "hanoi": "VN", "philippines": "PH", "filipina": "PH",
    "manila": "PH", "cambodia": "KH", "myanmar": "MM", "laos": "LA",
    "japan": "JP", "jepang": "JP", "tokyo": "JP", "osaka": "JP",
    "korea": "KR", "seoul": "KR", "china": "CN", "beijing": "CN",
    "shanghai": "CN", "hongkong": "HK", "hong kong": "HK", "taiwan": "TW",
    "india": "IN", "mumbai": "IN", "delhi": "IN",
    "pakistan": "PK", "bangladesh": "BD", "srilanka": "LK", "nepal": "NP",
    "saudi": "SA", "arab saudi": "SA", "mekkah": "SA", "makkah": "SA",
    "madinah": "SA", "jeddah": "SA", "riyadh": "SA",
    "uae": "AE", "dubai": "AE", "abu dhabi": "AE", "qatar": "QA", "doha": "QA",
    "kuwait": "KW", "oman": "OM", "bahrain": "BH", "yemen": "YE",
    "turkey": "TR", "turki": "TR", "istanbul": "TR",
    "egypt": "EG", "mesir": "EG", "cairo": "EG", "kairo": "EG",
    "morocco": "MA", "maroko": "MA", "algeria": "DZ", "tunisia": "TN",
    "nigeria": "NG", "kenya": "KE", "ghana": "GH", "south africa": "ZA",
    "australia": "AU", "sydney": "AU", "melbourne": "AU",
    "new zealand": "NZ", "usa": "US", "america": "US", "amerika": "US",
    "new york": "US", "california": "US", "los angeles": "US", "texas": "US",
    "canada": "CA", "toronto": "CA", "mexico": "MX", "meksiko": "MX",
    "brazil": "BR", "brasil": "BR", "argentina": "AR", "chile": "CL",
    "colombia": "CO", "peru": "PE", "venezuela": "VE",
    "england": "GB", "inggris": "GB", "london": "GB", "uk": "GB",
    "scotland": "GB", "ireland": "IE", "france": "FR", "perancis": "FR",
    "prancis": "FR", "paris": "FR", "germany": "DE", "jerman": "DE",
    "berlin": "DE", "netherlands": "NL", "belanda": "NL", "amsterdam": "NL",
    "belgium": "BE", "spain": "ES", "spanyol": "ES", "madrid": "ES",
    "barcelona": "ES", "italy": "IT", "italia": "IT", "roma": "IT",
    "milan": "IT", "portugal": "PT", "lisbon": "PT",
    "russia": "RU", "rusia": "RU", "moscow": "RU", "ukraine": "UA",
    "poland": "PL", "sweden": "SE", "norway": "NO", "denmark": "DK",
    "finland": "FI", "switzerland": "CH", "austria": "AT", "greece": "GR",
    "romania": "RO", "albania": "AL", "monaco": "MC",
}

# Aksara non-Latin yang memetakan cukup jelas ke satu negara.
# Aksara yang dipakai lintas banyak negara (ARABIC, CYRILLIC, LATIN) TIDAK
# dipakai untuk menebak negara -- Arab dipakai dari Maroko sampai Irak, jadi
# menebak satu negara dari situ akan salah lebih sering daripada benar.
AKSARA_NEGARA = {
    "THAI": "TH", "HANGUL": "KR", "HIRAGANA": "JP", "KATAKANA": "JP",
    "DEVANAGARI": "IN", "BENGALI": "BD", "KHMER": "KH", "LAO": "LA",
    "MYANMAR": "MM", "HEBREW": "IL", "GEORGIAN": "GE", "ARMENIAN": "AM",
}

# Kata bahasa Indonesia yang sangat khas. Kehadirannya menandakan penutur
# Indonesia -- sinyal LEMAH untuk negara (banyak diaspora), jadi confidence
# `low` dan hanya dipakai kalau tidak ada sinyal lain.
KATA_INDONESIA = {
    "aku","kamu","yang","gak","nggak","banget","udah","aja","doa","semoga",
    "insyaallah","alhamdulillah","terima kasih","makasih","sayang","cinta",
    "hidup","hati","rindu","kangen","teman","sahabat","keluarga","anak","ibu",
    "bapak","kakak","adik","jangan","selalu","tetap","semangat","sukses",
    "bahagia","syukur","rezeki","berkah","amin","aamiin","bismillah",
    "yuk","dong","deh","nih","sih","kok",
    "bisa","harus","sudah","belum","masih","lagi","juga","punya","mau","ingin",
}
# CATATAN: `follow`, `followback`, `salam`, `mari`, `kenal` SENGAJA tidak ada di
# sini meski sempat dimasukkan. `follow`/`followback` adalah kata Inggris yang
# dipakai global -- memakainya menandai `dell✨🌝` sebagai Indonesia tanpa dasar.
# Sisa kata di atas pun masih dipakai bahasa Melayu, jadi sinyal ini tetap
# `low` dan hanya dipakai kalau tidak ada bukti lokasi lain.

# ---------------------------------------------------------------------------
# Interest
# ---------------------------------------------------------------------------
INTEREST = {
    "music": ["music","musik","musisi","singer","penyanyi","song","lagu","band",
              "gitar","guitar","piano","drum","dj","rapper","hiphop","rock","pop",
              "vocalist","nyanyi","cover","karaoke","spotify","playlist","melodi",
              "konser","concert","koplo","dangdut","akustik"],
    "food": ["food","kuliner","makanan","masak","cooking","chef","resep","recipe",
             # perluasan: makanan/minuman yang muncul nyata di bio
             "keripik","kripik","camilan","cemilan","minuman","drink","boba",
             "juice","jus","roti","donat","pizza","ayam","sambal","frozen food",
             "foodie","kopi","coffee","cafe","kafe","bakery","catering","jajan",
             "snack","warung","resto","restoran","kue","cake","dessert","bakso",
             "seblak","mieayam","nasi","pedas","enak","lapar","makan"],
    "travel": ["travel","traveling","travelling","traveller","traveler","wisata",
               "jalan jalan","adventure","explore","exploring","backpacker","tour",
               "trip","liburan","holiday","vacation","pantai","beach","gunung",
               "mountain","hiking","camping","piknik","destinasi"],
    "sports": ["sport","olahraga","futsal","sepakbola","football","soccer","basket",
               "basketball","badminton","bulutangkis","running","lari","marathon",
               "cycling","sepeda","gowes","renang","swimming","atlet","athlete",
               "voli","volley","tenis","tennis","golf","boxing","tinju","mma",
               "silat","taekwondo","karate","skateboard","surfing"],
    "fitness": ["gym","fitness","workout","yoga","diet","healthy","sehat","muscle",
                "bodybuilding","kesehatan","nutrisi","kalori","olahraga pagi",
                "pilates","zumba","angkat beban","fitnes"],
    "beauty": ["beauty","makeup","make up","skincare","kosmetik","cosmetic","mua",
               "salon","kecantikan","glowing","skin","lipstik","lipstick","serum",
               "facial","perawatan","cantik","glow","bodycare","parfum","perfume"],
    "fashion": ["fashion","outfit","ootd","style","hijab","busana","baju","dress",
                "gaun","boutique","butik","thrift","thrifting","clothing","sepatu",
                "shoes","tas","bag","aksesoris","jilbab","kerudung","kebaya",
                "batik","streetwear","vintage"],
    "gaming": ["game","gaming","gamer","mobile legend","mlbb","pubg","free fire",
               "valorant","roblox","minecraft","esport","esports","streamer",
               "twitch","genshin","codm","dota","league of legends","noob","push rank",
               "mabar","gacha"],
    "business": ["bisnis","business","entrepreneur","usaha","umkm","olshop",
                 # perluasan: kosakata jual-beli yang lazim di bio
                 "produk","product","ready","stock","cod","harga","price","diskon",
                 "ongkir","checkout","preorder","open order","murah","promo",
                 "katalog","brand","official store","pesan","gratis ongkir",
                 "online shop","toko","shop","store","jual","jualan","reseller",
                 "dropship","dropshipper","marketing","trading","trader","investasi",
                 "investment","properti","property","saham","forex","affiliate",
                 "endorse","endorsement","promo","order","supplier","grosir",
                 "distributor","agen","rumah","perumahan","kredit","pinjaman"],
    "education": ["education","pendidikan","guru","teacher","dosen","mahasiswa",
                  "student","pelajar","sekolah","school","kampus","university",
                  "universitas","belajar","les","bimbel","beasiswa","skripsi",
                  "kuliah","sma","smp","smk","alumni","wisuda","ilmu","study"],
    "technology": ["tech","teknologi","programmer","developer","coding","koding",
                   "software","digital","gadget","komputer","laptop","ai",
                   "data","crypto","blockchain","nft","web","android","ios",
                   "python","javascript","hacker","cyber","robotik"],
    "religion": ["islam","muslim","muslimah","hijrah","dakwah","quran","alquran",
                 # perluasan: padanan Inggris yang muncul nyata di bio
                 "god","pray","prayer","blessed","faith","amen","bible","worship",
                 "grace","holy","imam","iman","taqwa","syahadat","tawakal",
                 "sholat","shalat","doa","ustadz","santri","pesantren","tauhid",
                 "sunnah","hadits","masjid","ramadan","ramadhan","puasa","umroh",
                 "haji","kristen","christian","jesus","yesus","tuhan","allah",
                 "gereja","church","hindu","buddha","katolik","pendeta","injil",
                 "bismillah","alhamdulillah","insyaallah","subhanallah","astaghfirullah"],
    "art": ["art","seni","artist","drawing","gambar","lukis","painting","design",
            "desain","sketsa","sketch","illustration","ilustrasi","kaligrafi",
            "craft","kerajinan","digital art","tattoo","tato","animasi"],
    "photography": ["photography","fotografi","photographer","fotografer","photo",
                    "foto","videografi","videographer","kamera","camera","editing",
                    "edit","lightroom","cinematic","potret","prewedding"],
    "automotive": ["otomotif","automotive","mobil","motor","car","bike","racing",
                   "modifikasi","bengkel","touring","balap","drag","offroad",
                   "vespa","harley","truck","truk"],
    "entertainment": ["film","movie","cinema","bioskop","drama","drakor","anime",
                      "manga","kpop","kdrama","series","netflix","komedi","comedy",
                      "lucu","hiburan","meme","tiktok","youtube","selebgram",
                      "artis","idol","fanbase","wibu","otaku"],
    "parenting": ["parenting","ibu","bunda","mama","mami","anak","bayi","baby",
                  # perluasan: `mom` sendiri sebelumnya tidak ada, hanya `momlife`
                  "mom","moms","mommy","momy","mamah","mother","bumil","busui",
                  "toddler","newborn","anakku",
                  "kids","keluarga","family","momlife","hamil","melahirkan",
                  "asi","balita","ayah","papa"],
    "pets": ["pet","kucing","cat","anjing","dog","hewan","peliharaan","aquarium",
             "burung","reptile","kelinci","hamster","ikan","meong","anabul"],
}

# Emoji -> interest. Hanya emoji yang maknanya langsung, bukan dekoratif.
EMOJI_INTEREST = {
    "⚽": "sports", "🏀": "sports", "🏈": "sports", "⚾": "sports", "🎾": "sports",
    "🏐": "sports", "🏸": "sports", "🥊": "sports", "🏆": "sports", "🚴": "sports",
    "🏃": "sports", "🏊": "sports", "⛳": "sports",
    "🎮": "gaming", "🕹": "gaming", "👾": "gaming",
    "🎵": "music", "🎶": "music", "🎤": "music", "🎸": "music", "🎹": "music",
    "🥁": "music", "🎧": "music", "🎼": "music",
    "📷": "photography", "📸": "photography", "🎥": "photography", "🎬": "entertainment",
    "🍔": "food", "🍕": "food", "🍜": "food", "🍲": "food", "🍰": "food",
    "☕": "food", "🍱": "food", "🥘": "food", "🧁": "food", "🍩": "food",
    "✈": "travel", "🌍": "travel", "🗺": "travel", "🏝": "travel", "⛰": "travel",
    "🏔": "travel", "🎒": "travel",
    "💄": "beauty", "💅": "beauty",
    "👗": "fashion", "👠": "fashion", "👜": "fashion", "🧕": "fashion",
    "💪": "fitness", "🏋": "fitness", "🧘": "fitness",
    "💻": "technology", "🖥": "technology", "⌨": "technology", "🤖": "technology",
    "📱": "technology",
    "📚": "education", "📖": "education", "🎓": "education", "✏": "education",
    "🕌": "religion", "☪": "religion", "✝": "religion", "⛪": "religion",
    "🙏": "religion", "📿": "religion",
    "🎨": "art", "🖌": "art", "🖍": "art",
    "🚗": "automotive", "🏍": "automotive", "🚙": "automotive", "🏎": "automotive",
    "🐱": "pets", "🐶": "pets", "🐾": "pets", "🐈": "pets", "🐕": "pets",
    "💰": "business", "💵": "business", "📈": "business", "🛒": "business",
    "🛍": "business", "💼": "business",
    "👶": "parenting", "🍼": "parenting",
    # perluasan emoji -- hanya yang maknanya langsung, bukan dekoratif
    "⚕": "fitness", "🩺": "fitness", "🥗": "fitness", "🏋": "fitness",
    "🍳": "food", "🥤": "food", "🧋": "food", "🍟": "food", "🍦": "food",
    "🎯": "sports", "🥇": "sports", "🏅": "sports", "🤸": "sports",
    "🎹": "music", "🎺": "music", "🪕": "music", "🎻": "music",
    "🖼": "art", "✒": "art", "🧵": "art", "🪡": "art",
    "📝": "education", "🏫": "education", "🔬": "education", "🧪": "education",
    "🕋": "religion", "📖": "religion", "🤲": "religion",
    "🛵": "automotive", "🚚": "automotive", "⛽": "automotive",
    "🐟": "pets", "🐰": "pets", "🦜": "pets",
    "🧳": "travel", "🗼": "travel", "🚆": "travel",
    "👒": "fashion", "🕶": "fashion",
    "🧴": "beauty", "🪞": "beauty", "💇": "beauty",
    "🎞": "entertainment", "🍿": "entertainment", "📺": "entertainment",
    "📊": "business", "🧾": "business", "🏪": "business",
}

# Urutan tetap untuk penelusuran, supaya `alasan` yang dilaporkan tidak
# berubah-ubah antar-proses (iterasi `set` string tidak stabil di Python).
KATA_INDONESIA_URUT = tuple(sorted(KATA_INDONESIA))

_RE_BUKAN_HURUF = re.compile(r"[^a-z\s]+")
_RE_SPASI = re.compile(r"\s+")
_RE_ULANG = re.compile(r"(.)\1{1,}")
_RE_BENDERA = re.compile("[\U0001F1E6-\U0001F1FF]{2}")
# Pin lokasi. Kehadirannya berarti orangnya SENGAJA menyatakan tempat, jadi
# nama tempat yang cocok di teks yang sama bukan kebetulan. Dipakai untuk
# menaikkan confidence, bukan untuk menebak tempatnya sendiri.
_PIN_LOKASI = ("\U0001F4CD", "\U0001F4CC", "\U0001F3E0", "\U0001F30F")
_RE_PEMISAH = re.compile(r"[._\-|/\\+]+")


def _normalisasi(teks: str | None) -> str:
    """Lipat unicode bergaya ke ASCII huruf kecil."""
    if not teks:
        return ""
    t = unicodedata.normalize("NFKD", teks)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    t = _RE_BUKAN_HURUF.sub(" ", t)
    return _RE_SPASI.sub(" ", t).strip()


def _token(*teks: str | None) -> list[str]:
    """Pecah nama/handle jadi token yang layak dicocokkan ke kamus.

    Tiga langkah, masing-masing menjawab bentuk data yang benar-benar ada:

      1. Pemisah `. _ - | /` diganti spasi -> `na.bilaaa09_` jadi dua token.
      2. Angka dibuang            -> `summmmmmm17`, `mariadi.21`.
      3. Huruf berulang diruntuhkan -> `bilaaa` jadi `bila`, `summmmmmm` jadi `sum`.

    Bentuk asli DAN bentuk yang diruntuhkan dua-duanya dikembalikan, karena
    meruntuhkan bisa merusak nama yang memang bergandeng dua huruf
    (`anna` -> `ana`, `hanna` -> `hana`) -- keduanya dicoba, yang cocok dipakai.
    """
    keluar: list[str] = []
    for t in teks:
        if not t:
            continue
        dasar = _normalisasi(_RE_PEMISAH.sub(" ", t))
        for tok in dasar.split():
            if len(tok) < 2:
                continue
            keluar.append(tok)
            runtuh = _RE_ULANG.sub(r"\1", tok)
            if runtuh != tok and len(runtuh) >= 2:
                keluar.append(runtuh)
    return keluar


def _cocok_kata(haystack: str, kata: str) -> bool:
    """Cocok sebagai kata utuh, bukan substring."""
    if " " in kata:
        return kata in haystack
    return re.search(rf"\b{re.escape(kata)}\b", haystack) is not None


@dataclass
class Terkaan:
    nilai: str
    confidence: str  # high | medium | low
    alasan: str = ""


@dataclass
class HasilFollower:
    gender: Terkaan
    negara: Terkaan
    kota: Terkaan | None
    interests: list[Terkaan] = field(default_factory=list)


_KUAT = {"high": 3, "medium": 2, "low": 1}


# ---------------------------------------------------------------------------
# Gender
# ---------------------------------------------------------------------------
def _tampak_bisnis(full_name: str | None, bio: str | None,
                   username: str | None, social_links: str | None = None) -> bool:
    """Akun toko/merek/instansi, bukan orang.

    Gender tidak berlaku untuk entitas, dan nama merek sering memuat kata yang
    kebetulan juga nama orang -- `LUNARA GOLD & DIAMOND BALI` tertebak
    perempuan lewat `luna`, `linasroti` lewat `lina`. Menandainya lebih dulu
    membuat seluruh aturan gender dilewati, jadi hasilnya `unknown`.
    """
    teks = _normalisasi(f"{full_name or ''} {bio or ''} {username or ''} "
                        f"{social_links or ''}")
    return any(_cocok_kata(teks, k) for k in PENANDA_BISNIS)


def _bukti_gender(full_name: str | None, username: str | None,
                  bio: str | None,
                  social_links: str | None = None) -> list[tuple[str, str, str]]:
    """Kumpulkan SEMUA bukti gender. Kembalikan (nilai, confidence, alasan)."""
    if _tampak_bisnis(full_name, bio, username, social_links):
        return []

    bukti: list[tuple[str, str, str]] = []
    mentah = f"{full_name or ''} {bio or ''}"

    # 1. Simbol gender eksplisit -- self-identification, bukan tafsiran.
    if SIMBOL_PRIA in mentah:
        bukti.append(("male", "high", "simbol ♂"))
    if SIMBOL_WANITA in mentah:
        bukti.append(("female", "high", "simbol ♀"))

    tok_nama = _token(full_name)
    tok_user = _token(username)

    # 2. Sapaan -- kuat, dan tidak bergantung kamus nama.
    for t in tok_nama + tok_user:
        if t in SAPAAN_PRIA:
            bukti.append(("male", "medium", f"sapaan '{t}'"))
        if t in SAPAAN_WANITA:
            bukti.append(("female", "medium", f"sapaan '{t}'"))

    # 2b. Partikel patronimik -- eksplisit, jadi confidence `high`.
    #     Diperiksa lebih dulu supaya `Ahmad binti Fatimah` tidak tertebak
    #     laki-laki hanya karena token pertamanya kebetulan nama laki-laki.
    for t in tok_nama + tok_user:
        if t in PARTIKEL_WANITA:
            bukti.append(("female", "high", f"partikel '{t}'"))
        elif t in PARTIKEL_PRIA:
            bukti.append(("male", "high", f"partikel '{t}'"))

    # 3. Awalan Arab/Islami pada nama lengkap.
    n_norm = _normalisasi(full_name)
    for aw in AWALAN_PRIA:
        if n_norm.startswith(aw.strip()):
            bukti.append(("male", "medium", f"awalan '{aw.strip()}'"))
            break
    for aw in AWALAN_WANITA:
        if n_norm.startswith(aw.strip()):
            bukti.append(("female", "medium", f"awalan '{aw.strip()}'"))
            break

    # 4. Kamus nama. Token PERTAMA full_name paling kuat; token lain dan token
    #    username lebih lemah karena posisinya tidak menjamin itu nama depan.
    if tok_nama:
        d = tok_nama[0]
        if d in NAMA_PRIA:
            bukti.append(("male", "medium", f"nama depan '{d}'"))
        elif d in NAMA_WANITA:
            bukti.append(("female", "medium", f"nama depan '{d}'"))

    for t in tok_nama[1:] + tok_user:
        if t in NAMA_PRIA:
            bukti.append(("male", "low", f"token '{t}'"))
        elif t in NAMA_WANITA:
            bukti.append(("female", "low", f"token '{t}'"))

    # 5. Sufiks morfologi Indonesia. Hanya pada token >= 6 huruf supaya kata
    #    pendek acak (`wan`, `anti`) tidak ikut tertangkap.
    for t in tok_nama + tok_user:
        if len(t) < 6:
            continue
        if any(t.endswith(s) for s in SUFIKS_WANITA):
            bukti.append(("female", "medium", f"sufiks pada '{t}'"))
        elif any(t.endswith(s) for s in SUFIKS_PRIA):
            bukti.append(("male", "medium", f"sufiks pada '{t}'"))

    # CATATAN -- ATURAN YANG SENGAJA DIBUANG
    #
    # Versi sebelumnya mencocokkan nama kamus sebagai AWALAN token panjang
    # (`yayukprasetyaa` -> `yayuk`). Aturan itu DIBUANG setelah diuji pada data
    # nyata: dalam bahasa Indonesia dan bahasa Roman, nama panjang sangat sering
    # berawalan sama dengan nama pendek bergender LAWAN.
    #
    #     agustina  diawali `agus`   -> tertebak male,   padahal perempuan
    #     septian   diawali `septi`  -> tertebak female,  padahal laki-laki
    #     mariadi   diawali `maria`  -> tertebak female,  padahal laki-laki
    #     aurelio   diawali `aurel`  -> tertebak female,  padahal laki-laki
    #
    # Aturan itu menyumbang ~188 deteksi tambahan, tapi sebagian besar salah.
    # Menukar 188 jawaban salah dengan 188 `unknown` adalah pertukaran yang
    # benar: `unknown` jujur, tebakan salah menyesatkan dan tidak terdeteksi
    # di hilir.

    return bukti


def _putuskan_gender(bukti: list[tuple[str, str, str]]) -> Terkaan:
    """Pilih satu jawaban dari kumpulan bukti.

    Aturan konflik: kalau bukti TERKUAT untuk pria dan wanita sama kuat,
    hasilnya `unknown`. Nama seperti `alisyah` bisa memicu sinyal ke dua arah,
    dan memilih salah satu hanya karena urutan pemeriksaan akan menghasilkan
    angka yang tidak bisa dipertanggungjawabkan.
    """
    if not bukti:
        return Terkaan("unknown", "high", "tidak ada sinyal gender")

    terbaik: dict[str, tuple[int, str, str]] = {}
    for nilai, conf, alasan in bukti:
        skor = _KUAT[conf]
        if nilai not in terbaik or skor > terbaik[nilai][0]:
            terbaik[nilai] = (skor, conf, alasan)

    if "male" in terbaik and "female" in terbaik:
        m, f = terbaik["male"][0], terbaik["female"][0]
        if m == f:
            return Terkaan("unknown", "high",
                           f"bukti bertentangan sama kuat ({terbaik['male'][2]} "
                           f"vs {terbaik['female'][2]})")
        menang = "male" if m > f else "female"
    else:
        menang = next(iter(terbaik))

    skor, conf, alasan = terbaik[menang]
    return Terkaan(menang, conf, alasan)


def tebak_gender(full_name: str | None, username: str | None = None,
                 bio: str | None = None,
                 social_links: str | None = None) -> Terkaan:
    """Turunkan gender dari nama, username, dan bio.

    Berbeda dari versi awal yang hanya melirik username kalau `full_name`
    kosong: di data nyata banyak `full_name` berisi sampah (`"Bitch"`, `";)"`,
    `"k"`) sementara username justru memuat nama asli (`yayukprasetyaa`).
    Keduanya sekarang selalu dibaca, lalu bukti terkuat yang menang.
    """
    return _putuskan_gender(_bukti_gender(full_name, username, bio, social_links))


# ---------------------------------------------------------------------------
# Lokasi
# ---------------------------------------------------------------------------
def _negara_dari_bendera(teks: str) -> str | None:
    """Emoji bendera -> kode ISO-3166 alfa-2.

    Sepasang Regional Indicator memetakan satu-ke-satu ke kode negara, jadi ini
    satu-satunya sinyal lokasi yang benar-benar tidak ambigu.
    """
    m = _RE_BENDERA.search(teks or "")
    if not m:
        return None
    return "".join(chr(ord(c) - 0x1F1E6 + ord("A")) for c in m.group())


def _aksara(teks: str) -> set[str]:
    """Aksara non-Latin yang muncul di teks."""
    hasil = set()
    for ch in teks or "":
        if ord(ch) < 128:
            continue
        try:
            nama = unicodedata.name(ch)
        except ValueError:
            continue
        for kunci in AKSARA_NEGARA:
            if nama.startswith(kunci) or f" {kunci} " in nama:
                hasil.add(kunci)
    return hasil


def tebak_lokasi(full_name: str | None, bio: str | None,
                 username: str | None = None,
                 social_links: str | None = None) -> tuple[Terkaan, Terkaan | None]:
    """Kembalikan (negara, kota). Kota bisa None kalau tidak diketahui.

    Urutan bukti dari yang paling kuat:
      1. emoji bendera        -> high   (pemetaan teknis, tanpa tafsiran)
      2. nama kota Indonesia  -> medium (menyiratkan negara ID juga)
      3. nama negara/kota dunia -> medium
      4. aksara khas          -> low    (hanya aksara yang jelas satu negara)
      5. kata bahasa Indonesia -> low   (penutur ID, tapi bisa diaspora)
    """
    mentah = f"{full_name or ''} {bio or ''} {username or ''} {social_links or ''}"
    teks = _normalisasi(mentah)

    kode_bendera = _negara_dari_bendera(mentah)

    # Pin lokasi dipakai sebagai PENGUAT, bukan sebagai penebak tempat.
    ada_pin = any(pin in mentah for pin in _PIN_LOKASI)

    # 2. kota Indonesia
    for kunci, kota in KOTA_ID.items():
        if kunci in KOTA_AMBIGU and not ada_pin:
            continue          # butuh pin lokasi; lihat catatan di KOTA_AMBIGU
        if _cocok_kata(teks, kunci):
            conf_kota = "high" if ada_pin else "medium"
            return (
                Terkaan(kode_bendera or "ID",
                        "high" if (kode_bendera or ada_pin) else "medium",
                        f"kota '{kunci}'" + (" + pin lokasi" if ada_pin else "")),
                Terkaan(kota, conf_kota,
                        f"kata '{kunci}'" + (" + pin lokasi" if ada_pin else "")),
            )

    # 2b. provinsi Indonesia -- lebih kasar dari kota, tapi jauh lebih baik
    #     daripada `unknown`. Dicek SETELAH kota supaya "Bandung, Jawa Barat"
    #     tetap menghasilkan kota Bandung, bukan provinsi.
    for kunci, prov in PROVINSI_ID.items():
        if _cocok_kata(teks, kunci):
            return (
                Terkaan(kode_bendera or "ID",
                        "high" if (kode_bendera or ada_pin) else "medium",
                        f"provinsi '{kunci}'"),
                Terkaan(prov, "medium" if ada_pin else "low", f"provinsi '{kunci}'"),
            )

    # 3. negara / kota dunia
    for kunci, kode in NEGARA_KATA.items():
        if _cocok_kata(teks, kunci):
            return (
                Terkaan(kode_bendera or kode,
                        "high" if kode_bendera else "medium", f"kata '{kunci}'"),
                None,
            )

    if kode_bendera:
        return Terkaan(kode_bendera, "high", "emoji bendera"), None

    # 4. aksara khas satu negara
    #
    # Ditelusuri mengikuti urutan AKSARA_NEGARA (dict, urutannya tetap), BUKAN
    # dengan mengiterasi himpunan hasil `_aksara()`. Urutan iterasi `set` string
    # di Python bergantung pada hash yang diacak tiap proses, jadi teks yang
    # memuat DUA aksara berbeda akan menghasilkan negara yang berbeda antar-run.
    # Itu sempat terjadi dan membuat jumlah baris L2 berubah pada rerun --
    # melanggar idempotensi tanpa ada perubahan data sama sekali.
    ditemukan = _aksara(mentah)
    for kunci, kode in AKSARA_NEGARA.items():
        if kunci in ditemukan:
            return Terkaan(kode, "low", f"aksara {kunci.lower()}"), None

    # 5. kata bahasa Indonesia -- sinyal paling lemah, dipakai terakhir.
    #    Diurutkan supaya `alasan` yang dilaporkan juga stabil antar-run.
    for kata in KATA_INDONESIA_URUT:
        if _cocok_kata(teks, kata):
            return Terkaan("ID", "low", f"kata bahasa Indonesia '{kata}'"), None

    return Terkaan("unknown", "high", "tidak ada sinyal lokasi"), None


# ---------------------------------------------------------------------------
# Interest
# ---------------------------------------------------------------------------
def tebak_interest(bio: str | None, full_name: str | None = None,
                   username: str | None = None,
                   social_links: str | None = None) -> list[Terkaan]:
    """Kembalikan SEMUA kategori yang cocok, bukan hanya satu.

    Urutan kekuatan bukti: bio (medium) > emoji (medium) > nama (low) >
    username (low). Bio memang tempat orang menyebutkan minatnya; username
    sering hanya kebetulan mengandung kata.
    """
    hasil: list[Terkaan] = []
    t_bio = _normalisasi(bio)
    t_nama = _normalisasi(full_name)
    t_user = _normalisasi(username)
    # Tautan eksternal (linktree, toko, portofolio) sering menyebut bidangnya.
    # Bukti LEMAH: domain bisa saja tidak berhubungan dengan minat pemiliknya.
    t_link = _normalisasi(social_links)
    mentah = f"{full_name or ''} {bio or ''}"

    # emoji -> kategori
    emoji_hit: dict[str, str] = {}
    for ch in mentah:
        kat = EMOJI_INTEREST.get(ch)
        if kat and kat not in emoji_hit:
            emoji_hit[kat] = ch

    for kategori, kata_kunci in INTEREST.items():
        # Panjang minimum 3 huruf. Kata dua huruf terlalu mudah bertabrakan
        # lintas bahasa -- `wa` (WhatsApp) menabrak kata sambung Arab pada
        # "Allahumma Sholli wa Sallim" dan menandainya sebagai bisnis.
        k = next((x for x in kata_kunci
                  if len(x) >= 3 and t_bio and _cocok_kata(t_bio, x)), None)
        if k:
            hasil.append(Terkaan(kategori, "medium", f"bio '{k}'"))
            continue
        if kategori in emoji_hit:
            hasil.append(Terkaan(kategori, "medium",
                                 f"emoji '{emoji_hit[kategori]}'"))
            continue
        k = next((x for x in kata_kunci if t_nama and _cocok_kata(t_nama, x)), None)
        if k:
            hasil.append(Terkaan(kategori, "low", f"nama '{k}'"))
            continue
        # username: hanya kata kunci >= 5 huruf, supaya potongan handle pendek
        # tidak memicu kategori secara kebetulan.
        k = next((x for x in kata_kunci
                  if len(x) >= 5 and t_user and _cocok_kata(t_user, x)), None)
        if k:
            hasil.append(Terkaan(kategori, "low", f"username '{k}'"))
            continue
        k = next((x for x in kata_kunci
                  if len(x) >= 5 and t_link and _cocok_kata(t_link, x)), None)
        if k:
            hasil.append(Terkaan(kategori, "low", f"tautan '{k}'"))

    return hasil


def analisis_follower(
    full_name: str | None,
    bio: str | None,
    username: str | None = None,
    social_links: str | None = None,
) -> HasilFollower:
    """Jalankan seluruh aturan untuk satu follower.

    `social_links` ikut dibaca sejak enrichment profil Instagram: tautan
    eksternal tersedia untuk 67 follower dan sering menyebut kota atau bidang
    usaha. Bobotnya paling rendah -- domain bisa saja tidak berhubungan dengan
    pemiliknya.
    """
    negara, kota = tebak_lokasi(full_name, bio, username, social_links)
    return HasilFollower(
        gender=tebak_gender(full_name, username, bio, social_links),
        negara=negara,
        kota=kota,
        interests=tebak_interest(bio, full_name, username, social_links),
    )


# ---------------------------------------------------------------------------
# Skor kualitas
# ---------------------------------------------------------------------------
def skor_kualitas(followers: list[dict]) -> dict[str, int | None]:
    """Tiga skor 0..100 dari sifat follower yang TERUKUR, bukan dari inferensi.

        follower_quality  -- porsi follower yang tampak berisi:
                             punya nama, tidak privat, punya bio/foto.
        authenticity      -- porsi yang TIDAK berciri bot: following jauh
                             melebihi followers (rasio > 5) dan followers sangat
                             rendah -- pola akun massal.
        audience_quality  -- rata-rata keduanya.

    Mengembalikan None untuk skor yang sinyalnya tidak tersedia, supaya 0 tidak
    salah dibaca sebagai "buruk" padahal artinya "tidak diketahui". Instagram
    tidak mengirim followers/following, jadi `authenticity` None untuk seluruh
    akun Instagram.
    """
    if not followers:
        return {"follower_quality_score": None, "authenticity_score": None,
                "audience_quality_score": None}

    n = len(followers)
    berisi = sum(
        1 for f in followers
        if (f.get("full_name") or f.get("username"))
        and not f.get("is_private")
        and (f.get("bio") or f.get("profile_pic_url"))
    )
    fq = round(berisi * 100 / n)

    punya_angka = [f for f in followers
                   if f.get("followers_count") is not None
                   and f.get("following_count") is not None]
    if punya_angka:
        wajar = 0
        for f in punya_angka:
            fol = f.get("followers_count") or 0
            ing = f.get("following_count") or 0
            if not (ing > 5 * max(fol, 1) and fol < 100):
                wajar += 1
        au = round(wajar * 100 / len(punya_angka))
    else:
        au = None

    aq = round((fq + au) / 2) if au is not None else fq
    return {"follower_quality_score": fq, "authenticity_score": au,
            "audience_quality_score": aq}
