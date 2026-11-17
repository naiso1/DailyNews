[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$runtime=Join-Path $env:LOCALAPPDATA 'DailyNewsRuntime\copilot-personal'
if (!(Test-Path -LiteralPath (Join-Path $runtime 'worker.json'))) { throw 'Personal worker configuration is missing.' }
$node=(Get-Command node.exe).Source
$script=Join-Path $repo 'deployment\workstation\copilot-personal-worker.cjs'
$launcher=Join-Path $runtime 'launch-worker.vbs'
$line='CreateObject("WScript.Shell").Run """'+$node.Replace('"','""')+'"" ""'+$script.Replace('"','""')+'""", 0, False'
[IO.File]::WriteAllText($launcher,$line,[Text.Encoding]::Unicode)
$scheduler=New-Object -ComObject Schedule.Service
$scheduler.Connect()
$definition=$scheduler.NewTask(0)
$who=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$definition.Principal.UserId=$who
$definition.Principal.LogonType=3
$definition.Principal.RunLevel=0
$definition.RegistrationInfo.Description='DailyNews personal Copilot worker; current user only, hidden window, no stored Windows password.'
$definition.Settings.Enabled=$true
$definition.Settings.StartWhenAvailable=$true
$definition.Settings.DisallowStartIfOnBatteries=$false
$definition.Settings.StopIfGoingOnBatteries=$false
$definition.Settings.ExecutionTimeLimit='PT0S'
$trigger=$definition.Triggers.Create(9)
$trigger.UserId=$who
$action=$definition.Actions.Create(0)
$action.Path=Join-Path $env:WINDIR 'System32\wscript.exe'
$action.Arguments='"'+$launcher+'"'
$task=$scheduler.GetFolder('\').RegisterTaskDefinition('DailyNewsCopilotPersonal',$definition,6,$who,$null,3)
$null=$task.Run($null)
Write-Output 'COPILOT_PERSONAL_INSTALLED CurrentUser InteractiveToken Hidden'
