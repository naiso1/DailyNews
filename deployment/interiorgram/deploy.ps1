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

$prepareCommand = @"
New-Item -ItemType Directory -Path '$remoteRoot\app' -Force | Out-Null
New-Item -ItemType Directory -Path '$remoteRoot\public' -Force | Out-Null
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

foreach ($file in @("index.html", "web.config")) {
    & scp @sshOptions `
        (Join-Path $sourceDirectory "public\$file") `
        "${Server}:Desktop/Interiorgram/public/$file"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not upload Interiorgram public file: $file"
    }
}

& scp @sshOptions `
    (Join-Path $sourceDirectory "install.ps1") `
    "${Server}:Desktop/Interiorgram/app/install.ps1"
if ($LASTEXITCODE -ne 0) {
    throw "Could not upload the Interiorgram installer."
}

$installCommand = @"
& '$remoteRoot\app\install.ps1'
"@
$installEncoded = [Convert]::ToBase64String(
    [Text.Encoding]::Unicode.GetBytes($installCommand)
)
& ssh @sshOptions $Server `
    "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $installEncoded"
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the Interiorgram IIS application."
}

$response = Invoke-WebRequest `
    -UseBasicParsing `
    -Uri "http://IEWEB01/interiorgram/" `
    -TimeoutSec 20
if ($response.StatusCode -ne 200 -or
    $response.Content -notmatch "<title>Interiorgram</title>") {
    throw "Interiorgram HTTP verification failed."
}

Write-Host "Interiorgram deployed."
Write-Host "URL: http://IEWEB01/interiorgram/"
