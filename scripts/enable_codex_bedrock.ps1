[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-z]{2}(?:-gov)?-[a-z]+-\d$")]
    [string]$Region,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^openai\.[A-Za-z0-9._-]+$")]
    [string]$ModelId,

    [switch]$Apply
)

$ErrorActionPreference = "Stop"

if ($Region -match "-gov-") {
    throw "Local Codex does not support the Bedrock Mantle path in GovCloud Regions."
}

$codexRoot = Join-Path $env:USERPROFILE ".codex"
$configPath = Join-Path $codexRoot "config.toml"
$envPath = Join-Path $codexRoot ".env"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

$hasBearerToken = -not [string]::IsNullOrWhiteSpace($env:AWS_BEARER_TOKEN_BEDROCK)
$hasSdkEnvironment = (
    -not [string]::IsNullOrWhiteSpace($env:AWS_ACCESS_KEY_ID) -or
    -not [string]::IsNullOrWhiteSpace($env:AWS_PROFILE)
)
$hasCodexEnvAuth = $false
if (Test-Path -LiteralPath $envPath) {
    $hasCodexEnvAuth = [bool](Select-String `
        -LiteralPath $envPath `
        -Pattern '^\s*AWS_BEARER_TOKEN_BEDROCK\s*=|^\s*AWS_PROFILE\s*=' `
        -Quiet)
}

Write-Output "Target provider: amazon-bedrock"
Write-Output "Target Region: $Region"
Write-Output "Target model: $ModelId"
Write-Output "AWS authentication configured: $($hasBearerToken -or $hasSdkEnvironment -or $hasCodexEnvAuth)"

if (-not $Apply) {
    Write-Output "Dry run only. No Codex setting was changed."
    Write-Output "Re-run with -Apply after AWS grants the Region, model and authentication."
    return
}

if (-not ($hasBearerToken -or $hasSdkEnvironment -or $hasCodexEnvAuth)) {
    throw "No Bedrock API key or AWS SDK credential source was detected. Configuration was not changed."
}

New-Item -ItemType Directory -Path $codexRoot -Force | Out-Null

if (Test-Path -LiteralPath $configPath) {
    Copy-Item `
        -LiteralPath $configPath `
        -Destination "$configPath.pre-bedrock-$timestamp.backup"
    $configLines = @([IO.File]::ReadAllLines($configPath))
}
else {
    $configLines = @()
}

$firstSection = $configLines.Count
for ($index = 0; $index -lt $configLines.Count; $index++) {
    if ($configLines[$index] -match '^\s*\[') {
        $firstSection = $index
        break
    }
}
$topLevel = @($configLines | Select-Object -First $firstSection)
$sections = @($configLines | Select-Object -Skip $firstSection)
$preservedTopLevel = @(
    $topLevel | Where-Object {
        $_ -notmatch '^\s*model_provider\s*=' -and
        $_ -notmatch '^\s*model\s*='
    }
)
$newConfig = @(
    'model_provider = "amazon-bedrock"'
    "model = `"$ModelId`""
) + $preservedTopLevel + $sections
$utf8NoBom = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllLines($configPath, $newConfig, $utf8NoBom)

if (Test-Path -LiteralPath $envPath) {
    Copy-Item `
        -LiteralPath $envPath `
        -Destination "$envPath.pre-bedrock-$timestamp.backup"
    $envLines = @([IO.File]::ReadAllLines($envPath))
}
else {
    $envLines = @()
}
$newEnv = @($envLines | Where-Object { $_ -notmatch '^\s*AWS_REGION\s*=' })
$newEnv += "AWS_REGION=$Region"
[IO.File]::WriteAllLines($envPath, $newEnv, $utf8NoBom)

Write-Output "Codex Bedrock configuration applied with backups."
Write-Output "Restart the Codex app or CLI, then use /status to verify provider and model."
