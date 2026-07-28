[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[0-9a-fA-F]{7,40}$")]
    [string]$ReleaseId
)

$ErrorActionPreference = "Stop"

$root = "C:\Users\Administrator\Desktop\DailyNews"
$incoming = Join-Path $root "incoming"
$releases = Join-Path $root "releases"
$activeFile = Join-Path $root "active-release.txt"
$releasePath = Join-Path $releases $ReleaseId
$archive = [IO.Path]::GetFullPath($ArchivePath)
$incomingPrefix = [IO.Path]::GetFullPath($incoming) + [IO.Path]::DirectorySeparatorChar
$entryHtmlName = [Text.Encoding]::UTF8.GetString(
    [Convert]::FromBase64String(
        "5YaF6KOF6KO95ZOB44OH44Kk44Oq44O844OL44Ol44O844K5Lmh0bWw="
    )
)

if (-not $archive.StartsWith($incomingPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Archive must be located under $incoming"
}
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    throw "Archive was not found: $archive"
}

New-Item -ItemType Directory -Path $releases -Force | Out-Null

if (-not (Test-Path -LiteralPath $releasePath)) {
    $staging = Join-Path $releases (".staging_" + $ReleaseId + "_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $staging | Out-Null

    try {
        & tar.exe -xf $archive -C $staging
        if ($LASTEXITCODE -ne 0) {
            throw "tar.exe failed with exit code $LASTEXITCODE"
        }

        $sourceHtml = Join-Path $staging $entryHtmlName
        $required = @(
            $sourceHtml,
            (Join-Path $staging "news_data.js"),
            (Join-Path $staging "insights_data.js"),
            (Join-Path $staging "dailynews_client.js"),
            (Join-Path $staging "images"),
            (Join-Path $staging "page_images")
        )
        foreach ($item in $required) {
            if (-not (Test-Path -LiteralPath $item)) {
                throw "Required release item was not found: $item"
            }
        }

        Copy-Item -LiteralPath $sourceHtml -Destination (Join-Path $staging "index.html")
        [IO.File]::WriteAllText(
            (Join-Path $staging "release.json"),
            (@{
                    releaseId  = $ReleaseId
                    activatedAt = (Get-Date).ToUniversalTime().ToString("o")
                } | ConvertTo-Json),
            (New-Object Text.UTF8Encoding($false))
        )
        Move-Item -LiteralPath $staging -Destination $releasePath
    }
    catch {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -LiteralPath $staging -Recurse -Force
        }
        throw
    }
}

$temporaryActiveFile = "$activeFile.tmp"
[IO.File]::WriteAllText(
    $temporaryActiveFile,
    $ReleaseId + [Environment]::NewLine,
    (New-Object Text.UTF8Encoding($false))
)
Move-Item -LiteralPath $temporaryActiveFile -Destination $activeFile -Force
Remove-Item -LiteralPath $archive -Force

Write-Host "Activated DailyNews release: $ReleaseId"
