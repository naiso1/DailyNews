[CmdletBinding()]
param(
    [string]$Server = "Administrator@IEWEB01",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\dailynews_ieweb01"
)

$ErrorActionPreference = "Stop"

$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$releaseId = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $releaseId -notmatch "^[0-9a-f]{40}$") {
    throw "Could not determine the Git commit ID."
}

$entryHtmlName = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String(
        "5YaF6KOF6KO95ZOB44OH44Kk44Oq44O844OL44Ol44O844K5Lmh0bWw="
    )
)
$required = @(
    $entryHtmlName,
    "header-layout-test.html",
    "news_data.js",
    "insights_data.js",
    "dailynews_client.js",
    "dailynews_account.js",
    "setup",
    "images",
    "page_images"
)
foreach ($item in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $repo $item))) {
        throw "Required public item was not found: $item"
    }
}

$publicChanges = @(& git -C $repo status --porcelain -- @required)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the public file status."
}
if ($publicChanges.Count -gt 0) {
    throw "Public files must be committed before deployment:`n$($publicChanges -join [Environment]::NewLine)"
}

$healthUrl = "http://IEWEB01:8082/health"
try {
    $currentHealth = Invoke-RestMethod $healthUrl -TimeoutSec 5
    if ($currentHealth.status -eq "ok" -and $currentHealth.release -eq $releaseId) {
        Write-Host "DailyNews is already current: $releaseId" -ForegroundColor Green
        return
    }
}
catch {
    Write-Host "DailyNews health check is unavailable; continuing deployment."
}

$temporaryDirectory = Join-Path $env:TEMP "DailyNewsDeploy"
New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
$archive = Join-Path $temporaryDirectory "$releaseId.tar"
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}

Push-Location $repo
try {
    & tar.exe -cf $archive -- @required
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the release archive."
    }
}
finally {
    Pop-Location
}

$sshOptions = @("-i", $IdentityFile, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes")
$remoteArchive = "Desktop/DailyNews/incoming/$releaseId.tar"
$remoteApp = "Desktop/DailyNews/app"

$prepareCommand = @"
New-Item -ItemType Directory -Path 'C:\Users\Administrator\Desktop\DailyNews\incoming' -Force | Out-Null
New-Item -ItemType Directory -Path 'C:\Users\Administrator\Desktop\DailyNews\app' -Force | Out-Null
"@
$prepareEncoded = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($prepareCommand)
)
& ssh @sshOptions $Server `
    "powershell.exe -NoProfile -NonInteractive -EncodedCommand $prepareEncoded"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to prepare the server incoming directory."
}

$appFiles = @(
    "server.js",
    "backup.js",
    "import_legacy.js",
    "activate-release.ps1",
    "install.ps1",
    "configure-iis.ps1"
)
foreach ($appFile in $appFiles) {
    $localAppFile = Join-Path $PSScriptRoot $appFile
    & scp @sshOptions $localAppFile "${Server}:${remoteApp}/$appFile"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upload server application file: $appFile"
    }
}

& scp @sshOptions $archive "${Server}:$remoteArchive"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload the release archive."
}

$activate = "C:\Users\Administrator\Desktop\DailyNews\app\activate-release.ps1"
$remoteArchivePath = "C:\Users\Administrator\Desktop\DailyNews\incoming\$releaseId.tar"
$activateCommand = "& '$activate' -ArchivePath '$remoteArchivePath' -ReleaseId '$releaseId'"
$activateEncoded = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($activateCommand)
)
& ssh @sshOptions $Server `
    "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $activateEncoded"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to activate the release."
}

$restartCommand = @"
Stop-ScheduledTask -TaskName 'DailyNewsServer' -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Start-ScheduledTask -TaskName 'DailyNewsServer'
"@
$restartEncoded = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($restartCommand)
)
& ssh @sshOptions $Server `
    "powershell.exe -NoProfile -NonInteractive -EncodedCommand $restartEncoded"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to restart the DailyNews server."
}

$health = $null
$deadline = (Get-Date).AddSeconds(30)
do {
    try {
        $health = Invoke-RestMethod $healthUrl -TimeoutSec 5
    }
    catch {
        Start-Sleep -Seconds 1
    }
} until ($health -or (Get-Date) -ge $deadline)

if ($health.status -ne "ok" -or $health.release -ne $releaseId) {
    throw "DailyNews health check did not return the expected release."
}

Remove-Item -LiteralPath $archive -Force
Write-Host "DailyNews deployed: $releaseId" -ForegroundColor Green
Write-Host "URL: http://IEWEB01:8082/"
