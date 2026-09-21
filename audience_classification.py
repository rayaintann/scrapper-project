"""Audience Classification -- dibaca LANGSUNG dari Audience Analysis existing.

Sumber kebenaran audiens adalah pipeline existing, bukan modul ini:

    l0_raw.{ig,tt}_followers_apify -> l0_harmonization.*_follower
      -> l1_silver.unified_follower
      -> asset audience_feature  -> feature.{ig,tt}_audience_analysis
      -> asset audience_gold     -> l2_gold.audience_{demographics,geo,interest}_daily

Semua angka di sana diturunkan dari bukti PER FOLLOWER (nama, username, bio
pengikut) oleh `audience_inference` + `creator_age_inference.ekstrak_umur`.
Modul ini TIDAK menghitung ulang, TIDAK menulis, dan TIDAK punya definisi
kedua: ia hanya membaca kolom existing dan menyajikannya per atribut.

    Gender    feature.*_audience_analysis.female_pct / male_pct / gender_known_pct
              (+ gender_breakdown) ; kol_profile_card.gender_reliability
    Age       feature.*_audience_analysis.age_gender_breakdown
              (age, age_top, age_known, coverage_pct)
    City      l2_gold.audience_geo_daily  geo_level = 'city'    (audience_date terbaru)
    Country   l2_gold.audience_geo_daily  geo_level = 'country' (audience_date terbaru)
    Interest  feature.*_audience_analysis.interest_top / interest_source
              (aturan existing, termasuk fallback `content_inferred`)

Satu-satunya aturan di sini adalah kapan sebuah ringkasan boleh disebut
"diketahui": minimal MIN_KNOWN follower dengan nilai diketahui dan nilai teratas
yang unik -- selain itu Unknown, walaupun sebarannya tetap tersedia di
evidence. Tidak ada input kreator (bio/username/kota/category kreator) yang
pernah dibaca modul ini.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from creator_classification import Attribute, Evidence

AUDIENCE_ATTRS = ("gender", "age", "city", "country", "interest")
AGE_BUCKETS = ("13-17", "18-24", "25-34", "35-44", "45+")
INTEREST_SOURCES = ("audience", "content_inferred")      # nilai existing feature.interest_source

MIN_KNOWN = 5
GENDER_SHARE_MIN = 60.0
_RANK = {"low": 1, "medium": 2, "high": 3}
_CONF = {"inferred_high": "high", "inferred_medium": "medium", "inferred_low": "low",
         "high": "high", "medium": "medium", "low": "low"}

SRC_GENDER = "feature.audience_analysis.female_pct/male_pct"
SRC_AGE = "feature.audience_analysis.age_gender_breakdown"
SRC_GEO = "l2_gold.audience_geo_daily"
SRC_INTEREST = "feature.audience_analysis.interest_top"


@dataclass(frozen=True)
class AudienceInput:
    """Satu baris feature.*_audience_analysis (+ geo L2) untuk satu social account."""
    platform: str | None = None
    has_data: bool = False
    female_pct: float | None = None
    male_pct: float | None = None
    gender_known_pct: float | None = None
    gender_counts: dict[str, float] = field(default_factory=dict)       # gender_breakdown
    gender_reliability: str | None = None                                # kol_profile_card
    age_counts: dict[str, float] = field(default_factory=dict)          # age_gender_breakdown.age
    age_top: str | None = None
    age_confidence: dict[str, str] = field(default_factory=dict)
    city: dict[str, tuple[float, str | None]] = field(default_factory=dict)
    country: dict[str, tuple[float, str | None]] = field(default_factory=dict)
    interest_top: str | None = None
    interest_source: str | None = None
    followers_analyzed: int | None = None


def _unknown(reason: str, evidence: list[Evidence] | None = None) -> Attribute:
    return Attribute(reason=reason, evidence=evidence or [])


def _known_top(counts: dict[str, float]) -> tuple[str | None, float, float, str]:
    known = sum(v for k, v in counts.items() if v and v > 0)
    if known < MIN_KNOWN:
        return None, 0, known, f"hanya {known:g} follower diketahui (< {MIN_KNOWN})"
    ranked = sorted(((v, k) for k, v in counts.items() if v and v > 0), reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None, 0, known, f"seri {ranked[0][1]} vs {ranked[1][1]}"
    return ranked[0][1], ranked[0][0], known, ""


def classify_gender(inp: AudienceInput) -> Attribute:
    if not inp.has_data or inp.female_pct is None or inp.male_pct is None:
        return _unknown("gender audiens: tidak ada feature audience / gender follower tidak diketahui")
    ev = [Evidence(SRC_GENDER, "female_pct", 0, f"{inp.female_pct:g}"),
          Evidence(SRC_GENDER, "male_pct", 0, f"{inp.male_pct:g}"),
          Evidence(SRC_GENDER, "gender_known_pct", 0, f"{inp.gender_known_pct}")]
    known = (inp.gender_counts.get("male", 0) or 0) + (inp.gender_counts.get("female", 0) or 0)
    if known < MIN_KNOWN:
        return _unknown(f"gender audiens: hanya {known:g} follower diketahui (< {MIN_KNOWN})", ev)
    value, share = ("female", inp.female_pct) if inp.female_pct > inp.male_pct else ("male", inp.male_pct)
    if inp.female_pct == inp.male_pct or share < GENDER_SHARE_MIN:
        return _unknown(f"gender audiens: seimbang ({inp.female_pct:g}% female / {inp.male_pct:g}% male)", ev)
    conf = (inp.gender_reliability or "").lower()
    return Attribute(value, SRC_GENDER, conf if conf in _RANK else "low", ev,
                     f"{share:g}% dari {known:g} follower yang gendernya diketahui")


def classify_age(inp: AudienceInput) -> Attribute:
    if not inp.has_data:
        return _unknown("umur audiens: tidak ada feature audience")
    counts = {k: v for k, v in inp.age_counts.items() if k in AGE_BUCKETS}
    ev = [Evidence(SRC_AGE, "age_top", 0, f"{inp.age_top} ({sum(counts.values()):g} diketahui)")]
    key, n, known, why = _known_top(counts)
    if key is None:
        return _unknown(f"umur audiens: {why}", ev)
    conf = _CONF.get(inp.age_confidence.get(key, ""), "low")
    return Attribute(key, SRC_AGE, conf, ev, f"{n:g}/{known:g} follower menyatakan umur")


def _classify_geo(geo: dict, level: str, has_data: bool) -> Attribute:
    if not has_data or not geo:
        return _unknown(f"{level} audiens: tidak ada baris {SRC_GEO}[{level}]")
    counts = {k: v for k, (v, _c) in geo.items() if k and k.lower() != "unknown"}
    unknown = sum(v for k, (v, _c) in geo.items() if not k or k.lower() == "unknown")
    key, n, known, why = _known_top(counts)
    ev = [Evidence(f"{SRC_GEO}[{level}]", "known", 0, f"{known:g} diketahui, {unknown:g} unknown")]
    if key is None:
        return _unknown(f"{level} audiens: {why}", ev)
    return Attribute(key, f"{SRC_GEO}[{level}]", _CONF.get(geo[key][1] or "", "low"), ev,
                     f"{n:g}/{known:g} follower yang lokasinya diketahui")


def classify_city(inp: AudienceInput) -> Attribute:
    return _classify_geo(inp.city, "city", inp.has_data)


def classify_country(inp: AudienceInput) -> Attribute:
    return _classify_geo(inp.country, "country", inp.has_data)


def classify_interest(inp: AudienceInput) -> Attribute:
    """Aturan existing apa adanya: interest_top + interest_source dari audience_feature."""
    if not inp.has_data or not inp.interest_top:
        return _unknown("interest audiens: interest_top kosong di feature audience")
    return Attribute(inp.interest_top, f"{SRC_INTEREST}:{inp.interest_source}",
                     "medium" if inp.interest_source == "audience" else "low",
                     [Evidence(SRC_INTEREST, inp.interest_top, 0, f"interest_source={inp.interest_source}")],
                     "interest_source=" + str(inp.interest_source))


def classify(inp: AudienceInput) -> dict[str, Attribute]:
    return {"gender": classify_gender(inp), "age": classify_age(inp), "city": classify_city(inp),
            "country": classify_country(inp), "interest": classify_interest(inp)}


def validate(res: dict[str, Attribute]) -> list[str]:
    out = []
    if set(res) != set(AUDIENCE_ATTRS):
        out.append(f"atribut audiens tidak lengkap/berlebih: {sorted(res)}")
    for a, v in res.items():
        if v.known and (not v.source or v.confidence not in _RANK):
            out.append(f"{a}: source/confidence tidak sah ({v.source}, {v.confidence})")
    g, age, c, i = res.get("gender"), res.get("age"), res.get("country"), res.get("interest")
    if g and g.known and g.value not in ("female", "male"):
        out.append(f"gender audiens tidak sah: {g.value!r}")
    if age and age.known and age.value not in AGE_BUCKETS:
        out.append(f"umur audiens tidak sah: {age.value!r}")
    if c and c.known and not (len(c.value) == 2 and c.value.isupper()):
        out.append(f"country audiens bukan ISO-2: {c.value!r}")
    if i and i.known and i.source.rsplit(":", 1)[-1] not in INTEREST_SOURCES:
        out.append(f"interest_source tidak dikenal: {i.source!r}")
    return out


# ---------------------------------------------------------------------------
# DB (read-only) -- tabel existing Audience Analysis
# ---------------------------------------------------------------------------
SQL_FEATURE = """
    SELECT social_account_id::text, 'instagram', gender_breakdown, female_pct, male_pct, gender_known_pct,
           age_gender_breakdown, interest_top, interest_source
      FROM feature.ig_audience_analysis
    UNION ALL
    SELECT social_account_id::text, 'tiktok', gender_breakdown, female_pct, male_pct, gender_known_pct,
           age_gender_breakdown, interest_top, interest_source
      FROM feature.tt_audience_analysis"""
SQL_RELIABILITY = """
    SELECT social_account_id::text, gender_reliability FROM l2_gold.kol_profile_card
     WHERE gender_reliability IS NOT NULL"""
SQL_GEO = """
    SELECT g.social_account_id::text, g.geo_level, g.geo_key, g.audience_count, g.confidence
      FROM l2_gold.audience_geo_daily g
     WHERE g.geo_level IN ('city', 'country')
       AND g.audience_date = (SELECT max(x.audience_date) FROM l2_gold.audience_geo_daily x
                               WHERE x.social_account_id = g.social_account_id)"""


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _opt(v) -> float | None:
    return None if v is None else float(v)


def load(conn) -> dict[str, AudienceInput]:
    """social_account_id -> AudienceInput dari feature + L2 existing. Akun tanpa feature: tidak ada."""
    with conn.cursor() as cur:
        cur.execute(SQL_RELIABILITY)
        rel = dict(cur.fetchall())
        cur.execute(SQL_GEO)
        geo: dict[str, dict[str, dict]] = defaultdict(lambda: {"city": {}, "country": {}})
        for sa, level, key, n, conf in cur.fetchall():
            geo[sa][level][key] = (_num(n), conf)
        cur.execute(SQL_FEATURE)
        out = {}
        for sa, platform, gb, fp, mp, kp, agb, itop, isrc in cur.fetchall():
            gb, agb = gb or {}, agb or {}
            g = geo.get(sa, {"city": {}, "country": {}})
            out[sa] = AudienceInput(
                platform=platform, has_data=True,
                female_pct=_opt(fp), male_pct=_opt(mp), gender_known_pct=_opt(kp),
                gender_counts={k: _num(gb.get(k)) for k in ("male", "female")},
                gender_reliability=rel.get(sa),
                age_counts={k: _num(v) for k, v in (agb.get("age") or {}).items() if k != "unknown"},
                age_top=agb.get("age_top"),
                age_confidence=dict(agb.get("confidence") or {}),
                city=g["city"], country=g["country"],
                interest_top=itop, interest_source=isrc,
                followers_analyzed=int(_num(agb.get("followers_analyzed"))) or None,
            )
    return out
