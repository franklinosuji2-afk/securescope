# Creates (or resets the password of) the READ-ONLY database role used by the weekly backup. Needs Docker Desktop.
#
#   .\scripts\create-backup-role.ps1
#
# It asks once for the normal (owner) connection string, typed hidden. It generates a random password for the
# role, runs the SQL, shows the role's flags, and copies the new read-only connection string to the clipboard so
# the password is never shown on screen. Paste it into setup-backup-schedule.ps1, then clear the clipboard.
# Running it again resets the password (use that if the password is ever exposed).
$ErrorActionPreference = "Stop"

function Test-Docker {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { docker info 2>&1 | Out-Null; return ($LASTEXITCODE -eq 0) }
    finally { $ErrorActionPreference = $old }
}
if (-not (Test-Docker)) { throw "Start Docker Desktop first." }

$secure = Read-Host "Paste the normal (owner) connection string (hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $owner = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ($owner -notmatch '^postgres(?:ql)?(?:\+psycopg)?://([^:@/\s]+):([^@\s]+)@([^/\s]+)/([^?\s]+)(\?\S*)?$') { throw "That does not look like a PostgreSQL connection string." }
# Copy every part now: later -match tests would overwrite $Matches.
$ownerUser = $Matches[1]
$ownerPassword = $Matches[2]
$hostName = $Matches[3] -replace '-pooler', ''   # pg_dump needs the direct host, not the pooled one
$db = $Matches[4]
$query = $Matches[5]
if ($db -notmatch '^[A-Za-z0-9_-]+$') { throw "Unexpected database name." }
$ownerUrl = "postgresql://" + $ownerUser + ":" + $ownerPassword + "@" + $hostName + "/" + $db + $query

$chars = [char[]]'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$pw = -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })

$template = @'
DO $do$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'backup_reader') THEN
    ALTER ROLE backup_reader WITH LOGIN PASSWORD '__PW__';
  ELSE
    CREATE ROLE backup_reader WITH LOGIN PASSWORD '__PW__';
  END IF;
END
$do$;
GRANT CONNECT ON DATABASE "__DB__" TO backup_reader;
GRANT USAGE ON SCHEMA public TO backup_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_reader;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO backup_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO backup_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO backup_reader;
SELECT 'role: ' || rolname || ', superuser: ' || rolsuper || ', createrole: ' || rolcreaterole || ', createdb: ' || rolcreatedb FROM pg_roles WHERE rolname = 'backup_reader';
'@
$sql = $template.Replace('__PW__', $pw).Replace('__DB__', $db)

$env:PGURL = $ownerUrl
$strict = $ErrorActionPreference
$ErrorActionPreference = "Continue"   # psql reports problems through its exit code, checked below
try {
    $text = $sql | docker run --rm -i -e PGURL postgres:18-alpine sh -c 'set -f; psql $PGURL -v ON_ERROR_STOP=1 -At' 2>&1 | Out-String
    $failed = ($LASTEXITCODE -ne 0)
}
finally { $ErrorActionPreference = $strict; Remove-Item Env:PGURL -ErrorAction SilentlyContinue }
# An error message can quote the SQL; hide both secrets before anything is shown.
$text = $text.Replace($pw, "<hidden>").Replace($ownerPassword, "<hidden>")
if ($failed) { Write-Host $text; throw "The role was not fully created. Nothing was copied." }
Write-Host $text.Trim()

Set-Clipboard -Value ("postgresql://backup_reader:" + $pw + "@" + $hostName + "/" + $db + $query)
$pw = $null; $owner = $null; $ownerUrl = $null; $ownerPassword = $null; $sql = $null
Write-Host "Done. The read-only connection string is on your clipboard (the password is not shown)." -ForegroundColor Green
Write-Host "Next: run .\scripts\setup-backup-schedule.ps1 and paste it (Ctrl+V) when asked, then clear the clipboard."
