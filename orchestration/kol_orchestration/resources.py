"""Dagster resources untuk pipeline KOL.

Resource di-inject ke asset (bukan dipakai sebagai global), supaya tiap asset
bisa diuji sendiri tanpa menyentuh database sungguhan.

Baru satu resource di Fase 0:
  - PostgresResource : koneksi ke database `kol`
                       (schema l0_raw, l0_harmonization, l0_extra, l1_silver,
                       feature, public).

KEAMANAN: kredensial TIDAK PERNAH ditulis di kode. Semuanya dari environment
variable, dibaca di repository.py. File `.env` sudah masuk .gitignore.

CATATAN PENTING — beda procedure vs function di database `kol`:

    l0_harmonization.sp_sync_*()   adalah PROCEDURE  -> dipanggil `CALL ...`
    l1_silver.sp_build_unified_*() adalah FUNCTION   -> dipanggil `SELECT ...`

Keduanya tidak bisa saling menggantikan: `CALL` ke function akan gagal, begitu
juga sebaliknya. Karena itu resource ini menyediakan dua method terpisah
(`call_procedure` dan `call_function`), bukan satu method serbaguna yang
gampang salah pakai.

Ini berbeda dari project referensi (database `tsdb`) yang seluruh pengisi
Silver-nya berupa procedure.
"""

from __future__ import annotations

from dagster import ConfigurableResource
import psycopg2


class PostgresResource(ConfigurableResource):
    """Pembungkus koneksi psycopg2 ke database `kol`."""

    connection_string: str          # di-inject dari environment di repository.py
    connect_timeout: int = 15

    # --- koneksi -----------------------------------------------------------

    def get_conn(self):
        """Koneksi baru. Pemanggil bertanggung jawab menutupnya."""
        return psycopg2.connect(self.connection_string, connect_timeout=self.connect_timeout)

    # --- pemanggil transformasi -------------------------------------------

    def call_procedure(self, proc_call: str) -> None:
        """Jalankan PROCEDURE. Contoh:

            CALL l0_harmonization.sp_sync_instagram_post()

        Dipakai layer harmonization. Autocommit dimatikan lalu commit manual,
        supaya kegagalan di tengah tidak menyisakan hasil separuh.
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(proc_call)
            conn.commit()
        finally:
            conn.close()

    def call_function(self, func_call: str) -> None:
        """Jalankan FUNCTION yang mengembalikan void. Contoh:

            SELECT l1_silver.sp_build_unified_post()

        Dipakai layer L1 Silver di database `kol`. Sengaja dipisah dari
        `call_procedure` karena sintaksnya memang berbeda dan salah pilih
        akan gagal saat runtime, bukan saat review.
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(func_call)
            conn.commit()
        finally:
            conn.close()

    # --- pembantu metadata -------------------------------------------------

    def count_rows(self, table_name: str) -> int:
        """Jumlah baris satu tabel, untuk metadata Dagster.

        `table_name` HARUS schema-qualified, mis. 'l1_silver.unified_post'.
        Nilainya di-interpolasi ke SQL, jadi hanya boleh diisi konstanta dari
        kode — jangan pernah dari input pengguna.
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {table_name}")
                return cur.fetchone()[0]
        finally:
            conn.close()

    def scalar(self, sql: str, params: tuple | None = None):
        """Ambil satu nilai dari satu query. Untuk pengecekan ringan di asset,
        mis. menghitung ukuran sampel sebelum memutuskan menulis atau tidak."""
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                row = cur.fetchone()
                return row[0] if row else None
        finally:
            conn.close()
