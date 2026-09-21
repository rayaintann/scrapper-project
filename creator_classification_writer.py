"""Tulis hasil Creator Classification ke DB `kol` (storage migration 052) dan
verifikasi Audience Classification terhadap Audience Analysis existing.

    python creator_classification_writer.py [--dry-run]   # default: tidak menulis apa pun
    python creator_classification_writer.py --rehearse    # WRITE -> GUARD -> ROLLBACK
    python creator_classification_writer.py --commit      # WRITE -> GUARD -> COMMIT (ROLLBACK kalau guard gagal)
    python creator_classification_writer.py --verify      # verifikasi read-only

Storage per output (tidak ada tabel baru; taxonomy hanya DIBACA):

    CREATOR
      gender, age   l2_gold.kol_profile_card.creator_gender*/creator_age*
                    milik asset production `creator_gender`/`creator_age`, yang
                    memakai fungsi yang sama dengan classifier -> DIVERIFIKASI,
                    tidak ditulis ulang (tidak ada writer kedua untuk kolom itu).
      category      public.kol_directory.inferred_category_id  (FK kol_categories)
      subcategory   public.kol_directory.inferred_subcategory_id (FK, parent_id = category)
                    + inferred_category_source/_confidence/_evidence/_at.
                    category_id / category_ids (roster kurasi) TIDAK disentuh.
      style,        public.kol_attribute_map dengan source='creator_classification',
      personality   confidence, evidence. Baris source='curated' tidak pernah
                    ditimpa/dihapus; kalau kind yang sama sudah punya baris
                    curated, classifier tidak menulis kind itu.
    AUDIENCE  -- TIDAK ditulis oleh writer ini. Sumber kebenarannya Audience
              Analysis existing (asset audience_feature / audience_gold), yang
              sudah menulis hasil per-follower ke:
      gender        feature.{ig,tt}_audience_analysis.gender_breakdown/female_pct/
                    male_pct/gender_known_pct + l2_gold.audience_demographics_daily
                    (audience_type 'gender')
      age           feature.*.age_gender_breakdown + audience_demographics_daily ('age')
      city,country  feature.*.geo_distribution + l2_gold.audience_geo_daily
      interest      feature.*.top_interest/interest_top/interest_source +
                    l2_gold.audience_interest_daily
              Writer hanya MEMBACA dan memverifikasi (cakupan vs unified_follower,
              query pembaca Autometric kolGold.ts). Kolom ringkasan audiens di
              kartu dari 052 dihapus migration 053 (sumber kebenaran ganda).

Writer bersifat konvergen: menjalankan ulang tanpa perubahan data = 0 write.
Baris milik classifier yang tidak lagi didukung bukti dibersihkan (hanya baris
classifier; data kurasi tidak pernah).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

import psycopg2
from psycopg2.extras import Json

import audience_classification as A
import creator_classification as C
import creator_classification_dryrun as D
from config import load_config

CREATOR_SOURCE = "creator_classification"
EXPECT_ACTIVE = 1980
MAP_KINDS = ("style", "personality")
CARD_CREATOR = ("gender", "age")
EVIDENCE_MODES = {"l1": False, "l1+l0raw": True}

KD_COLS = ("inferred_category_id", "inferred_subcategory_id", "inferred_category_source",
           "inferred_category_confidence", "inferred_subcategory_confidence",
           "inferred_category_evidence")
KD_ALL_NEW = KD_COLS + ("inferred_category_at",)
MAP_NEW = ("source", "confidence", "evidence")


# ---------------------------------------------------------------------------
# Nilai yang diinginkan (murni)
# ---------------------------------------------------------------------------
def _ev(tax: C.Taxonomy, attr: str, a: C.Attribute) -> list[dict]:
    out = []
    for e in a.evidence:
        d = {"source": e.source, "label": D.ev_label(tax, attr, e.label), "weight": e.weight,
             "detail": D.redact(e.detail, 200)}
        if attr in D.TAX_ATTRS and e.label in tax.by_code:
            d["code"] = e.label
        out.append(d)
    return out


def desired_kd(tax: C.Taxonomy, res: dict[str, C.Attribute], mode: str) -> dict:
    cat, sub = res["category"], res["subcategory"]
    if not cat.known:
        return dict.fromkeys(KD_COLS)
    def meta(attr, a):
        return {"id": a.ref.id, "name": a.ref.name, "code": a.ref.code, "basis": a.source,
                "confidence": a.confidence, "reason": a.reason, "evidence": _ev(tax, attr, a)}
    return {
        "inferred_category_id": cat.ref.id,
        "inferred_subcategory_id": sub.ref.id if sub.known else None,
        "inferred_category_source": CREATOR_SOURCE,
        "inferred_category_confidence": cat.confidence,
        "inferred_subcategory_confidence": sub.confidence if sub.known else None,
        "inferred_category_evidence": {"evidence_mode": mode, "category": meta("category", cat),
                                       "subcategory": meta("subcategory", sub) if sub.known else None},
    }


def desired_map(tax: C.Taxonomy, res: dict[str, C.Attribute], attr_ids: dict, mode: str) -> dict:
    out = {}
    for kind in MAP_KINDS:
        a = res[kind]
        if a.known:
            out[kind] = {"attribute_id": attr_ids[(kind, a.value)], "key": a.value,
                         "confidence": a.confidence,
                         "evidence": {"evidence_mode": mode, "basis": a.source, "reason": a.reason,
                                      "evidence": _ev(tax, kind, a)}}
    return out


def _norm(v):
    """jsonb dari DB (dict) vs dict Python: bandingkan sebagai JSON kanonik."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, ensure_ascii=False)
    return None if v is None else str(v)


def _differs(want: dict, have: dict) -> bool:
    return any(_norm(want[k]) != _norm(have.get(k)) for k in want)


# ---------------------------------------------------------------------------
# Plan (murni)
# ---------------------------------------------------------------------------
@dataclass
class State:
    kd: dict[str, dict]                     # kol_id -> kolom inferred_* sekarang
    map: dict[str, list[dict]]              # kol_id -> [{id, kind, key, source, confidence, evidence}]


@dataclass
class Plan:
    kd_updates: list[tuple[str, dict]] = field(default_factory=list)
    map_inserts: list[dict] = field(default_factory=list)
    map_updates: list[dict] = field(default_factory=list)
    map_deletes: list[str] = field(default_factory=list)
    classified: Counter = field(default_factory=Counter)
    unknown: Counter = field(default_factory=Counter)
    skipped_curated: Counter = field(default_factory=Counter)
    unchanged: Counter = field(default_factory=Counter)
    cleared: Counter = field(default_factory=Counter)
    verified: Counter = field(default_factory=Counter)
    card_mismatch: list[tuple] = field(default_factory=list)
    invalid: list[tuple[str, str]] = field(default_factory=list)

    @property
    def n_changes(self) -> int:
        return (len(self.kd_updates) + len(self.map_inserts)
                + len(self.map_updates) + len(self.map_deletes))


def plan(tax: C.Taxonomy, results, state: State, attr_ids: dict, mode: str) -> Plan:
    """results: iterable (kol_id, social_account_id, res_creator, card_creator, audience_input, res_audience)."""
    p = Plan()
    for kid, sa, res, card, ainp, aud in results:
        for a in D.ATTRS:
            (p.classified if res[a].known else p.unknown)["creator_" + a] += 1
        for a in A.AUDIENCE_ATTRS:
            (p.classified if aud[a].known else p.unknown)["audience_" + a] += 1
        problems = C.validate(res, tax) + D.tax_problems(tax, res) + A.validate(aud)
        if problems:
            p.invalid.extend((kid, x) for x in problems)
            continue

        # Creator gender/age: diverifikasi terhadap kartu.
        for a in CARD_CREATOR:
            have, want = card.get(a), res[a].value
            if (None if have is None else str(have)) == want:
                if want is not None:
                    p.verified["creator_" + a] += 1
            else:
                p.card_mismatch.append((kid, a, None if have is None else str(have), want))
        # Audience: dibaca dari Audience Analysis existing, tidak ditulis.
        for a in A.AUDIENCE_ATTRS:
            p.verified["audience_" + a] += aud[a].known

        # Creator category/subcategory -> kol_directory.inferred_*
        want = desired_kd(tax, res, mode)
        have = state.kd.get(kid, {})
        if _differs(want, have):
            p.kd_updates.append((kid, want))
            if want["inferred_category_id"] is None:
                p.cleared["creator_category"] += 1
        else:
            p.unchanged["creator_category"] += want["inferred_category_id"] is not None

        # Creator style/personality -> kol_attribute_map
        wants = desired_map(tax, res, attr_ids, mode)
        rows = state.map.get(kid, [])
        for kind in MAP_KINDS:
            curated = [r for r in rows if r["kind"] == kind and r["source"] != CREATOR_SOURCE]
            ours = [r for r in rows if r["kind"] == kind and r["source"] == CREATOR_SOURCE]
            w = wants.get(kind)
            if curated:
                if w:
                    p.skipped_curated["creator_" + kind] += 1
                p.map_deletes.extend(r["id"] for r in ours)       # kurasi menang
                continue
            if w is None:
                p.map_deletes.extend(r["id"] for r in ours)
                p.cleared["creator_" + kind] += bool(ours)
                continue
            keep = next((r for r in ours if r["key"] == w["key"]), None)
            p.map_deletes.extend(r["id"] for r in ours if r is not keep)
            if keep is None:
                p.map_inserts.append({"kol_directory_id": kid, "kind": kind, **w})
            elif _differs({"confidence": w["confidence"], "evidence": w["evidence"]}, keep):
                p.map_updates.append({"id": keep["id"], "kind": kind, **w})
            else:
                p.unchanged["creator_" + kind] += 1
    return p


# ---------------------------------------------------------------------------
# DB: baca state
# ---------------------------------------------------------------------------
SQL_ATTRIBUTE_IDS = "SELECT id::text, kind, attribute_key FROM public.kol_attribute WHERE is_active"
SQL_STATE_KD = f"SELECT id::text, {', '.join(KD_COLS)} FROM public.kol_directory"
SQL_STATE_MAP = """
    SELECT m.id::text, m.kol_directory_id::text, a.kind, a.attribute_key, m.source, m.confidence, m.evidence
      FROM public.kol_attribute_map m JOIN public.kol_attribute a ON a.id = m.kol_attribute_id"""


def read_state(cur) -> State:
    cur.execute(SQL_STATE_KD)
    kd = {r[0]: {c: (str(v) if isinstance(v, (bytes,)) else v) for c, v in zip(KD_COLS, r[1:])}
          for r in cur.fetchall()}
    for v in kd.values():
        for c in ("inferred_category_id", "inferred_subcategory_id"):
            v[c] = str(v[c]) if v[c] is not None else None
    cur.execute(SQL_STATE_MAP)
    mp: dict[str, list[dict]] = {}
    for mid, kid, kind, key, src, conf, ev in cur.fetchall():
        mp.setdefault(kid, []).append({"id": mid, "kind": kind, "key": key, "source": src,
                                       "confidence": conf, "evidence": ev})
    return State(kd, mp)


def load_inputs(conn, prototype: bool, tahun: int):
    """Classifier creator + audience untuk semua KOL aktif (read-only)."""
    data = D.load(conn)
    tax, rows, _viol = D.run(prototype, data, tahun)
    audience_in = A.load(conn)
    with conn.cursor() as cur:
        cur.execute(SQL_ATTRIBUTE_IDS)
        attr_ids = {}
        for aid, kind, key in cur.fetchall():
            assert (kind, key) not in attr_ids, f"attribute_key ganda: {kind} {key}"
            attr_ids[(kind, key)] = aid
    results = []
    for kol, _inp, res, cv in rows:
        ainp = audience_in.get(kol[3], A.AudienceInput())
        results.append((kol[0], kol[3], res, {"gender": cv["card_gender"], "age": cv["card_age"]},
                        ainp, A.classify(ainp)))
    return tax, rows, results, attr_ids


# ---------------------------------------------------------------------------
# Snapshot + guard
# ---------------------------------------------------------------------------
FULL_FP = ("public.kol_categories", "public.agency_kol_accounts", "public.kol_attribute",
           "l2_gold.kol_profile_card", "l1_silver.unified_follower",
           "public.kol_social_account", "feature.ig_audience_analysis", "feature.tt_audience_analysis",
           "l2_gold.audience_demographics_daily", "l2_gold.audience_geo_daily",
           "l2_gold.audience_interest_daily")
PARTIAL_FP = {  # tabel target: sidik jari atas SEMUA kolom KECUALI kolom classifier
    "public.kol_directory": KD_ALL_NEW,
}


def _cols(cur, table: str, exclude) -> list[str]:
    schema, name = table.split(".")
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
                "ORDER BY ordinal_position", (schema, name))
    return [c for (c,) in cur.fetchall() if c not in exclude]


def _fp(cur, table: str, expr: str = "t::text", where: str = "") -> list:
    cur.execute(f"SELECT count(*), md5(coalesce(string_agg({expr}, '|' ORDER BY {expr}), '')) "
                f"FROM {table} t {where}")
    return list(cur.fetchone())


SQL_COUNTS = {
    "active": "SELECT count(*) FROM public.kol_directory WHERE directory_status = 'active'",
    "map_dupes": """SELECT count(*) FROM (SELECT 1 FROM public.kol_attribute_map
                     GROUP BY kol_directory_id, kol_attribute_id HAVING count(*) > 1) d""",
    "map_orphans": """SELECT count(*) FROM public.kol_attribute_map m
                        LEFT JOIN public.kol_attribute a ON a.id = m.kol_attribute_id AND a.is_active
                        LEFT JOIN public.kol_directory k ON k.id = m.kol_directory_id
                       WHERE a.id IS NULL OR k.id IS NULL""",
    "map_ours_multi": f"""SELECT count(*) FROM (SELECT 1 FROM public.kol_attribute_map m
                            JOIN public.kol_attribute a ON a.id = m.kol_attribute_id
                           WHERE m.source = '{CREATOR_SOURCE}'
                           GROUP BY m.kol_directory_id, a.kind HAVING count(*) > 1) d""",
    "map_mixed": f"""SELECT count(*) FROM (SELECT 1 FROM public.kol_attribute_map m
                       JOIN public.kol_attribute a ON a.id = m.kol_attribute_id
                      GROUP BY m.kol_directory_id, a.kind
                     HAVING bool_or(m.source = '{CREATOR_SOURCE}') AND bool_or(m.source <> '{CREATOR_SOURCE}')) d""",
    "kd_invalid": """SELECT count(*) FROM public.kol_directory k
                       LEFT JOIN public.kol_categories c ON c.id = k.inferred_category_id
                       LEFT JOIN public.kol_categories s ON s.id = k.inferred_subcategory_id
                      WHERE (k.inferred_category_id IS NOT NULL AND (c.id IS NULL OR c.level <> 'category'
                              OR c.parent_id IS NOT NULL OR c.code IS NULL))
                         OR (k.inferred_subcategory_id IS NOT NULL AND (s.id IS NULL OR s.level <> 'sub_category'
                              OR s.parent_id IS DISTINCT FROM k.inferred_category_id))""",
    "category_orphans": """SELECT count(*) FROM public.kol_directory k,
                             unnest(coalesce(k.category_ids, '{}') || k.category_id) c(id)
                            WHERE c.id IS NOT NULL
                              AND NOT EXISTS (SELECT 1 FROM public.kol_categories kc WHERE kc.id = c.id)""",
}


def snapshot(cur) -> dict:
    snap = {t: _fp(cur, t) for t in FULL_FP}
    for t, excl in PARTIAL_FP.items():
        cols = _cols(cur, t, excl)
        snap[t + " (non-classifier columns)"] = _fp(cur, t, "row(" + ", ".join(f't."{c}"' for c in cols) + ")::text")
    snap["public.kol_attribute_map (curated rows)"] = _fp(
        cur, "public.kol_attribute_map", where=f"WHERE t.source <> '{CREATOR_SOURCE}'")
    for k, q in SQL_COUNTS.items():
        cur.execute(q)
        snap[k] = cur.fetchone()[0]
    return snap


FP_KEYS_EXCLUDED = set(SQL_COUNTS)


def guards(before: dict, after: dict, n_planned: int, n_done: int, n_left: int,
           expect_active: int = EXPECT_ACTIVE) -> list[str]:
    bad = []
    if not (before["active"] == after["active"] == expect_active):
        bad.append(f"active KOL {before['active']} -> {after['active']}, expected {expect_active}")
    for k in before:
        if k not in FP_KEYS_EXCLUDED and before[k] != after.get(k):
            bad.append(f"{k} berubah: {before[k]} -> {after.get(k)}")
    if n_done != n_planned:
        bad.append(f"written {n_done} != candidate {n_planned}")
    if n_left:
        bad.append(f"state belum konvergen: {n_left} perubahan tersisa setelah write")
    for k in ("map_dupes", "map_orphans", "map_ours_multi", "map_mixed", "kd_invalid"):
        if after[k]:
            bad.append(f"{k} = {after[k]}")
    if after["category_orphans"] > before["category_orphans"]:
        bad.append(f"orphan category reference bertambah {before['category_orphans']} -> {after['category_orphans']}")
    return bad


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
SQL_MAP_DELETE = f"DELETE FROM public.kol_attribute_map WHERE id = %s AND source = '{CREATOR_SOURCE}'"
SQL_MAP_INSERT = f"""
    INSERT INTO public.kol_attribute_map (kol_directory_id, kol_attribute_id, assigned_by, note, source, confidence, evidence)
    VALUES (%s, %s, NULL, NULL, '{CREATOR_SOURCE}', %s, %s)
    ON CONFLICT (kol_directory_id, kol_attribute_id) DO NOTHING"""
SQL_MAP_UPDATE = f"""UPDATE public.kol_attribute_map SET confidence = %s, evidence = %s
                      WHERE id = %s AND source = '{CREATOR_SOURCE}'"""
SQL_KD_UPDATE = f"""
    UPDATE public.kol_directory
       SET {', '.join(f'{c} = %({c})s' for c in KD_COLS)},
           inferred_category_at = CASE WHEN %(inferred_category_id)s::uuid IS NULL THEN NULL ELSE now() END
     WHERE id = %(kid)s"""


def _jsonify(d: dict) -> dict:
    return {k: Json(v) if isinstance(v, (dict, list)) else v for k, v in d.items()}


def execute_plan(cur, p: Plan) -> int:
    done = 0
    for mid in p.map_deletes:
        cur.execute(SQL_MAP_DELETE, (mid,)); done += cur.rowcount
    for w in p.map_inserts:
        cur.execute(SQL_MAP_INSERT, (w["kol_directory_id"], w["attribute_id"], w["confidence"], Json(w["evidence"])))
        done += cur.rowcount
    for w in p.map_updates:
        cur.execute(SQL_MAP_UPDATE, (w["confidence"], Json(w["evidence"]), w["id"])); done += cur.rowcount
    for kid, want in p.kd_updates:
        cur.execute(SQL_KD_UPDATE, {**_jsonify(want), "kid": kid}); done += cur.rowcount
    return done


def apply(conn, replan, p: Plan, *, commit: bool, snap=snapshot, check=guards) -> tuple[int, list[str], bool]:
    """Satu transaksi: snapshot -> write -> snapshot -> re-plan -> guard -> COMMIT/ROLLBACK.
    `replan(cur)` menghitung ulang plan dari state DB di transaksi yang sama.
    Tanpa commit=True selalu ROLLBACK. Error apa pun -> ROLLBACK lalu dilempar ulang."""
    try:
        with conn.cursor() as cur:
            before = snap(cur)
            done = execute_plan(cur, p)
            after = snap(cur)
            left = replan(cur).n_changes
        problems = check(before, after, p.n_changes, done, left)
        if problems or not commit:
            conn.rollback()
            return done, problems, False
        conn.commit()
        return done, problems, True
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def print_plan(p: Plan, n: int) -> None:
    print(f"\n== PLAN (active KOL {n}) ==")
    rows = [("CREATOR", None)] + [(f"creator_{a}", a) for a in D.ATTRS] + \
           [("AUDIENCE", None)] + [(f"audience_{a}", a) for a in A.AUDIENCE_ATTRS]
    for key, a in rows:
        if a is None:
            print(key)
            continue
        print(f"  {a:12} classified {p.classified[key]:>5} | unknown {p.unknown[key]:>5}"
              + (f" | verified in DB {p.verified[key]}" if key in ("creator_gender", "creator_age") else "")
              + (f" | read from existing Audience Analysis {p.verified[key]}" if key.startswith("audience_") else "")
              + (f" | skipped curated {p.skipped_curated[key]}" if key in ("creator_style", "creator_personality") else ""))
    print(f"\ncandidate writes: {p.n_changes}  (kol_directory.inferred_* {len(p.kd_updates)}, "
          f"kol_attribute_map insert {len(p.map_inserts)} / update {len(p.map_updates)} / delete {len(p.map_deletes)}; "
          f"audience: 0 -- dibaca dari feature/L2 existing)")
    print(f"unchanged: {dict(p.unchanged)} | cleared: {dict(p.cleared)} | skipped curated: {dict(p.skipped_curated)}")
    print(f"invalid taxonomy / parent-child / audience: {len(p.invalid)}")
    for kid, x in p.invalid[:10]:
        print("   ", kid, x)
    print(f"creator gender/age differing from kol_profile_card: {len(p.card_mismatch)}")
    for m in p.card_mismatch[:10]:
        print("   ", m)


def print_examples(rows, results, n_ex: int = 8) -> None:
    print("\n== EXAMPLES ==")
    by = {r[0]: r for r in results}
    shown = 0
    for kol, _inp, res, _c in sorted(rows, key=lambda r: (-sum(r[2][a].known for a in D.ATTRS), r[0][0])):
        _kid, _sa, _res, _card, _ainp, aud = by[kol[0]]
        if shown >= n_ex:
            break
        if not (res["category"].known and (res["style"].known or any(aud[a].known for a in A.AUDIENCE_ATTRS))):
            continue
        shown += 1
        c = {a: (res[a].ref.as_dict() if a in D.TAX_ATTRS and res[a].known else res[a].value) for a in D.ATTRS}
        print(f"@{kol[1]} ({kol[2]})")
        print(f"   creator : {json.dumps(c, ensure_ascii=False)}")
        print(f"   audience: {json.dumps({a: aud[a].value for a in A.AUDIENCE_ATTRS}, ensure_ascii=False)}")


SQL_VERIFY = f"""
    WITH act AS (SELECT k.*, s.social_account_id FROM public.kol_directory k
                   JOIN public.kol_social_account s ON s.kol_id = k.id
                  WHERE k.directory_status = 'active')
    SELECT
      (SELECT count(*) FROM act),
      (SELECT count(c.creator_gender) FROM act JOIN l2_gold.kol_profile_card c USING (social_account_id)),
      (SELECT count(c.creator_age) FROM act JOIN l2_gold.kol_profile_card c USING (social_account_id)),
      (SELECT count(inferred_category_id) FROM act),
      (SELECT count(inferred_subcategory_id) FROM act),
      (SELECT count(*) FROM public.kol_attribute_map m JOIN public.kol_attribute a ON a.id = m.kol_attribute_id
        WHERE a.kind = 'style' AND m.kol_directory_id IN (SELECT id FROM act)),
      (SELECT count(*) FROM public.kol_attribute_map m JOIN public.kol_attribute a ON a.id = m.kol_attribute_id
        WHERE a.kind = 'personality' AND m.kol_directory_id IN (SELECT id FROM act)),
      (SELECT count(DISTINCT social_account_id) FROM l2_gold.audience_demographics_daily
        WHERE audience_type = 'gender' AND dimension_key <> 'unknown' AND audience_count > 0
          AND social_account_id IN (SELECT social_account_id FROM act)),
      (SELECT count(DISTINCT social_account_id) FROM l2_gold.audience_demographics_daily
        WHERE audience_type = 'age' AND dimension_key <> 'unknown' AND audience_count > 0
          AND social_account_id IN (SELECT social_account_id FROM act)),
      (SELECT count(DISTINCT social_account_id) FROM l2_gold.audience_geo_daily
        WHERE geo_level = 'city' AND geo_key <> 'unknown' AND audience_count > 0
          AND social_account_id IN (SELECT social_account_id FROM act)),
      (SELECT count(DISTINCT social_account_id) FROM l2_gold.audience_geo_daily
        WHERE geo_level = 'country' AND geo_key <> 'unknown' AND audience_count > 0
          AND social_account_id IN (SELECT social_account_id FROM act)),
      (SELECT count(DISTINCT social_account_id) FROM l2_gold.audience_interest_daily
        WHERE interest_key <> 'unknown' AND audience_count > 0
          AND social_account_id IN (SELECT social_account_id FROM act)),
      (SELECT count(*) FROM public.kol_attribute_map WHERE source = '{CREATOR_SOURCE}'),
      (SELECT count(*) FROM public.kol_attribute_map WHERE source <> '{CREATOR_SOURCE}')"""
SQL_VERIFY_TAX = """
    SELECT
      count(*) FILTER (WHERE k.inferred_category_id IS NOT NULL),
      count(*) FILTER (WHERE c.id IS NOT NULL AND c.level = 'category' AND c.parent_id IS NULL AND c.code IS NOT NULL),
      count(*) FILTER (WHERE k.inferred_subcategory_id IS NOT NULL),
      count(*) FILTER (WHERE s.id IS NOT NULL AND s.level = 'sub_category'),
      count(*) FILTER (WHERE s.id IS NOT NULL AND s.parent_id = k.inferred_category_id),
      count(*) FILTER (WHERE c.name IS NOT NULL AND c.name <> c.code AND c.name !~ '^[A-Z]{2,5}(\\.[A-Z]{2,5})?$'),
      count(*) FILTER (WHERE s.name IS NOT NULL AND s.name <> s.code AND s.name !~ '^[A-Z]{2,5}(\\.[A-Z]{2,5})?$'),
      count(*) FILTER (WHERE k.inferred_category_source = 'creator_classification'),
      count(*) FILTER (WHERE c.name IN ('FOD.CUL','BEA.MKP','FIT.GYM') OR s.name IN ('FOD.CUL','BEA.MKP','FIT.GYM'))
      FROM public.kol_directory k
      LEFT JOIN public.kol_categories c ON c.id = k.inferred_category_id
      LEFT JOIN public.kol_categories s ON s.id = k.inferred_subcategory_id
     WHERE k.inferred_category_id IS NOT NULL OR k.inferred_subcategory_id IS NOT NULL"""


#: Integrasi audiens: cakupan feature/L2 terhadap follower, tidak ada kolom
#: ringkasan kedua, dan query pembaca existing (src/lib/discover/kolGold.ts:
#: join kol_social_account + audience_date terbaru) mengembalikan data.
SQL_VERIFY_AUDIENCE = """
    WITH fol AS (SELECT DISTINCT social_account_id FROM l1_silver.unified_follower
                  WHERE social_account_id IS NOT NULL),
         feat AS (SELECT social_account_id FROM feature.ig_audience_analysis
                  UNION SELECT social_account_id FROM feature.tt_audience_analysis),
         act AS (SELECT k.id AS kol_id, s.social_account_id FROM public.kol_directory k
                   JOIN public.kol_social_account s ON s.kol_id = k.id
                  WHERE k.directory_status = 'active')
    SELECT
      (SELECT count(*) FROM fol),
      (SELECT count(*) FROM feat),
      (SELECT count(*) FROM fol WHERE social_account_id NOT IN (SELECT social_account_id FROM feat)),
      (SELECT count(*) FROM fol WHERE social_account_id NOT IN
          (SELECT social_account_id FROM l2_gold.audience_demographics_daily)),
      (SELECT count(*) FROM fol WHERE social_account_id NOT IN
          (SELECT social_account_id FROM l2_gold.audience_geo_daily)),
      (SELECT count(*) FROM fol WHERE social_account_id NOT IN
          (SELECT social_account_id FROM l2_gold.audience_interest_daily)),
      (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'l2_gold' AND table_name = 'kol_profile_card'
          AND column_name IN ('audience_age_top', 'audience_city_top', 'audience_country_top',
                              'audience_interest_segment', 'audience_classification_source',
                              'audience_classification_evidence')),
      (SELECT count(*) FROM act WHERE EXISTS (
          SELECT 1 FROM l2_gold.audience_demographics_daily a
           WHERE a.social_account_id = act.social_account_id AND a.audience_type = 'gender'
             AND a.audience_date = (SELECT max(x.audience_date) FROM l2_gold.audience_demographics_daily x
                                     WHERE x.social_account_id = a.social_account_id
                                       AND x.audience_type = 'gender'))),
      (SELECT count(*) FROM act WHERE EXISTS (
          SELECT 1 FROM l2_gold.audience_geo_daily g
           WHERE g.social_account_id = act.social_account_id
             AND g.audience_date = (SELECT max(x.audience_date) FROM l2_gold.audience_geo_daily x
                                     WHERE x.social_account_id = g.social_account_id))),
      (SELECT count(*) FROM act WHERE EXISTS (
          SELECT 1 FROM l2_gold.audience_interest_daily i
           WHERE i.social_account_id = act.social_account_id
             AND i.audience_date = (SELECT max(x.audience_date) FROM l2_gold.audience_interest_daily x
                                     WHERE x.social_account_id = i.social_account_id))),
      (SELECT count(*) FROM (SELECT social_account_id, audience_date, audience_type, dimension_key
                               FROM l2_gold.audience_demographics_daily GROUP BY 1,2,3,4 HAVING count(*) > 1) d),
      (SELECT count(*) FROM (SELECT social_account_id, audience_date, geo_level, geo_key
                               FROM l2_gold.audience_geo_daily GROUP BY 1,2,3,4 HAVING count(*) > 1) d),
      (SELECT count(*) FROM (SELECT social_account_id, audience_date, interest_key
                               FROM l2_gold.audience_interest_daily GROUP BY 1,2,3 HAVING count(*) > 1) d)"""


def verify(conn, prototype: bool, mode: str, tahun: int) -> dict:
    tax, rows, results, attr_ids = load_inputs(conn, prototype, tahun)
    with conn.cursor() as cur:
        state = read_state(cur)
        p = plan(tax, results, state, attr_ids, mode)
        cur.execute(SQL_VERIFY)
        v = cur.fetchone()
        cur.execute(SQL_VERIFY_TAX)
        t = cur.fetchone()
        cur.execute(SQL_VERIFY_AUDIENCE)
        au = cur.fetchone()
        snap = snapshot(cur)
    def pct(ok, tot):
        return f"{100 * ok / tot:.0f}% ({ok}/{tot})" if tot else "n/a (0)"
    return {
        "active_kol": v[0],
        "creator": {"gender": v[1], "age": v[2], "category": v[3], "subcategory": v[4],
                    "style": v[5], "personality": v[6]},
        "audience": {"gender": v[7], "age": v[8], "city": v[9], "country": v[10], "interest": v[11]},
        "audience_integration": {
            "accounts with followers (unified_follower)": au[0],
            "accounts in feature.*_audience_analysis": au[1],
            "follower accounts missing feature": au[2],
            "follower accounts missing L2 demographics / geo / interest": (au[3], au[4], au[5]),
            "redundant kol_profile_card.audience_* columns": au[6],
            "active KOL readable by kolGold.ts gender / geo / interest query": (au[7], au[8], au[9]),
            "L2 duplicate keys demographics / geo / interest": (au[10], au[11], au[12]),
        },
        "attribute_map": {"creator_classification": v[12], "curated": v[13]},
        "classified": dict(p.classified), "unknown": dict(p.unknown),
        "pending_changes": p.n_changes, "skipped_curated": dict(p.skipped_curated),
        "errors": {"invalid": len(p.invalid), "creator_card_mismatch": len(p.card_mismatch),
                   **{k: snap[k] for k in ("map_dupes", "map_orphans", "map_ours_multi", "map_mixed", "kd_invalid")}},
        "taxonomy": {
            "category FK valid": pct(t[1], t[0]),
            "subcategory FK valid": pct(t[3], t[2]),
            "subcategory parent valid": pct(t[4], t[2]),
            "display name = kol_categories.name": "100% (nama selalu di-join dari kol_categories)",
            "category display name != code": pct(t[5], t[0]),
            "subcategory display name != code": pct(t[6], t[2]),
            "source = creator_classification": pct(t[7], t[0]),
            "FOD.CUL/BEA.MKP/FIT.GYM as display name": t[8],
        },
    }


def print_verify(rep: dict) -> None:
    print("\n== VERIFICATION (read-only) ==")
    print(f"Active KOL: {rep['active_kol']}")
    for side in ("creator", "audience"):
        print(side.upper())
        for a, n in rep[side].items():
            print(f"  {a.capitalize():12} in DB {n:>5} | classified {rep['classified'].get(f'{side}_{a}', 0):>5}"
                  f" | unknown {rep['unknown'].get(f'{side}_{a}', 0):>5}")
    print(f"kol_attribute_map rows: {rep['attribute_map']}")
    print(f"Pending changes: {rep['pending_changes']} | skipped curated: {rep['skipped_curated']}")
    print(f"Errors: {rep['errors']}")
    for k, v in rep["taxonomy"].items():
        print(f"  {k}: {v}")
    print("AUDIENCE INTEGRATION (existing Audience Analysis = source of truth)")
    for k, v in rep["audience_integration"].items():
        print(f"  {k}: {v}")


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="default: tidak menulis apa pun")
    g.add_argument("--rehearse", action="store_true", help="WRITE -> GUARD -> ROLLBACK")
    g.add_argument("--commit", action="store_true", help="WRITE -> GUARD -> COMMIT")
    g.add_argument("--verify", action="store_true", help="verifikasi read-only")
    ap.add_argument("--evidence", choices=tuple(EVIDENCE_MODES), default="l1+l0raw",
                    help="l1 = L1 + roster + card; l1+l0raw = + businessCategoryName/latestPosts "
                         "yang sudah ada di l0_raw.ig_profile_apify (tanpa scraping)")
    ap.add_argument("--out", default="output/creator_classification_write_plan.json")
    args = ap.parse_args()
    prototype = EVIDENCE_MODES[args.evidence]
    tahun = date.today().year
    conn = psycopg2.connect(connect_timeout=10, **load_config().postgres.as_connect_kwargs())
    try:
        if args.verify:
            conn.set_session(readonly=True)
            print_verify(verify(conn, prototype, args.evidence, tahun))
            return 0
        write = args.rehearse or args.commit
        if not write:
            conn.set_session(readonly=True)
        with conn.cursor() as cur:
            before = snapshot(cur) if not write else None
            if write:   # gagal cepat kalau ada transaksi lain yang memegang lock tabel target
                cur.execute("SET LOCAL lock_timeout = '15s'")
        tax, rows, results, attr_ids = load_inputs(conn, prototype, tahun)
        with conn.cursor() as cur:
            state = read_state(cur)
        p = plan(tax, results, state, attr_ids, args.evidence)
        print(f"evidence mode: {args.evidence}")
        print_plan(p, len(rows))
        print_examples(rows, results)
        if not write:
            with conn.cursor() as cur:
                after = snapshot(cur)
            conn.rollback()
            same = before == after
            print(f"\nDB fingerprint before == after: {same}")
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"generated": date.today().isoformat(), "evidence": args.evidence,
                           "n_changes": p.n_changes, "kd_updates": p.kd_updates,
                           "map_inserts": p.map_inserts, "map_updates": p.map_updates, "map_deletes": p.map_deletes,
                           "invalid": p.invalid, "card_mismatch": p.card_mismatch},
                          f, ensure_ascii=False, indent=1, default=str)
            print(f"plan written: {args.out} (no database writes)")
            return 0 if same and not p.invalid else 1
        if p.invalid:
            conn.rollback()
            print("\nABORT: ada hasil tidak valid -- ROLLBACK")
            return 1

        def replan(cur):
            return plan(tax, results, read_state(cur), attr_ids, args.evidence)
        done, problems, committed = apply(conn, replan, p, commit=args.commit)
        print(f"\nwritten in transaction: {done} / candidate {p.n_changes}")
        for x in problems:
            print("  GUARD FAILED:", x)
        print("COMMIT" if committed else "ROLLBACK" + (" (guard gagal)" if problems else " (rehearse)"))
        return 0 if not problems else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
