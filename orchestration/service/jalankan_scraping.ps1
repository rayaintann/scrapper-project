<#
.SYNOPSIS
    Menjalankan SATU prosedur scraping yang sudah ada, sebagai action dari
    Scheduled Task.

.DESCRIPTION
    Script ini TIDAK berisi pipeline scraping. Ia hanya pembungkus tipis di
    atas entry point yang sudah ada di root project:

        profile-ig   -> pipeline.py
        profile-tt   -> tiktok_pipeline.py
        post-ig      -> post_pipeline.py --platform instagram
        post-tt      -> post_pipeline.py --platform tiktok
        followers    -> scrape_followers.py

    Tidak ada logika pemilihan KOL, penagihan, retry, maupun penulisan L0 di
    sini — semuanya sudah ada di script Python-nya dan tidak digandakan.

    POLANYA MENGIKUTI `jalankan_dagster.ps1` di folder yang sama: `Start-Process`
    dengan redirect langsung (bukan pipe PowerShell, yang menelan baris terakhir
    saat proses mati mendadak), rotasi satu generasi, dan `*.run.log` terpisah
    untuk riwayat lintas sesi.

    BEDANYA DENGAN DAGSTER TASK
    ===========================
    Task Dagster menjalankan proses yang hidup terus. Task ini menjalankan
    proses yang SELESAI, lalu Scheduled Task memanggilnya lagi sesuai jadwal.
    Karena itu di sini ada `-Wait`: exit code prosesnya diteruskan ke Task
    Scheduler supaya riwayat "Last Run Result" bermakna.

    CADENCE DAN CAKUPAN TIDAK DITENTUKAN DI SINI
    ============================================
    Script ini tidak punya jadwal dan tidak punya default cakupan produksi.
    Berapa sering dan seberapa banyak ditentukan saat memasang task
    (`pasang_task_scraping.ps1 -Jadwal ... -Argumen ...`), bukan di dalam kode.
    Itu disengaja: cadence, scope KOL, dan budget Apify masih menunggu
    keputusan bisnis, dan menuliskannya di sini akan membekukan keputusan yang
    belum diambil.

    CONCURRENCY
    ===========
    Tidak dijaga di sini, melainkan di `run_lock.py` yang dipakai tiap entry
    point. Kalau prosedur yang sama masih berjalan, prosesnya keluar dengan
    kode 75 dan Task Scheduler mencatatnya sebagai "sudah berjalan", bukan
    sebagai kegagalan.

.PARAMETER Prosedur
    'profile-ig', 'profile-tt', 'post-ig', 'post-tt', atau 'followers'.

.PARAMETER Argumen
    Argumen tambahan untuk script Python, sebagai SATU string dipisah spasi.
    Di sinilah cakupan ditentukan, misalnya:
        '--limit 50 --order stale --max-cost-usd 0.50'

    Sengaja string, bukan array. Task Scheduler menyimpan action-nya sebagai
    satu baris perintah, dan array PowerShell yang melewati batas itu berubah
    jadi satu token berkoma -- yang lalu ditolak argparse dengan exit 2.
    String yang dipecah di sini bertahan melewati batas itu apa adanya.

.EXAMPLE
    .\jalankan_scraping.ps1 -Prosedur followers -Argumen '--limit-akun 5 --dry-run'
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('profile-ig', 'profile-tt', 'post-ig', 'post-tt', 'followers')]
    [string]$Prosedur,

    [string]$Argumen = ''
)

$ErrorActionPreference = 'Stop'

# service/ -> orchestration/ -> root project
$Orchestration = Split-Path -Parent $PSScriptRoot
$Root          = Split-Path -Parent $Orchestration
$Python        = Join-Path $Root 'venv\Scripts\python.exe'
$LogDir        = Join-Path $Root 'output\service_logs'

if (-not (Test-Path $Python)) {
    throw "Python venv tidak ditemukan: $Python"
}
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Setiap prosedur memakai entry point yang SUDAH ADA. `--yes` dipasang di sini
# untuk dua script yang punya konfirmasi interaktif: tanpa itu, Task Scheduler
# menjalankan proses yang menunggu ketikan yang tidak akan pernah datang.
# post_pipeline.py dan scrape_followers.py memang tidak punya prompt.
$peta = @{
    'profile-ig' = @{ script = 'pipeline.py';         awal = @('--yes') }
    'profile-tt' = @{ script = 'tiktok_pipeline.py';  awal = @('--yes') }
    'post-ig'    = @{ script = 'post_pipeline.py';    awal = @('--platform', 'instagram') }
    'post-tt'    = @{ script = 'post_pipeline.py';    awal = @('--platform', 'tiktok') }
    'followers'  = @{ script = 'scrape_followers.py'; awal = @() }
}

# Dipecah di sini, satu kali, setelah selamat melewati batas Task Scheduler.
$argExtra = @()
if ($Argumen -and $Argumen.Trim()) {
    $argExtra = $Argumen.Trim() -split '\s+'
}

$pilihan   = $peta[$Prosedur]
$scriptPath = Join-Path $Root $pilihan.script
if (-not (Test-Path $scriptPath)) {
    throw "Entry point tidak ditemukan: $scriptPath"
}

$argLengkap = @($scriptPath) + $pilihan.awal + $argExtra

# Rotasi satu generasi, sama seperti jalankan_dagster.ps1. `Start-Process`
# menimpa file redirect-nya dan tidak bisa append, jadi riwayat lintas sesi
# dikumpulkan terpisah di *.run.log.
$LogOut    = Join-Path $LogDir "$Prosedur.log"
$LogErr    = Join-Path $LogDir "$Prosedur.err.log"
$LogSiklus = Join-Path $LogDir "$Prosedur.run.log"

foreach ($f in @($LogOut, $LogErr)) {
    if (Test-Path $f) { Move-Item $f "$f.1" -Force }
}
if ((Test-Path $LogSiklus) -and ((Get-Item $LogSiklus).Length -gt 5MB)) {
    Move-Item $LogSiklus "$LogSiklus.1" -Force
}

$mulai = Get-Date
Add-Content -Path $LogSiklus -Encoding utf8 -Value (
    "[{0:yyyy-MM-dd HH:mm:ss}] START {1} -> {2} {3}" -f `
        $mulai, $Prosedur, $pilihan.script, (($pilihan.awal + $argExtra) -join ' ')
)

# -Wait supaya exit code prosesnya bisa diteruskan; -NoNewWindow supaya tidak
# ada jendela yang berkedip saat task berjalan di sesi interaktif.
$proc = Start-Process -FilePath $Python `
                      -ArgumentList $argLengkap `
                      -WorkingDirectory $Root `
                      -RedirectStandardOutput $LogOut `
                      -RedirectStandardError $LogErr `
                      -NoNewWindow -Wait -PassThru

$kode    = $proc.ExitCode
$durasi  = (Get-Date) - $mulai

# 75 = run_lock.EXIT_TERKUNCI. Dibedakan dari kegagalan dengan sengaja: task
# yang dilewati karena eksekusi sebelumnya belum selesai BUKAN error, dan
# menandainya merah akan membuat orang berhenti memperhatikan riwayat task.
$label = switch ($kode) {
    0       { 'SELESAI' }
    75      { 'DILEWATI (prosedur sedang berjalan)' }
    default { "GAGAL (exit $kode)" }
}

Add-Content -Path $LogSiklus -Encoding utf8 -Value (
    "[{0:yyyy-MM-dd HH:mm:ss}] {1} {2} durasi {3:hh\:mm\:ss}" -f `
        (Get-Date), $label, $Prosedur, $durasi
)

Write-Output "$Prosedur -> $label (durasi $($durasi.ToString('hh\:mm\:ss')))"

# Exit code diteruskan APA ADANYA supaya "Last Run Result" di Task Scheduler
# mencerminkan hasil sebenarnya, termasuk kode khusus 3 (plafon biaya) dan
# 4 (sebagian akun gagal) dari scrape_followers.py.
exit $kode
