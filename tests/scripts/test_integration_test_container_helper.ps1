$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "..\..\scripts\integration-test-container.ps1")

$global:DockerScenario = "missing"
function global:docker {
    $Arguments = $args

    $global:LASTEXITCODE = 0
    if ($Arguments -contains "ps") {
        return ""
    }
    throw "docker inspect should not run when the test container is missing"
}

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

Write-Output "PASS: missing test container is rejected"
