[CmdletBinding()]
param(
    [string]$CertificateUrl = "http://IEWEB01/setup/IEWEB01-DailyNews.cer"
)

$ErrorActionPreference = "Stop"
$expectedThumbprint = "637AE40A8EC03E1CE638C730E4883F3B283377A0"
$certificatePath = Join-Path $env:TEMP "IEWEB01-DailyNews.cer"

Invoke-WebRequest `
    -Uri $CertificateUrl `
    -OutFile $certificatePath `
    -UseBasicParsing

$certificate = [Security.Cryptography.X509Certificates.X509Certificate2]::new(
    $certificatePath
)
if ($certificate.Thumbprint -ne $expectedThumbprint) {
    throw "Certificate verification failed. Expected $expectedThumbprint, received $($certificate.Thumbprint)."
}
if ($certificate.Subject -ne "CN=IEWEB01") {
    throw "Unexpected certificate subject: $($certificate.Subject)"
}
if ($certificate.NotAfter -le (Get-Date)) {
    throw "The IEWEB01 certificate has expired."
}

$store = [Security.Cryptography.X509Certificates.X509Store]::new(
    "Root",
    "CurrentUser"
)
try {
    $store.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $store.Add($certificate)
}
finally {
    $store.Close()
}

$status = Invoke-RestMethod -Uri "https://IEWEB01/api/status" -TimeoutSec 20
if ($status.status -ne "ok") {
    throw "Certificate installation completed, but the DailyNews health check failed."
}

Write-Host "IEWEB01 certificate installed for $env:USERNAME." -ForegroundColor Green
Write-Host "Close all Chrome or Edge windows, then open https://IEWEB01/."
