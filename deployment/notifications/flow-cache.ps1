# Windows CurrentUser DPAPI protects the MSAL cache. No password or plaintext
# fallback. Keep outside OneDrive, the repository, and release packages.
$script:DailyNewsFlowApplicationId = '689e5960-2e49-4505-98d8-369236220fc6'
$script:DailyNewsFlowBridgeSource = Join-Path $PSScriptRoot 'flow-cache-bridge.cs'

function Initialize-DailyNewsFlowCacheBridge {
    if (-not ('DailyNewsFlowCacheBridge' -as [type])) {
        Add-Type -Path $script:DailyNewsFlowBridgeSource -ReferencedAssemblies ([Microsoft.Identity.Client.PublicClientApplicationBuilder].Assembly.Location)
    }
}

function Get-DailyNewsFlowCachePath {
    return (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'DailyNewsRuntime\auth\flow-msal.dpapi')
}

function Invoke-DailyNewsFlowCacheLock {
    param([Parameter(Mandatory=$true)][scriptblock]$Operation)
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $mutex=New-Object Threading.Mutex($false, ('Local\DailyNewsFlowCache-'+$sid))
    $locked=$false
    try {
        try { $locked=$mutex.WaitOne(10000) } catch [Threading.AbandonedMutexException] { $locked=$true }
        if (-not $locked) { throw 'Flow cache is busy.' }
        & $Operation
    } finally { if ($locked) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
}

function Write-DailyNewsFlowCache {
    param([Parameter(Mandatory=$true)][object]$Payload)
    Add-Type -AssemblyName System.Security
    $cachePath=Get-DailyNewsFlowCachePath
    $folder=Split-Path -Parent $cachePath
    $null=[IO.Directory]::CreateDirectory($folder)
    if ((Get-Item -LiteralPath $folder).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Flow cache directory cannot be a link.'
    }
    $acl=New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
    $rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
    $acl.AddAccessRule($rule)
    [IO.Directory]::SetAccessControl($folder,$acl)
    $plain=[Text.Encoding]::UTF8.GetBytes(($Payload | ConvertTo-Json -Depth 5 -Compress))
    try { $encrypted=[Security.Cryptography.ProtectedData]::Protect($plain,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser) }
    finally { if ($plain) { [Array]::Clear($plain,0,$plain.Length) } }
    $temporary=Join-Path $folder ([Guid]::NewGuid().ToString('N')+'.tmp')
    try {
        [IO.File]::WriteAllBytes($temporary,$encrypted)
        if ([IO.File]::Exists($cachePath)) { [IO.File]::Replace($temporary,$cachePath,[NullString]::Value) }
        else { [IO.File]::Move($temporary,$cachePath) }
    } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
}

function Read-DailyNewsFlowCache {
    $cachePath=Get-DailyNewsFlowCachePath
    if (-not [IO.File]::Exists($cachePath)) { return $null }
    Add-Type -AssemblyName System.Security
    $plain=$null
    try {
        $plain=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($cachePath),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
        $payload=[Text.Encoding]::UTF8.GetString($plain) | ConvertFrom-Json
        if ($payload.version -ne 1 -or $payload.applicationId -cne $script:DailyNewsFlowApplicationId -or
            -not $payload.homeAccountId -or -not $payload.cache) { throw 'Invalid Flow cache.' }
        return $payload
    } finally { if ($plain) { [Array]::Clear($plain,0,$plain.Length) } }
}

function Save-DailyNewsFlowCache {
    $sessionVariable=Get-Variable currentSession -Scope Global -ErrorAction SilentlyContinue
    if (-not $sessionVariable -or -not $sessionVariable.Value.msalClientApp -or -not $sessionVariable.Value.msalAccount) { return }
    $session=$sessionVariable.Value
    if ($session.applicationId -cne $script:DailyNewsFlowApplicationId -or $session.endpoint -cne 'prod') {
        throw 'Only the standard production Flow account can be cached.'
    }
    Initialize-DailyNewsFlowCacheBridge
    if (-not $session.dailyNewsCacheBridge) {
        $session.dailyNewsCacheBridge=New-Object DailyNewsFlowCacheBridge($session.msalClientApp.UserTokenCache,$null)
    }
    $pending=$session.msalClientApp.GetAccountsAsync()
    if (-not $pending.Wait(10000)) { throw 'Flow cache capture timed out.' }
    $null=$pending.GetAwaiter().GetResult()
    $cache=$session.dailyNewsCacheBridge.Export()
    try {
        Write-DailyNewsFlowCache @{
            version=1; applicationId=$session.applicationId
            homeAccountId=$session.msalAccount.HomeAccountId.Identifier
            tenantId=$session.tenantId; userId=$session.userId
            cache=[Convert]::ToBase64String($cache)
        }
    } finally { if ($cache) { [Array]::Clear($cache,0,$cache.Length) } }
}

function Restore-DailyNewsFlowCache {
    $sessionVariable=Get-Variable currentSession -Scope Global -ErrorAction SilentlyContinue
    if ($sessionVariable -and $sessionVariable.Value.loggedIn) { return }
    $payload=Read-DailyNewsFlowCache
    if (-not $payload) { return }
    $client=[Microsoft.Identity.Client.PublicClientApplicationBuilder]::Create($script:DailyNewsFlowApplicationId).WithAuthority(
        [Microsoft.Identity.Client.AzureCloudInstance]::AzurePublic,
        [Microsoft.Identity.Client.AadAuthorityAudience]::AzureAdAndPersonalMicrosoftAccount,$true).WithDefaultRedirectUri().Build()
    $cache=[Convert]::FromBase64String($payload.cache)
    Initialize-DailyNewsFlowCacheBridge
    try { $bridge=New-Object DailyNewsFlowCacheBridge($client.UserTokenCache,$cache) }
    finally { [Array]::Clear($cache,0,$cache.Length) }
    $pending=$client.GetAccountsAsync()
    if (-not $pending.Wait(10000)) { throw 'Flow cache account lookup timed out.' }
    $accounts=@($pending.GetAwaiter().GetResult() | Where-Object { $_.HomeAccountId.Identifier -ceq $payload.homeAccountId })
    if ($accounts.Count -ne 1) { throw 'Saved Flow account was not found.' }
    $global:currentSession=@{
        loggedIn=$true; recursed=$false; endpoint='prod'; applicationId=$script:DailyNewsFlowApplicationId
        msalClientApp=$client; msalAccount=$accounts[0]; tenantId=$payload.tenantId; userId=$payload.userId
        resourceTokens=@{}
        dailyNewsCacheBridge=$bridge
    }
}

function Clear-DailyNewsFlowCache {
    # Explicitly forget locally saved authorization; this does not revoke it in Entra.
    Invoke-DailyNewsFlowCacheLock {
        $cachePath=Get-DailyNewsFlowCachePath
        if ([IO.File]::Exists($cachePath)) { [IO.File]::Delete($cachePath) }
        $global:currentSession=$null
        $script:DailyNewsFlowAuth.Blocked=$true
    }
}
