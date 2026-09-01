<#
.SYNOPSIS
    Menghentikan dan mencopot Scheduled Task Dagster yang dipasang
    `pasang_task_windows.ps1`.

.DESCRIPTION
    Hanya menyentuh dua task di folder `\KOL Pipeline\`. Tidak menghapus
    DAGSTER_HOME, riwayat run, status sensor, maupun data apa pun di database.
    Setelah dicopot, sensor berhenti dievaluasi sampai daemon dijalankan lagi.

.EXAMPLE
    .\orchestration\service\copot_task_windows.ps1
#>
$ErrorActionPreference = 'Stop'

$TaskPath = '\KOL Pipeline\'
$Nama = @('KOL Dagster Daemon', 'KOL Dagster Webserver', 'KOL Dagster Code Server')

foreach ($n in $Nama) {
    $task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $n -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Output "  lewati    : $TaskPath$n (tidak terpasang)"
        continue
    }
    if ($task.State -eq 'Running') {
        Stop-ScheduledTask -TaskPath $TaskPath -TaskName $n
    }
    Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $n -Confirm:$false
    Write-Output "  dicopot   : $TaskPath$n"
}

# Proses yang sudah terlanjur hidup tidak ikut mati saat task di-unregister.
$sisa = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like '*dagster._daemon*' -or $_.CommandLine -like '*dagster_webserver*' -or $_.CommandLine -like '*api grpc*'
}
if ($sisa) {
    Write-Output ""
    Write-Output "Proses Dagster yang masih hidup (hentikan manual bila perlu):"
    $sisa | ForEach-Object { Write-Output ("  PID {0}" -f $_.ProcessId) }
}

Write-Output ""
Write-Output "DAGSTER_HOME, riwayat run, dan status sensor TIDAK dihapus."
