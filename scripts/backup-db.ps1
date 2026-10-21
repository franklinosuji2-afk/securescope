# Takes a logical backup of the production database and checks that the file is readable.
# Needs Docker Desktop running. The connection string is read from an environment variable so it is never
# typed on a command line, saved in a file or pasted anywhere:
#
#   $env:SECURESCOPE_BACKUP_URL = "<Neon connection string>"   # postgresql://... (the +psycopg form also works)
#   .\scripts\backup-db.ps1
#   Remove-Item Env:SECURESCOPE_BACKUP_URL
#
# Output: backups\securescope-YYYYMMDD-HHMMSS.dump (PostgreSQL custom format). Keep backups off this repo
# folder's git history: backups\ is ignored by .gitignore. Treat the file like the database itself; it
# contains user emails and password hashes.
$ErrorActionPreference = "Stop"

if (-not $env:SECURESCOPE_BACKUP_URL) { throw "Set SECURESCOPE_BACKUP_URL first (see the comment at the top)." }
$url = $env:SECURESCOPE_BACKUP_URL -replace '^postgresql\+psycopg://', 'postgresql://'

$dir = Join-Path $PSScriptRoot "..\backups"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$dir = (Resolve-Path $dir).Path   # a plain absolute path, without ".." segments, for Docker
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$file = "securescope-$stamp.dump"

# The URL reaches the container through an inherited environment variable (-e PGURL without a value), so it
# does not appear on any command line.
$env:PGURL = $url
$dump = 'pg_dump --format=custom --no-owner --no-privileges --dbname "$PGURL" --file /out/' + $file
docker run --rm -e PGURL -v "${dir}:/out" postgres:18-alpine sh -c $dump
Remove-Item Env:PGURL
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed. No backup was made." }

# A backup that cannot be read is not a backup: list its contents.
$check = 'pg_restore --list /out/' + $file + ' > /dev/null'
docker run --rm -v "${dir}:/out" postgres:18-alpine sh -c $check
if ($LASTEXITCODE -ne 0) { throw "The backup file could not be read back. Do not rely on it." }

$size = (Get-Item (Join-Path $dir $file)).Length
Write-Host "Backup written: backups\$file ($size bytes) and verified readable." -ForegroundColor Green
Write-Host "A backup only counts once a restore has been tested: run .\scripts\restore-test.ps1 backups\$file"
