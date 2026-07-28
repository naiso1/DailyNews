[CmdletBinding()]
param(
    [string]$AllowedClient = "172.29.41.49"
)

$ErrorActionPreference = "Stop"

$root = "C:\Users\Administrator\Desktop\DailyNews"
$appDir = Join-Path $root "app"
$serverScript = Join-Path $appDir "server.js"
$node = "C:\Program Files\nodejs\node.exe"
$taskName = "DailyNewsServer"
$firewallName = "DailyNews TCP 8082"

foreach ($directory in @(
        $root,
        $appDir,
        (Join-Path $root "incoming"),
        (Join-Path $root "releases"),
        (Join-Path $root "logs"),
        (Join-Path $root "data"),
        (Join-Path $root "data\backups")
    )) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $node -PathType Leaf)) {
    throw "Node.js was not found: $node"
}
if (-not (Test-Path -LiteralPath $serverScript -PathType Leaf)) {
    throw "DailyNews server script was not found: $serverScript"
}
if (Get-NetTCPConnection -LocalPort 8082 -State Listen -ErrorAction SilentlyContinue) {
    throw "TCP port 8082 is already in use."
}

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute $node `
    -Argument ('"' + $serverScript + '"') `
    -WorkingDirectory $appDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Serves approved DailyNews releases on TCP port 8082." `
    -Force | Out-Null

Get-NetFirewallRule -DisplayName $firewallName -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
New-NetFirewallRule `
    -DisplayName $firewallName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalAddress "202.15.67.132" `
    -LocalPort 8082 `
    -RemoteAddress $AllowedClient `
    -Profile Any | Out-Null

Start-ScheduledTask -TaskName $taskName

$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 500
    $listener = Get-NetTCPConnection -LocalPort 8082 -State Listen -ErrorAction SilentlyContinue
} until ($listener -or (Get-Date) -ge $deadline)

if (-not $listener) {
    $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
    throw "DailyNews server did not start. Task result: $($taskInfo.LastTaskResult)"
}

Write-Host "DailyNews server installed."
Write-Host "URL: http://IEWEB01:8082/"
