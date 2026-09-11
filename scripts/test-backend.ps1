param(
    [string]$TestRunId = "",
    [string]$PytestArgs = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $TestRunId) {
    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    $suffix = -join ((97..122) | Get-Random -Count 5 | ForEach-Object { [char]$_ })
    $TestRunId = "vr-$stamp-$suffix"
}

if ($TestRunId -notmatch '^[a-zA-Z0-9-]+$') {
    throw "TestRunId may contain only letters, numbers, and hyphens."
}

$safeId = $TestRunId.ToLowerInvariant()
$projectName = "landvaluation-test-$safeId"
$env:TEST_RUN_ID = $safeId
$env:POSTGRES_DB = "land_valuation_test_$($safeId -replace '-', '_')"
$env:APP_POSTGRES_USER = "lv_test_$($safeId -replace '-', '_')"
$env:APP_POSTGRES_PASSWORD = "integration-app-secret"
$env:MINIO_BUCKET = "land-valuation-test-$safeId"
$env:PYTEST_ARGS = $PytestArgs

if ($env:POSTGRES_DB -eq 'land_valuation' -or $projectName -notlike 'landvaluation-test-*') {
    throw "Safety guard refused to run against a non-isolated database/project."
}

$compose = @('compose', '-p', $projectName, '-f', 'docker-compose.integration.yml')
$exitCode = 1
try {
    Write-Host "Starting isolated backend test environment: $projectName"
    & docker @compose up -d --build db minio minio-init migrate
    if ($LASTEXITCODE -ne 0) { throw "Failed to start isolated test dependencies." }

    Write-Host "Running backend tests with TEST_RUN_ID=$safeId"
    & docker @compose run --rm test
    $exitCode = $LASTEXITCODE
}
finally {
    Write-Host "Removing isolated test containers and volumes: $projectName"
    & docker @compose down --volumes --remove-orphans
}

exit $exitCode
