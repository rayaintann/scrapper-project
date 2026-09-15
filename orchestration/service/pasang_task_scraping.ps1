<#
.SYNOPSIS
    Memasang SATU Scheduled Task untuk satu prosedur scraping.

.DESCRIPTION
    Mengikuti pola `pasang_task_windows.ps1` di folder yang sama: TaskPath
    '\KOL Pipeline\', RunLevel Limited, MultipleInstances IgnoreNew.

    BEDANYA: script ini memasang SATU task per pemanggilan, dan jadwalnya
    WAJIB diberikan. Tidak ada jadwal bawaan.

    KENAPA TIDAK ADA JADWAL BAWAAN
    ==============================
    Cadence (harian? mingguan? bulanan?), cakupan KOL (berapa akun per run?),
    dan budget Apify BELUM ditentukan — ketiganya keputusan bisnis. Memasang
    default di sini akan membekukan keputusan yang belum diambil, dan default
    yang salah pada prosedur berbiaya adalah default yang mahal.

    Jadi script ini menyediakan MEKANISMEnya, dan angkanya diisi saat memasang.
    Mengubah cadence nanti tidak perlu menyentuh satu baris pun kode scraping:
    cukup pasang ulang task dengan `-Jadwal` yang berbeda.

    MultipleInstances IgnoreNew memberi lapis pertama perlindungan bentrok di
    tingkat Task Scheduler; `run_lock.py` di dalam Python memberi lapis kedua
    yang juga bekerja ketika prosedur yang sama dijalankan manual dari terminal.

.PARAMETER Prosedur
    'profile-ig', 'profile-tt', 'post-ig', 'post-tt', atau 'followers'.

.PARAMETER Jadwal
    'Harian', 'Mingguan', atau 'Sekali'. WAJIB — tidak ada default.

.PARAMETER Jam
    Waktu mulai, format HH:mm. Default '02:00' (di luar jam kerja).

.PARAMETER HariMingguan
    Untuk -Jadwal Mingguan. Default 'Sunday'.

.PARAMETER Argumen
    Argumen untuk script Python sebagai SATU string dipisah spasi —
    DI SINILAH cakupan ditentukan. Contoh: '--limit 50 --order stale'

.PARAMETER Pengguna
    Default: pengguna saat ini.

.EXAMPLE
    # Uji dulu tanpa biaya: dry-run tiap hari 02:00
    .\pasang_task_scraping.ps1 -Prosedur followers -Jadwal Harian `
        -Argumen '--limit-akun 5 --dry-run'

.EXAMPLE
    # Setelah cadence & budget diputuskan
    .\pasang_task_scraping.ps1 -Prosedur post-ig -Jadwal Mingguan -Jam '03:00' `
        -Argumen '--limit 50 --order stale --max-charge-usd 2.00'
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('profile-ig', 'profile-tt', 'post-ig', 'post-tt', 'followers')]
    [string]$Prosedur,

    [Parameter(Mandatory = $true)]
    [ValidateSet('Harian', 'Mingguan', 'Sekali')]
    [string]$Jadwal,

    [ValidatePattern('^\d{2}:\d{2}$')]
    [string]$Jam = '02:00',

    [ValidateSet('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')]
    [string]$HariMingguan = 'Sunday',

    [string]$Argumen = '',

    [string]$Pengguna = "$env:USERDOMAIN\$env:USERNAME"
)

$ErrorActionPreference = 'Stop'

$ServiceDir = $PSScriptRoot
$Launcher   = Join-Path $ServiceDir 'jalankan_scraping.ps1'
$TaskPath   = '\KOL Pipeline\'
$Nama       = "KOL Scrape $Prosedur"

if (-not (Test-Path $Launcher)) {
    throw "Launcher tidak ditemukan: $Launcher"
}

# Satu string berkutip, bukan array: Task Scheduler menyimpan action-nya
# sebagai SATU baris perintah, dan array PowerShell tidak selamat melewati
# batas itu (berubah jadi token berkoma yang ditolak argparse dengan exit 2).
$argLauncher = @('-Prosedur', $Prosedur)
if ($Argumen -and $Argumen.Trim()) {
    $argLauncher += @('-Argumen', "`"$($Argumen.Trim())`"")
}

# NAMA SENGAJA BUKAN `$argumen`: PowerShell tidak membedakan huruf besar-kecil
# pada nama variabel, jadi `$argumen` akan MENIMPA parameter `$Argumen` dan
# membuat deskripsi task mencatat baris perintah PowerShell, bukan cakupan
# yang diminta.
$argPowershell = @(
    '-NoProfile'
    '-NonInteractive'
    '-WindowStyle', 'Hidden'
    '-ExecutionPolicy', 'Bypass'
    '-File', "`"$Launcher`""
) + $argLauncher

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ($argPowershell -join ' ') `
    -WorkingDirectory (Split-Path -Parent $ServiceDir)

$trigger = switch ($Jadwal) {
    'Harian'   { New-ScheduledTaskTrigger -Daily -At $Jam }
    'Mingguan' { New-ScheduledTaskTrigger -Weekly -DaysOfWeek $HariMingguan -At $Jam }
    'Sekali'   { New-ScheduledTaskTrigger -Once -At $Jam }
}

# MultipleInstances IgnoreNew: kalau run sebelumnya belum selesai saat jadwal
# berikutnya tiba, Task Scheduler TIDAK memulai yang kedua. Ini lapis pertama;
# run_lock.py adalah lapis kedua yang juga menjaga pemanggilan manual.
#
# ExecutionTimeLimit 6 jam: berbeda dari task Dagster yang sengaja tanpa batas.
# Prosedur ini SELESAI, jadi yang menggantung berarti macet, dan proses macet
# yang memegang kunci akan memblokir semua run berikutnya.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6)

$principal = New-ScheduledTaskPrincipal `
    -UserId $Pengguna `
    -LogonType Interactive `
    -RunLevel Limited

$deskripsi = "Menjalankan $Prosedur lewat jalankan_scraping.ps1. " +
             "Cakupan: $Argumen. " +
             "Concurrency dijaga run_lock.py; log per akun masuk public.scheduler_logs."

Register-ScheduledTask `
    -TaskName $Nama `
    -TaskPath $TaskPath `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description $deskripsi `
    -Force | Out-Null

Write-Output "Terpasang : $TaskPath$Nama"
Write-Output "  jadwal  : $Jadwal $Jam$(if ($Jadwal -eq 'Mingguan') { " ($HariMingguan)" })"
Write-Output "  perintah: jalankan_scraping.ps1 -Prosedur $Prosedur $Argumen"
Write-Output ""
Write-Output "Uji sekarang tanpa menunggu jadwal:"
Write-Output "  Start-ScheduledTask -TaskPath '$TaskPath' -TaskName '$Nama'"
Write-Output "Lepas lagi:"
Write-Output "  Unregister-ScheduledTask -TaskPath '$TaskPath' -TaskName '$Nama' -Confirm:`$false"
