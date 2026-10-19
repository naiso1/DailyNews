$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../deployment/notifications/flow-session.ps1')
$audience='https://service.flow.microsoft.com/'
$uri='https://api.flow.microsoft.com/providers/Microsoft.ProcessSimple/environments/test/flows/test?api-version=2016-11-01'
$script:passed=0
function Assert($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
function Assert-Throws([scriptblock]$Operation,[string]$Code) {
    try { & $Operation | Out-Null } catch {
        Assert ($_.Exception.Message.Contains($Code)) ('Unexpected error: '+$_.Exception.Message)
        return
    }
    throw 'Expected failure did not occur.'
}
function Reset-Test {
    $global:currentSession=$null
    $script:DailyNewsFlowAuth=@{InteractiveAttempts=0;Blocked=$false}
    $script:interactive=0; $script:silent=0; $script:http=0
    $script:silentResult=$null; $script:interactiveFails=$false; $script:networkFails=$false
    $script:networkStatus=0
}
function Set-TestToken {
    param([int]$Minutes=60)
    $global:currentSession=@{loggedIn=$true;resourceTokens=@{
        $audience=@{accessToken='fake-test-token';expiresOn=[DateTimeOffset]::UtcNow.AddMinutes($Minutes)}
    }}
}
# All authentication/network boundaries are replaced. Tests never open UI or send mail.
function Import-DailyNewsPowerAppsModule {}
function Restore-DailyNewsFlowCache {}
function Save-DailyNewsFlowCache {}
function Add-PowerAppsAccount {
    param($Endpoint,$Audience,$ErrorAction)
    $script:interactive++
    Assert ($Audience -ceq 'https://service.flow.microsoft.com/') 'Sign-in must target Flow directly.'
    if ($script:interactiveFails) { throw 'Cancelled' }
    Set-TestToken
}
function Invoke-DailyNewsFlowSilentToken {
    $script:silent++
    if ($script:silentResult -eq 'error') { throw 'UiRequired' }
    return $script:silentResult
}
Add-Type -TypeDefinition @'
using System;
public sealed class FlowTestResponse { public int StatusCode {get;set;} }
public sealed class FlowTestException : Exception {
    public FlowTestResponse Response {get;set;}
    public FlowTestException(int status) { Response=new FlowTestResponse { StatusCode=status }; }
}
'@
function Invoke-WebRequest {
    param($Uri,$Method,$Headers,$UseBasicParsing,$TimeoutSec,$MaximumRedirection,$ErrorAction,$Body,$ContentType)
    $script:http++
    Assert ($Headers.Authorization -ceq 'Bearer fake-test-token') 'Wrong cached token.'
    Assert ($TimeoutSec -eq 30 -and $MaximumRedirection -eq 0) 'Network must be bounded without redirects.'
    if ($script:networkFails) { throw [FlowTestException]::new($script:networkStatus) }
    return [pscustomobject]@{Content='{"status":"ok"}';Headers=@{Date='Thu, 08 Oct 2026 00:00:00 GMT'}}
}

Reset-Test
Set-TestToken
1..5 | ForEach-Object { $null=Invoke-DailyNewsFlowRequest -Uri $uri }
Assert ($script:http -eq 5 -and $script:interactive -eq 0 -and $script:silent -eq 0) 'Valid authentication was not reused.'
$script:passed++

Reset-Test
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri $uri} 'SIGNIN_REQUIRED'
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri $uri} 'SIGNIN_REQUIRED'
Assert ($script:interactive -eq 0 -and $script:http -eq 0 -and $script:silent -eq 1) 'Missing credentials triggered UI or repeated refresh.'
$script:passed++

Reset-Test
Set-TestToken -Minutes -1
$script:silentResult=[pscustomobject]@{AccessToken='fake-test-token';ExpiresOn=[DateTimeOffset]::UtcNow.AddHours(1)}
$null=Invoke-DailyNewsFlowRequest -Uri $uri
$null=Invoke-DailyNewsFlowRequest -Uri $uri
Assert ($script:silent -eq 1 -and $script:interactive -eq 0 -and $script:http -eq 2) 'Silent refresh was not reused.'
$script:passed++

Reset-Test
Set-TestToken -Minutes 2
$script:silentResult='error'
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri $uri} 'SIGNIN_REQUIRED'
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri $uri} 'SIGNIN_REQUIRED'
Assert ($script:interactive -eq 0 -and $script:http -eq 0 -and $script:silent -eq 1) 'A refresh failure must stop without UI.'
$script:passed++

Reset-Test
Connect-DailyNewsFlow -SignIn
Connect-DailyNewsFlow -SignIn
$null=Invoke-DailyNewsFlowRequest -Uri $uri
Assert ($script:interactive -eq 1 -and $script:http -eq 1) 'A second edition/sign-in did not reuse the authentication.'
$script:passed++

Reset-Test
$script:interactiveFails=$true
Assert-Throws {Connect-DailyNewsFlow -SignIn} 'SIGNIN_INCOMPLETE'
. (Join-Path $PSScriptRoot '../deployment/notifications/flow-session.ps1')
function Restore-DailyNewsFlowCache {}
function Save-DailyNewsFlowCache {}
Assert-Throws {Connect-DailyNewsFlow -SignIn} 'SIGNIN_ALREADY_ATTEMPTED'
Assert ($script:interactive -eq 1) 'Reloading or cancellation opened a second sign-in window.'
$script:passed++

Reset-Test
Set-TestToken
$script:networkFails=$true; $script:networkStatus=401
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri $uri} 'HTTP 401'
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri $uri} 'SIGNIN_REQUIRED'
Assert ($script:http -eq 1 -and $script:interactive -eq 0) 'An unauthorized API response retried or opened UI.'
$script:passed++

Reset-Test
Set-TestToken
$script:networkFails=$true; $script:networkStatus=503
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri $uri -Method POST -Body @{a=1}} 'HTTP 503'
Assert ($script:http -eq 1 -and $script:interactive -eq 0) 'An uncertain write was retried.'
$script:passed++

Reset-Test
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri 'https://api.flow.microsoft.com.evil.test/providers/Microsoft.ProcessSimple/environments/x'} 'Unexpected Flow endpoint'
Assert-Throws {Invoke-DailyNewsFlowRequest -Uri 'https://api.flow.microsoft.com:8443/providers/Microsoft.ProcessSimple/environments/x'} 'Unexpected Flow endpoint'
Assert ($script:http -eq 0 -and $script:silent -eq 0 -and $script:interactive -eq 0) 'Unexpected host touched authentication.'
$script:passed++
Write-Output ("PASS: {0} authentication/no-retry scenarios; no network, no UI, no mail." -f $script:passed)
