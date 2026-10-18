$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../deployment/windows-server/remote-command.ps1')
function Assert($Condition, [string]$Message) { if (!$Condition) { throw $Message } }
function Invoke-TestRemote([string]$Script, [int]$TimeoutSeconds = 10) {
    $encoded = New-DailyNewsRemoteCommand -Script $Script -TimeoutSeconds $TimeoutSeconds
    & ([scriptblock]::Create([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($encoded))))
}
function Assert-Throws([scriptblock]$Action, [string]$Text) {
    try { & $Action | Out-Null } catch {
        Assert ($_.Exception.Message.Contains($Text)) $_.Exception.Message
        return
    }
    throw "Expected failure containing: $Text"
}
$before = @(Get-Job).Count
$value = Invoke-TestRemote 'Write-Output "verified"'
Assert ($value -eq 'verified') 'Remote output was lost.'
Assert-Throws { Invoke-TestRemote 'throw "simulated activation failure"' } 'simulated activation failure'
# A stuck management operation must be stopped, not allowed to activate later.
$marker = Join-Path $env:TEMP ('dailynews-timeout-' + [guid]::NewGuid().ToString('N'))
$escaped = $marker.Replace("'", "''")
$watch = [Diagnostics.Stopwatch]::StartNew()
Assert-Throws { Invoke-TestRemote "Start-Sleep -Seconds 5; Set-Content -LiteralPath '$escaped' -Value stale" 1 } 'timed out'
Assert ($watch.Elapsed.TotalSeconds -lt 8) 'Timeout was not bounded.'
Start-Sleep -Seconds 5
Assert (!(Test-Path -LiteralPath $marker)) 'Timed-out operation was left running.'
Assert (@(Get-Job).Count -eq $before) 'Background job leaked.'

# Test task identity guards with a fake scheduler. No real task is stopped.
$global:DailyNewsTest_stops = 0; $global:DailyNewsTest_starts = 0
$global:DailyNewsTest_action = [pscustomobject]@{ Arguments = '' }
$actions = [pscustomobject]@{ Count = 1 }
$actions | Add-Member ScriptMethod Item { param($index) return $global:DailyNewsTest_action }
$global:DailyNewsTest_task = [pscustomobject]@{ Definition = [pscustomobject]@{ Actions = $actions }; State = 3 }
$global:DailyNewsTest_task | Add-Member ScriptMethod Stop { param($flags) $global:DailyNewsTest_stops++; $this.State = 3 }
$global:DailyNewsTest_task | Add-Member ScriptMethod Run { param($args) $global:DailyNewsTest_starts++ }
$folder = [pscustomobject]@{}
$folder | Add-Member ScriptMethod GetTask { param($name) return $global:DailyNewsTest_task }
$global:DailyNewsTest_scheduler = [pscustomobject]@{ Folder = $folder }
$global:DailyNewsTest_scheduler | Add-Member ScriptMethod Connect {}
$global:DailyNewsTest_scheduler | Add-Member ScriptMethod GetFolder { param($path) return $this.Folder }
function New-Object { param($ComObject) Assert ($ComObject -eq 'Schedule.Service') 'Unexpected COM object'; return $global:DailyNewsTest_scheduler }
function Test-Path { param($LiteralPath,$PathType) return $true }
$restart = Join-Path $PSScriptRoot '../deployment/windows-server/restart-server.ps1'
foreach ($edition in @('interior','exterior')) {
    $name = if ($edition -eq 'exterior') { 'DailyNewsExterior\app\start-exterior.ps1' } else { 'DailyNews\app\server.js' }
    $global:DailyNewsTest_action.Arguments = '"C:\Users\Administrator\Desktop\' + $name + '"'
    & $restart -Edition $edition | Out-Null
}
Assert ($global:DailyNewsTest_stops -eq 2 -and $global:DailyNewsTest_starts -eq 2) 'Existing tasks were not restarted once.'
$global:DailyNewsTest_action.Arguments = '"C:\other-application\server.js"'
Assert-Throws { & $restart -Edition exterior } 'Unexpected action'
Assert ($global:DailyNewsTest_stops -eq 2 -and $global:DailyNewsTest_starts -eq 2) 'An unrelated task was stopped.'
Write-Output 'PASS: remote success/error/timeout cleanup and edition-specific restart guards'
