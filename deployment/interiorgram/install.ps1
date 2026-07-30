[CmdletBinding()]
param(
    [string]$Root = "C:\Users\Administrator\Desktop\Interiorgram",
    [string]$ParentSite = "DailyNews",
    [string]$Alias = "interiorgram"
)

$ErrorActionPreference = "Stop"

Import-Module WebAdministration

$publicDirectory = Join-Path $Root "public"
$appDirectory = Join-Path $Root "app"
$serverScript = Join-Path $appDirectory "server.js"
$backupScript = Join-Path $appDirectory "backup.js"
$node = "C:\Program Files\nodejs\node.exe"
$applicationPool = "Interiorgram"
$serverTaskName = "InteriorgramServer"
$backupTaskName = "InteriorgramBackup"

foreach ($directory in @(
        $Root,
        $appDirectory,
        $publicDirectory,
        (Join-Path $Root "data"),
        (Join-Path $Root "backups"),
        (Join-Path $Root "logs"),
        (Join-Path $Root "incoming")
    )) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

foreach ($file in @($node, $serverScript, $backupScript, (Join-Path $publicDirectory "web.config"))) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Required Interiorgram file was not found: $file"
    }
}
if (-not (Test-Path "IIS:\Sites\$ParentSite")) {
    throw "Parent IIS site was not found: $ParentSite"
}

if (-not (Test-Path "IIS:\AppPools\$applicationPool")) {
    New-WebAppPool -Name $applicationPool | Out-Null
}
Set-ItemProperty "IIS:\AppPools\$applicationPool" -Name managedRuntimeVersion -Value ""
Set-ItemProperty "IIS:\AppPools\$applicationPool" -Name processModel.identityType -Value 4
Set-ItemProperty "IIS:\AppPools\$applicationPool" -Name startMode -Value "AlwaysRunning"

$applicationPath = "/$Alias"
$existingApplication = Get-WebApplication -Site $ParentSite |
    Where-Object { $_.Path -eq $applicationPath }
if ($existingApplication) {
    Set-ItemProperty "IIS:\Sites\$ParentSite\$Alias" `
        -Name physicalPath `
        -Value $publicDirectory
    Set-ItemProperty "IIS:\Sites\$ParentSite\$Alias" `
        -Name applicationPool `
        -Value $applicationPool
}
else {
    New-WebApplication `
        -Site $ParentSite `
        -Name $Alias `
        -PhysicalPath $publicDirectory `
        -ApplicationPool $applicationPool | Out-Null
}

Set-WebConfigurationProperty `
    -PSPath "IIS:\" `
    -Location "$ParentSite/$Alias" `
    -Filter "system.webServer/security/authentication/anonymousAuthentication" `
    -Name "userName" `
    -Value ""

$applicationIdentity = "IIS AppPool\$applicationPool"
$traverseDirectories = @(
    (Split-Path (Split-Path $Root -Parent) -Parent),
    (Split-Path $Root -Parent)
)
foreach ($directory in $traverseDirectories) {
    & icacls.exe $directory /grant "${applicationIdentity}:(X)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not grant IIS traverse permission to $directory"
    }
}
& icacls.exe $Root /grant "${applicationIdentity}:(OI)(CI)(RX)" /T /C | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not grant IIS read permission to $Root"
}

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

if (Get-ScheduledTask -TaskName $serverTaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $serverTaskName -ErrorAction SilentlyContinue
    $stopDeadline = (Get-Date).AddSeconds(15)
    do {
        $existingListener = Get-NetTCPConnection `
            -LocalAddress "127.0.0.1" `
            -LocalPort 8083 `
            -State Listen `
            -ErrorAction SilentlyContinue
        if ($existingListener) {
            Start-Sleep -Milliseconds 500
        }
    } until (-not $existingListener -or (Get-Date) -ge $stopDeadline)
    if ($existingListener) {
        throw "Interiorgram port 8083 is still in use after stopping the existing task."
    }
    Unregister-ScheduledTask -TaskName $serverTaskName -Confirm:$false
}
$serverAction = New-ScheduledTaskAction `
    -Execute $node `
    -Argument ('"' + $serverScript + '"') `
    -WorkingDirectory $appDirectory
$serverTrigger = New-ScheduledTaskTrigger -AtStartup
$serverSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable
Register-ScheduledTask `
    -TaskName $serverTaskName `
    -Action $serverAction `
    -Trigger $serverTrigger `
    -Principal $principal `
    -Settings $serverSettings `
    -Description "Serves Interiorgram on loopback port 8083." `
    -Force | Out-Null

if (Get-ScheduledTask -TaskName $backupTaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $backupTaskName -Confirm:$false
}
$backupAction = New-ScheduledTaskAction `
    -Execute $node `
    -Argument ('"' + $backupScript + '"') `
    -WorkingDirectory $appDirectory
$backupTrigger = New-ScheduledTaskTrigger -Daily -At "04:40"
$backupSettings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable
Register-ScheduledTask `
    -TaskName $backupTaskName `
    -Action $backupAction `
    -Trigger $backupTrigger `
    -Principal $principal `
    -Settings $backupSettings `
    -Description "Backs up Interiorgram SQLite data and retains 35 days." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $serverTaskName
$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 500
    $listener = Get-NetTCPConnection `
        -LocalAddress "127.0.0.1" `
        -LocalPort 8083 `
        -State Listen `
        -ErrorAction SilentlyContinue
} until ($listener -or (Get-Date) -ge $deadline)
if (-not $listener) {
    $taskResult = (Get-ScheduledTaskInfo -TaskName $serverTaskName).LastTaskResult
    throw "Interiorgram server did not start. Task result: $taskResult"
}

Restart-WebAppPool -Name $applicationPool

$health = Invoke-RestMethod -Uri "http://127.0.0.1:8083/health" -TimeoutSec 10
if ($health.status -ne "ok") {
    throw "Interiorgram loopback health check failed."
}

Write-Host "Interiorgram application installed."
Write-Host "Ideas: $($health.ideas)"
Write-Host "URL: http://IEWEB01/$Alias/"
