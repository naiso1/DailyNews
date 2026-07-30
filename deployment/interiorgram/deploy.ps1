[CmdletBinding()]
param(
    [string]$Server = "Administrator@IEWEB01",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\dailynews_ieweb01",
    [string]$ContentSource = ""
)

$ErrorActionPreference = "Stop"

$sourceDirectory = $PSScriptRoot
$remoteRoot = "C:\Users\Administrator\Desktop\Interiorgram"
$node = (Get-Command node.exe -ErrorAction Stop).Source
$sshOptions = @(
    "-i", $IdentityFile,
    "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes"
)

if (-not $ContentSource) {
    $dailyNewsRoot = Split-Path (Split-Path $sourceDirectory -Parent) -Parent
    $projectsRoot = Split-Path $dailyNewsRoot -Parent
    $candidates = @(
        Get-ChildItem -LiteralPath $projectsRoot -Directory |
            Where-Object {
                Test-Path -LiteralPath (
                    Join-Path $_.FullName "IDEA_GENERATION_GUIDELINES.md"
                ) -PathType Leaf
            }
    )
    if ($candidates.Count -ne 1) {
        throw "Could not uniquely locate the existing Interiorgram project."
    }
    $ContentSource = $candidates[0].FullName
}

foreach ($required in @(
        "app\server.js",
        "app\backup.js",
        "public\web.config",
        "tools\prepare_legacy_site.js",
        "install.ps1"
    )) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceDirectory $required) -PathType Leaf)) {
        throw "Required Interiorgram deployment file was not found: $required"
    }
}
foreach ($required in @("index.html", "style.css", "script.js", "data.js", "images")) {
    if (-not (Test-Path -LiteralPath (Join-Path $ContentSource $required))) {
        throw "Required existing Interiorgram source was not found: $required"
    }
}

$temporaryRoot = Join-Path $env:TEMP "InteriorgramDeploy"
$deploymentId = [Guid]::NewGuid().ToString("N")
$workingDirectory = Join-Path $temporaryRoot $deploymentId
$packageDirectory = Join-Path $workingDirectory "package"
$publicDirectory = Join-Path $packageDirectory "public"
$appDirectory = Join-Path $packageDirectory "app"
$archive = Join-Path $workingDirectory "interiorgram.tar"

New-Item -ItemType Directory -Path $publicDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $appDirectory -Force | Out-Null

try {
    & $node `
        (Join-Path $sourceDirectory "tools\prepare_legacy_site.js") `
        $ContentSource `
        $publicDirectory `
        (Join-Path $sourceDirectory "public\web.config")
    if ($LASTEXITCODE -ne 0) {
        throw "Could not prepare the existing Interiorgram content."
    }
    & robocopy.exe `
        (Join-Path $ContentSource "images") `
        (Join-Path $publicDirectory "images") `
        /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Could not copy the existing Interiorgram images."
    }

    Copy-Item `
        -LiteralPath (Join-Path $sourceDirectory "app\server.js") `
        -Destination (Join-Path $appDirectory "server.js") `
        -Force
    Copy-Item `
        -LiteralPath (Join-Path $sourceDirectory "app\backup.js") `
        -Destination (Join-Path $appDirectory "backup.js") `
        -Force

    & tar.exe -cf $archive -C $packageDirectory app public
    if ($LASTEXITCODE -ne 0) {
        throw "Could not build the Interiorgram deployment archive."
    }

    $prepareCommand = @"
`$ErrorActionPreference = 'Stop'
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
`$ErrorActionPreference = 'Stop'
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
        -TimeoutSec 30
    if ($page.StatusCode -ne 200 -or
        $page.Content -notmatch "Interiorgram \| AI") {
        throw "Interiorgram page verification failed."
    }
    $health = Invoke-RestMethod `
        -Uri "http://IEWEB01/interiorgram/health" `
        -TimeoutSec 30
    if ($health.status -ne "ok" -or $health.ideas -lt 1) {
        throw "Interiorgram health verification failed."
    }

    Write-Host "Existing Interiorgram deployed."
    Write-Host "Ideas: $($health.ideas)"
    Write-Host "URL: http://IEWEB01/interiorgram/"
}
finally {
    $resolvedTemporaryRoot = [IO.Path]::GetFullPath($temporaryRoot)
    $resolvedWorkingDirectory = [IO.Path]::GetFullPath($workingDirectory)
    if ($resolvedWorkingDirectory.StartsWith(
            $resolvedTemporaryRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase
        ) -and (Test-Path -LiteralPath $workingDirectory)) {
        Remove-Item -LiteralPath $workingDirectory -Recurse -Force
    }
}
