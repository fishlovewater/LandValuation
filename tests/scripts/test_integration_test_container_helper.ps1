$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\..\scripts\integration-test-container.ps1")

function global:docker {
    $Arguments = $args

    $global:LASTEXITCODE = 0
    if ($Arguments -contains "ps") {
        if ($global:DockerScenario -eq "missing") {
            return ""
        }
        if ($Arguments -notcontains "--all") {
            throw "exited test containers require docker compose ps --all"
        }
        return "test-container-id"
    }
    if ($Arguments -contains "inspect") {
        return '{"Status":"exited","ExitCode":0}'
    }
    throw "Unexpected docker invocation: $Arguments"
}

$global:DockerScenario = "missing"
$threw = $false
try {
    Assert-IntegrationTestContainerSucceeded `
        -ComposeProject "valuation-review-test" `
        -ComposeFile "docker-compose.integration.yml"
}
catch {
    $threw = $true
    if ($_.Exception.Message -notmatch "test container was not created") {
        throw
    }
}

if (-not $threw) {
    throw "Expected a missing test container to be rejected"
}

$global:DockerScenario = "exited"
Assert-IntegrationTestContainerSucceeded `
    -ComposeProject "valuation-review-test" `
    -ComposeFile "docker-compose.integration.yml"

Write-Output "PASS: missing and exited test containers are handled"
