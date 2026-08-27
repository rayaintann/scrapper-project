"""Orkestrasi Dagster untuk pipeline KOL (database `kol`).

Struktur yang direncanakan:
    resources.py    koneksi database (Fase 0 — sudah ada)
    repository.py   Definitions: daftar asset, job, schedule, resource
    assets/         asset per layer (Fase 1 dan seterusnya)
"""
