function Assert-IntegrationTestContainerSucceeded {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$ComposeProject,
        [Parameter(Mandatory = $true)][string]$ComposeFile
    )

    $testContainerId = & docker compose -p $ComposeProject -f $ComposeFile ps -q test
    $composePsExitCode = $LASTEXITCODE
    if ($composePsExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($testContainerId)) {
        throw "integration tests failed: test container was not created"
    }

    $testContainerId = ($testContainerId | Select-Object -First 1).Trim()
    $stateJson = & docker inspect $testContainerId --format '{{json .State}}'
    $inspectExitCode = $LASTEXITCODE
    if ($inspectExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($stateJson)) {
        throw "integration tests failed: unable to inspect test container $testContainerId"
    }

    try {
        $state = $stateJson | ConvertFrom-Json
    }
    catch {
        throw "integration tests failed: invalid state for test container $testContainerId"
    }

    if ($state.Status -ne "exited" -or [int]$state.ExitCode -ne 0) {
        throw "integration tests failed: test container status=$($state.Status), exit_code=$($state.ExitCode)"
    }
}
