$ErrorActionPreference = "Stop"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Import-Module Microsoft.PowerApps.PowerShell
Add-PowerAppsAccount -Endpoint prod | Out-Null

$environmentName = "Default-2113d5b5-fefb-4c1d-bc26-12d7f8c3581d"
$flowName = "94732731-b972-483b-b973-16dea2efa3fd"
$route = "https://{flowEndpoint}/providers/Microsoft.Flow/environments/$environmentName/flows/${flowName}?api-version={apiVersion}"
$flow = Get-Flow -EnvironmentName $environmentName -FlowName $flowName
$properties = $flow.Internal.properties
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = Join-Path $PSScriptRoot "logs\power_automate_before_mailing_list_$stamp.json"
$properties | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $backupPath -Encoding UTF8

$condition = $properties.definition.actions.Check_DailyNews_success
$successMail = $condition.actions.Send_success_mail
if ($null -eq $successMail) {
    throw "Send_success_mail was not found in the DailyNews flow."
}

$oneDriveConnection = Get-PowerAppConnection -EnvironmentName $environmentName |
    Where-Object { $_.ConnectorName -eq "shared_onedriveforbusiness" } |
    Select-Object -First 1
if ($null -eq $oneDriveConnection) {
    throw "OneDrive for Business connection was not found. Create it once in Power Automate and run this script again."
}

$oneDriveReference = [ordered]@{
    connectionName = $oneDriveConnection.ConnectionName
    source = "Embedded"
    id = "/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness"
    displayName = "OneDrive for Business"
    iconUri = "https://connectoricons-prod.azureedge.net/releases/v1.0.1685/1.0.1685.3700/onedriveforbusiness/icon.png"
    brandColor = "#0078D4"
    tier = "Standard"
    apiName = "onedriveforbusiness"
    isProcessSimpleApiReferenceConversionAlreadyDone = $false
}
$properties.connectionReferences |
    Add-Member -NotePropertyName "shared_onedriveforbusiness" -NotePropertyValue $oneDriveReference -Force

$getMailingList = [ordered]@{
    runAfter = @{}
    type = "OpenApiConnection"
    inputs = [ordered]@{
        parameters = [ordered]@{
            path = "/DailyNewsAutomation/mailing_list.json"
            inferContentType = $true
        }
        host = [ordered]@{
            apiId = "/providers/Microsoft.PowerApps/apis/shared_onedriveforbusiness"
            connectionName = "shared_onedriveforbusiness"
            operationId = "GetFileContentByPath"
        }
        authentication = "@parameters('`$authentication')"
    }
}

$successMail.runAfter = [ordered]@{
    Get_DailyNews_mailing_list = @("Succeeded")
}
$successMail.inputs.parameters.'emailMessage/To' = "@json(string(body('Get_DailyNews_mailing_list')))?['to']"

$mailingListFailure = [ordered]@{
    runAfter = [ordered]@{
        Get_DailyNews_mailing_list = @("Failed", "TimedOut")
    }
    type = "OpenApiConnection"
    inputs = [ordered]@{
        parameters = [ordered]@{
            "emailMessage/To" = "yuki.nakamura@toyoda-gosei.co.jp"
            "emailMessage/Subject" = "[要確認] DailyNewsメール配信先の取得失敗"
            "emailMessage/Body" = "<p>業務用OneDriveのDailyNewsAutomation/mailing_list.jsonを取得できなかったため、関係者向けメールは送信しませんでした。</p><p>DailyNews PCのOneDrive同期とメール配信先ファイルを確認してください。</p><p>（自動配信・管理者のみ）</p>"
            "emailMessage/Importance" = "High"
        }
        host = $successMail.inputs.host
        authentication = "@parameters('`$authentication')"
    }
}

$condition.actions = [ordered]@{
    Get_DailyNews_mailing_list = $getMailingList
    Send_success_mail = $successMail
    Notify_mailing_list_failure = $mailingListFailure
}

$body = [ordered]@{
    properties = [ordered]@{
        displayName = $properties.displayName
        definition = $properties.definition
        connectionReferences = $properties.connectionReferences
        environment = $properties.environment
    }
}

try {
    InvokeApi -Method PATCH -Route $route -Body $body -ThrowOnFailure | Out-Null
    $updated = Get-Flow -EnvironmentName $environmentName -FlowName $flowName
    $updatedCondition = $updated.Internal.properties.definition.actions.Check_DailyNews_success
    if ($null -eq $updatedCondition.actions.Get_DailyNews_mailing_list -or
        $updatedCondition.actions.Send_success_mail.inputs.parameters.'emailMessage/To' -notmatch "Get_DailyNews_mailing_list") {
        throw "Updated flow verification failed."
    }
    Write-Host "FLOW_MAILING_LIST_UPDATE_OK"
    Write-Host ("OneDrive connection: " + $oneDriveConnection.ConnectionName)
    Write-Host "Recipient file: /DailyNewsAutomation/mailing_list.json"
}
catch {
    Write-Warning "Update failed; restoring the saved flow definition."
    $backup = Get-Content -LiteralPath $backupPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $restoreBody = [ordered]@{
        properties = [ordered]@{
            displayName = $backup.displayName
            definition = $backup.definition
            connectionReferences = $backup.connectionReferences
            environment = $backup.environment
        }
    }
    InvokeApi -Method PATCH -Route $route -Body $restoreBody -ThrowOnFailure | Out-Null
    throw
}
