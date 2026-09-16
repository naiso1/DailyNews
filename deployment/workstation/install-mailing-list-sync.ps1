[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$runtime = Join-Path $env:LOCALAPPDATA "DailyNewsRuntime"
$python = Join-Path $runtime "venv\Scripts\pythonw.exe"
$script = Join-Path $PSScriptRoot "sync-mailing-list.py"
$task = "DailyNews_ExteriorMailingListSync"
$action = New-ScheduledTaskAction -Execute $python -Argument ('-B "' + $script + '"') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -MultipleInstances IgnoreNew
# Keep the installed task name so upgrades cannot leave two syncing tasks running.
Register-ScheduledTask -TaskName $task -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Refresh interior and exterior opt-in recipients every two minutes; no news collection or mail sending." -Force | Out-Null
Write-Output "EDITION_MAILING_LIST_SYNC_INSTALLED"
