param([string]$ReadTestFile)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../deployment/notifications/flow-cache.ps1')
if ($ReadTestFile) {
    $script:testCache=$ReadTestFile
    function Get-DailyNewsFlowCachePath { return $script:testCache }
    $payload=Invoke-DailyNewsFlowCacheLock { Read-DailyNewsFlowCache }
    if ($payload.homeAccountId -cne 'fake-account' -or $payload.cache -cne 'ZmFrZS1jYWNoZQ==') { throw 'Cross-process restore failed.' }
    Write-Output 'Child process decrypted test cache.'
    exit
}
$folder=Join-Path ([IO.Path]::GetTempPath()) ('dailynews-cache-test-'+[Guid]::NewGuid().ToString('N'))
$script:testCache=Join-Path $folder 'flow-msal.dpapi'
function Get-DailyNewsFlowCachePath { return $script:testCache }
try {
    $payload=@{version=1;applicationId=$script:DailyNewsFlowApplicationId;homeAccountId='fake-account';cache='ZmFrZS1jYWNoZQ=='}
    Invoke-DailyNewsFlowCacheLock { Write-DailyNewsFlowCache $payload }
    $bytes=[IO.File]::ReadAllBytes($script:testCache)
    if ([Text.Encoding]::UTF8.GetString($bytes).Contains('fake-account')) { throw 'Plaintext leaked.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -ReadTestFile $script:testCache
    if ($LASTEXITCODE -ne 0) { throw 'Child cache test failed.' }
    Invoke-DailyNewsFlowCacheLock { Write-DailyNewsFlowCache $payload }
    $acl=Get-Acl -LiteralPath $folder
    if (-not $acl.AreAccessRulesProtected -or @($acl.Access).Count -ne 1) { throw 'Cache directory ACL is not private.' }
    [IO.File]::WriteAllText($script:testCache,'invalid-test-cache')
    $failed=$false
    try { Read-DailyNewsFlowCache | Out-Null } catch { $failed=$true }
    if (-not $failed) { throw 'Damaged cache was accepted.' }
    Import-Module Microsoft.PowerApps.PowerShell -DisableNameChecking
    $client=[Microsoft.Identity.Client.PublicClientApplicationBuilder]::Create($script:DailyNewsFlowApplicationId).WithAuthority([Microsoft.Identity.Client.AzureCloudInstance]::AzurePublic,[Microsoft.Identity.Client.AadAuthorityAudience]::AzureAdAndPersonalMicrosoftAccount,$true).WithDefaultRedirectUri().Build()
    Initialize-DailyNewsFlowCacheBridge
    $bridge=New-Object DailyNewsFlowCacheBridge($client.UserTokenCache,$null)
    if (@($client.GetAccountsAsync().GetAwaiter().GetResult()).Count -ne 0) { throw 'Unexpected real account in test.' }
    $data=$bridge.Export()
    $bridge2=New-Object DailyNewsFlowCacheBridge($client.UserTokenCache,$data)
    if (@($client.GetAccountsAsync().GetAwaiter().GetResult()).Count -ne 0) { throw 'Restored empty cache must be empty.' }
    Write-Output 'PASS: encrypted roundtrip across processes, atomic replacement, private ACL, corruption rejected, installed MSAL serialization. No sign-in or mail.'
} finally {
    $resolved=[IO.Path]::GetFullPath($folder)
    $temp=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if ($resolved.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase) -and (Split-Path -Leaf $resolved).StartsWith('dailynews-cache-test-')) {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction SilentlyContinue
    }
}
