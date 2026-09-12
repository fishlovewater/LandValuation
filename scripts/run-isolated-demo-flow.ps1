[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$KeepStack
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectName = 'landvaluation-acceptance'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $RepoRoot 'frontend'
$ApiUrl = 'http://127.0.0.1:18100'
$FrontendUrl = 'http://127.0.0.1:5174'

$ComposeArgs = @(
    '--project-name', $ProjectName,
    '-f', 'docker-compose.yml',
    '-f', 'docker-compose.demo.yml',
    '-f', 'docker-compose.acceptance.yml',
    '--env-file', '.env.example'
)

function Invoke-AcceptanceCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$DiscardOutput
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & docker compose @ComposeArgs @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        $summary = ($output | Select-Object -Last 20 | Out-String).Trim()
        throw "Acceptance Compose command failed: docker compose $($Arguments -join ' ')`n$summary"
    }

    if (-not $DiscardOutput) {
        return $output
    }
}

function Wait-AcceptanceApi {
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri "$ApiUrl/health/live" -Method Get -TimeoutSec 2
            if ($response.status -eq 'live') {
                return
            }
        }
        catch {
            if ($attempt -eq 60) {
                throw "Acceptance API did not become live at $ApiUrl."
            }
        }
        Start-Sleep -Seconds 1
    }
}

Push-Location $RepoRoot
try {
    Write-Host 'Resetting isolated acceptance stack and volumes...'
    Invoke-AcceptanceCompose -Arguments @('down', '--volumes', '--remove-orphans') -DiscardOutput

    if (-not $SkipBuild) {
        Write-Host 'Building acceptance API and migration images...'
        Invoke-AcceptanceCompose -Arguments @('build', 'migrate', 'api') -DiscardOutput
    }

    Write-Host 'Starting isolated acceptance services...'
    Invoke-AcceptanceCompose -Arguments @('up', '-d') -DiscardOutput
    Wait-AcceptanceApi

    Write-Host 'Seeding a fresh Demo lifecycle generation...'
    $seedOutput = Invoke-AcceptanceCompose -Arguments @('exec', '-T', 'api', 'python', '-m', 'app.demo', 'seed')
    $seedCompact = (($seedOutput | ForEach-Object { [string]$_ }) -join '') -replace '\s+', ''
    $uuidMatches = [regex]::Matches(
        $seedCompact,
        '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    )
    if ($uuidMatches.Count -lt 2) {
        throw 'Acceptance Demo seed output did not contain the expected case/form IDs.'
    }

    Write-Host 'Seeding the dedicated External Review acceptance case...'
    $externalSeedOutput = Invoke-AcceptanceCompose -Arguments @(
        'exec', '-T', 'api', 'python', '-m', 'app.review.demo', 'seed'
    )
    $externalSeedRaw = ($externalSeedOutput | Out-String).Trim()
    try {
        $externalSeed = $externalSeedRaw | ConvertFrom-Json
    }
    catch {
        throw 'External Review Demo seed did not return valid JSON.'
    }
    if (-not $externalSeed.ok -or [string]::IsNullOrWhiteSpace([string]$externalSeed.review_id)) {
        throw "External Review Demo seed failed: $externalSeedRaw"
    }

    $env:E2E_BASE_URL = $FrontendUrl
    $env:VITE_DEV_PORT = '5174'
    $env:VITE_DEV_API_TARGET = $ApiUrl
    $env:VITE_API_BASE_URL = '/api/v1'
    $env:KNOWLEDGE_ANSWER_PROVIDER = 'ollama'
    $env:E2E_CASE_ID = $uuidMatches[0].Value
    $env:E2E_F03_FORM_ID = $uuidMatches[1].Value
    $env:E2E_CASE_NO = 'DEMO-F03-PERSISTENT-001'
    $env:E2E_EXTERNAL_REVIEW_ID = [string]$externalSeed.review_id
    $env:E2E_EXTERNAL_CASE_NO = 'DEMO-EXTERNAL-REVIEW-001'
    $env:E2E_APPRAISER_USERNAME = 'valuation_demo'
    $env:E2E_REVIEWER_USERNAME = 'review_demo'
    $env:E2E_INSPECTOR_USERNAME = 'inspector_demo'
    $env:E2E_APPRAISER_PASSWORD = 'Demo1234!'
    $env:E2E_REVIEWER_PASSWORD = 'Demo1234!'
    $env:E2E_INSPECTOR_PASSWORD = 'Demo1234!'
    $env:E2E_PERMISSION_GATE_ENABLED = 'true'
    $env:E2E_PERMISSION_CODE = 'knowledge.read'
    $env:E2E_PERMISSION_OPERATOR_COMMAND = 'docker compose --project-directory .. -p landvaluation-acceptance -f ../docker-compose.yml -f ../docker-compose.demo.yml -f ../docker-compose.acceptance.yml --env-file ../.env.example exec -T api python -m app.demo permission %E2E_PERMISSION_ACTION% %E2E_PERMISSION_CODE%'
    Remove-Item Env:CI -ErrorAction SilentlyContinue

    Write-Host 'Running the real Assistant -> Valuation -> Review -> History browser journey...'
    Push-Location $FrontendRoot
    try {
        & npm.cmd run test:e2e -- tests/e2e/demo-flow.spec.ts tests/e2e/external-review-demo.spec.ts --workers=1
        if ($LASTEXITCODE -ne 0) {
            throw "Playwright acceptance failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if (-not $KeepStack) {
        Write-Host 'Removing isolated acceptance containers and volumes...'
        try {
            Invoke-AcceptanceCompose -Arguments @('down', '--volumes', '--remove-orphans') -DiscardOutput
        }
        catch {
            Write-Warning $_
        }
    }
    Pop-Location
}
