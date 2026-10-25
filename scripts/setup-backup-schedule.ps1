# One-time setup of the weekly backup. Run it yourself in PowerShell (it asks for the connection string):
#
#   .\scripts\setup-backup-schedule.ps1
#
# 1. Asks for the connection string of the READ-ONLY backup role (typed hidden, never shown or saved in plain text).
# 2. Refuses it if that role could write anything (it checks the database itself).
# 3. Stores it encrypted for your Windows user on this PC only (%LOCALAPPDATA%\SecureScope\backup-url.txt).
# 4. Creates the scheduled task "SecureScope weekly backup". It runs while you are signed in to Windows and
#    Docker Desktop is running; if the PC was off at the time, it runs at the next start (StartWhenAvailable).
param([string]$Day = "Sunday", [string]$Time = "21:00", [int]$Keep = 8)
$ErrorActionPreference = "Stop"

function Test-Docker {
    # Native commands write errors to stderr; with "Stop" that would end the script, so relax it for this check.
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { docker info 2>&1 | Out-Null; return ($LASTEXITCODE -eq 0) }
    finally { $ErrorActionPreference = $old }
}
if (-not (Test-Docker)) { throw "Start Docker Desktop first." }

$secure = Read-Host "Paste the READ-ONLY connection string (hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ($plain -notmatch '^postgres(ql)?(\+psycopg)?://[^:@/\s]+:[^@\s]+@\S+$') { throw "That does not look like a PostgreSQL connection string." }
if ($plain -match '-pooler\.') { throw "Use the direct connection string (the host name without '-pooler'): pg_dump needs it." }
$url = $plain -replace '^postgresql\+psycopg://', 'postgresql://' -replace '^postgres://', 'postgresql://'

# The role must be unable to write. Ask the database itself rather than trusting the name.
$sql = "select coalesce((select bool_or(has_table_privilege(current_user, c.oid, 'INSERT') or has_table_privilege(current_user, c.oid, 'UPDATE') or has_table_privilege(current_user, c.oid, 'DELETE')) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind = 'r'), false) or pg_has_role(current_user, 'pg_write_all_data', 'member') or exists (select 1 from pg_roles where rolname = current_user and (rolsuper or rolcreaterole or rolcreatedb)) as can_write"
$env:PGURL = $url
$strict = $ErrorActionPreference
$ErrorActionPreference = "Continue"   # a failed connection is reported by our own message below
try {
    # The SQL goes in through standard input and the URL through the environment, so neither needs quoting
    # on a command line (and "set -f" stops the shell from treating * or ? in a password as a pattern).
    $answer = $sql | docker run --rm -i -e PGURL postgres:18-alpine sh -c 'set -f; psql $PGURL -At'
    if ($LASTEXITCODE -ne 0) { throw "Could not connect with that connection string. Check the user, password and host." }
}
finally { $ErrorActionPreference = $strict; Remove-Item Env:PGURL -ErrorAction SilentlyContinue }
if ("$answer".Trim() -ne "f") { throw "This role can change data or has administrator rights. Create the read-only role (docs\OPERATIONS.md, section 2) and use its connection string. Nothing was saved." }
Write-Host "The role is read-only." -ForegroundColor Green

$dir = Join-Path $env:LOCALAPPDATA "SecureScope"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$secureUrl = ConvertTo-SecureString $url -AsPlainText -Force
$secureUrl | ConvertFrom-SecureString | Set-Content -Path (Join-Path $dir "backup-url.txt")
$plain = $null; $url = $null

$script = (Resolve-Path (Join-Path $PSScriptRoot "backup-scheduled.ps1")).Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -Keep {1}' -f $script, $Keep)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Day -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "SecureScope weekly backup" -Action $action -Trigger $trigger -Settings $settings -Description "Weekly dump of the SecureScope database with a read-only role. Log: backups\backup-log.txt" -Force | Out-Null
Write-Host "Scheduled task created: every $Day at $Time. Test it now with:  Start-ScheduledTask -TaskName 'SecureScope weekly backup'" -ForegroundColor Green
