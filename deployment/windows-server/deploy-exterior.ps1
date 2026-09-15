[CmdletBinding()]
param(
    [string]$Server = "Administrator@IEWEB01",
    [string]$IdentityFile = "$env:USERPROFILE\.ssh\dailynews_ieweb01",
    [switch]$PackageOnly
)
$ErrorActionPreference = "Stop"
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$content = Join-Path $repo "content\exterior"
$root = "C:\Users\Administrator\Desktop\DailyNewsExterior"
$entry = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("5YaF6KOF6KO95ZOB44OH44Kk44Oq44O844OL44Ol44O844K5Lmh0bWw="))
$shared = @($entry,"header-layout-test.html","activity-preview.html","source-list-preview.html","currency-conversion-preview.html",
    "exchange_rates.js","dailynews_annotations.js","dailynews_config.js","dailynews_client.js","dailynews_account.js",
    "dailynews_activity.js","dailynews_sources.js","release_history.js")
foreach ($name in @("news_data.js","insights_data.js","source_list_data.js")) {
    if (!(Test-Path -LiteralPath (Join-Path $content $name))) { throw "Exterior content missing: $name" }
}
$tempRoot = Join-Path $repo "runtime\exterior\deployment"
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
$staging = Join-Path $tempRoot ("package_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $staging | Out-Null
foreach ($name in $shared) { Copy-Item -LiteralPath (Join-Path $repo $name) -Destination (Join-Path $staging $name) }
# Always package the current common UI. Exterior derives NEW dates from its own data.
foreach ($name in @("news_data.js","insights_data.js","source_list_data.js","publication_status.json")) {
    if (Test-Path -LiteralPath (Join-Path $content $name)) {
        Copy-Item -LiteralPath (Join-Path $content $name) -Destination (Join-Path $staging $name)
    }
}
foreach ($folder in @("images","page_images")) {
    $destination = Join-Path $staging $folder
    New-Item -ItemType Directory -Path $destination | Out-Null
    if (Test-Path -LiteralPath (Join-Path $content $folder)) {
        Get-ChildItem -LiteralPath (Join-Path $content $folder) -Force | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
        }
    }
    Get-ChildItem -LiteralPath (Join-Path $repo $folder) -File | Where-Object { $_.Name -match '^(icon_|globe_icon|placeholder)' } | ForEach-Object {
        if (!(Test-Path -LiteralPath (Join-Path $destination $_.Name))) {
            Copy-Item -LiteralPath $_.FullName -Destination $destination
        }
    }
}
# Content-addressed releases allow publication without bundling unrelated working-tree changes.
$manifest = Get-ChildItem -LiteralPath $staging -Recurse -File | Sort-Object FullName | ForEach-Object {
    $_.FullName.Substring($staging.Length) + ":" + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
}
$hasher = [Security.Cryptography.SHA1]::Create()
$releaseId = ([BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes(($manifest -join "`n"))))).Replace("-", "").ToLowerInvariant()
$hasher.Dispose()
$archive = Join-Path $tempRoot "$releaseId.tar"
& tar.exe -cf $archive -C $staging .
if ($LASTEXITCODE -ne 0) { throw "Exterior packaging failed." }
Copy-Item -LiteralPath (Join-Path $staging $entry) -Destination (Join-Path $staging "index.html")
@{edition="exterior";release=$releaseId;archive=$archive;preview=$staging} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $tempRoot "package.json") -Encoding UTF8
if ($PackageOnly) { Write-Output "PACKAGE_READY $staging"; return }

$sshOptions = @("-i",$IdentityFile,"-o","IdentitiesOnly=yes","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes")
function Invoke-Remote([string]$Script) {
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes("`$ErrorActionPreference='Stop';`$ProgressPreference='SilentlyContinue';" + $Script))
    & ssh @sshOptions $Server "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded"
    if ($LASTEXITCODE -ne 0) { throw "Exterior remote operation failed." }
}
Invoke-Remote "foreach (`$part in @('app','incoming','data','logs','releases')) {New-Item -ItemType Directory -Path (Join-Path '$root' `$part) -Force | Out-Null}"
foreach ($name in @("server.js","backup.js","manage-mailing-list.js","activate-release.ps1","install-exterior.ps1")) {
    & scp @sshOptions (Join-Path $PSScriptRoot $name) "${Server}:Desktop/DailyNewsExterior/app/$name"
    if ($LASTEXITCODE -ne 0) { throw "Exterior application upload failed: $name" }
}
& scp @sshOptions $archive "${Server}:Desktop/DailyNewsExterior/incoming/$releaseId.tar"
if ($LASTEXITCODE -ne 0) { throw "Exterior archive upload failed." }
Invoke-Remote "& '$root\app\activate-release.ps1' -Root '$root' -ArchivePath '$root\incoming\$releaseId.tar' -ReleaseId '$releaseId'; & '$root\app\install-exterior.ps1' -Root '$root'"
$health = $null
$deadline = (Get-Date).AddSeconds(30)
do {
    try { $health = Invoke-RestMethod "http://IEWEB01/exterior/health" -TimeoutSec 5 } catch { Start-Sleep -Seconds 1 }
} until (($health -and $health.release -eq $releaseId) -or (Get-Date) -ge $deadline)
if ($health.status -ne "ok" -or $health.release -ne $releaseId) { throw "Exterior release verification failed." }
Write-Output "EXTERIOR_DEPLOYED $releaseId http://IEWEB01/exterior/"
