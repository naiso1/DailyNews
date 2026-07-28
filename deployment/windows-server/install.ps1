[CmdletBinding()]
param(
    [string[]]$AllowedClients = @("172.29.0.0/16", "202.15.67.0/24")
)

$ErrorActionPreference = "Stop"

$root = "C:\Users\Administrator\Desktop\DailyNews"
$appDir = Join-Path $root "app"
$serverScript = Join-Path $appDir "server.js"
$node = "C:\Program Files\nodejs\node.exe"
$taskName = "DailyNewsServer"
$backupTaskName = "DailyNewsBackup"
$backupScript = Join-Path $appDir "backup.js"
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
if (-not (Test-Path -LiteralPath $backupScript -PathType Leaf)) {
    throw "DailyNews backup script was not found: $backupScript"
}

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$stopDeadline = (Get-Date).AddSeconds(15)
do {
    $existingListener = Get-NetTCPConnection `
        -LocalPort 8082 `
        -State Listen `
        -ErrorAction SilentlyContinue
    if ($existingListener) {
        Start-Sleep -Milliseconds 500
    }
} until (-not $existingListener -or (Get-Date) -ge $stopDeadline)
if ($existingListener) {
    throw "TCP port 8082 is still in use after stopping the existing task."
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

$existingBackupTask = Get-ScheduledTask -TaskName $backupTaskName -ErrorAction SilentlyContinue
if ($existingBackupTask) {
    Unregister-ScheduledTask -TaskName $backupTaskName -Confirm:$false
}
$backupAction = New-ScheduledTaskAction `
    -Execute $node `
    -Argument ('"' + $backupScript + '"') `
    -WorkingDirectory $appDir
$backupTrigger = New-ScheduledTaskTrigger -Daily -At "04:30"
$backupSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable
Register-ScheduledTask `
    -TaskName $backupTaskName `
    -Action $backupAction `
    -Trigger $backupTrigger `
    -Principal $principal `
    -Settings $backupSettings `
    -Description "Creates a consistent DailyNews SQLite backup and retains 35 days." `
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
    -RemoteAddress $AllowedClients `
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
