"""Dry-run Creator Classification atas KOL aktif -- READ-ONLY, tidak menulis ke DB.

    python creator_classification_dryrun.py [--out output/creator_classification_dryrun.json]

Membaca taxonomy + bukti dari DB `kol` dalam sesi READ ONLY, menjalankan
`creator_classification.classify` untuk setiap KOL aktif, lalu mencetak
coverage, validasi taxonomy, contoh, dan kasus Unknown. Hasil per KOL ditulis
ke file JSON di `output/` (di-.gitignore) -- TIDAK ke database.

Dua mode, supaya jelas mana yang bisa dipakai production:

    A  production-eligible   L1 (unified_profile, unified_post) + roster + card
    B  A + PROTOTYPE         + businessCategoryName / isBusinessAccount /
                               latestPosts dari l0_raw.ig_profile_apify.raw_payload

Mode B membaca `l0_raw` hanya sebagai bukti prototype SEMENTARA: data itu
sudah ada (tidak ada scraping), tapi belum diharmonisasi ke L1, jadi flow
production belum boleh membacanya. Setiap post dari jalur itu diberi
`source = 'l0_raw.ig_profile_apify.latestPosts (prototype)'`.

NIK roster hanya diteruskan ke `creator_age_nik.umur_dari_nik` di memori --
tidak dicetak, tidak ditulis ke file.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date

import psycopg2

import audience_classification as A
import creator_classification as C
import creator_classification_lexicon as L
from config import load_config

PROTO_POST_SOURCE = "l0_raw.ig_profile_apify.latestPosts (prototype)"
# Digit dipisah spasi, titik, kurung, atau tanda hubung APA PUN (termasuk
# U+2010..U+2015 yang dipakai bio seperti "0838‑5756").
_RE_PHONE = re.compile(r"\+?\d(?:[\s().\-‐-―]*\d){7,}")
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def redact(text: str | None, n: int = 90) -> str:
    """Bio untuk dicetak: tanpa nomor telepon/email (bio kreator sering memuatnya)."""
    t = _RE_EMAIL.sub("<email>", text or "")
    t = _RE_PHONE.sub("<phone>", t)
    return " ".join(t.split())[:n]
#: Output creator. `role` tetap dihitung di dalam classifier (dipakai aturan
#: personality `expert`) tapi BUKAN output dan tidak pernah ditulis.
ATTRS = ("gender", "age", "category", "subcategory", "style", "personality")

SQL_TAXONOMY_CATEGORIES = """
    SELECT id, name, code, level, parent_id FROM public.kol_categories"""
SQL_TAXONOMY_ATTRIBUTES = "SELECT kind, attribute_key FROM public.kol_attribute WHERE is_active"

SQL_KOL = """
    SELECT kd.id::text, kd.username, pl.key, s.social_account_id::text,
           (SELECT array_agg(kc.name ORDER BY kc.name) FROM public.kol_categories kc
             WHERE kc.id = ANY (COALESCE(kd.category_ids, ARRAY[kd.category_id])))
      FROM public.kol_directory kd
      JOIN public.platforms pl ON pl.id = kd.platform_id
      JOIN public.kol_social_account s ON s.kol_id = kd.id
     WHERE kd.directory_status = 'active'
     ORDER BY kd.id"""
SQL_PROFILE = """
    SELECT DISTINCT ON (social_account_id) social_account_id::text, username, display_name, bio
      FROM l1_silver.unified_profile ORDER BY social_account_id, date DESC"""
SQL_POSTS = """
    SELECT social_account_id::text, content_id, caption, hashtags, media_type, video_duration
      FROM l1_silver.unified_post"""
SQL_ROSTER = """
    SELECT kol_directory_id::text,
           (array_agg(btrim(influencer_gender)) FILTER (WHERE btrim(influencer_gender) IN ('0','1')))[1],
           (array_agg(influencer_no_ktp) FILTER (WHERE btrim(coalesce(influencer_no_ktp,'')) <> ''))[1]
      FROM l0_raw.kol_roster_import WHERE kol_directory_id IS NOT NULL GROUP BY 1"""
SQL_CARD = """
    SELECT DISTINCT ON (social_account_id) social_account_id::text, creator_gender,
           creator_gender_source, creator_age, creator_age_source
      FROM l2_gold.kol_profile_card ORDER BY social_account_id, profile_snapshot_date DESC NULLS LAST"""
SQL_PROTO = """
    SELECT DISTINCT ON (social_account_id) social_account_id::text,
           raw_payload::jsonb ->> 'businessCategoryName',
           (raw_payload::jsonb ->> 'isBusinessAccount')::boolean,
           raw_payload::jsonb -> 'latestPosts'
      FROM l0_raw.ig_profile_apify ORDER BY social_account_id, scraped_at DESC NULLS LAST"""


def load(conn):
    with conn.cursor() as cur:
        cur.execute(SQL_TAXONOMY_CATEGORIES); cats = cur.fetchall()
        cur.execute(SQL_TAXONOMY_ATTRIBUTES); attrs = cur.fetchall()
        cur.execute(SQL_KOL); kols = cur.fetchall()
        cur.execute(SQL_PROFILE); prof = {r[0]: r[1:] for r in cur.fetchall()}
        cur.execute(SQL_POSTS)
        posts = defaultdict(list)
        for sa, cid, cap, tags, mt, dur in cur.fetchall():
            posts[sa].append((str(cid), C.Post(cap, tuple(tags or ()), mt,
                                               float(dur) if dur is not None else None)))
        cur.execute(SQL_ROSTER); roster = {r[0]: r[1:] for r in cur.fetchall()}
        cur.execute(SQL_CARD); card = {r[0]: r[1:] for r in cur.fetchall()}
        cur.execute(SQL_PROTO); proto = {r[0]: r[1:] for r in cur.fetchall()}
    return C.Taxonomy.from_rows(cats, attrs), kols, prof, posts, roster, card, proto


def build_input(kol, prof, posts, roster, card, proto, prototype: bool) -> tuple[C.CreatorInput, dict]:
    kid, username, platform, sa, cat_names = kol
    p_user, display_name, bio = prof.get(sa, (None, None, None))
    r_gender, nik = roster.get(kid, (None, None))
    c = card.get(sa, (None, None, None, None))
    manual_gender = c[0] if c[1] == "manual" else None
    manual_age = c[2] if c[3] == "manual" else None
    l1 = posts.get(sa, [])
    items = [p for _cid, p in l1]
    declared = is_business = None
    if prototype and sa in proto:
        declared, is_business, latest = proto[sa]
        if declared in ("None", ""):
            declared = None
        seen = {cid for cid, _p in l1}
        for lp in latest or []:
            if str(lp.get("id")) in seen:
                continue
            items.append(C.Post(lp.get("caption"), tuple(lp.get("hashtags") or ()),
                                lp.get("type"), lp.get("videoDuration"), PROTO_POST_SOURCE))
    inp = C.CreatorInput(kid, platform, username or p_user, display_name, bio, declared, is_business,
                         tuple(cat_names or ()), r_gender, nik, manual_gender, manual_age, tuple(items))
    return inp, {"card_gender": c[0], "card_gender_source": c[1], "card_age": c[2], "card_age_source": c[3]}


TAX_ATTRS = ("category", "subcategory")


def ev_label(tax: C.Taxonomy, attr: str, label: str) -> str:
    """Label evidence category/subcategory adalah kode internal; tampilkan nama DB."""
    return tax.name_of(label) if attr in TAX_ATTRS else label


def attr_json(tax: C.Taxonomy, attr: str, a: C.Attribute) -> dict:
    ev = []
    for e in a.evidence:
        d = {"source": e.source, "label": ev_label(tax, attr, e.label), "weight": e.weight, "detail": e.detail}
        if attr in TAX_ATTRS and e.label in tax.by_code:
            d["code"] = e.label
        ev.append(d)
    meta = {"source": a.source, "confidence": a.confidence, "reason": a.reason, "evidence": ev}
    if attr in TAX_ATTRS:
        return meta                       # objeknya ditulis terpisah: {id, name, code} | null
    return {"value": a.value, **meta}


def aud_json(a: C.Attribute) -> dict:
    return {"value": a.value, "source": a.source, "confidence": a.confidence, "reason": a.reason,
            "evidence": [{"source": e.source, "label": e.label, "detail": e.detail} for e in a.evidence]}


def kol_json(tax: C.Taxonomy, kol, res, aud: dict[str, C.Attribute]) -> dict:
    creator = {}
    for a in ATTRS:
        if a in TAX_ATTRS:
            creator[a] = res[a].ref.as_dict() if res[a].known else None
        else:
            creator[a] = attr_json(tax, a, res[a])
    return {"kol_id": kol[0], "username": kol[1], "platform": kol[2],
            "creator": creator,
            "creator_taxonomy_meta": {a: attr_json(tax, a, res[a]) for a in TAX_ATTRS},
            "audience": {a: aud_json(aud[a]) for a in A.AUDIENCE_ATTRS}}


def tax_problems(tax: C.Taxonomy, res) -> list[str]:
    """Pemeriksaan independen dari C.validate: id ada, parent_id cocok, nama DB, bukan kode."""
    out = []
    cat, sub = res["category"], res["subcategory"]
    for what, a in (("category", cat), ("subcategory", sub)):
        if not a.known:
            continue
        r = a.ref
        if r is None or tax.rows.get(r.id) != r:
            out.append(f"{what}: id tidak ada di kol_categories")
            continue
        if a.value != r.name:
            out.append(f"{what}: value {a.value!r} != nama DB {r.name!r}")
        if C._CODE_LIKE.match(r.name):
            out.append(f"{what}: nama berbentuk kode {r.name!r}")
    if cat.known and (cat.ref.level != "category" or cat.ref.parent_id is not None
                      or cat.ref.code not in L.CATEGORY_TARGETS):
        out.append(f"category bukan canonical: {cat.ref.name!r}")
    if sub.known:
        if not cat.known:
            out.append("subcategory tanpa category")
        elif sub.ref.level != "sub_category" or sub.ref.parent_id != cat.ref.id:
            out.append(f"subcategory {sub.ref.name!r}: parent_id != category.id")
    return out


def run(mode_proto: bool, data, tahun: int):
    tax, kols, prof, posts, roster, card, proto = data
    out, violations = [], []
    for kol in kols:
        inp, card_vals = build_input(kol, prof, posts, roster, card, proto, mode_proto)
        res = C.classify(inp, tax, tahun)
        v = C.validate(res, tax)
        if v:
            violations.append((kol[0], v))
        out.append((kol, inp, res, card_vals))
    return tax, out, violations


def coverage(rows) -> dict:
    cov = {}
    for a in ATTRS:
        src = Counter((r[2][a].source or "unknown").split("+")[0] if r[2][a].known else "unknown" for r in rows)
        known = sum(1 for r in rows if r[2][a].known)
        cov[a] = {"classified": known, "unknown": len(rows) - known,
                  "coverage_pct": round(100 * known / len(rows), 1), "by_source": dict(src.most_common())}
    return cov


def print_cov(title, cov, n):
    print(f"\n== COVERAGE {title} (total {n}) ==")
    print(f"{'attribute':12} {'classified':>10} {'unknown':>8} {'%':>6}  by source")
    for a, c in cov.items():
        print(f"{a:12} {c['classified']:>10} {c['unknown']:>8} {c['coverage_pct']:>5}%  {c['by_source']}")


def short(tax: C.Taxonomy, attr: str, a: C.Attribute) -> str:
    if not a.known:
        return f"Unknown ({a.reason})"
    ev = "; ".join(f"{e.source}:{ev_label(tax, attr, e.label)}={e.weight:g}[{e.detail}]" for e in a.evidence[:4])
    val = json.dumps(a.ref.as_dict(), ensure_ascii=False) if a.ref else a.value
    return f"{val} [{a.source}/{a.confidence}] <- {ev}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output/creator_classification_dryrun.json")
    args = ap.parse_args()
    tahun = date.today().year

    cfg = load_config()
    conn = psycopg2.connect(connect_timeout=10, **cfg.postgres.as_connect_kwargs())
    conn.set_session(readonly=True)
    try:
        data = load(conn)
        audience_in = A.load(conn)
    finally:
        conn.close()

    tax, rows_a, viol_a = run(False, data, tahun)
    _, rows_b, viol_b = run(True, data, tahun)
    n = len(rows_b)
    cov_a, cov_b = coverage(rows_a), coverage(rows_b)
    lv = Counter(r.level for r in tax.rows.values())
    print(f"active KOL: {n} | taxonomy: {len(L.CATEGORY_TARGETS)} canonical category "
          f"(dari {lv['category']} baris level=category), {lv['sub_category']} subcategory, "
          f"{len(tax.styles)} style, {len(tax.personalities)} personality")
    print_cov("A: production-eligible (L1 + roster + card)", cov_a, n)
    print_cov("B: A + prototype raw evidence (IG businessCategoryName + latestPosts)", cov_b, n)

    # Konsistensi gender/umur dengan hasil production di kol_profile_card.
    g_same = sum(1 for _k, _i, r, c in rows_b if (r["gender"].value or None) == (c["card_gender"] or None))
    a_same = sum(1 for _k, _i, r, c in rows_b
                 if (r["age"].value or None) == (str(c["card_age"]) if c["card_age"] is not None else None))
    print(f"\n== CONSISTENCY with production kol_profile_card ==\n"
          f"gender identical: {g_same}/{n} | age identical: {a_same}/{n}")

    print("\n== TAXONOMY VALIDATION ==")
    print(f"violations mode A: {len(viol_a)} | mode B: {len(viol_b)}")
    for kid, v in (viol_a + viol_b)[:10]:
        print("  ", kid, v)
    for title, rows in (("A", rows_a), ("B", rows_b)):
        probs = [(r[0][0], p) for r in rows for p in tax_problems(tax, r[2])]
        n_cat = sum(r[2]["category"].known for r in rows)
        n_sub = sum(r[2]["subcategory"].known for r in rows)
        print(f"mode {title}: category resolved {n_cat}, subcategory resolved {n_sub}, "
              f"ref/parent/name problems: {len(probs)}")
        for kid, p in probs[:10]:
            print("   ", kid, p)
    cats = Counter(f"{r[2]['category'].ref.code} {r[2]['category'].ref.name}"
                   for r in rows_b if r[2]["category"].known)
    subs = Counter(f"{r[2]['subcategory'].ref.code} {r[2]['subcategory'].ref.name}"
                   for r in rows_b if r[2]["subcategory"].known)
    print("category values:", dict(cats.most_common()))
    print("subcategory values:", dict(subs.most_common()))
    print("style values:", dict(Counter(r[2]["style"].value for r in rows_b if r[2]["style"].known)))
    print("personality values:", dict(Counter(r[2]["personality"].value for r in rows_b if r[2]["personality"].known)))
    print(f"style outside taxonomy/inferable: "
          f"{sum(1 for r in rows_b if r[2]['style'].known and (r[2]['style'].value not in tax.styles or r[2]['style'].value in L.STYLE_NOT_INFERABLE))}"
          f" | personality outside: {sum(1 for r in rows_b if r[2]['personality'].known and (r[2]['personality'].value not in tax.personalities or r[2]['personality'].value in L.PERSONALITY_NOT_INFERABLE))}")

    # 20 contoh dengan bukti lengkap: yang paling banyak atribut terisi, beragam kategori/role.
    def richness(r):
        return sum(r[2][a].known for a in ATTRS)
    picked, seen_cat = [], Counter()
    for r in sorted(rows_b, key=lambda r: (-richness(r), r[0][0])):
        key = (r[2]["category"].value, r[2]["style"].value)
        if seen_cat[key] >= 2:
            continue
        seen_cat[key] += 1
        picked.append(r)
        if len(picked) == 20:
            break
    print("\n== 20 EXAMPLES (mode B) ==")
    for kol, inp, res, _c in picked:
        print(f"\n@{kol[1]} ({kol[2]}) | bio: {redact(inp.bio)!r} | declared: {inp.declared_category} "
              f"| roster: {list(inp.roster_categories)} | posts: {len(inp.posts)}")
        for a in ATTRS:
            print(f"   {a:11} {short(tax, a, res[a])}")

    # Kasus ambiguous/konflik.
    amb = []
    for kol, inp, res, _c in rows_b:
        for a in ("category", "subcategory", "style", "personality"):
            reason = res[a].reason
            if not res[a].known and any(w in reason for w in ("bertentangan", "seri", "beberapa kategori", "terlalu lemah", "hanya bukti lemah")):
                amb.append((a, kol, inp, res[a]))
    by_attr = defaultdict(list)
    for x in amb:
        by_attr[x[0]].append(x)
    print(f"\n== AMBIGUOUS / CONFLICTING -> Unknown (total {len(amb)}) ==")
    for a, xs in by_attr.items():
        print(f"  {a}: {len(xs)}")
    shown = 0
    for a in ("category", "subcategory", "style", "personality"):
        for _a, kol, inp, attr in by_attr.get(a, [])[:3]:
            print(f"\n[{a}] @{kol[1]} ({kol[2]}) | bio: {redact(inp.bio, 80)!r} | declared: {inp.declared_category}")
            print(f"   -> {attr.reason}")
            for e in attr.evidence[:4]:
                print(f"      {e.source}:{ev_label(tax, a, e.label)} w={e.weight:g} [{e.detail}]")
            shown += 1

    # Audience: dari data follower saja, per social_account_id KOL.
    aud = {k[0]: A.classify(audience_in.get(k[3], A.AudienceInput())) for k, _i, _r, _c in rows_b}
    aud_viol = [(kid, v) for kid, r in aud.items() for v in A.validate(r)]
    print(f"\n== AUDIENCE (total {n}; akun dengan data follower: "
          f"{sum(1 for k, *_ in rows_b if k[3] in audience_in)}) ==")
    cov_aud = {}
    for a in A.AUDIENCE_ATTRS:
        known = sum(r[a].known for r in aud.values())
        cov_aud[a] = {"classified": known, "unknown": n - known,
                      "values": dict(Counter(r[a].value for r in aud.values() if r[a].known).most_common())}
        print(f"{a:12} {known:>6} {n - known:>6}  {cov_aud[a]['values']}")
    print(f"audience violations: {len(aud_viol)}")

    report = {"generated": date.today().isoformat(), "active_kol": n,
              "coverage_audience": cov_aud, "violations_audience": len(aud_viol),
              "coverage_mode_a_production_eligible": cov_a,
              "coverage_mode_b_with_prototype_raw_evidence": cov_b,
              "violations": {"mode_a": len(viol_a), "mode_b": len(viol_b)},
              "kols": [kol_json(tax, k, res, aud[k[0]]) for k, _i, res, _c in rows_b]}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\nreport written: {args.out} (no database writes)")


if __name__ == "__main__":
    main()
