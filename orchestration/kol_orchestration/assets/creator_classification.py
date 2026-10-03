"""Asset Category + Subcategory KREATOR untuk KOL BARU ("Add New KOL").

    l1_silver.unified_profile / unified_post  (+ l0_raw profil, roster, kartu)
        -> creator_classification.classify()            (classifier existing, tidak diubah)
        -> creator_classification_writer (mode ADDITIVE)
    => public.kol_directory.inferred_category_id / inferred_subcategory_id (+ source,
       confidence, evidence) dan public.kol_attribute_map (style/personality)

        -> creator_category_bridge
    => public.kol_directory.category_id / category_ids   (field yang dibaca aplikasi)

ALUR KOL BARU
=============
"Add New KOL" menulis `l0_raw.ig/tt_profile_apify` -> `l0_raw_new_data_sensor` ->
`transform_chain_job` -> ... -> `unified_post` / `kol_profile_card` ->
`creator_classification` -> `creator_category_bridge`. Tidak ada scraper, taxonomy,
leksikon, atau ambang baru: yang dipanggil adalah classifier + writer existing.

HANYA KOL YANG BELUM PUNYA CATEGORY
===================================
Target = KOL aktif dengan `category_id`, `category_ids`, DAN `inferred_category_id`
kosong. KOL lain tidak dibaca apalagi ditulis. Writer dijalankan ADDITIVE:

    * tidak menimpa category/subcategory yang sudah ada (kurasi maupun inferred),
    * hasil Unknown tidak menulis apa pun (tidak ada pengosongan),
    * tidak ada DELETE/UPDATE atas `kol_attribute_map`.

Classifier yang tidak menemukan bukti cukup mengembalikan Unknown -- KOL itu tetap
tanpa category dan dicoba lagi pada run berikutnya (mis. setelah post-nya masuk).
Run tanpa target berhenti setelah satu SELECT.

ISOLASI
=======
Transaksi memakai REPEATABLE READ: guard writer membandingkan sidik jari sebelum
dan sesudah write, dan asset lain / "Add New KOL" boleh menulis bersamaan. Dengan
snapshot yang stabil, guard hanya menilai perubahan milik transaksi ini sendiri.
Guard gagal -> ROLLBACK -> asset gagal (tidak ada write separuh).
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

from dagster import AssetKey, Failure, MetadataValue, Output, asset

from kol_orchestration.resources import PostgresResource

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import creator_category_bridge as B  # noqa: E402
import creator_classification_writer as W  # noqa: E402

GROUP = "gold_profile"
#: Mode evidence default writer (sama dengan `one_pass.EVIDENCE_MODE`).
EVIDENCE_MODE = "l1+l0raw"
_ISOLATION = "REPEATABLE READ"

_DEPS = [AssetKey("unified_profile"), AssetKey("unified_post"), AssetKey("kol_profile_card")]


def _conn(postgres: PostgresResource):
    conn = postgres.get_conn()
    conn.set_session(isolation_level=_ISOLATION)
    return conn


def _jalankan_klasifikasi(postgres: PostgresResource) -> Output:
    conn = _conn(postgres)
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '15s'")
            target = W.unclassified_ids(cur)
        if not target:
            conn.rollback()
            return Output(0, metadata={"kol_target": 0, "baris_ditulis": 0})

        # Audiens tidak ditulis writer dan tidak ikut menentukan category: tidak dibaca.
        tax, _rows, results, attr_ids = W.load_inputs(
            conn, W.EVIDENCE_MODES[EVIDENCE_MODE], date.today().year, audience_in={}, kol_ids=target)
        with conn.cursor() as cur:
            p = W.plan(tax, results, W.read_state(cur), attr_ids, EVIDENCE_MODE, additive=True)

        hasil = {kid: res for kid, _sa, res, *_ in results}
        confidence = Counter(want["inferred_category_confidence"] for _kid, want in p.kd_updates)
        metadata = {
            "kol_target": len(target),
            "category_terisi": len(p.kd_updates),
            "subcategory_terisi": sum(1 for _k, w in p.kd_updates if w["inferred_subcategory_id"]),
            "category_unknown": len(target) - len(p.kd_updates) - len({k for k, _x in p.invalid}),
            "hasil_tidak_valid": len(p.invalid),
            "confidence": MetadataValue.json(dict(confidence)),
            "alasan_unknown": MetadataValue.json(
                {kid: hasil[kid]["category"].reason for kid in target
                 if kid in hasil and not hasil[kid]["category"].known}),
        }
        if not p.n_changes:
            conn.rollback()
            return Output(0, metadata={**metadata, "baris_ditulis": 0})

        def replan(cur):
            return W.plan(tax, results, W.read_state(cur), attr_ids, EVIDENCE_MODE, additive=True)

        done, problems, committed = W.apply(conn, replan, p, commit=True, snap=W.snapshot_directory)
        if problems:
            raise Failure(description="Guard creator_classification gagal -- ROLLBACK: "
                                      + "; ".join(problems), metadata=metadata)
        return Output(len(p.kd_updates), metadata={**metadata, "baris_ditulis": done,
                                                    "commit": committed})
    finally:
        conn.close()


def _jalankan_bridge(postgres: PostgresResource) -> Output:
    conn = _conn(postgres)
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '15s'")
            p = B.plan(B.read_candidates(cur))
        metadata = {
            "kandidat_dibridge": len(p.updates),
            "dilewati": MetadataValue.json({why: len(ids) for why, ids in p.skipped.items()}),
            "category": MetadataValue.json(
                {c.username or c.kol_id: {"category": c.category_name, "subcategory": c.subcategory_name,
                                          "confidence": c.confidence} for c in p.updates}),
        }
        if not p.updates:
            conn.rollback()
            return Output(0, metadata={**metadata, "baris_ditulis": 0})
        done, problems, committed = B.apply(conn, p, commit=True)
        if problems:
            raise Failure(description="Guard creator_category_bridge gagal -- ROLLBACK: "
                                      + "; ".join(problems), metadata=metadata)
        return Output(done, metadata={**metadata, "baris_ditulis": done, "commit": committed})
    finally:
        conn.close()


@asset(
    name="creator_classification",
    group_name=GROUP,
    deps=_DEPS,
    kinds={"postgres", "python"},
    description=(
        "public.kol_directory.inferred_category_id / inferred_subcategory_id (+ style/"
        "personality di kol_attribute_map) untuk KOL BARU yang belum punya category. "
        "Classifier + writer existing, mode additive: tidak menimpa, tidak mengosongkan, "
        "tidak menghapus. Unknown dibiarkan Unknown."
    ),
)
def creator_classification(postgres: PostgresResource) -> Output:
    return _jalankan_klasifikasi(postgres)


@asset(
    name="creator_category_bridge",
    group_name=GROUP,
    deps=[AssetKey("creator_classification")],
    kinds={"postgres", "python"},
    description=(
        "public.kol_directory.category_id / category_ids := hasil classifier "
        "(confidence high/medium), HANYA bila kedua kolom itu masih kosong. Category "
        "yang sudah terisi tidak pernah disentuh. Subcategory tetap di "
        "inferred_subcategory_id."
    ),
)
def creator_category_bridge(postgres: PostgresResource) -> Output:
    return _jalankan_bridge(postgres)


creator_classification_assets = [creator_classification, creator_category_bridge]
