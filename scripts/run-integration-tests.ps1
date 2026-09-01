param([string]$PytestArgs = "")

# PytestArgs accepts only whitespace-separated pytest selectors and options.
# Quote the entire PowerShell argument; embedded shell quoting is intentionally unsupported.
if ($PytestArgs -match '[^A-Za-z0-9_./\\:\-\s=,\[\]\(\)]') {
    throw "PytestArgs may contain only pytest selectors and simple options"
}

$runId = "vr-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
$project = "valuation-review-$runId"
$env:TEST_RUN_ID = $runId
$env:POSTGRES_DB = "land_valuation_test_" + $runId.Replace("-", "_")
$env:MINIO_BUCKET = "land-valuation-test-$runId"
$env:APP_POSTGRES_USER = "land_valuation_runtime_" + $runId.Replace("-", "_")
$env:APP_POSTGRES_PASSWORD = [guid]::NewGuid().ToString("N")
$env:APP_ENV = "test"
$env:PYTEST_ARGS = $PytestArgs
. (Join-Path $PSScriptRoot "integration-test-container.ps1")
try {
    docker compose -p $project -f docker-compose.integration.yml up --build --abort-on-container-exit --exit-code-from test
    $composeUpExitCode = $LASTEXITCODE
    Assert-IntegrationTestContainerSucceeded `
        -ComposeProject $project `
        -ComposeFile "docker-compose.integration.yml"
    if ($composeUpExitCode -ne 0) { throw "integration tests failed (compose exit code $composeUpExitCode)" }
}
finally {
    docker compose -p $project -f docker-compose.integration.yml down --volumes --remove-orphans
    $residue = docker ps -a --filter "label=com.docker.compose.project=$project" --format "{{.ID}}"
    if ($residue) { throw "test containers remain: $residue" }
    $volumes = docker volume ls --filter "label=com.docker.compose.project=$project" --format "{{.Name}}"
    if ($volumes) { throw "test volumes remain: $volumes" }
}
