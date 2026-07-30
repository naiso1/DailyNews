[CmdletBinding()]
param(
    [string]$Server = "Administrator@IEWEB01",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\dailynews_ieweb01"
)

$ErrorActionPreference = "Stop"

$sourceDirectory = $PSScriptRoot
$remoteRoot = "C:\Users\Administrator\Desktop\Interiorgram"
$sshOptions = @(
    "-i", $IdentityFile,
    "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes"
)

foreach ($required in @(
        "app\server.js",
        "app\backup.js",
        "public\index.html",
        "public\styles.css",
        "public\app.js",
        "public\web.config",
        "content\posts.json"
    )) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceDirectory $required) -PathType Leaf)) {
        throw "Required Interiorgram source file was not found: $required"
    }
}

$temporaryDirectory = Join-Path $env:TEMP "InteriorgramDeploy"
New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
$archive = Join-Path $temporaryDirectory "interiorgram.tar"
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}

Push-Location $sourceDirectory
try {
    & tar.exe -cf $archive -- app public content
    if ($LASTEXITCODE -ne 0) {
        throw "Could not build the Interiorgram deployment archive."
    }
}
finally {
    Pop-Location
}

$prepareCommand = @"
New-Item -ItemType Directory -Path '$remoteRoot\incoming' -Force | Out-Null
New-Item -ItemType Directory -Path '$remoteRoot\data' -Force | Out-Null
New-Item -ItemType Directory -Path '$remoteRoot\backups' -Force | Out-Null
New-Item -ItemType Directory -Path '$remoteRoot\logs' -Force | Out-Null
"@
$prepareEncoded = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($prepareCommand)
)
& ssh @sshOptions $Server `
    "powershell.exe -NoProfile -NonInteractive -EncodedCommand $prepareEncoded"
if ($LASTEXITCODE -ne 0) {
    throw "Could not prepare the Interiorgram server directory."
}

$remoteArchive = "Desktop/Interiorgram/incoming/interiorgram.tar"
& scp @sshOptions $archive "${Server}:$remoteArchive"
if ($LASTEXITCODE -ne 0) {
    throw "Could not upload the Interiorgram archive."
}
& scp @sshOptions `
    (Join-Path $sourceDirectory "install.ps1") `
    "${Server}:Desktop/Interiorgram/app/install.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "Could not upload the Interiorgram installer."
}

$installCommand = @"
& tar.exe -xf '$remoteRoot\incoming\interiorgram.tar' -C '$remoteRoot'
if (`$LASTEXITCODE -ne 0) {
    throw 'Could not extract the Interiorgram deployment archive.'
}
& '$remoteRoot\app\install.ps1'
Remove-Item -LiteralPath '$remoteRoot\incoming\interiorgram.tar' -Force
"@
$installEncoded = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($installCommand)
)
& ssh @sshOptions $Server `
    "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $installEncoded"
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the Interiorgram application."
}

$page = Invoke-WebRequest `
    -UseBasicParsing `
    -Uri "http://IEWEB01/interiorgram/" `
    -TimeoutSec 20
if ($page.StatusCode -ne 200 -or
    $page.Content -notmatch "<title>Interiorgram</title>") {
    throw "Interiorgram page verification failed."
}
$health = Invoke-RestMethod `
    -Uri "http://IEWEB01/interiorgram/health" `
    -TimeoutSec 20
if ($health.status -ne "ok") {
    throw "Interiorgram health verification failed."
}

Remove-Item -LiteralPath $archive -Force
Write-Host "Interiorgram deployed."
Write-Host "Posts: $($health.posts)"
Write-Host "URL: http://IEWEB01/interiorgram/"
