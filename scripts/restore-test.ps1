# Proves a backup works: restores it into a throw-away local PostgreSQL container and prints row counts.
# Usage: .\scripts\restore-test.ps1 backups\securescope-YYYYMMDD-HHMMSS.dump
# Needs Docker Desktop running. Nothing is sent anywhere and the container is deleted at the end.
param([Parameter(Mandatory = $true)][string]$BackupFile)
$ErrorActionPreference = "Stop"

$full = (Resolve-Path $BackupFile).Path
$dir = Split-Path $full
$name = Split-Path $full -Leaf
$container = "securescope-restore-test"

# Remove a leftover container from an earlier run (checked first, so no error output is needed).
$left = docker ps -aq --filter "name=^$container$"
if ($left) { docker rm -f $container | Out-Null }
docker run -d --name $container -e POSTGRES_PASSWORD=restore-test-only -e POSTGRES_DB=restore postgres:18-alpine | Out-Null
try {
    for ($i = 0; $i -lt 30; $i++) {
        docker exec $container pg_isready -h 127.0.0.1 -U postgres -d restore | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    docker cp $full "${container}:/tmp/$name"
    docker exec $container pg_restore --no-owner --no-privileges -U postgres -d restore --exit-on-error "/tmp/$name"
    if ($LASTEXITCODE -ne 0) { throw "Restore failed." }

    Write-Host "`nRow counts after restore:" -ForegroundColor Cyan
    $sql = "select relname || ': ' || (xpath('/row/c/text()', query_to_xml('select count(*) as c from ' || quote_ident(relname), false, true, '')))[1]::text from pg_stat_user_tables order by relname"
    docker exec $container psql -U postgres -d restore -Atc $sql
    docker exec $container psql -U postgres -d restore -Atc "select 'schema version: ' || version_num from alembic_version"
    Write-Host "`nRestore test passed." -ForegroundColor Green
}
finally {
    docker rm -f $container | Out-Null
}
