[CmdletBinding()]
param(
    [string]$Root = "C:\Users\Administrator\Desktop\DailyNewsExterior",
    [ValidateRange(1024,65535)][int]$Port = 8084
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$app = Join-Path $Root "app"
$proxy = "C:\inetpub\DailyNewsExteriorProxy"
$task = "DailyNewsExteriorServer"
$node = "C:\Program Files\nodejs\node.exe"
foreach ($part in @("app","data","data\backups","incoming","releases","logs")) {
    New-Item -ItemType Directory -Path (Join-Path $Root $part) -Force | Out-Null
}
if (!(Test-Path -LiteralPath $node)) { throw "Node.js is unavailable." }
if (!(Test-Path -LiteralPath (Join-Path $app "server.js"))) { throw "server.js is unavailable." }
# Do not overwrite app/shared-identity.json when refreshing the launcher.
if ((Test-Path -LiteralPath (Join-Path $app "shared-identity.json")) -and
    !(Test-Path -LiteralPath (Join-Path $app "shared-identity.js"))) {
    throw "Shared identity module is required for this installation."
}
$launcher = @"
`$ErrorActionPreference = 'Stop'
`$env:DAILYNEWS_EDITION = 'exterior'
`$env:DAILYNEWS_ROOT = '$Root'
`$env:DAILYNEWS_HOST = '127.0.0.1'
`$env:DAILYNEWS_PORT = '$Port'
& '$node' '$app\server.js'
exit `$LASTEXITCODE
"@
[IO.File]::WriteAllText((Join-Path $app "start-exterior.ps1"), $launcher, (New-Object Text.UTF8Encoding($false)))

if (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $task
    $deadline = (Get-Date).AddSeconds(15)
    do {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($listener) { Start-Sleep -Milliseconds 500 }
    } until (!$listener -or (Get-Date) -ge $deadline)
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Exterior port is occupied; existing applications were not stopped."
}
$principal = New-ScheduledTaskPrincipal -UserId SYSTEM -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $app "start-exterior.ps1") + '"') -WorkingDirectory $app
Register-ScheduledTask -TaskName $task -Action $action -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal $principal -Settings $settings -Force | Out-Null
$backup = New-ScheduledTaskAction -Execute $node -Argument ('"' + (Join-Path $app "backup.js") + '"') -WorkingDirectory $app
Register-ScheduledTask -TaskName "DailyNewsExteriorBackup" -Action $backup -Trigger (New-ScheduledTaskTrigger -Daily -At "04:50") -Principal $principal -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)) -Force | Out-Null

# A child IIS application clears the inherited catch-all rewrite. No parent site is recreated.
Import-Module WebAdministration
if (!(Test-Path "IIS:\Sites\DailyNews")) { throw "Existing DailyNews IIS site is unavailable." }
New-Item -ItemType Directory -Path $proxy -Force | Out-Null
$xml = @"
<?xml version="1.0" encoding="UTF-8"?>
<configuration><system.webServer><rewrite><rules><clear />
<rule name="DailyNews exterior reverse proxy" stopProcessing="true"><match url="(.*)" />
<action type="Rewrite" url="http://127.0.0.1:$Port/{R:1}" appendQueryString="true" /></rule>
</rules></rewrite></system.webServer></configuration>
"@
[IO.File]::WriteAllText((Join-Path $proxy "web.config"), $xml, (New-Object Text.UTF8Encoding($false)))
if (!(Test-Path "IIS:\AppPools\DailyNewsExterior")) { New-WebAppPool -Name DailyNewsExterior | Out-Null }
Set-ItemProperty "IIS:\AppPools\DailyNewsExterior" -Name managedRuntimeVersion -Value ""
$existing = Get-WebApplication -Site DailyNews | Where-Object { $_.Path -eq "/exterior" }
if ($existing) {
    Set-ItemProperty "IIS:\Sites\DailyNews\exterior" -Name physicalPath -Value $proxy
    Set-ItemProperty "IIS:\Sites\DailyNews\exterior" -Name applicationPool -Value DailyNewsExterior
} else {
    New-WebApplication -Site DailyNews -Name exterior -PhysicalPath $proxy -ApplicationPool DailyNewsExterior | Out-Null
}
Start-ScheduledTask -TaskName $task
Write-Output "EXTERIOR_INSTALLED"
