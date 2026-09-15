[CmdletBinding()]
param(
    [string]$EnvironmentName = "Default-2113d5b5-fefb-4c1d-bc26-12d7f8c3581d",
    [string]$SourceFlowName = "94732731-b972-483b-b973-16dea2efa3fd",
    [string]$DisplayName = "外装製品デイリーニュース 平日08時配信",
    [Parameter(Mandatory = $true)][string]$AdministratorEmail,
    [string]$SourcePropertiesFile,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "../../runtime/notifications/exterior"),
    [switch]$SignIn,
    [switch]$Create
)

$ErrorActionPreference = "Stop"
if ($AdministratorEmail -notmatch '^[^\s@;]+@[^\s@;]+\.[^\s@;]+$') {
    throw "Specify one administrator email address."
}
if ($SourcePropertiesFile -and $Create) {
    throw "Offline source files can only prepare a preview, not create a live flow."
}
if (-not $SourcePropertiesFile) {
    Import-Module Microsoft.PowerApps.PowerShell -DisableNameChecking
    if ($SignIn) { Add-PowerAppsAccount -Endpoint prod | Out-Null }
    if (-not $global:currentSession -or $global:currentSession.loggedIn -ne $true) {
        throw "Power Apps sign-in is required. Run with -SignIn in an interactive PowerShell window."
    }
    $source = (Get-Flow -EnvironmentName $EnvironmentName -FlowName $SourceFlowName).Internal.properties
} else {
    $source = Get-Content -LiteralPath $SourcePropertiesFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($source.properties) { $source = $source.properties }
}
if (-not $source.definition -or -not $source.connectionReferences) {
    throw "The source must contain definition and connectionReferences."
}

# Copy only in memory. Never PATCH or disable the existing interior flow.
$sourceJson = $source | ConvertTo-Json -Depth 100 -Compress
$copyJson = $sourceJson.Replace(
    'https://naiso1.github.io/DailyNews/automation_status.xml',
    'https://naiso1.github.io/DailyNews/content/exterior/automation_status.xml'
).Replace('/DailyNewsAutomation/mailing_list.json', '/DailyNewsAutomation/exterior/mailing_list.json'
).Replace('DailyNews success ', 'DailyNews exterior success '
).Replace('内装製品デイリーニュース', '外装製品デイリーニュース'
).Replace('内装開発デイリーニュース', '外装製品デイリーニュース')
# A preview can also start from the existing exterior flow without duplicating its path.
$copyJson = [regex]::Replace($copyJson, '(?i)http://ieweb01/(?!exterior/)', 'http://IEWEB01/exterior/')
$copy = $copyJson | ConvertFrom-Json
$condition = $copy.definition.actions.Check_DailyNews_success
$success = $condition.actions.Send_success_mail
if (-not $success) { $success = $condition.actions.Has_subscribers.actions.Send_success_mail }
$listAction = $condition.actions.Get_DailyNews_mailing_list
if (-not $success -or -not $listAction) {
    throw "The existing flow differs from the expected mailing-list flow; inspect before proceeding."
}
$listAction.inputs.parameters.path = '/DailyNewsAutomation/exterior/mailing_list.json'
$success.inputs.parameters.'emailMessage/To' = "@json(string(body('Get_DailyNews_mailing_list')))?['to']"
$success.inputs.parameters.'emailMessage/Subject' = '【外装製品デイリーニュース】@{formatDateTime(convertTimeZone(utcNow(),''UTC'',''Tokyo Standard Time''),''yyyy-MM-dd'')}'
$success.inputs.parameters.'emailMessage/Body' = '<p>外装製品デイリーニュースを更新しました。</p><p><a href="http://IEWEB01/exterior/">外装製品デイリーニュースを開く</a></p><p>メール配信の登録・停止は外装サイトから設定できます。</p>'

function Set-NotificationRecipients($Node) {
    if ($null -eq $Node -or $Node -is [string] -or $Node -is [ValueType]) { return }
    if ($Node -is [System.Collections.IEnumerable] -and $Node -isnot [pscustomobject]) {
        foreach ($child in $Node) { Set-NotificationRecipients $child }
        return
    }
    $parameters = $Node.inputs.parameters
    if ($parameters -and $parameters.PSObject.Properties['emailMessage/To']) {
        if ($Node -ne $success) { $parameters.'emailMessage/To' = $AdministratorEmail }
        foreach ($key in @('emailMessage/Cc', 'emailMessage/Bcc')) {
            $parameters.PSObject.Properties.Remove($key)
        }
    }
    foreach ($property in @($Node.PSObject.Properties)) { Set-NotificationRecipients $property.Value }
}
Set-NotificationRecipients $copy.definition.actions

function New-AdministratorNotification([string]$Subject, [string]$Message, $RunAfter) {
    $notification = $success | ConvertTo-Json -Depth 100 -Compress | ConvertFrom-Json
    $notification | Add-Member -NotePropertyName runAfter -NotePropertyValue $RunAfter -Force
    $notification.inputs.parameters.'emailMessage/To' = $AdministratorEmail
    $notification.inputs.parameters.'emailMessage/Subject' = $Subject
    $notification.inputs.parameters.'emailMessage/Body' = $Message
    $notification.inputs.parameters | Add-Member -NotePropertyName 'emailMessage/Importance' -NotePropertyValue 'High' -Force
    return $notification
}

# JSON validation prevents using an interior or malformed recipient export.
# recipientCount is optional for compatibility; an empty `to` always skips sending.
$parseList = [pscustomobject]@{
    type = 'ParseJson'
    runAfter = [ordered]@{ Get_DailyNews_mailing_list = @('Succeeded') }
    inputs = [ordered]@{
        content = "@json(string(body('Get_DailyNews_mailing_list')))"
        schema = [ordered]@{
            type = 'object'
            properties = [ordered]@{
                edition_id = [ordered]@{ type = 'string'; enum = @('exterior') }
                to = [ordered]@{ type = 'string' }
                recipientCount = [ordered]@{ type = 'integer'; minimum = 0 }
            }
            required = @('edition_id', 'to')
        }
    }
}
$success | Add-Member -NotePropertyName runAfter -NotePropertyValue ([ordered]@{}) -Force
$success.inputs.parameters.'emailMessage/To' = "@body('Parse_exterior_mailing_list')?['to']"
$sendFailure = New-AdministratorNotification `
    '[要確認] 外装製品デイリーニュース メール送信失敗' `
    '<p>外装ニュースの公開は完了しましたが、購読者向けメールの送信が失敗またはタイムアウトしました。</p><p>Power Automateの実行履歴を確認してください。タイムアウト時は実際に送信済みの場合もあるため、再送前に送信済みメールを確認してください。</p><p>（自動配信・管理者のみ）</p>' `
    ([ordered]@{ Send_success_mail = @('Failed', 'TimedOut') })
$hasSubscribers = [pscustomobject]@{
    type = 'If'
    runAfter = [ordered]@{ Parse_exterior_mailing_list = @('Succeeded') }
    expression = [ordered]@{
        and = @(
            [ordered]@{ not = [ordered]@{ equals = @("@trim(body('Parse_exterior_mailing_list')?['to'])", '') } },
            [ordered]@{ greater = @("@coalesce(body('Parse_exterior_mailing_list')?['recipientCount'], 1)", 0) }
        )
    }
    actions = [ordered]@{ Send_success_mail = $success; Notify_send_failure = $sendFailure }
    else = [ordered]@{ actions = [ordered]@{} }
}
$listFailure = New-AdministratorNotification `
    '[要確認] 外装製品デイリーニュース 配信先取得失敗' `
    '<p>業務用OneDriveから外装の配信先を取得できなかったため、購読者向けメールを送信しませんでした。</p><p>OneDrive同期と /DailyNewsAutomation/exterior/mailing_list.json を確認してください。</p><p>（自動配信・管理者のみ）</p>' `
    ([ordered]@{ Get_DailyNews_mailing_list = @('Failed', 'TimedOut') })
$validationFailure = New-AdministratorNotification `
    '[要確認] 外装製品デイリーニュース 配信先データ不正' `
    '<p>外装の配信先JSONを検証できなかったため、購読者向けメールを送信しませんでした。</p><p>edition_id が exterior であること、to が文字列であること、JSONが正常であることを確認してください。</p><p>（自動配信・管理者のみ）</p>' `
    ([ordered]@{ Parse_exterior_mailing_list = @('Failed', 'TimedOut') })
$condition.actions = [ordered]@{
    Get_DailyNews_mailing_list = $listAction
    Parse_exterior_mailing_list = $parseList
    Has_subscribers = $hasSubscribers
    Notify_mailing_list_failure = $listFailure
    Notify_mailing_list_validation_failure = $validationFailure
}

$triggers = @($copy.definition.triggers.PSObject.Properties)
if ($triggers.Count -ne 1 -or $triggers[0].Value.type -ne 'Recurrence') {
    throw "Expected exactly one scheduled Recurrence trigger."
}
$recurrence = [pscustomobject]@{
    frequency = 'Week'; interval = 1; timeZone = 'Tokyo Standard Time'
    schedule = [pscustomobject]@{ weekDays = @('Monday','Tuesday','Wednesday','Thursday','Friday'); hours = @(8); minutes = @(0) }
}
$triggers[0].Value | Add-Member -NotePropertyName recurrence -NotePropertyValue $recurrence -Force
$triggers[0].Value | Add-Member -NotePropertyName runtimeConfiguration -NotePropertyValue ([pscustomobject]@{concurrency = [pscustomobject]@{runs = 1}}) -Force

$definitionJson = $copy.definition | ConvertTo-Json -Depth 100 -Compress
foreach ($required in @(
    'https://naiso1.github.io/DailyNews/content/exterior/automation_status.xml',
    'DailyNews exterior success ',
    '/DailyNewsAutomation/exterior/mailing_list.json',
    'http://IEWEB01/exterior/'
)) {
    if (-not $definitionJson.Contains($required)) { throw "Expected exterior setting is missing: $required" }
}
foreach ($forbidden in @(
    'https://naiso1.github.io/DailyNews/automation_status.xml',
    '/DailyNewsAutomation/mailing_list.json',
    'DailyNews success '
)) {
    if ($definitionJson.Contains($forbidden)) { throw "An interior notification setting remains in the copy." }
}
$body = [ordered]@{ properties = [ordered]@{
    displayName = $DisplayName; state = 'Stopped'
    definition = $copy.definition; connectionReferences = $copy.connectionReferences
    environment = $copy.environment
} }
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$body | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $outputPath 'create-request.json') -Encoding UTF8
@{
    environmentName = $EnvironmentName; sourceFlowName = $SourceFlowName
    displayName = $DisplayName; requestedState = 'Stopped'; preparedAt = (Get-Date).ToString('o')
    status = 'prepared'; liveVerified = $false
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'manifest.json') -Encoding UTF8
if (-not $Create) {
    Write-Host "EXTERIOR_FLOW_PREPARED: $outputPath"
    return
}

$existing = @(Get-Flow -EnvironmentName $EnvironmentName | Where-Object { $_.DisplayName -eq $DisplayName })
if ($existing.Count) { throw "A flow with this exterior name already exists. Inspect it before creating another." }
$route = "https://{flowEndpoint}/providers/Microsoft.Flow/environments/$EnvironmentName/flows?api-version={apiVersion}"
$created = InvokeApi -Method POST -Route $route -Body $body -ThrowOnFailure
$createdId = $created.name
if (-not $createdId) {
    throw "Creation response did not contain an ID. Inspect My flows for the prepared name before retrying."
}
# Stop again through the supported cmdlet, then verify the returned state.
Disable-Flow -EnvironmentName $EnvironmentName -FlowName $createdId | Out-Null
$verified = Get-Flow -EnvironmentName $EnvironmentName -FlowName $createdId
$state = $verified.Internal.properties.state
@{
    environmentName = $EnvironmentName; sourceFlowName = $SourceFlowName; flowName = $createdId
    displayName = $DisplayName; state = $state; createdAt = (Get-Date).ToString('o')
    status = 'created'; liveVerified = ($state -eq 'Stopped')
    url = "https://make.powerautomate.com/environments/$EnvironmentName/flows/$createdId/details"
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $outputPath 'manifest.json') -Encoding UTF8
if ($state -ne 'Stopped') { throw "New exterior flow state is $state. Turn it off in Power Automate before continuing." }
Write-Host "EXTERIOR_FLOW_CREATED_STOPPED: $createdId"
