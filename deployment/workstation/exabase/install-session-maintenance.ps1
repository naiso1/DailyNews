[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $env:LOCALAPPDATA 'DailyNewsRuntime'
$python = Join-Path $runtime 'venv\Scripts\pythonw.exe'
$consolePython = Join-Path $runtime 'venv\Scripts\python.exe'
$script = Join-Path $PSScriptRoot 'maintain-session.py'
foreach ($file in @($python, $consolePython, $script)) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw 'The processing runtime is not installed.' }
}
& $consolePython -B $script --validate-only
if ($LASTEXITCODE -ne 0) { throw 'Session maintenance requires the enabled processing workstation and installed exaBase runtime.' }
$action = New-ScheduledTaskAction -Execute $python -Argument ('-B "' + $script + '"') -WorkingDirectory $PSScriptRoot
# Use :10/:40, away from the 00:00 news task. No wake or catch-up storm after sleep.
$trigger = New-ScheduledTaskTrigger -Once -At ([datetime]::Today.AddMinutes(10)) -RepetitionInterval (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'DailyNews_ExaBaseSessionMaintenance' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Check and save refreshed exaBase authentication every 30 minutes; no image generation or mail; skip while DailyNews runs.' -Force | Out-Null
Write-Output 'EXABASE_SESSION_MAINTENANCE_INSTALLED'
