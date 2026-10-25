# Registers "SecureScope backup check": it runs backup-check.ps1 a few minutes after you sign in to Windows
# and once a day, so a missed or failed weekly backup is noticed within a day. No password or secret is involved.
#
#   .\scripts\setup-backup-check.ps1
#   .\scripts\setup-backup-check.ps1 -MaxAgeDays 9 -DailyAt 12:00
param([int]$MaxAgeDays = 9, [string]$DailyAt = "12:00")
$ErrorActionPreference = "Stop"

$script = (Resolve-Path (Join-Path $PSScriptRoot "backup-check.ps1")).Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -MaxAgeDays {1} -Quiet' -f $script, $MaxAgeDays)
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$atLogon.Delay = "PT5M"
$daily = New-ScheduledTaskTrigger -Daily -At $DailyAt
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "SecureScope backup check" -Action $action -Trigger @($atLogon, $daily) -Settings $settings -Description "Warns if the newest SecureScope database backup is older than $MaxAgeDays days or the last run failed." -Force | Out-Null
Write-Host "Scheduled task created: at sign-in (after 5 minutes) and daily at $DailyAt. Test it now with:  .\scripts\backup-check.ps1" -ForegroundColor Green
