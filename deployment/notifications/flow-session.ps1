# Dot-source once in the same PowerShell process used for both editions.
# Reading status never opens a sign-in window. Windows protects the persistent cache.
. (Join-Path $PSScriptRoot 'flow-cache.ps1')
if (-not (Get-Variable DailyNewsFlowAuth -Scope Script -ErrorAction SilentlyContinue)) {
    $script:DailyNewsFlowAuth = @{InteractiveAttempts=0; Blocked=$false}
}
$script:DailyNewsFlowAudience = 'https://service.flow.microsoft.com/'

function Import-DailyNewsPowerAppsModule {
    Import-Module Microsoft.PowerApps.PowerShell -DisableNameChecking -ErrorAction Stop
}

function Get-DailyNewsCachedFlowToken {
    $sessionVariable = Get-Variable currentSession -Scope Global -ErrorAction SilentlyContinue
    if (-not $sessionVariable -or -not $sessionVariable.Value.loggedIn) { return $null }
    $entry = $sessionVariable.Value.resourceTokens[$script:DailyNewsFlowAudience]
    if (-not $entry -or [string]::IsNullOrWhiteSpace($entry.accessToken) -or -not $entry.expiresOn) { return $null }
    # Compare UTC explicitly and leave a margin for the workstation clock and request.
    if ([DateTimeOffset]$entry.expiresOn -le [DateTimeOffset]::UtcNow.AddMinutes(3)) { return $null }
    return $entry.accessToken
}

function Invoke-DailyNewsFlowSilentToken {
    $sessionVariable = Get-Variable currentSession -Scope Global -ErrorAction SilentlyContinue
    if (-not $sessionVariable -or -not $sessionVariable.Value.loggedIn) { return $null }
    $session = $sessionVariable.Value
    if (-not $session.msalClientApp -or -not $session.msalAccount) { return $null }
    # Use the same scope spelling as the installed Microsoft Power Apps module.
    [string[]]$scopes = "$script:DailyNewsFlowAudience/.default"
    $cancel = New-Object Threading.CancellationTokenSource
    try {
        $cancel.CancelAfter(30000)
        $pending = $session.msalClientApp.AcquireTokenSilent($scopes, $session.msalAccount).ExecuteAsync($cancel.Token)
        if (-not $pending.Wait(31000)) { throw 'Silent sign-in timed out.' }
        return $pending.GetAwaiter().GetResult()
    } finally { $cancel.Dispose() }
}

function Get-DailyNewsFlowAccessToken {
    if ($script:DailyNewsFlowAuth.Blocked) {
        throw 'DAILYNEWS_FLOW_SIGNIN_REQUIRED: Authentication needs attention. No sign-in window or automatic retry was started.'
    }
    $token = Get-DailyNewsCachedFlowToken
    if ($token) { return $token }
    try {
        $result = Invoke-DailyNewsFlowCacheLock {
            Restore-DailyNewsFlowCache
            $silentResult = Invoke-DailyNewsFlowSilentToken
            if ($silentResult) { Save-DailyNewsFlowCache }
            return $silentResult
        }
        if ($result -and $result.AccessToken -and $result.ExpiresOn) {
            if (-not $global:currentSession.resourceTokens) { $global:currentSession.resourceTokens=@{} }
            $global:currentSession.resourceTokens[$script:DailyNewsFlowAudience]=@{
                accessToken=$result.AccessToken; expiresOn=$result.ExpiresOn
            }
            $token = Get-DailyNewsCachedFlowToken
            if ($token) { return $token }
        }
    } catch {
        # Do not log token details, user identifiers, claims challenges, or SDK errors.
        # MFA/conditional-access requirements must be handled interactively, explicitly.
    }
    $script:DailyNewsFlowAuth.Blocked=$true
    throw 'DAILYNEWS_FLOW_SIGNIN_REQUIRED: Authentication could not be reused silently. Call Connect-DailyNewsFlow -SignIn once when the user can authenticate.'
}

function Connect-DailyNewsFlow {
    [CmdletBinding()]
    param([switch]$SignIn)
    Import-DailyNewsPowerAppsModule
    try { $null=Get-DailyNewsFlowAccessToken; return } catch {
        if (-not $SignIn) { throw }
    }
    if ($script:DailyNewsFlowAuth.InteractiveAttempts -ge 1) {
        throw 'DAILYNEWS_FLOW_SIGNIN_ALREADY_ATTEMPTED: Sign-in was already requested in this process. No additional window was opened.'
    }
    # Consume the allowance before opening a window; cancellation/failure cannot loop.
    $script:DailyNewsFlowAuth.InteractiveAttempts++
    try {
        Add-PowerAppsAccount -Endpoint prod -Audience $script:DailyNewsFlowAudience -ErrorAction Stop | Out-Null
        $script:DailyNewsFlowAuth.Blocked=$false
        $null=Get-DailyNewsFlowAccessToken
        Invoke-DailyNewsFlowCacheLock { Save-DailyNewsFlowCache }
    } catch {
        $script:DailyNewsFlowAuth.Blocked=$true
        throw 'DAILYNEWS_FLOW_SIGNIN_INCOMPLETE: Sign-in did not finish successfully. No automatic retry was started.'
    }
}

function Invoke-DailyNewsFlowRequest {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$Uri,
        [ValidateSet('GET','POST','PATCH')][string]$Method='GET',
        [object]$Body,
        [switch]$RawResponse
    )
    $parsed=[Uri]$Uri
    if ($parsed.Scheme -cne 'https' -or $parsed.DnsSafeHost -cne 'api.flow.microsoft.com' -or
        -not $parsed.IsDefaultPort -or $parsed.UserInfo -or $parsed.Fragment -or
        $parsed.AbsolutePath -notmatch '^/providers/Microsoft\.(ProcessSimple|Flow)/environments/') {
        throw 'Unexpected Flow endpoint. No authentication or network request was attempted.'
    }
    $token=Get-DailyNewsFlowAccessToken
    $args=@{Uri=$Uri;Method=$Method;Headers=@{Authorization=('Bearer '+$token);'Cache-Control'='no-cache'};
        UseBasicParsing=$true;TimeoutSec=30;MaximumRedirection=0;ErrorAction='Stop'}
    if ($PSBoundParameters.ContainsKey('Body')) {
        $args.Body=($Body | ConvertTo-Json -Depth 100 -Compress)
        $args.ContentType='application/json; charset=utf-8'
    }
    try { $response=Invoke-WebRequest @args }
    catch {
        $status=$null
        if ($_.Exception.Response) { $status=[int]$_.Exception.Response.StatusCode }
        if ($status -in @(401,403)) { $script:DailyNewsFlowAuth.Blocked=$true }
        # A POST/PATCH might have reached the service. Never retry a write here.
        throw ('DAILYNEWS_FLOW_REQUEST_FAILED: HTTP {0}. No automatic retry or sign-in was started. Verify delivery before repeating a write.' -f $status)
    } finally { $token=$null; $args.Headers.Clear() }
    if ($RawResponse) { return $response }
    if (-not [string]::IsNullOrWhiteSpace($response.Content)) { return $response.Content | ConvertFrom-Json }
}
