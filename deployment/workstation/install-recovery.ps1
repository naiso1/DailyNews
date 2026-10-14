[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $env:LOCALAPPDATA 'DailyNewsRuntime'
$python = Join-Path $runtime 'venv\Scripts\pythonw.exe'
$script = Join-Path $PSScriptRoot 'run.py'
foreach ($file in @($python, $script)) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw 'DailyNews runtime is missing.' }
}
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $python -Argument ('-B "' + $script + '" --recover-if-needed') -WorkingDirectory $PSScriptRoot
$onLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
$onLogon.Delay = 'PT2M'
# The periodic trigger retries a temporarily unavailable network after sign-in.
$periodic = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 12) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'DailyNews_ResumeAfterSignIn' -Action $action -Trigger @($onLogon,$periodic) -Principal $principal -Settings $settings -Description 'Recover unpublished weekday news after sign-in; shared process lock, two attempts per edition/day, no direct mail.' -Force | Out-Null
$daily = Get-ScheduledTask -TaskName 'DailyNews_RunSearchAndUpdate' -ErrorAction SilentlyContinue
if ($daily) {
    # The previous seven-hour limit can kill the launcher just before exterior finishes.
    $daily.Settings.ExecutionTimeLimit = 'PT12H'
    try {
        Set-ScheduledTask -TaskName $daily.TaskName -Settings $daily.Settings | Out-Null
        Write-Output 'DAILYNEWS_NIGHTLY_LIMIT_12H'
    } catch {
        if ($_.CategoryInfo.Category -ne 'PermissionDenied') { throw }
        Write-Warning 'The existing nightly task is protected; its limit is unchanged. The recovery task uses 12 hours and checks for surviving children.'
    }
}
Write-Output 'DAILYNEWS_RECOVERY_INSTALLED'
