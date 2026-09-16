[CmdletBinding()]
param(
    [string]$InteriorRoot = "C:\Users\Administrator\Desktop\DailyNews",
    [string]$ExteriorRoot = "C:\Users\Administrator\Desktop\DailyNewsExterior",
    [switch]$Apply
)
$ErrorActionPreference = "Stop"
$node = "C:\Program Files\nodejs\node.exe"
$interiorDb = Join-Path $InteriorRoot "data\dailynews.sqlite"
$exteriorDb = Join-Path $ExteriorRoot "data\dailynews.sqlite"
$migration = Join-Path $PSScriptRoot "migrate-shared-identity.js"
foreach ($file in @($node, $migration, $interiorDb, $exteriorDb)) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required file missing: $file" }
}
foreach ($editionRoot in @($InteriorRoot, $ExteriorRoot)) {
    $app = Join-Path $editionRoot "app"
    foreach ($name in @("server.js", "shared-identity.js")) {
        if (!(Test-Path -LiteralPath (Join-Path $app $name))) { throw "Deploy both server applications first: $app\$name" }
    }
    if (!(Select-String -LiteralPath (Join-Path $app "server.js") -Pattern "shared-identity.json" -Quiet)) {
        throw "Server does not support shared identity: $app"
    }
}
# Default is a read-only plan, including account and enabled-recipient counts only.
& $node $migration --interior-db $interiorDb --exterior-db $exteriorDb
if ($LASTEXITCODE -ne 0) { throw "Shared identity preflight failed." }
if (!$Apply) { Write-Output "PLAN_ONLY: rerun with -Apply after reviewing the counts."; return }
$tasks = @("DailyNewsServer", "DailyNewsExteriorServer")
foreach ($task in $tasks) {
    if (!(Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue)) { throw "Expected server task missing: $task" }
}
foreach ($task in $tasks) { Stop-ScheduledTask -TaskName $task }
$deadline = (Get-Date).AddSeconds(20)
do {
    $listeners = @(Get-NetTCPConnection -LocalPort 8082,8084 -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count) { Start-Sleep -Milliseconds 400 }
} until (!$listeners.Count -or (Get-Date) -ge $deadline)
if ($listeners.Count) { throw "Servers did not stop; migration was not applied. Inspect the tasks before restarting." }
# Create a consistent backup of EACH database before any change.
# A failed apply leaves tasks stopped; do not restart an unreviewed mixed state.
& $node $migration --interior-db $interiorDb --exterior-db $exteriorDb --apply
if ($LASTEXITCODE -ne 0) { throw "Shared identity migration failed; servers remain stopped for recovery." }
$config = @{ identityDb = [IO.Path]::GetFullPath($interiorDb); exteriorDb = [IO.Path]::GetFullPath($exteriorDb) } | ConvertTo-Json
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
foreach ($editionRoot in @($InteriorRoot, $ExteriorRoot)) {
    $configPath = Join-Path $editionRoot "app\shared-identity.json"
    if (Test-Path -LiteralPath $configPath) {
        Copy-Item -LiteralPath $configPath -Destination ($configPath + ".before-" + $stamp) -ErrorAction Stop
    }
    [IO.File]::WriteAllText($configPath, $config, (New-Object Text.UTF8Encoding($false)))
}
foreach ($task in $tasks) { Start-ScheduledTask -TaskName $task }
Write-Output "SHARED_IDENTITY_ENABLED: verify both health/config endpoints and preserved recipient counts."
