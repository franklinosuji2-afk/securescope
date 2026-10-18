# Local audit: dependency vulnerabilities, lint, types, formatting. Run from anywhere: .\scripts\audit.ps1
# Stops at the first failing step and exits non-zero, so a green result means every check passed.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")

function Step([string]$name, [scriptblock]$run) {
    Write-Host "`n== $name ==" -ForegroundColor Cyan
    & $run
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $name" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Step "npm audit (high and above)" { npm audit --audit-level=high }
Step "ESLint" { npm run lint }
Step "TypeScript" { npm run typecheck }
Step "Prettier (check only)" { npm run format:check }

Write-Host "`nAll checks passed." -ForegroundColor Green
