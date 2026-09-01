<#
.SYNOPSIS
    Menjalankan satu proses Dagster (codeserver, daemon, atau webserver)
    sebagai background process yang persistent di Windows.

.DESCRIPTION
    Script ini TIDAK dipanggil manual sehari-hari. Ia adalah action dari
    Scheduled Task yang dipasang `pasang_task_windows.ps1`, dan itulah yang
    membuat Dagster hidup tanpa siapa pun membuka terminal.

    Perannya ada tiga; DUA yang wajib dan harus hidup bersamaan:

        codeserver  WAJIB. Server gRPC yang memuat `kol_orchestration.repository`
                    SEKALI lalu melayani daemon dan webserver. Tanpa ini
                    `workspace.yaml` tidak bisa di-resolve dan daemon tidak
                    menemukan code location mana pun.

        daemon      WAJIB. Inilah yang mengevaluasi `l0_raw_new_data_sensor`
                    tiap 60 detik dan meluncurkan `transform_chain_job` ketika
                    ada data baru di l0_raw. Tanpa proses ini sensor tidak
                    pernah jalan, seberapa pun statusnya RUNNING di UI.

        webserver   OPSIONAL. Hanya UI di http://127.0.0.1:3000. Sensor tetap
                    bekerja walau ini dimatikan.

    URUTAN: `codeserver` harus start lebih dulu. Daemon akan mencoba menyambung
    ulang kalau server belum siap, tapi tick-tick awalnya akan gagal.

    KENAPA BUKAN `dagster dev`
    ==========================
    `dagster dev` adalah alat pengembangan: ia mati begitu terminal yang
    memanggilnya ditutup, dan tidak punya kebijakan restart. Dua proses
    terpisah lewat Scheduled Task memberi tiga hal yang `dagster dev` tidak
    bisa: hidup lagi otomatis setelah login, restart sendiri kalau crash, dan
    UI bisa dimatikan tanpa mematikan sensor.

    TIDAK ADA SCRAPING DI SINI
    ==========================
    Script ini tidak pernah memanggil Apify, `scheduler_engine.py`, atau
    `one_shot_scrape_job`. Yang bisa dijalankan sensor hanya
    `transform_chain_job` — SQL transformasi murni. Scraping tetap jalur
    terpisah yang Anda kendalikan sendiri.

.PARAMETER Peran
    'codeserver', 'daemon' (default), atau 'webserver'.

.PARAMETER Port
    Port webserver. Diabaikan selain Peran = webserver. Default 3000.

.PARAMETER PortCodeServer
    Port code server gRPC. Harus sama dengan `port` di workspace.yaml.
    Default 4266.

.EXAMPLE
    # Uji manual di foreground (Ctrl+C untuk berhenti)
    .\orchestration\service\jalankan_dagster.ps1 -Peran daemon
#>
param(
    [ValidateSet('codeserver', 'daemon', 'webserver')]
    [string]$Peran = 'daemon',

    [int]$Port = 3000,

    [int]$PortCodeServer = 4266
)

$ErrorActionPreference = 'Stop'

# service/ -> orchestration/ -> root project
$Orchestration = Split-Path -Parent $PSScriptRoot
$Root          = Split-Path -Parent $Orchestration

$DagsterHome = Join-Path $Orchestration '.dagster_home'
$Scripts     = Join-Path $Root 'venv\Scripts'
$LogDir      = Join-Path $DagsterHome 'service_logs'

# DAGSTER_HOME wajib dan harus folder TETAP. Tanpa ini Dagster memakai folder
# sementara acak, dan status sensor (RUNNING) serta cursor-nya hilang tiap
# proses restart — sensor akan mengulang tick baseline terus-menerus.
$env:DAGSTER_HOME = $DagsterHome

if (-not (Test-Path $DagsterHome)) {
    throw "DAGSTER_HOME tidak ditemukan: $DagsterHome"
}
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Rotasi sederhana: proses ini hidup berbulan-bulan, log mentahnya tidak boleh
# tumbuh tanpa batas. Satu generasi cadangan sudah cukup untuk diagnosa.
#
# stdout dan stderr dipisah karena `Start-Process` tidak bisa mengarahkan
# keduanya ke file yang sama. Lihat catatan di bawah soal kenapa bukan pipe.
# `Start-Process` MENIMPA file redirect-nya, tidak bisa append. Jadi keluaran
# proses ditulis ke file per-sesi (`.log` / `.err.log`, ditimpa tiap start,
# generasi sebelumnya disimpan sebagai `.1`), sementara riwayat start/stop
# dikumpulkan terpisah di `$Peran.run.log` yang memang di-append.
$LogOut   = Join-Path $LogDir "$Peran.log"
$LogErr   = Join-Path $LogDir "$Peran.err.log"
$LogSiklus = Join-Path $LogDir "$Peran.run.log"

foreach ($f in @($LogOut, $LogErr)) {
    if (Test-Path $f) { Move-Item $f "$f.1" -Force }
}
if ((Test-Path $LogSiklus) -and ((Get-Item $LogSiklus).Length -gt 5MB)) {
    Move-Item $LogSiklus "$LogSiklus.1" -Force
}

$exe, $argumen = switch ($Peran) {
    'codeserver' {
        # SENGAJA TANPA `--heartbeat`.
        # ============================
        # Code server yang di-spawn daemon dijalankan dengan
        # `--heartbeat --heartbeat-timeout 20`, dan daemon hanya memegang code
        # location selama satu tick. Dengan sensor tiap 60 detik, ada ~40 detik
        # hening sehingga server itu mematikan diri tiap siklus lalu di-spawn
        # ulang — mengimpor ulang seluruh modul yang berat setiap kali.
        # `DAEMON_GRPC_SERVER_HEARTBEAT_TTL` di Dagster hardcoded 20 detik dan
        # tidak ada opsi dagster.yaml untuk mengubahnya.
        #
        # Server yang dijalankan di sini tidak punya flag itu, jadi ia hidup
        # sampai dihentikan. Modul di-impor SEKALI saat start.
        #
        # `--location-name` harus sama dengan `location_name` di workspace.yaml
        # dan dengan nama lama, supaya status RUNNING dan cursor sensor tidak
        # dianggap milik location baru.
        (Join-Path $Scripts 'dagster.exe'),
        @('api', 'grpc', '-h', '127.0.0.1', '-p', "$PortCodeServer",
          '-m', 'kol_orchestration.repository',
          '--location-name', 'kol_orchestration.repository')
    }
    'daemon' {
        (Join-Path $Scripts 'dagster-daemon.exe'), @('run', '-w', 'workspace.yaml')
    }
    'webserver' {
        # -h 127.0.0.1: UI hanya bisa dibuka dari mesin ini. Dagster tidak punya
        # autentikasi bawaan, jadi mengikatnya ke 0.0.0.0 berarti siapa pun di
        # jaringan bisa meluncurkan job.
        (Join-Path $Scripts 'dagster-webserver.exe'),
        @('-h', '127.0.0.1', '-p', "$Port", '-w', 'workspace.yaml')
    }
}

if (-not (Test-Path $exe)) {
    throw "Executable tidak ditemukan: $exe. Jalankan: venv\Scripts\pip.exe install -e .\orchestration"
}

# workspace.yaml dibaca relatif terhadap folder kerja.
Set-Location $Orchestration

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] START $Peran -> $exe $($argumen -join ' ')" |
    Out-File -FilePath $LogSiklus -Append -Encoding utf8

# JANGAN pakai `& $exe | Out-File`.
# ==================================
# Pipeline PowerShell membungkus proses anak: keluarannya di-buffer di dalam
# PowerShell, dan ketika daemon mati mendadak, baris terakhir — termasuk
# traceback penyebabnya — hilang sebelum sempat ditulis. Itu persis yang terjadi
# 28 Agustus 2026: daemon berhenti di tengah tick dan log-nya putus tanpa jejak
# error, sehingga penyebabnya baru ketahuan setelah daemon dijalankan ulang
# dengan redirect biasa.
#
# `Start-Process -RedirectStandardOutput/-RedirectStandardError` menyerahkan
# handle file langsung ke proses anak, jadi tidak ada buffer PowerShell di
# tengah dan baris terakhir sebelum crash selalu sampai ke disk.
$proses = Start-Process -FilePath $exe -ArgumentList $argumen `
    -WorkingDirectory $Orchestration -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $LogOut -RedirectStandardError $LogErr

$kode = $proses.ExitCode
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] STOP $Peran exit=$kode" |
    Out-File -FilePath $LogSiklus -Append -Encoding utf8
exit $kode
