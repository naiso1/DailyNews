[CmdletBinding()]
param(
    [string[]]$AllowedClients = @("172.29.0.0/16", "202.15.67.0/24")
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$siteName = "DailyNews"
$hostName = "IEWEB01"
$proxyRoot = "C:\inetpub\DailyNewsProxy"
$certificateName = "IEWEB01 DailyNews"
$certificateExport = "C:\Users\Administrator\Desktop\DailyNews\app\IEWEB01-DailyNews.cer"
$rewriteInstaller = Join-Path $env:TEMP "rewrite_amd64_en-US.msi"
$arrInstaller = Join-Path $env:TEMP "requestRouter_amd64.msi"
$rewriteUrl = "https://download.microsoft.com/download/1/2/8/128E2E22-C1B9-44A4-BE2A-5859ED1D4592/rewrite_amd64_en-US.msi"
$arrUrl = "https://download.microsoft.com/download/E/9/8/E9849D6A-020E-47E4-9FD0-A023E99B54EB/requestRouter_amd64.msi"

function Install-MicrosoftMsi {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
    $signature = Get-AuthenticodeSignature -FilePath $Destination
    if ($signature.Status -ne "Valid" -or
        $signature.SignerCertificate.Subject -notmatch "Microsoft") {
        throw "Installer signature validation failed: $Destination"
    }

    $process = Start-Process `
        -FilePath "msiexec.exe" `
        -ArgumentList @("/i", "`"$Destination`"", "/quiet", "/norestart") `
        -Wait `
        -PassThru `
        -WindowStyle Hidden
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "Installer failed with exit code $($process.ExitCode): $Destination"
    }
}

Import-Module ServerManager
Install-WindowsFeature Web-Server, Web-Mgmt-Tools | Out-Null

Import-Module WebAdministration
$modules = @(Get-WebGlobalModule | Select-Object -ExpandProperty Name)
if ($modules -notcontains "RewriteModule") {
    Install-MicrosoftMsi -Url $rewriteUrl -Destination $rewriteInstaller
}

Import-Module WebAdministration -Force
$modules = @(Get-WebGlobalModule | Select-Object -ExpandProperty Name)
if ($modules -notcontains "ApplicationRequestRouting") {
    Install-MicrosoftMsi -Url $arrUrl -Destination $arrInstaller
}

Import-Module WebAdministration -Force
$modules = @(Get-WebGlobalModule | Select-Object -ExpandProperty Name)
if ($modules -notcontains "RewriteModule" -or
    $modules -notcontains "ApplicationRequestRouting") {
    throw "IIS URL Rewrite or ARR was not installed correctly."
}

& "$env:WINDIR\System32\inetsrv\appcmd.exe" `
    set config /section:system.webServer/proxy `
    /enabled:true /preserveHostHeader:true | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Could not enable the IIS ARR proxy."
}

New-Item -ItemType Directory -Path $proxyRoot -Force | Out-Null
$webConfig = @'
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="DailyNews reverse proxy" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://202.15.67.132:8082/{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <security>
      <requestFiltering allowDoubleEscaping="false">
        <requestLimits maxAllowedContentLength="1048576" />
      </requestFiltering>
    </security>
    <httpProtocol>
      <customHeaders>
        <add name="X-Content-Type-Options" value="nosniff" />
        <add name="Referrer-Policy" value="strict-origin-when-cross-origin" />
      </customHeaders>
    </httpProtocol>
  </system.webServer>
</configuration>
'@
[IO.File]::WriteAllText(
    (Join-Path $proxyRoot "web.config"),
    $webConfig,
    (New-Object Text.UTF8Encoding($false))
)

if (Test-Path "IIS:\Sites\$siteName") {
    Remove-Website -Name $siteName
}
if (-not (Test-Path "IIS:\AppPools\$siteName")) {
    New-WebAppPool -Name $siteName | Out-Null
}
Set-ItemProperty "IIS:\AppPools\$siteName" -Name managedRuntimeVersion -Value ""
Set-ItemProperty "IIS:\AppPools\$siteName" -Name processModel.identityType -Value 4

New-Website `
    -Name $siteName `
    -PhysicalPath $proxyRoot `
    -ApplicationPool $siteName `
    -Port 80 `
    -HostHeader $hostName | Out-Null

$certificate = Get-ChildItem Cert:\LocalMachine\My |
    Where-Object {
        $_.FriendlyName -eq $certificateName -and
        $_.NotAfter -gt (Get-Date).AddDays(30)
    } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if (-not $certificate) {
    $certificate = New-SelfSignedCertificate `
        -Type SSLServerAuthentication `
        -Subject "CN=$hostName" `
        -DnsName $hostName `
        -FriendlyName $certificateName `
        -CertStoreLocation "Cert:\LocalMachine\My" `
        -NotAfter (Get-Date).AddYears(3) `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -HashAlgorithm SHA256
}

New-WebBinding `
    -Name $siteName `
    -Protocol https `
    -Port 443 `
    -HostHeader $hostName `
    -SslFlags 1

$existingSslBinding = Get-ChildItem IIS:\SslBindings |
    Where-Object {
        $_.Port -eq 443 -and
        $_.Host -eq $hostName
    } |
    Select-Object -First 1
if ($existingSslBinding -and
    $existingSslBinding.Thumbprint -ne $certificate.Thumbprint) {
    Remove-Item -LiteralPath $existingSslBinding.PSPath -Force
    $existingSslBinding = $null
}
if (-not $existingSslBinding) {
    New-Item `
        -Path "IIS:\SslBindings\0.0.0.0!443!$hostName" `
        -Thumbprint $certificate.Thumbprint `
        -SSLFlags 1 | Out-Null
}

Export-Certificate `
    -Cert $certificate `
    -FilePath $certificateExport `
    -Force | Out-Null

foreach ($ruleName in @("DailyNews IIS HTTP 80", "DailyNews IIS HTTPS 443")) {
    Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule
}
New-NetFirewallRule `
    -DisplayName "DailyNews IIS HTTP 80" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalAddress "202.15.67.132" `
    -LocalPort 80 `
    -RemoteAddress $AllowedClients `
    -Profile Any | Out-Null
New-NetFirewallRule `
    -DisplayName "DailyNews IIS HTTPS 443" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalAddress "202.15.67.132" `
    -LocalPort 443 `
    -RemoteAddress $AllowedClients `
    -Profile Any | Out-Null

Start-Website -Name $siteName
Write-Host "DailyNews IIS proxy configured."
Write-Host "HTTP:  http://$hostName/"
Write-Host "HTTPS: https://$hostName/"
Write-Host "Certificate: $certificateExport"
