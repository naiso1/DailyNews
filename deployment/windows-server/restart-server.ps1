[CmdletBinding()]
param(
    [ValidateSet('interior', 'exterior')][string]$Edition = 'interior'
)
$ErrorActionPreference = 'Stop'
$exterior = $Edition -eq 'exterior'
$taskName = if ($exterior) { 'DailyNewsExteriorServer' } else { 'DailyNewsServer' }
$root = 'C:\Users\Administrator\Desktop\' + $(if ($exterior) { 'DailyNewsExterior' } else { 'DailyNews' })
$entry = Join-Path $root $(if ($exterior) { 'app\start-exterior.ps1' } else { 'app\server.js' })
$port = if ($exterior) { 8084 } else { 8082 }

# Task Scheduler's COM API does not depend on the CIM provider used by
# Get/Stop/Start-ScheduledTask. Preserve the registered task, identity and triggers.
$scheduler = New-Object -ComObject 'Schedule.Service'
$scheduler.Connect()
$task = $scheduler.GetFolder('\').GetTask($taskName)
$actions = $task.Definition.Actions
if ($actions.Count -ne 1 -or !$actions.Item(1).Arguments.Contains($entry)) {
    throw "Unexpected action for $taskName; refusing to stop another application."
}
if (!(Test-Path -LiteralPath $entry -PathType Leaf)) { throw "Server entry point missing: $entry" }
$task.Stop(0)
$deadline = (Get-Date).AddSeconds(20)
do {
    $listening = @([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -eq $port }).Count -gt 0
    if (!$listening -and $task.State -ne 4) { break }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)
if ($listening -or $task.State -eq 4) { throw "$taskName did not stop within 20 seconds." }
[void]$task.Run($null)
Write-Output "SERVER_RESTART_REQUESTED $Edition"
