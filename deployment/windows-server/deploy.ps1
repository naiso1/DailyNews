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
    "news_data.js",
    "insights_data.js",
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

& ssh @sshOptions $Server `
    'powershell -NoProfile -Command "New-Item -ItemType Directory -Path C:\Users\Administrator\Desktop\DailyNews\incoming -Force | Out-Null"'
if ($LASTEXITCODE -ne 0) {
    throw "Failed to prepare the server incoming directory."
}

& scp @sshOptions $archive "${Server}:$remoteArchive"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload the release archive."
}

$activate = "C:\Users\Administrator\Desktop\DailyNews\app\activate-release.ps1"
$remoteArchivePath = "C:\Users\Administrator\Desktop\DailyNews\incoming\$releaseId.tar"
& ssh @sshOptions $Server `
    "powershell -NoProfile -ExecutionPolicy Bypass -File `"$activate`" -ArchivePath `"$remoteArchivePath`" -ReleaseId `"$releaseId`""
if ($LASTEXITCODE -ne 0) {
    throw "Failed to activate the release."
}

$health = Invoke-RestMethod "http://IEWEB01:8082/health" -TimeoutSec 15
if ($health.status -ne "ok" -or $health.release -ne $releaseId) {
    throw "DailyNews health check did not return the expected release."
}

Remove-Item -LiteralPath $archive -Force
Write-Host "DailyNews deployed: $releaseId" -ForegroundColor Green
Write-Host "URL: http://IEWEB01:8082/"
