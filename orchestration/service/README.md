# Dagster persistent di Windows

Supaya `l0_raw_new_data_sensor` tetap mendeteksi data baru **tanpa siapa pun
membuka terminal** — termasuk sesudah Claude Code ditutup dan sesudah Windows
restart.

```
Scheduler scraping (jalur Anda, terpisah)
   └─► public.scheduler_logs + l0_raw
          └─► [code server + daemon Dagster]            ← proses di folder ini
                 l0_raw_new_data_sensor
                 └─► transform_chain_job
                        └─► L0 Harmonization → L1 Silver → Feature → L2 Gold
```

Proses di folder ini **tidak pernah memanggil Apify dan tidak melakukan
scraping**. Satu-satunya job yang bisa dipicu sensor adalah
`transform_chain_job`, yang isinya SQL transformasi murni.

---

## Isi folder

| File | Fungsi |
|---|---|
| `jalankan_dagster.ps1` | Menjalankan satu proses Dagster (`codeserver`, `daemon`, atau `webserver`). Dipanggil Scheduled Task, bukan manual |
| `pasang_task_windows.ps1` | Memasang Scheduled Task (code server + daemon; webserver opsional). **Jalankan sekali** |
| `copot_task_windows.ps1` | Mencopot semua task. Tidak menghapus data/riwayat apa pun |

---

## Pasang (sekali saja)

```powershell
cd D:\intern\scrapper-project
.\orchestration\service\pasang_task_windows.ps1

# nyalakan sekarang tanpa menunggu login berikutnya — code server DULU
Start-ScheduledTask -TaskPath '\KOL Pipeline\' -TaskName 'KOL Dagster Code Server'
Start-ScheduledTask -TaskPath '\KOL Pipeline\' -TaskName 'KOL Dagster Daemon'
```

Tidak butuh hak administrator.

---

## Task yang dipasang

| Task | Wajib? | Isi |
|---|---|---|
| `KOL Dagster Code Server` | **WAJIB**, selalu dipasang | `dagster api grpc` di `127.0.0.1:4266`. Memuat `kol_orchestration.repository` **sekali** lalu melayani daemon. Harus start lebih dulu |
| `KOL Dagster Daemon` | **WAJIB**, selalu dipasang | `dagster-daemon run`. **Inilah yang mengevaluasi sensor.** Tanpa proses ini sensor tidak pernah jalan, walau statusnya `RUNNING` di UI |
| `KOL Dagster Webserver` | opsional, hanya dengan `-DenganWebserver` | UI di `http://127.0.0.1:3000` |

Trigger **At log on**, restart otomatis 3× dengan jeda 5 menit kalau proses mati,
tanpa batas waktu eksekusi, jendela tersembunyi.

---

## ⚠️ Jangan jalankan webserver dan daemon bersamaan di storage SQLite

Instance ini memakai storage SQLite di `DAGSTER_HOME`. Webserver dan daemon
sebagai dua proses terpisah sama-sama menulis ke file SQLite yang sama, dan di
Windows itu memicu:

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
```

**Ini bukan teori.** 28 Agustus 2026 daemon mati karenanya persis di tick yang
seharusnya mendeteksi 11 baris baru di `l0_raw`. Rantai L0→L2 baru jalan setelah
webserver dimatikan dan daemon dihidupkan sendirian — lalu berhasil dalam satu
tick: 13 asset, 34 detik.

Karena itu webserver **tidak dipasang bawaan**. Pilihan Anda:

1. **Jalankan UI sesekali saja** (rekomendasi). Hentikan daemon, buka UI,
   tutup lagi, hidupkan daemon.
2. **Pindahkan storage Dagster ke Postgres.** Ini menghilangkan penguncian file
   sepenuhnya sehingga keduanya bisa hidup bersamaan. Tambahkan di
   `.dagster_home/dagster.yaml`:

   ```yaml
   storage:
     postgres:
       postgres_db:
         username: { env: DAGSTER_PG_USER }
         password: { env: DAGSTER_PG_PASSWORD }
         hostname: { env: DAGSTER_PG_HOST }
         db_name:  { env: DAGSTER_PG_DB }
         port: 5432
   ```

   Pakai database **tersendiri**, jangan `kol` — Dagster membuat tabelnya
   sendiri dan itu tidak boleh mencampuri schema pipeline.

---

## Kenapa code server dijalankan sebagai proses sendiri

Dulu `workspace.yaml` berisi `python_module: kol_orchestration.repository`.
Artinya tiap proses (daemon, webserver) **men-spawn code server-nya sendiri**
sebagai proses anak terkelola. Akibatnya log daemon dibanjiri:

```
dagster.code_server - WARNING - No heartbeat received in 20 seconds, shutting down
```

satu kali tiap menit, selamanya.

### Akar penyebabnya, dari sumber Dagster yang terpasang

| Fakta | Sumber |
|---|---|
| `DAEMON_GRPC_SERVER_HEARTBEAT_TTL = 20` | `dagster/_daemon/controller.py:59` |
| Code server terkelola dijalankan dengan `--heartbeat --heartbeat-timeout 20` | `grpc_server_registry.py:203` |
| *"You should ensure that any processes returned by this registry have at least one GrpcServerCodeLocation hitting the server with a heartbeat while you want the process to stay running."* | `grpc_server_registry.py:65` |
| *"Lack of any heartbeats will ensure that the server will eventually die once they're no longer being held by any threads."* | `grpc_server_registry.py:244` |
| `dagster.yaml` hanya mengenal `local_startup_timeout` dan `reload_timeout` di bawah `code_servers` — **tidak ada knob untuk TTL** | `_core/instance/config.py:572` |

Daemon memegang code location **hanya selama satu tick**. Karena
`l0_raw_new_data_sensor` dievaluasi tiap **60 detik** sementara TTL-nya **20
detik**, ada ~40 detik hening tiap siklus → server mematikan diri → tick
berikutnya men-spawn server baru dan **mengimpor ulang seluruh modul**
(`scheduler_engine`, `apify_*`, `audience_inference`). Boros, dan pernah membuat
satu tick menggantung sampai daemon harus dihidupkan ulang.

Bukti empirisnya:

| Konfigurasi | Warning |
|---|---:|
| `dagster dev` (webserver + daemon berbagi satu code server) | **0** |
| Scheduled Task daemon + webserver (masing-masing spawn sendiri) | 111 |
| Daemon sendirian, code server terkelola | tiap siklus |
| **Daemon + code server terpisah (sekarang)** | **0** |

`dagster dev` bersih bukan karena lebih baik, tapi karena webserver memegang code
location terus-menerus (TTL-nya 45 detik dan ia polling), sehingga server bersama
itu tidak pernah kelaparan heartbeat.

### Solusinya

`dagster api grpc` **tanpa** flag `--heartbeat` — tanpa flag itu server hidup
sampai dihentikan. Daemon cukup menyambung sebagai klien lewat:

```yaml
load_from:
  - grpc_server:
      host: 127.0.0.1
      port: 4266
      location_name: "kol_orchestration.repository"
```

**`location_name` WAJIB sama persis dengan nama lama.** Status sensor (`RUNNING`)
dan cursor-nya disimpan Dagster dengan kunci nama location. Kalau namanya
berubah, sensor dianggap baru: status balik ke `STOPPED` dan cursor hilang,
sehingga tick berikutnya jadi baseline lagi. Nama itu dijaga di dua tempat
(`workspace.yaml` dan `--location-name` di launcher) dan diuji di
`tests/test_l0_raw_sensor.py::CodeServerTerpisah`.

### Konsekuensi yang harus diingat

Code server memuat modul **sekali saat start**. Setelah mengubah kode di
`kol_orchestration/` (mis. `sensors.py`), **restart code server** supaya
perubahannya terpakai:

```powershell
# Restart-ScheduledTask tidak ada di modul ScheduledTasks -- Stop lalu Start.
Stop-ScheduledTask  -TaskPath '\KOL Pipeline' -TaskName 'KOL Dagster Code Server'
Start-ScheduledTask -TaskPath '\KOL Pipeline' -TaskName 'KOL Dagster Code Server'
```

Dengan `python_module` yang lama, perubahan otomatis terbaca tiap tick — itu
satu-satunya kelebihannya, dan tidak sebanding dengan biayanya.

---

## ⚠️ Kenapa launcher tidak memakai pipe PowerShell

`jalankan_dagster.ps1` memakai `Start-Process -RedirectStandardOutput/-Error`,
bukan `& $exe | Out-File`. Alasannya bukan soal gaya:

Pipeline PowerShell mem-buffer keluaran proses anak di dalam PowerShell. Ketika
daemon mati mendadak, baris terakhir — termasuk traceback penyebabnya — hilang
sebelum sempat ditulis ke disk. Log daemon 28 Agustus 2026 putus begitu saja
tanpa jejak error; penyebabnya (`database is locked`) baru ketahuan setelah
daemon dijalankan ulang dengan redirect biasa.

`Start-Process` menyerahkan handle file langsung ke proses anak, jadi tidak ada
buffer di tengah. Konsekuensinya: file redirect ditimpa tiap start (generasi
sebelumnya jadi `.1`), dan riwayat start/stop dikumpulkan terpisah.

| File | Isi |
|---|---|
| `daemon.log` | stdout sesi berjalan |
| `daemon.err.log` | stderr sesi berjalan — **log Dagster mendarat di sini** |
| `daemon.log.1` / `daemon.err.log.1` | sesi sebelumnya |
| `daemon.run.log` | riwayat START/STOP lintas sesi |

---

## Kenapa bukan `dagster dev`

`dagster dev` adalah alat pengembangan:

- mati begitu terminal pemanggilnya ditutup — persis masalah yang mau dihindari;
- tidak punya kebijakan restart kalau crash;
- webserver dan daemon terikat jadi satu, jadi mematikan UI ikut mematikan sensor.

Dua proses terpisah lewat Task Scheduler memberi ketiganya.

---

## Kenapa Scheduled Task, bukan Windows Service

Akun yang dipakai project ini **bukan administrator**. Windows Service
(`sc create`), NSSM/WinSW, dan trigger *At startup* semuanya butuh hak admin
karena harus berjalan sebagai `SYSTEM`.

Yang tersedia tanpa admin adalah Scheduled Task dengan trigger **At log on**
dan hak user biasa. Konsekuensinya harus disadari:

> **Dagster hidup saat Anda LOGIN, bukan saat Windows menyala.**

Untuk desktop yang dipakai orang, ini memenuhi "hidup lagi otomatis setelah
restart". Yang TIDAK tercakup: mesin menyala tapi belum ada yang login (mis.
server headless yang di-reboot jam 3 pagi, sementara scraping dijadwalkan
jam 4 pagi).

### Kalau nanti butuh hidup sebelum login

Perlu hak administrator, lalu **salah satu**:

1. **Ubah principal task jadi SYSTEM** — paling ringan, tanpa software baru:

   ```powershell
   # jalankan PowerShell sebagai Administrator
   $p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
   Set-ScheduledTask -TaskPath '\KOL Pipeline\' -TaskName 'KOL Dagster Daemon' -Principal $p
   # lalu ganti trigger jadi at-startup
   $t = New-ScheduledTaskTrigger -AtStartup
   Set-ScheduledTask -TaskPath '\KOL Pipeline\' -TaskName 'KOL Dagster Daemon' -Trigger $t
   ```

   Perhatikan: `.env` dibaca dari root project lewat path absolut, jadi tetap
   terbaca oleh SYSTEM. Yang perlu dicek adalah izin baca SYSTEM atas folder
   `D:\intern\scrapper-project`.

2. **NSSM** (`nssm install KOLDagsterDaemon`) kalau ingin service Windows
   sungguhan dengan kontrol `services.msc`.

---

## Setelah Windows restart — apa yang terjadi

1. Windows menyala, Anda login.
2. Task Scheduler menjalankan `KOL Dagster Daemon` (dan webserver).
3. `jalankan_dagster.ps1` men-set `DAGSTER_HOME` ke
   `orchestration\.dagster_home` — folder **tetap**, jadi:
   - status sensor `RUNNING` **tetap tersimpan**, tidak perlu di-toggle ulang;
   - **cursor sensor tetap tersimpan**, jadi sensor tidak mengulang tick
     baseline dan tidak mentransformasi ulang data lama.
4. Daemon mulai mengevaluasi sensor tiap 60 detik.
5. Begitu scraping menulis baris baru ke `l0_raw`, tick berikutnya memicu
   `transform_chain_job` sampai `l2_gold`.

Tidak ada langkah manual di antaranya.

---

## Memeriksa keadaan

```powershell
# status task
Get-ScheduledTask -TaskPath '\KOL Pipeline\' |
    ForEach-Object { $_ | Get-ScheduledTaskInfo | Select-Object TaskName, LastRunTime, LastTaskResult }

# log daemon — log Dagster mendarat di .err.log, bukan .log
Get-Content orchestration\.dagster_home\service_logs\daemon.err.log -Tail 30

# riwayat start/stop lintas sesi
Get-Content orchestration\.dagster_home\service_logs\daemon.run.log -Tail 10
```

Untuk membuka UI sesekali — hentikan daemon dulu supaya tidak bentrok SQLite:

```powershell
Stop-ScheduledTask -TaskPath '\KOL Pipeline\' -TaskName 'KOL Dagster Daemon'
.\orchestration\service\jalankan_dagster.ps1 -Peran webserver   # Ctrl+C untuk berhenti
Start-ScheduledTask -TaskPath '\KOL Pipeline\' -TaskName 'KOL Dagster Daemon'
```

Di UI: **Automation → l0_raw_new_data_sensor** menampilkan status, tick
terakhir, dan alasan skip tiap tick.

---

## Menghentikan

```powershell
# sementara
Stop-ScheduledTask  -TaskPath '\KOL Pipeline\' -TaskName 'KOL Dagster Daemon'
Disable-ScheduledTask -TaskPath '\KOL Pipeline\' -TaskName 'KOL Dagster Daemon'

# permanen
.\orchestration\service\copot_task_windows.ps1
```

Mencopot task **tidak** menghapus `DAGSTER_HOME`, riwayat run, status sensor,
maupun data di database.

---

## Yang TIDAK dipasang folder ini

- ❌ Task/schedule scraping — jalur scraping tetap milik Anda
- ❌ `ScheduleDefinition` / cron di Dagster — tetap 0
- ❌ Pemanggilan Apify dari mana pun
- ❌ Tabel logging baru — `public.scheduler_logs` tetap khusus scraping,
  state sensor tetap di cursor bawaan Dagster
