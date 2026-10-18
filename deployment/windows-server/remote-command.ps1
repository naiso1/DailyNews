# Keep remote management calls bounded even when a Windows management provider hangs.
function New-DailyNewsRemoteCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Script,
        [ValidateRange(1, 1800)][int]$TimeoutSeconds = 180
    )
    $payload = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Script))
    $wrapper = @'
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$job = Start-Job -ArgumentList '__PAYLOAD__' -ScriptBlock {
    param($payload)
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    & ([scriptblock]::Create([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($payload))))
}
try {
    if (!(Wait-Job -Job $job -Timeout __TIMEOUT__)) {
        Stop-Job -Job $job
        throw 'DailyNews remote operation timed out after __TIMEOUT__ seconds.'
    }
    Receive-Job -Job $job -ErrorAction Stop
    if ($job.State -ne 'Completed') { throw 'DailyNews remote operation failed.' }
} finally {
    Remove-Job -Job $job -Force
}
'@
    $wrapper = $wrapper.Replace('__PAYLOAD__', $payload).Replace('__TIMEOUT__', [string]$TimeoutSeconds)
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($wrapper))
}
