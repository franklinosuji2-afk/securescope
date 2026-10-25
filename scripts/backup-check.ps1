# Warns you when no recent backup exists, for example because the PC was off or Docker was not running.
# It reads no secrets and talks to no database: it only looks at the backups folder and the backup log.
# Registered by setup-backup-check.ps1 to run at sign-in and once a day.
#
#   .\scripts\backup-check.ps1              # warns if the newest dump is older than 9 days or the last run failed
#   .\scripts\backup-check.ps1 -MaxAgeDays 3
param([int]$MaxAgeDays = 9, [switch]$Quiet)
$ErrorActionPreference = "Stop"
if ($MaxAgeDays -lt 1) { $MaxAgeDays = 1 }

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backups = Join-Path $repo "backups"
$log = Join-Path $backups "backup-log.txt"

$problem = $null
$newest = $null
if (Test-Path $backups) {
    $newest = Get-ChildItem $backups -Filter "securescope-*.dump" -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -ge 1024 } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}
if (-not $newest) {
    $problem = "No backup file was found in $backups."
}
else {
    $age = (New-TimeSpan -Start $newest.LastWriteTime -End (Get-Date)).TotalDays
    if ($age -gt $MaxAgeDays) {
        $problem = "The newest backup is {0:N0} days old ({1}). The limit is {2} days." -f $age, $newest.Name, $MaxAgeDays
    }
}
if (-not $problem -and (Test-Path $log)) {
    # Skip this script's own WARNING lines, so a failed run is still seen the next day.
    $last = Get-Content $log | Where-Object { $_ -notmatch " WARNING " } | Select-Object -Last 1
    if ($last -match "^\S+ \S+ FAILED ") { $problem = "The last backup run failed. See backups\backup-log.txt." }
}

if (-not $problem) {
    if (-not $Quiet) { Write-Host ("Backups are current: {0}." -f $newest.Name) -ForegroundColor Green }
    return
}

if (Test-Path $backups) {
    Add-Content -Path $log -Value ("{0} WARNING {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $problem)
}
Write-Host "WARNING: $problem" -ForegroundColor Yellow
try {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("$problem`nRun: Start-ScheduledTask -TaskName 'SecureScope weekly backup'", "SecureScope backup check") | Out-Null
} catch { }
exit 1
