$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$python=Join-Path $env:LOCALAPPDATA 'DailyNewsRuntime/venv/Scripts/pythonw.exe'
if (-not(Test-Path -LiteralPath $python)) {throw 'DailyNews runtime pythonw.exe was not found.'}
$script=Join-Path $PSScriptRoot 'run_scheduled.py'
$action=New-ScheduledTaskAction -Execute $python -Argument ('"'+$script+'"') -WorkingDirectory $repo
$triggers=@((New-ScheduledTaskTrigger -Daily -At '08:35'),(New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"))
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal=New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'DailyNewsWeeklyUsageReport' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'Collect private group usage at 08:35 and sign-in. Weekly email is a separate Monday 09:00 cloud flow, test recipient Nakamura only.' -Force | Select-Object TaskName,State
