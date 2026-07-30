[CmdletBinding()]
param(
    [string]$ContentSource = ""
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "deploy.ps1") -ContentSource $ContentSource
