"""Creator Classification -- atribut KREATOR dari bukti milik kreator sendiri.

    Gender · Age · Role · Category -> Subcategory · Content Style · Personality

Modul MURNI: tidak ada koneksi database, tidak ada panggilan jaringan, tidak
ada LLM, tidak ada acak. Input yang sama selalu menghasilkan output yang sama.
Pembaca data ada di `creator_classification_dryrun.py`; modul ini hanya
menerima `CreatorInput` dan `Taxonomy`.

============================================================================
GENDER DAN UMUR -- TIDAK DIHITUNG ULANG DI SINI
============================================================================
Keduanya sudah production (asset `creator_gender`, `creator_age`). Modul ini
hanya MEMANGGIL fungsi yang sama, dengan urutan prioritas yang sama:

    gender  manual -> roster (`influencer_gender` 0/1) -> name_inference -> Unknown
            (`creator_gender_inference.pilih_gender`)
    umur    manual -> bio_self_declared -> roster_ktp (NIK) -> Unknown
            (`creator_age_inference.ekstrak_umur`, `creator_age_nik.umur_dari_nik`)

Logic gender/umur di repo riset (Autometric_research, `run-t2-enrichment`)
menebak FOLLOWER lewat LLM. Itu atribut AUDIENS dan sengaja tidak dipakai.

============================================================================
BUKTI DAN BOBOT
============================================================================
    declared category (IG businessCategoryName)      3.0   kuat
    bio                                              2.0   kuat (+0.5 per istilah
                                                           berbeda tambahan, maks 3.0)
    topik berulang di >= 2 post                      2.0   kuat/sedang
    topik di 1 post                                  1.0   sedang
    hashtag saja                                     0.5   pendukung (maks 1.0)
    display name / username                          0.25  pendukung saja

Nama akun TIDAK PERNAH cukup sendirian: bobot nama hanya dihitung untuk label
yang sudah punya bukti lain. Hasil dipilih kalau skor tertinggi >= 2.0 DAN
unggul >= 1.0 atas kandidat kedua; selain itu Unknown dengan alasan tertulis.
Confidence: `high` kalau skor >= 4.0 dari >= 2 sumber independen, selain itu
`medium`. Unknown adalah jawaban yang sah.

============================================================================
TAXONOMY
============================================================================
`public.kol_categories` adalah satu-satunya sumber taxonomy kategori. Kategori
dan subkategori adalah DUA hasil terpisah, masing-masing satu baris tabel itu
(`TaxRef`: id, name, code, level, parent_id):

    category     baris level='category', parent_id NULL, salah satu dari
                 14 kode canonical (CATEGORY_TARGETS)
    subcategory  baris level='sub_category' dengan parent_id == category.id,
                 atau None kalau buktinya tidak cukup

Nama tampilan selalu `kol_categories.name`; kode hanya identifier internal
(leksikon dikunci per kode). Relasi induk-anak selalu dari `parent_id`, tidak
pernah dari prefix kode. `Taxonomy` menolak leksikon yang menunjuk baris yang
tidak ada, dan `validate()` memeriksa setiap hasil terhadap baris DB-nya.

Role adalah label PERANTARA (Creator, Media, Politician/Public Official, ...),
bukan kolom dan bukan taxonomy. Untuk Politician/Public Official yang dinilai
hanya PERAN yang terlihat dari bukti (jabatan, akun resmi) -- tidak pernah
afiliasi politik, preferensi, ideologi, maupun pilihan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import audience_inference as _A
import creator_classification_lexicon as L
import creator_gender_inference as _G
from creator_age_inference import SUMBER_MANUAL as AGE_SOURCE_MANUAL
from creator_age_inference import ekstrak_umur
from creator_age_nik import nik_aktif, umur_dari_nik

# ---------------------------------------------------------------------------
# Bobot dan ambang
# ---------------------------------------------------------------------------
W_DECLARED = 3.0
W_BIO = 2.0
W_BIO_EXTRA_TERM = 0.5      # per istilah berbeda tambahan di bio
W_BIO_MAX = 3.0             # tetap di bawah declared category
W_REPEATED_POSTS = 2.0
W_SINGLE_POST = 1.0
W_HASHTAG = 0.5
W_HASHTAG_CAP = 1.0
W_NAME = 0.25

MIN_SCORE = 2.0
MIN_MARGIN = 1.0
HIGH_SCORE = 4.0

STYLE_MIN_POSTS = 3
STYLE_MIN_HITS = 2
STYLE_MIN_RATIO = 0.3

PERSONALITY_MIN_POSTS = 5
PERSONALITY_MIN_HITS = 3
PERSONALITY_MIN_RATIO = 0.4

#: Bentuk kode kol_categories (`FOD`, `FOD.CUL`, `TEC.SAAS`) -- tidak boleh
#: muncul sebagai nama kategori/subkategori di hasil.
_CODE_LIKE = re.compile(r"^[A-Z]{2,5}(\.[A-Z]{2,5})?$")

SOURCE_DECLARED = "declared_category"
SOURCE_BIO = "bio"
SOURCE_POSTS = "posts"
SOURCE_HASHTAG = "hashtags"
SOURCE_NAME = "name"
SOURCE_ROSTER = "roster"
SOURCE_ACCOUNT_FLAG = "is_business"

#: Sumber yang dihitung "independen" untuk confidence tinggi.
_STRONG_SOURCES = frozenset({SOURCE_DECLARED, SOURCE_BIO, SOURCE_POSTS})


# ---------------------------------------------------------------------------
# Tipe data
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Post:
    caption: str | None = None
    hashtags: tuple[str, ...] = ()
    media_type: str | None = None
    video_duration: float | None = None
    source: str = "l1_silver.unified_post"


@dataclass(frozen=True)
class CreatorInput:
    kol_id: str
    platform: str | None = None
    username: str | None = None
    display_name: str | None = None
    bio: str | None = None
    declared_category: str | None = None
    is_business: bool | None = None
    roster_categories: tuple[str, ...] = ()
    roster_gender: str | None = None
    nik: str | None = None                  # dipakai lalu dibuang; tidak pernah masuk evidence
    manual_gender: str | None = None
    manual_age: int | None = None
    posts: tuple[Post, ...] = ()


@dataclass(frozen=True)
class Evidence:
    source: str
    label: str
    weight: float
    detail: str = ""


@dataclass(frozen=True)
class TaxRef:
    """Satu baris `public.kol_categories`, apa adanya dari DB."""
    id: str
    name: str
    code: str | None
    level: str
    parent_id: str | None

    def as_dict(self) -> dict:
        """Bentuk keluaran: nama DB + kode sebagai identifier, tanpa digabung."""
        return {"id": self.id, "name": self.name, "code": self.code}


@dataclass
class Attribute:
    value: str | None = None
    source: str | None = None
    confidence: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    reason: str = ""
    #: Hanya untuk category/subcategory: baris kol_categories-nya. `value` lalu
    #: berisi `ref.name` (nama DB), tidak pernah kode.
    ref: TaxRef | None = None

    @property
    def known(self) -> bool:
        return self.value is not None


def _unknown(reason: str, evidence: list[Evidence] | None = None) -> Attribute:
    return Attribute(reason=reason, evidence=evidence or [])


# ---------------------------------------------------------------------------
# Taxonomy dari DB
# ---------------------------------------------------------------------------
@dataclass
class Taxonomy:
    """Taxonomy yang dibaca dari DB `kol`, divalidasi terhadap leksikon.

    rows            kol_categories.id -> TaxRef (SEMUA baris, termasuk legacy)
    styles          attribute_key kind 'style'
    personalities   attribute_key kind 'personality'

    Indeks turunan (bukan sumber kedua): `by_code` untuk baris yang punya kode,
    `category_by_name` untuk mengenali nama kategori roster.
    """

    rows: dict[str, TaxRef]
    styles: frozenset[str]
    personalities: frozenset[str]
    by_code: dict[str, TaxRef] = field(init=False, repr=False)
    category_by_name: dict[str, TaxRef] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.by_code = {r.code: r for r in self.rows.values() if r.code}
        self.category_by_name = {r.name: r for r in self.rows.values() if r.level == "category"}
        missing = []
        for code in L.CATEGORY_TARGETS:
            r = self.by_code.get(code)
            if r is None or r.level != "category" or r.parent_id is not None:
                missing.append(f"category:{code}")
        for code in set(L.BUSINESS_CATEGORY_TO_CATEGORY.values()) | set(L.ROSTER_LEGACY_TO_CODE.values()):
            if code not in L.CATEGORY_TARGETS:
                missing.append(f"category-target:{code}")
        for code in L.SUBCATEGORY_LEXICON:
            r = self.by_code.get(code)
            if r is None or r.level != "sub_category":
                missing.append(f"subcategory:{code}")
            elif self.rows.get(r.parent_id) is None or self.rows[r.parent_id].code not in L.CATEGORY_TARGETS:
                missing.append(f"subcategory-parent:{code}")
        missing += [f"style:{k}" for k in L.STYLE_CUES if k not in self.styles]
        missing += [f"personality:{k}" for k in L.PERSONALITY_FROM_STYLE if k not in self.personalities]
        for k in ("creator_personality.inspirational", "creator_personality.tech_savvy",
                  "creator_personality.expert"):
            if k not in self.personalities:
                missing.append(f"personality:{k}")
        if missing:
            raise ValueError("leksikon menunjuk baris yang tidak ada di taxonomy DB: "
                             + ", ".join(sorted(set(missing))))

    @classmethod
    def from_rows(cls, category_rows, attribute_rows) -> "Taxonomy":
        """category_rows: (id, name, code, level, parent_id) dari kol_categories;
        attribute_rows: (kind, attribute_key) dari kol_attribute."""
        rows = {str(cid): TaxRef(str(cid), name, code, level, str(pid) if pid else None)
                for cid, name, code, level, pid in category_rows}
        styles = frozenset(k for kind, k in attribute_rows if kind == "style")
        pers = frozenset(k for kind, k in attribute_rows if kind == "personality")
        return cls(rows, styles, pers)

    def category(self, code: str) -> TaxRef:
        return self.by_code[code]

    def children(self, category_id: str) -> list[TaxRef]:
        """Baris level='sub_category' dengan parent_id == category_id (dari DB)."""
        return sorted((r for r in self.rows.values()
                       if r.level == "sub_category" and r.parent_id == category_id),
                      key=lambda r: r.code or r.name)

    def name_of(self, code: str) -> str:
        r = self.by_code.get(code)
        return r.name if r else code


# ---------------------------------------------------------------------------
# Teks
# ---------------------------------------------------------------------------
def _norm(teks: str | None) -> str:
    return _A._normalisasi(teks)


def _hits(norm_text: str, terms: tuple[str, ...]) -> list[str]:
    """Istilah yang muncul sebagai kata/frasa utuh di teks yang sudah dinormalisasi."""
    if not norm_text:
        return []
    return [t for t in terms if _A._cocok_kata(norm_text, _norm(t))]


def _tag_tokens(hashtags) -> list[str]:
    out = []
    for h in hashtags or ():
        t = _norm(str(h)).replace(" ", "")
        if t:
            out.append(t)
    return out


def _tag_hits(tags: list[str], terms: tuple[str, ...]) -> list[str]:
    """Hashtag digabung (`#skincareroutine`), jadi dicocokkan sebagai awalan/isi --
    hanya untuk istilah >= 5 huruf supaya `ai`/`mc` tidak menyala di mana-mana."""
    found = []
    for term in terms:
        key = _norm(term).replace(" ", "")
        if len(key) < 5:
            continue
        if any(tag == key or tag.startswith(key) or (len(key) >= 6 and key in tag) for tag in tags):
            found.append(term)
    return found


# ---------------------------------------------------------------------------
# Skor generik: label -> bukti
# ---------------------------------------------------------------------------
def _collect(inp: CreatorInput, lexicon: dict[str, tuple[str, ...]],
             declared: dict[str, str] | None = None,
             labels: set[str] | None = None) -> dict[str, list[Evidence]]:
    """Kumpulkan bukti per label dari declared category, bio, post, hashtag, nama."""
    ev: dict[str, list[Evidence]] = {}

    def add(label: str, e: Evidence) -> None:
        if labels is None or label in labels:
            ev.setdefault(label, []).append(e)

    if declared and inp.declared_category and inp.declared_category in declared:
        add(declared[inp.declared_category],
            Evidence(SOURCE_DECLARED, declared[inp.declared_category], W_DECLARED, inp.declared_category))

    bio = _norm(inp.bio)
    for label, terms in lexicon.items():
        h = _hits(bio, terms)
        if h:
            w = min(W_BIO + W_BIO_EXTRA_TERM * (len(set(h)) - 1), W_BIO_MAX)
            add(label, Evidence(SOURCE_BIO, label, w, ", ".join(h[:4])))

    post_hits: dict[str, int] = {}
    tag_hits: dict[str, int] = {}
    post_terms: dict[str, set[str]] = {}
    for p in inp.posts:
        cap = _norm(p.caption)
        tags = _tag_tokens(p.hashtags)
        for label, terms in lexicon.items():
            h = _hits(cap, terms)
            if h:
                post_hits[label] = post_hits.get(label, 0) + 1
                post_terms.setdefault(label, set()).update(h[:3])
            elif _tag_hits(tags, terms):
                tag_hits[label] = tag_hits.get(label, 0) + 1
    for label, n in post_hits.items():
        w = W_REPEATED_POSTS if n >= 2 else W_SINGLE_POST
        add(label, Evidence(SOURCE_POSTS, label, w,
                            f"{n}/{len(inp.posts)} post: " + ", ".join(sorted(post_terms[label])[:4])))
    for label, n in tag_hits.items():
        add(label, Evidence(SOURCE_HASHTAG, label, min(W_HASHTAG * n, W_HASHTAG_CAP),
                            f"{n} post hanya lewat hashtag"))

    # Nama: pendukung saja -- hanya untuk label yang SUDAH punya bukti lain.
    names = _norm(" ".join(x for x in (inp.display_name, inp.username) if x).replace("_", " ").replace(".", " "))
    for label, terms in lexicon.items():
        if label in ev:
            h = _hits(names, terms)
            if h:
                add(label, Evidence(SOURCE_NAME, label, W_NAME, ", ".join(h[:2])))
    return ev


def _decide(ev: dict[str, list[Evidence]], what: str,
            tie_break=None, show=lambda label: label) -> Attribute:
    """Pilih label dari bukti: skor >= MIN_SCORE dan unggul >= MIN_MARGIN.

    `show` mengubah identifier internal (mis. kode) menjadi nama untuk pesan.
    """
    if not ev:
        return _unknown(f"tidak ada bukti {what}")
    scored = sorted(((sum(e.weight for e in es), label) for label, es in ev.items()),
                    key=lambda x: (-x[0], x[1]))
    all_ev = [e for es in ev.values() for e in es]
    top_score, top = scored[0]
    top_sources = {e.source for e in ev[top]}
    if top_sources <= {SOURCE_NAME, SOURCE_HASHTAG}:
        return _unknown(f"{what}: hanya bukti lemah ({', '.join(sorted(top_sources))})", all_ev)
    if top_score < MIN_SCORE:
        return _unknown(f"{what}: bukti terlalu lemah ({show(top)} {top_score:.2f} < {MIN_SCORE})", all_ev)
    if len(scored) > 1 and top_score - scored[1][0] < MIN_MARGIN:
        second_score, second = scored[1]
        if tie_break:
            chosen = tie_break(top, second)
            if chosen:
                score_of = {label: sc for sc, label in scored}
                other = second if chosen == top else top
                # Peran spesifik hanya menang kalau skornya sendiri memenuhi ambang;
                # kalau tidak, pemenang skor (Creator) yang dipakai.
                pick = chosen if score_of[chosen] >= MIN_SCORE else top
                srcs = {e.source for e in ev[pick]}
                why = ("peran lebih spesifik" if pick == chosen
                       else f"{chosen} di bawah ambang ({score_of[chosen]:.2f})")
                return Attribute(pick, "inference", _confidence(score_of[pick], srcs), ev[pick],
                                 f"{pick} dipilih atas {other if pick == chosen else chosen} ({why})")
        return _unknown(f"{what}: bukti bertentangan ({show(top)} {top_score:.2f} vs "
                        f"{show(second)} {second_score:.2f})", all_ev)
    return Attribute(top, "inference", _confidence(top_score, top_sources), ev[top],
                     f"skor {top_score:.2f}")


def _confidence(score: float, sources: set[str]) -> str:
    strong = len(sources & _STRONG_SOURCES)
    return "high" if score >= HIGH_SCORE and strong >= 2 else "medium"


# ---------------------------------------------------------------------------
# Gender dan umur: delegasi ke modul production
# ---------------------------------------------------------------------------
def classify_gender(inp: CreatorInput) -> Attribute:
    if inp.manual_gender:
        return Attribute(inp.manual_gender, _G.SUMBER_MANUAL, "high",
                         [Evidence("manual", inp.manual_gender, 0, "diisi manusia; tidak ditimpa")],
                         "manual")
    h = _G.pilih_gender(inp.roster_gender, inp.display_name, inp.username)
    if not h.diketahui:
        return _unknown(f"gender: {h.alasan or 'tidak ada sinyal'}")
    return Attribute(h.nilai, h.source, h.confidence,
                     [Evidence(h.source, h.nilai, 0, h.alasan)], h.alasan)


def classify_age(inp: CreatorInput, tahun_acuan: int | None = None) -> Attribute:
    if inp.manual_age is not None:
        return Attribute(str(inp.manual_age), AGE_SOURCE_MANUAL, "high",
                         [Evidence("manual", str(inp.manual_age), 0, "diisi manusia; tidak ditimpa")], "manual")
    h = ekstrak_umur(inp.bio, tahun_acuan=tahun_acuan) if tahun_acuan else ekstrak_umur(inp.bio)
    if h.diketahui:
        return Attribute(str(h.umur), h.source, h.confidence,
                         [Evidence(h.source, h.band or str(h.umur), 0, h.alasan)], h.alasan)
    if inp.nik and nik_aktif():
        n = umur_dari_nik(inp.nik, tahun_acuan) if tahun_acuan else umur_dari_nik(inp.nik)
        if n.diketahui:
            # Nomornya TIDAK disimpan di evidence -- hanya jenis sumbernya.
            return Attribute(str(n.umur), n.source, n.confidence,
                             [Evidence(n.source, n.band or str(n.umur), 0, "tanggal lahir dari NIK roster")],
                             "NIK roster")
        return _unknown(f"umur: bio tidak menyatakan umur; NIK tidak terurai ({n.alasan})")
    return _unknown("umur: tidak ada pernyataan umur di bio dan tidak ada NIK")


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------
def _role_tie_break(a: str, b: str) -> str | None:
    pair = {a, b}
    if L.ROLE_CREATOR in pair:
        other = (pair - {L.ROLE_CREATOR}).pop()
        if other in L.ROLES_SPECIFIC_OVER_CREATOR:
            return other
    return None


def classify_role(inp: CreatorInput) -> Attribute:
    ev = _collect(inp, L.ROLE_BIO_LEXICON, declared=L.BUSINESS_CATEGORY_ROLE)
    # Posts tidak dipakai untuk role: satu caption "promo" tidak membuat akun jadi bisnis.
    ev = {k: [e for e in v if e.source not in (SOURCE_POSTS, SOURCE_HASHTAG)] for k, v in ev.items()}
    ev = {k: v for k, v in ev.items() if v}
    if inp.is_business and L.ROLE_BUSINESS in ev:
        ev[L.ROLE_BUSINESS].append(Evidence(SOURCE_ACCOUNT_FLAG, L.ROLE_BUSINESS, 0.5,
                                            "isBusinessAccount = true"))
    return _decide(ev, "role", tie_break=_role_tie_break)


# ---------------------------------------------------------------------------
# Kategori dan subkategori
# ---------------------------------------------------------------------------
def _roster_targets(inp: CreatorInput, tax: Taxonomy) -> tuple[set[str], list[str]]:
    """Kategori roster -> kode canonical. Baris canonical dikenali dari `code`-nya
    di DB; label legacy lewat crosswalk kompatibilitas; sisanya dicatat, tidak dipakai."""
    targets, dropped = set(), []
    for name in inp.roster_categories:
        row = tax.category_by_name.get(name)
        if name in L.AUDIENCE_SEGMENT_CATEGORIES:
            dropped.append(f"{name} (segmen audiens)")
        elif row is not None and row.code in L.CATEGORY_TARGETS:
            targets.add(row.code)
        elif name in L.ROSTER_LEGACY_TO_CODE:
            targets.add(L.ROSTER_LEGACY_TO_CODE[name])
        elif name in L.ROSTER_UNMAPPED:
            dropped.append(f"{name} (legacy, tidak ada padanan canonical)")
        else:
            dropped.append(f"{name} (tidak dikenal)")
    return targets, dropped


def _resolve(attr: Attribute, tax: Taxonomy) -> Attribute:
    """Kode internal -> baris kol_categories. `value` menjadi nama DB, `ref` barisnya."""
    if attr.known:
        attr.ref = tax.by_code[attr.value]
        attr.value = attr.ref.name
    return attr


def classify_category(inp: CreatorInput, tax: Taxonomy) -> Attribute:
    roster, dropped = _roster_targets(inp, tax)
    ev = _collect(inp, L.CATEGORY_LEXICON, declared=L.BUSINESS_CATEGORY_TO_CATEGORY,
                  labels=set(L.CATEGORY_TARGETS))
    note = f"; roster diabaikan: {', '.join(dropped)}" if dropped else ""
    names = lambda codes: ", ".join(tax.name_of(c) for c in sorted(codes))  # noqa: E731

    if len(roster) == 1:
        # Roster = data kurasi manusia: menang atas inference. Konflik dicatat, tidak menimpa.
        code = next(iter(roster))
        evidence = [Evidence(SOURCE_ROSTER, code, 0, "kategori roster (kurasi)")]
        others = sorted(k for k in ev if k != code and sum(e.weight for e in ev[k]) >= MIN_SCORE)
        if others:
            evidence += [e for k in others for e in ev[k]]
            return _resolve(Attribute(code, SOURCE_ROSTER, "high", evidence,
                                      f"roster; bukti lain menunjuk {names(others)} "
                                      f"(konflik dicatat, roster menang){note}"), tax)
        return _resolve(Attribute(code, SOURCE_ROSTER, "high", evidence + ev.get(code, []),
                                  "roster" + note), tax)

    if len(roster) > 1:
        sub = {k: v for k, v in ev.items() if k in roster}
        pick = _decide(sub, "kategori (di antara pilihan roster)", show=tax.name_of)
        if pick.known:
            pick.source = f"{SOURCE_ROSTER}+{pick.source}"
            pick.evidence.insert(0, Evidence(SOURCE_ROSTER, pick.value, 0, "roster: " + names(roster)))
            pick.reason = f"roster menyebut {names(roster)}; bukti memilih {tax.name_of(pick.value)}{note}"
            return _resolve(pick, tax)
        return _unknown(f"roster menyebut beberapa kategori ({names(roster)}) "
                        f"dan bukti tidak memilih satu{note}", pick.evidence)

    res = _decide(ev, "kategori", show=tax.name_of)
    res.reason += note
    return _resolve(res, tax)


def classify_subcategory(inp: CreatorInput, category: Attribute, tax: Taxonomy) -> Attribute:
    """Kandidat HANYA baris sub_category dengan parent_id == category.id."""
    if not category.known or category.ref is None:
        return _unknown("subkategori: kategori Unknown")
    children = tax.children(category.ref.id)
    if not children:
        return _unknown(f"subkategori: kategori {category.value} tidak punya subkategori di taxonomy")
    lex = {c.code: L.SUBCATEGORY_LEXICON[c.code] for c in children if c.code in L.SUBCATEGORY_LEXICON}
    res = _resolve(_decide(_collect(inp, lex), f"subkategori {category.value}", show=tax.name_of), tax)
    if res.known and res.ref.parent_id != category.ref.id:   # pragma: no cover
        raise AssertionError("subkategori di luar induknya")  # dijaga oleh `children`
    return res


# ---------------------------------------------------------------------------
# Style dan personality -- hanya dari POLA caption
# ---------------------------------------------------------------------------
def _captioned(inp: CreatorInput) -> list[Post]:
    return [p for p in inp.posts if _norm(p.caption)]


def _post_hit_counts(posts: list[Post], cues: dict[str, tuple[str, ...]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in posts:
        text = _norm(p.caption)
        tags = _tag_tokens(p.hashtags)
        for key, terms in cues.items():
            if _hits(text, terms) or _tag_hits(tags, terms):
                counts[key] = counts.get(key, 0) + 1
    return counts


def classify_style(inp: CreatorInput) -> Attribute:
    posts = _captioned(inp)
    n = len(posts)
    if n < STYLE_MIN_POSTS:
        return _unknown(f"style: hanya {n} post ber-caption (< {STYLE_MIN_POSTS})")
    counts = _post_hit_counts(posts, L.STYLE_CUES)
    ok = sorted(((c, k) for k, c in counts.items()
                 if c >= STYLE_MIN_HITS and c / n >= STYLE_MIN_RATIO), key=lambda x: (-x[0], x[1]))
    ev = [Evidence(SOURCE_POSTS, k, 0, f"{c}/{n} post") for k, c in sorted(counts.items())]
    if not ok:
        return _unknown(f"style: tidak ada pola yang muncul di >= {STYLE_MIN_HITS} post "
                        f"dan >= {int(STYLE_MIN_RATIO * 100)}% dari {n} post", ev)
    if len(ok) > 1 and ok[0][0] == ok[1][0]:
        return _unknown(f"style: seri {ok[0][1]} vs {ok[1][1]} ({ok[0][0]}/{n} post)", ev)
    c, key = ok[0]
    conf = "high" if n >= 6 and c / n >= 0.5 else "medium"
    return Attribute(key, "caption_pattern", conf, ev, f"{c}/{n} post")


def classify_personality(inp: CreatorInput, role: Attribute, category: Attribute) -> Attribute:
    posts = _captioned(inp)
    n = len(posts)
    if n < PERSONALITY_MIN_POSTS:
        return _unknown(f"personality: hanya {n} post ber-caption (< {PERSONALITY_MIN_POSTS})")
    style = _post_hit_counts(posts, L.STYLE_CUES)
    extra = _post_hit_counts(posts, {"inspirational": L.INSPIRATIONAL_CUES, "tech": L.TECH_CUES})

    def union(keys: tuple[str, ...]) -> int:
        return sum(1 for p in posts if _post_hit_counts([p], {k: L.STYLE_CUES[k] for k in keys}))

    cand: dict[str, tuple[int, str]] = {}
    for pkey, skeys in L.PERSONALITY_FROM_STYLE.items():
        c = union(skeys)
        cand[pkey] = (c, "+".join(skeys))
    cand["creator_personality.inspirational"] = (extra.get("inspirational", 0), "motivasi/inspirasi")
    if category.ref is not None and category.ref.code in ("TEC", "GAM"):
        cand["creator_personality.tech_savvy"] = (extra.get("tech", 0), "istilah teknologi")
    if role.value == L.ROLE_PROFESSIONAL:
        edu = union(("content_style.educational", "content_style.tutorial"))
        if edu >= 2 and edu / n >= 0.3:
            # Expert = Educational + peran Professional yang terbukti: lebih spesifik,
            # jadi menggantikan Educational (bukan bersaing lalu seri).
            cand["creator_personality.expert"] = (max(edu, PERSONALITY_MIN_HITS), "profesional + konten edukatif")
            cand.pop("creator_personality.educational", None)

    ev = [Evidence(SOURCE_POSTS, k, 0, f"{c}/{n} post ({why})") for k, (c, why) in sorted(cand.items()) if c]
    ok = sorted(((c, k) for k, (c, _w) in cand.items()
                 if c >= PERSONALITY_MIN_HITS and c / n >= PERSONALITY_MIN_RATIO), key=lambda x: (-x[0], x[1]))
    if not ok:
        return _unknown(f"personality: tidak ada pola yang konsisten (>= {PERSONALITY_MIN_HITS} post "
                        f"dan >= {int(PERSONALITY_MIN_RATIO * 100)}% dari {n})", ev)
    if len(ok) > 1 and ok[0][0] == ok[1][0]:
        return _unknown(f"personality: seri {ok[0][1]} vs {ok[1][1]}", ev)
    c, key = ok[0]
    return Attribute(key, "caption_pattern", "medium", ev, f"inferred dari {c}/{n} post; bukan fakta psikologis")


# ---------------------------------------------------------------------------
# Semua atribut
# ---------------------------------------------------------------------------
def classify(inp: CreatorInput, tax: Taxonomy, tahun_acuan: int | None = None) -> dict[str, Attribute]:
    role = classify_role(inp)
    category = classify_category(inp, tax)
    return {
        "gender": classify_gender(inp),
        "age": classify_age(inp, tahun_acuan),
        "role": role,
        "category": category,
        "subcategory": classify_subcategory(inp, category, tax),
        "style": classify_style(inp),
        "personality": classify_personality(inp, role, category),
    }


def validate(result: dict[str, Attribute], tax: Taxonomy) -> list[str]:
    """Pelanggaran taxonomy pada satu hasil. Kosong = valid."""
    out: list[str] = []
    bad = out.append
    cat, sub = result["category"], result["subcategory"]
    if cat.known:
        r = cat.ref
        if r is None or tax.rows.get(r.id) != r:
            bad(f"kategori tidak ter-resolve ke kol_categories.id: {cat.value}")
        else:
            if r.level != "category" or r.parent_id is not None or r.code not in L.CATEGORY_TARGETS:
                bad(f"kategori bukan kategori canonical: {r.name}")
            if cat.value != r.name:
                bad(f"nama kategori bukan nama DB: {cat.value!r} != {r.name!r}")
    if sub.known:
        r = sub.ref
        if r is None or tax.rows.get(r.id) != r:
            bad(f"subkategori tidak ter-resolve ke kol_categories.id: {sub.value}")
        else:
            if r.level != "sub_category":
                bad(f"subkategori bukan baris sub_category: {r.name}")
            if cat.ref is None or r.parent_id != cat.ref.id:
                bad(f"subkategori {r.name} bukan anak (parent_id) dari {cat.value}")
            if sub.value != r.name:
                bad(f"nama subkategori bukan nama DB: {sub.value!r} != {r.name!r}")
    for a in (cat, sub):
        if a.known and _CODE_LIKE.match(a.value):
            bad(f"nama berbentuk kode: {a.value}")
    st = result["style"]
    if st.known and (st.value not in tax.styles or st.value in L.STYLE_NOT_INFERABLE):
        bad(f"style di luar taxonomy/inferable: {st.value}")
    pe = result["personality"]
    if pe.known and (pe.value not in tax.personalities or pe.value in L.PERSONALITY_NOT_INFERABLE):
        bad(f"personality di luar taxonomy/inferable: {pe.value}")
    ro = result["role"]
    if ro.known and ro.value not in L.ROLES:
        bad(f"role tidak dikenal: {ro.value}")
    return out
