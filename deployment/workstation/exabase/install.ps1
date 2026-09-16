[CmdletBinding()]
param(
    [string]$SourceDirectory = '\\tgfs1\ＩＥ開発部\01_内装開発室\01_個別開発テーマ\03_個別テーマ活動フォルダ\生成AI活用\exaBase自動化\exaBase画像複数枚生成ツール'
)
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $env:LOCALAPPDATA 'DailyNewsRuntime\exabase'
$engineDirectory = Join-Path $runtime 'engine'
$source = Join-Path $SourceDirectory 'playwright_engine.js'
$expectedHash = '481517DD4230AB85AFD490E5B3DB491B0F599CD46F4E1E550AACAF8571353D76'
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'The shared exaBase engine changed. Review it before updating the pinned version.'
}
New-Item -ItemType Directory -Path $engineDirectory -Force | Out-Null
# Session plaintext exists only briefly here; prevent access by other normal users.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = New-Object Security.AccessControl.DirectorySecurity
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @($identity, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')), (New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))) {
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $runtime -AclObject $acl
Copy-Item -LiteralPath $source -Destination (Join-Path $engineDirectory 'playwright_engine.js') -Force
'{"name":"dailynews-exabase-runtime","private":true,"version":"1.0.0","dependencies":{"playwright-core":"1.55.0"}}' |
    Set-Content -LiteralPath (Join-Path $engineDirectory 'package.json') -Encoding ASCII
& npm.cmd install --prefix $engineDirectory --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'Could not install the pinned Playwright dependency.' }
@{
    schemaVersion = 1; engineSha256 = $expectedHash.ToLowerInvariant()
    sourceVersion = 'exaBase image batch lite 1.1.4'; playwrightVersion = '1.55.0'
    installedAt = (Get-Date).ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'installation.json') -Encoding UTF8
Write-Output 'EXABASE_RUNTIME_INSTALLED'
