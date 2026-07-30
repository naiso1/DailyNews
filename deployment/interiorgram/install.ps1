[CmdletBinding()]
param(
    [string]$Root = "C:\Users\Administrator\Desktop\Interiorgram",
    [string]$ParentSite = "DailyNews",
    [string]$Alias = "interiorgram"
)

$ErrorActionPreference = "Stop"

Import-Module WebAdministration

$publicDirectory = Join-Path $Root "public"
$applicationPool = "Interiorgram"

foreach ($directory in @(
        $Root,
        (Join-Path $Root "app"),
        $publicDirectory,
        (Join-Path $Root "data"),
        (Join-Path $Root "backups"),
        (Join-Path $Root "logs")
    )) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

if (-not (Test-Path "IIS:\Sites\$ParentSite")) {
    throw "Parent IIS site was not found: $ParentSite"
}
if (-not (Test-Path -LiteralPath (Join-Path $publicDirectory "index.html"))) {
    throw "Interiorgram index.html was not found in $publicDirectory"
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

Restart-WebAppPool -Name $applicationPool

Write-Host "Interiorgram IIS application installed."
Write-Host "URL: http://IEWEB01/$Alias/"
