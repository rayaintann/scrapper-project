<#
.SYNOPSIS
    Memasang dua Scheduled Task supaya Dagster hidup sendiri di Windows.

.DESCRIPTION
    Setelah ini dijalankan sekali, tidak ada lagi terminal yang perlu dibuka:
    daemon Dagster hidup otomatis tiap kali Anda login, termasuk sesudah
    Windows restart, dan hidup lagi sendiri kalau crash.

    TASK YANG DIPASANG
    ==================
        KOL Dagster Code Server WAJIB, dipasang selalu. Server gRPC di
                                127.0.0.1:4266 yang memuat definisi SEKALI.
                                Tanpa ini daemon tidak menemukan code location.
        KOL Dagster Daemon      WAJIB, dipasang selalu. Mengevaluasi
                                l0_raw_new_data_sensor dan meluncurkan
                                transform_chain_job saat ada data baru di l0_raw.
        KOL Dagster Webserver   OPSIONAL, hanya dengan -DenganWebserver.
                                UI di http://127.0.0.1:3000.

    KENAPA WEBSERVER TIDAK DIPASANG BAWAAN
    ======================================
    Instance ini memakai storage SQLite di DAGSTER_HOME. Kalau webserver dan
    daemon berjalan sebagai dua proses terpisah, keduanya menulis ke file SQLite
    yang sama dan di Windows itu memicu `database is locked`. 28 Agustus 2026
    daemon MATI karenanya persis di tick yang seharusnya mendeteksi data baru,
    sehingga rantai L0->L2 tidak jalan sampai daemon dihidupkan ulang sendirian.

    Daemon adalah yang wajib; UI bisa dijalankan sesekali saat dibutuhkan.
    Kalau UI memang perlu hidup terus, pindahkan storage Dagster ke Postgres
    (lihat service/README.md) -- itu menghilangkan penguncian file sepenuhnya.

    Keduanya di folder task `\KOL Pipeline\` supaya tidak tercampur dengan task
    Windows lain, dan gampang dilihat di Task Scheduler.

    KENAPA TRIGGER "AT LOG ON", BUKAN "AT STARTUP"
    ==============================================
    Trigger at-startup dan Windows Service sungguhan mengharuskan task berjalan
    sebagai SYSTEM, dan itu butuh hak administrator. Akun yang dipakai project
    ini bukan administrator, jadi yang tersedia adalah at-logon dengan hak user
    biasa. Konsekuensinya jelas dan harus disadari:

        Dagster hidup saat Anda LOGIN, bukan saat Windows menyala.

    Untuk desktop yang dipakai orang, ini memenuhi kebutuhan "hidup lagi setelah
    restart". Kalau nanti scraping dijadwalkan pada jam ketika mesin menyala
    tapi belum ada yang login, jalur upgrade-nya ada di README folder ini.

    KENAPA BUKAN `dagster dev`
    ==========================
    `dagster dev` mati bersama terminal pemanggilnya dan tidak punya kebijakan
    restart. Dua task terpisah memberi: hidup otomatis, restart saat crash, dan
    UI bisa dimatikan tanpa mematikan sensor.

    TIDAK ADA SCRAPING
    ==================
    Task ini hanya menjalankan proses Dagster. Tidak ada task scraping yang
    dibuat, tidak ada Apify yang dipanggil, dan satu-satunya job yang bisa
    dipicu sensor adalah `transform_chain_job` (SQL transformasi murni).

.PARAMETER DenganWebserver
    Ikut pasang task webserver (UI). TIDAK dipasang secara default -- lihat
    peringatan SQLite di bawah.

.PARAMETER Port
    Port webserver. Default 3000.

.EXAMPLE
    .\orchestration\service\pasang_task_windows.ps1

.NOTES
    Idempoten: menjalankannya berkali-kali hanya menimpa definisi task yang sama.
    Untuk mencopot: .\copot_task_windows.ps1
#>
param(
    [switch]$DenganWebserver,
    [int]$Port = 3000
)

$ErrorActionPreference = 'Stop'

$ServiceDir = $PSScriptRoot
$Launcher   = Join-Path $ServiceDir 'jalankan_dagster.ps1'
$TaskPath   = '\KOL Pipeline\'

if (-not (Test-Path $Launcher)) {
    throw "Launcher tidak ditemukan: $Launcher"
}

$Pengguna = "$env:USERDOMAIN\$env:USERNAME"

function Pasang-Task {
    param(
        [string]$Nama,
        [string]$Deskripsi,
        [string[]]$ArgumenLauncher
    )

    $argumen = @(
        '-NoProfile'
        '-NonInteractive'
        '-WindowStyle', 'Hidden'
        '-ExecutionPolicy', 'Bypass'
        '-File', "`"$Launcher`""
    ) + $ArgumenLauncher

    $action = New-ScheduledTaskAction `
        -Execute 'powershell.exe' `
        -Argument ($argumen -join ' ') `
        -WorkingDirectory (Split-Path -Parent $ServiceDir)

    # At-logon untuk pengguna ini. Tidak butuh hak administrator.
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $Pengguna

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5) `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit ([TimeSpan]::Zero)

    # RunLevel Limited: hak user biasa, bukan elevated. Dagster tidak butuh
    # lebih, dan proses jangka panjang sebaiknya seminim mungkin haknya.
    $principal = New-ScheduledTaskPrincipal `
        -UserId $Pengguna `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $Nama `
        -TaskPath $TaskPath `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description $Deskripsi `
        -Force | Out-Null

    Write-Output "  terpasang : $TaskPath$Nama"
}

Write-Output "Memasang Scheduled Task Dagster untuk $Pengguna"
Write-Output ""

# Code server dipasang DULU: daemon tidak bisa me-resolve workspace.yaml tanpa
# server ini hidup di 127.0.0.1:4266.
Pasang-Task `
    -Nama 'KOL Dagster Code Server' `
    -Deskripsi (
        'WAJIB. Code server gRPC di 127.0.0.1:4266 yang memuat ' +
        'kol_orchestration.repository sekali lalu melayani daemon. Dijalankan ' +
        'TANPA --heartbeat supaya tidak mematikan diri di sela tick sensor. ' +
        'TIDAK memanggil Apify dan tidak melakukan scraping.'
    ) `
    -ArgumenLauncher @('-Peran', 'codeserver')

Pasang-Task `
    -Nama 'KOL Dagster Daemon' `
    -Deskripsi (
        'WAJIB. Daemon Dagster: mengevaluasi l0_raw_new_data_sensor dan ' +
        'menjalankan transform_chain_job (L0 -> L2) saat ada data baru di ' +
        'l0_raw. TIDAK memanggil Apify dan tidak melakukan scraping.'
    ) `
    -ArgumenLauncher @('-Peran', 'daemon')

if ($DenganWebserver) {
    Pasang-Task `
        -Nama 'KOL Dagster Webserver' `
        -Deskripsi (
            "OPSIONAL. UI Dagster di http://127.0.0.1:$Port. Sensor tetap " +
            'berjalan walau task ini dimatikan. PERINGATAN: menjalankannya ' +
            'bersamaan dengan daemon di storage SQLite bisa memicu ' +
            '"database is locked" dan mematikan daemon.'
        ) `
        -ArgumenLauncher @('-Peran', 'webserver', '-Port', "$Port")
}

Write-Output ""
Write-Output "Selesai. Task berjalan otomatis tiap login (termasuk sesudah restart)."
if (-not $DenganWebserver) {
    Write-Output "Webserver TIDAK dipasang (hindari lock SQLite). Pasang dengan -DenganWebserver bila UI perlu hidup terus."
}
Write-Output "Untuk menyalakannya SEKARANG tanpa menunggu login berikutnya:"
Write-Output "    Start-ScheduledTask -TaskPath '$TaskPath' -TaskName 'KOL Dagster Code Server'"
Write-Output "    Start-ScheduledTask -TaskPath '$TaskPath' -TaskName 'KOL Dagster Daemon'"
if ($DenganWebserver) {
    Write-Output "    Start-ScheduledTask -TaskPath '$TaskPath' -TaskName 'KOL Dagster Webserver'"
}
Write-Output ""
Write-Output "Log proses: orchestration\.dagster_home\service_logs\"
