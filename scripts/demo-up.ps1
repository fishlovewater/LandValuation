[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$Bedrock,
    [string]$BedrockRegion = 'ap-northeast-1',
    [string]$BedrockModelId = 'global.anthropic.claude-sonnet-4-5-20250929-v1:0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectName = 'landvaluation-persistent-demo'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$FrontendUrl = 'http://127.0.0.1:5173'
$ApiUrl = 'http://127.0.0.1:18000'
$ReadyUrl = "$ApiUrl/health/ready"

$ComposeArgs = @(
    '--project-name', $ProjectName,
    '-f', 'docker-compose.yml',
    '-f', 'docker-compose.demo.yml',
    '--env-file', '.env.example'
)

if ($Bedrock) {
    if ([string]::IsNullOrWhiteSpace($env:AWS_BEARER_TOKEN_BEDROCK)) {
        throw @"
Bedrock Demo requires AWS_BEARER_TOKEN_BEDROCK in this process environment.
Do not paste the key into source files. Set it in the terminal before launching this script.
"@
    }

    $env:BEDROCK_REGION = $BedrockRegion
    $env:BEDROCK_MODEL_ID = $BedrockModelId
    $ComposeArgs += @('-f', 'docker-compose.bedrock.yml')
}

function Invoke-DemoCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$DiscardOutput
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Docker Compose writes normal build/progress messages to stderr. Under
        # Windows PowerShell, ErrorActionPreference=Stop can turn those messages
        # into NativeCommandError records before LASTEXITCODE can be inspected.
        # Treat the native process exit code as authoritative instead.
        $ErrorActionPreference = 'Continue'
        $output = & docker compose @ComposeArgs @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        $summary = ($output | Select-Object -Last 12 | Out-String).Trim()
        throw "Demo Compose command failed: docker compose $($Arguments -join ' ')`n$summary"
    }

    if (-not $DiscardOutput) {
        return $output
    }
}

function Get-DemoStatus {
    $output = Invoke-DemoCompose -Arguments @('exec', '-T', 'api', 'python', '-m', 'app.demo', 'status')
    $raw = ($output | Out-String).Trim()
    if (-not $raw) {
        throw 'Demo status returned no output.'
    }

    try {
        $status = $raw | ConvertFrom-Json
    }
    catch {
        throw 'Demo status did not return valid JSON.'
    }

    if (-not $status.ok) {
        throw "Demo status failed: $($status.error)"
    }

    return $status
}

function Wait-DemoApiReady {
    $attempts = 60
    for ($attempt = 1; $attempt -le $attempts; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri $ReadyUrl -Method Get -TimeoutSec 2
            if ($response) {
                return
            }
        }
        catch {
            if ($attempt -eq $attempts) {
                throw "Demo API did not become ready at $ReadyUrl. Check Demo Compose logs."
            }
        }
        Start-Sleep -Seconds 1
    }
}

Push-Location $RepoRoot
try {
    if (-not $SkipBuild) {
        Write-Host 'Building isolated Demo API and migration images...'
        Invoke-DemoCompose -Arguments @('build', 'migrate', 'api') -DiscardOutput
    }

    Write-Host 'Starting isolated Demo PostgreSQL, MinIO, migration, and API services...'
    Invoke-DemoCompose -Arguments @(
        'up', '-d',
        'db', 'db-role-init', 'migrate', 'minio', 'minio-init', 'knowledge-init', 'api'
    ) -DiscardOutput

    Wait-DemoApiReady
    $status = Get-DemoStatus

    if (-not $status.ready) {
        $hasCase = $null -ne $status.case -and -not [string]::IsNullOrWhiteSpace([string]$status.case.case_id)
        if ($hasCase -and -not $status.pre_submission) {
            throw @"
The isolated Demo already contains a submitted or reviewed case.
For safety this script will not reseed it automatically.
Use the documented project-scoped teardown procedure before starting a fresh Demo generation.
"@
        }

        Write-Host 'Seeding the production-shaped Demo lifecycle generation...'
        Invoke-DemoCompose -Arguments @('exec', '-T', 'api', 'python', '-m', 'app.demo', 'seed') -DiscardOutput
        $status = Get-DemoStatus
    }

    if (-not $status.ready) {
        throw 'Demo seed completed but readiness is still false. Run app.demo status and inspect the isolated Demo logs.'
    }

    Write-Host 'Seeding the dedicated External Review Demo case...'
    Invoke-DemoCompose -Arguments @(
        'exec', '-T', 'api', 'python', '-m', 'app.review.demo', 'seed'
    ) -DiscardOutput

    Write-Host 'Preparing the typed-login development system administrator...'
    Invoke-DemoCompose -Arguments @(
        'exec', '-T', 'api', 'python', '-m', 'app.demo.admin', 'seed'
    ) -DiscardOutput

    Write-Host 'Indexing official Knowledge PDFs (idempotent; OCR is used only where required)...'
    Invoke-DemoCompose -Arguments @(
        'exec', '-T', 'api', 'python', '-m', 'app.knowledge.import_official',
        '--approved-by-username', 'valuation_demo'
    ) -DiscardOutput

    Write-Host ''
    Write-Host 'Demo backend is ready.'
    Write-Host "API:      $ApiUrl"
    Write-Host "Swagger:  $ApiUrl/docs"
    Write-Host "Frontend: $FrontendUrl"
    if ($Bedrock) {
        Write-Host "AI:       Amazon Bedrock ($BedrockRegion / $BedrockModelId)"
    }
    Write-Host ''
    Write-Host 'Start the frontend in another PowerShell window:'
    Write-Host '  cd frontend'
    Write-Host '  npm run dev'
    Write-Host ''
    Write-Host 'Then use the three one-click Demo role buttons. No username/password typing is required.'
    Write-Host 'Account-management testing uses the separate system_admin_demo typed-login account with the standard local Demo password.'
}
finally {
    Pop-Location
}
