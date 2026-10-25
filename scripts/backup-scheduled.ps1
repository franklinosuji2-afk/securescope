# Weekly backup, run by Windows Task Scheduler (set up once with setup-backup-schedule.ps1).
# It reads the READ-ONLY database connection string from a file that Windows encrypts for your user account
# on this PC only, runs backup-db.ps1, keeps the newest backups and writes one line to backups\backup-log.txt.
# The connection string is never printed or logged. On a failure a message box appears and the log says why.
#
#   .\scripts\backup-scheduled.ps1 -CheckOnly   # checks everything except the dump itself
param([int]$Keep = 8, [switch]$CheckOnly)
$ErrorActionPreference = "Stop"
if ($Keep -lt 3) { $Keep = 3 }   # never keep fewer than three, so one bad run cannot leave you with nothing

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backups = Join-Path $repo "backups"
New-Item -ItemType Directory -Force -Path $backups | Out-Null
$log = Join-Path $backups "backup-log.txt"
$secretFile = Join-Path $env:LOCALAPPDATA "SecureScope\backup-url.txt"

function Test-Docker {
    # Native commands write errors to stderr; with "Stop" that would end the script, so relax it for this check.
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { docker info 2>&1 | Out-Null; return ($LASTEXITCODE -eq 0) }
    finally { $ErrorActionPreference = $old }
}

function Write-Log([string]$status, [string]$message) {
    $line = "{0} {1} {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $status, $message
    Add-Content -Path $log -Value $line
    Write-Host $line
}

try {
    if (-not (Test-Path $secretFile)) { throw "No stored connection string. Run scripts\setup-backup-schedule.ps1 first." }
    if (-not (Test-Docker)) { throw "Docker Desktop is not running." }

    $secure = Get-Content $secretFile | ConvertTo-SecureString   # only this Windows user on this PC can decrypt it
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $env:SECURESCOPE_BACKUP_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

    if ($CheckOnly) { Write-Host "Check passed: Docker is running and the stored connection string can be read." -ForegroundColor Green; return }

    $before = @(Get-ChildItem $backups -Filter "securescope-*.dump" -ErrorAction SilentlyContinue).Name
    & (Join-Path $PSScriptRoot "backup-db.ps1")
    $new = Get-ChildItem $backups -Filter "securescope-*.dump" | Where-Object { $before -notcontains $_.Name } | Sort-Object LastWriteTime | Select-Object -Last 1
    if (-not $new -or $new.Length -lt 1024) { throw "No new backup file was written, or it is empty." }

    # Remove the oldest dumps only after a new one exists and was checked readable by backup-db.ps1.
    $old = Get-ChildItem $backups -Filter "securescope-*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep
    foreach ($file in $old) { Remove-Item $file.FullName -Force }
    $kept = @(Get-ChildItem $backups -Filter "securescope-*.dump").Count
    Write-Log "OK" ("{0} ({1} bytes), {2} backups kept" -f $new.Name, $new.Length, $kept)
}
catch {
    $reason = $_.Exception.Message
    Write-Log "FAILED" $reason
    if (-not $CheckOnly) {
        try {
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show("The SecureScope backup failed: $reason`nSee backups\backup-log.txt.", "SecureScope backup") | Out-Null
        } catch { }
    }
    exit 1
}
finally {
    Remove-Item Env:SECURESCOPE_BACKUP_URL -ErrorAction SilentlyContinue
}
