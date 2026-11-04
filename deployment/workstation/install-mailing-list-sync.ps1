[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$runtime = Join-Path $env:LOCALAPPDATA "DailyNewsRuntime"
$python = Join-Path $runtime "venv\Scripts\pythonw.exe"
$script = Join-Path $PSScriptRoot "sync-mailing-list.py"
$task = "DailyNews_ExteriorMailingListSync"
$action = New-ScheduledTaskAction -Execute $python -Argument ('-B "' + $script + '"') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '07:50'
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
# Keep the installed task name so upgrades cannot leave two syncing tasks running.
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Enroll new room members and refresh recipients at 07:50 on weekdays before daily mail; no mail sending." -Force | Out-Null
Write-Output "EDITION_MAILING_LIST_SYNC_INSTALLED"
