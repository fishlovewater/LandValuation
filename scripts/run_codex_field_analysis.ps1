[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [Guid]$CaseId,

    [Parameter(Mandatory = $true)]
    [Guid]$DocumentId,

    [Parameter(Mandatory = $true)]
    [ValidateSet("F01", "F02", "F03", "F04", "S01", "F02-RF")]
    [string]$FormCode,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._:/-]*$")]
    [string]$ModelId,

    [string]$ApiBaseUrl = "http://localhost:8000/api/v1",

    [string]$Username = "APPRAISER_test",

    [string]$CodexExecutable
)

$ErrorActionPreference = "Stop"

function ConvertFrom-SecureValue {
    param([Parameter(Mandatory = $true)][SecureString]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function Resolve-CodexExecutable {
    param([string]$ExplicitPath)

    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $resolved = [IO.Path]::GetFullPath($ExplicitPath)
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "The specified Codex executable does not exist."
        }
        return $resolved
    }

    $extensionRoot = Join-Path $env:USERPROFILE ".vscode\extensions"
    if (Test-Path -LiteralPath $extensionRoot -PathType Container) {
        $extensionExecutable = Get-ChildItem `
            -LiteralPath $extensionRoot `
            -Directory `
            -Filter "openai.chatgpt-*-win32-x64" |
            Sort-Object LastWriteTime -Descending |
            ForEach-Object {
                Join-Path $_.FullName "bin\windows-x86_64\codex.exe"
            } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if ($extensionExecutable) {
            return [IO.Path]::GetFullPath($extensionExecutable)
        }
    }

    $command = Get-Command codex -CommandType Application -ErrorAction Stop
    return $command.Source
}

function Get-EvidenceKey {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value) {
        return ""
    }
    $normalized = $Value.Normalize([Text.NormalizationForm]::FormKC)
    return [Text.RegularExpressions.Regex]::Replace(
        $normalized,
        "[\s,，:：|]",
        ""
    )
}

function Get-EvidenceProjection {
    param([AllowEmptyString()][string]$Value)

    $keyBuilder = [Text.StringBuilder]::new()
    $originalIndexes = [Collections.Generic.List[int]]::new()
    if ($null -eq $Value) {
        return [pscustomobject]@{
            Key = ""
            OriginalIndexes = @()
        }
    }
    for ($index = 0; $index -lt $Value.Length; $index++) {
        $normalizedPart = $Value.Substring($index, 1).Normalize(
            [Text.NormalizationForm]::FormKC
        )
        foreach ($character in $normalizedPart.ToCharArray()) {
            if ([Text.RegularExpressions.Regex]::IsMatch(
                [string]$character,
                "[\s,，:：|]"
            )) {
                continue
            }
            $null = $keyBuilder.Append($character)
            $originalIndexes.Add($index)
        }
    }
    return [pscustomobject]@{
        Key = $keyBuilder.ToString()
        OriginalIndexes = @($originalIndexes)
    }
}

function Find-ExactOcrEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$OcrText,
        [Parameter(Mandatory = $true)][string]$SourceText
    )

    if ($OcrText.Contains($SourceText)) {
        return $SourceText
    }
    $sourceProjection = Get-EvidenceProjection -Value $SourceText
    if ([string]::IsNullOrWhiteSpace($sourceProjection.Key)) {
        return $null
    }
    $ocrProjection = Get-EvidenceProjection -Value $OcrText
    $projectedIndex = $ocrProjection.Key.IndexOf(
        $sourceProjection.Key,
        [StringComparison]::Ordinal
    )
    if ($projectedIndex -lt 0) {
        return $null
    }
    $lastProjectedIndex = $projectedIndex + $sourceProjection.Key.Length - 1
    $originalStart = $ocrProjection.OriginalIndexes[$projectedIndex]
    $originalEnd = $ocrProjection.OriginalIndexes[$lastProjectedIndex]
    return $OcrText.Substring($originalStart, $originalEnd - $originalStart + 1)
}

function Find-UniqueExactValueEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$OcrText,
        [Parameter(Mandatory = $true)][string]$ExtractedValue
    )

    if ([string]::IsNullOrWhiteSpace($ExtractedValue)) {
        return $null
    }
    $firstIndex = $OcrText.IndexOf(
        $ExtractedValue,
        [StringComparison]::Ordinal
    )
    if ($firstIndex -lt 0) {
        return $null
    }
    $secondIndex = $OcrText.IndexOf(
        $ExtractedValue,
        $firstIndex + $ExtractedValue.Length,
        [StringComparison]::Ordinal
    )
    if ($secondIndex -ge 0) {
        return $null
    }
    return $OcrText.Substring($firstIndex, $ExtractedValue.Length)
}

function Repair-CandidateEvidence {
    param(
        [Parameter(Mandatory = $true)]$Result,
        [Parameter(Mandatory = $true)][string]$OcrText
    )

    $repairCount = 0
    foreach ($candidate in @($Result.candidates)) {
        $sourceText = [string]$candidate.source_text
        if ([string]::IsNullOrWhiteSpace($sourceText)) {
            continue
        }
        $exactEvidence = Find-ExactOcrEvidence `
            -OcrText $OcrText `
            -SourceText $sourceText
        if ($null -eq $exactEvidence) {
            $exactEvidence = Find-UniqueExactValueEvidence `
                -OcrText $OcrText `
                -ExtractedValue ([string]$candidate.extracted_value)
        }
        if (
            $null -ne $exactEvidence -and
            -not [string]::Equals(
                $sourceText,
                $exactEvidence,
                [StringComparison]::Ordinal
            )
        ) {
            $candidate.source_text = $exactEvidence
            $repairCount++
        }
    }
    return $repairCount
}

function Get-CandidateEvidenceErrors {
    param(
        [Parameter(Mandatory = $true)]$Result,
        [Parameter(Mandatory = $true)][string]$OcrText
    )

    $errors = [Collections.Generic.List[string]]::new()
    foreach ($candidate in @($Result.candidates)) {
        $fieldName = [string]$candidate.field_name
        $sourceText = [string]$candidate.source_text
        $extractedValue = [string]$candidate.extracted_value
        if ([string]::IsNullOrWhiteSpace($sourceText)) {
            $errors.Add("${fieldName}: source_text is empty")
            continue
        }
        if ([string]::IsNullOrWhiteSpace($extractedValue)) {
            $errors.Add("${fieldName}: extracted_value is empty")
            continue
        }
        if (-not $OcrText.Contains($sourceText)) {
            $errors.Add("${fieldName}: source_text is not an exact OCR substring")
            continue
        }
        $valueKey = Get-EvidenceKey -Value $extractedValue
        $sourceKey = Get-EvidenceKey -Value $sourceText
        if ([string]::IsNullOrWhiteSpace($valueKey) -or -not $sourceKey.Contains($valueKey)) {
            $errors.Add("${fieldName}: extracted_value is not present in source_text")
        }
    }
    return @($errors)
}

function Select-UnambiguousCandidates {
    param(
        [Parameter(Mandatory = $true)]$Result,
        [Parameter(Mandatory = $true)][string]$OcrText
    )

    $selected = [Collections.Generic.List[object]]::new()
    $errors = [Collections.Generic.List[string]]::new()
    $skippedDuplicateCount = 0
    foreach ($group in @($Result.candidates | Group-Object -Property field_name)) {
        $valid = [Collections.Generic.List[object]]::new()
        $invalidErrors = [Collections.Generic.List[string]]::new()
        foreach ($candidate in @($group.Group)) {
            $candidateResult = [pscustomobject]@{
                candidates = @($candidate)
            }
            $candidateErrors = @(
                Get-CandidateEvidenceErrors `
                    -Result $candidateResult `
                    -OcrText $OcrText
            )
            if ($candidateErrors.Count -eq 0) {
                $valid.Add($candidate)
            }
            else {
                foreach ($candidateError in $candidateErrors) {
                    $invalidErrors.Add($candidateError)
                }
            }
        }
        if ($valid.Count -eq 0) {
            foreach ($invalidError in $invalidErrors) {
                $errors.Add($invalidError)
            }
            continue
        }
        $distinctValues = @(
            $valid |
                ForEach-Object { [string]$_.extracted_value } |
                Sort-Object -Unique
        )
        if ($distinctValues.Count -gt 1) {
            $errors.Add(
                "$($group.Name): multiple conflicting candidates have exact OCR evidence"
            )
            continue
        }
        $selected.Add($valid[0])
        $skippedDuplicateCount += $group.Count - 1
    }
    $Result.candidates = @($selected)
    return [pscustomobject]@{
        Errors = @($errors)
        SkippedDuplicateCount = $skippedDuplicateCount
    }
}

function Invoke-CodexStructuredAnalysis {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][string]$SchemaPath,
        [Parameter(Mandatory = $true)][string]$ResultPath,
        [Parameter(Mandatory = $true)][string]$ModelId,
        [Parameter(Mandatory = $true)][string]$CodexExecutable,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )

    if (Test-Path -LiteralPath $ResultPath -PathType Leaf) {
        Remove-Item -LiteralPath $ResultPath -Force
    }
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $CodexExecutable
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardInputEncoding = [Text.UTF8Encoding]::new($false)
    foreach ($argument in @(
        "exec",
        "--ephemeral",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--output-schema", $SchemaPath,
        "--output-last-message", $ResultPath,
        "--model", $ModelId,
        "-"
    )) {
        $startInfo.ArgumentList.Add($argument)
    }

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Codex CLI failed to start."
    }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.Write($Prompt)
    $process.StandardInput.Close()
    $process.WaitForExit()
    $stdout = $stdoutTask.Result.Trim()
    $stderr = $stderrTask.Result.Trim()

    if ($process.ExitCode -ne 0) {
        $diagnostic = @($stderr, $stdout) |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            Select-Object -Unique
        $diagnosticText = if ($diagnostic.Count -gt 0) {
            $diagnostic -join [Environment]::NewLine
        }
        else {
            "Codex CLI did not provide diagnostic output."
        }
        throw "Codex CLI failed with exit code $($process.ExitCode). No candidate was imported.`nCodex diagnostic:`n$diagnosticText"
    }
    if (-not (Test-Path -LiteralPath $ResultPath -PathType Leaf)) {
        throw "Codex CLI did not create the structured result file."
    }
    return Get-Content -LiteralPath $ResultPath -Raw | ConvertFrom-Json
}

$securePassword = Read-Host "API password for $Username" -AsSecureString
$plainPassword = ConvertFrom-SecureValue -Value $securePassword
try {
    $loginBody = @{
        username = $Username
        password = $plainPassword
    } | ConvertTo-Json
    $login = Invoke-RestMethod `
        -Uri "$ApiBaseUrl/auth/login" `
        -Method Post `
        -ContentType "application/json" `
        -Body $loginBody
}
finally {
    $plainPassword = $null
    $loginBody = $null
}

if (-not $login.access_token) {
    throw "API login did not return an access token."
}

$headers = @{ Authorization = "Bearer $($login.access_token)" }
$documentPath = "valuation/cases/$CaseId/documents/$DocumentId/extraction"
$requestBody = @{ form_code = $FormCode } | ConvertTo-Json
$package = Invoke-RestMethod `
    -Uri "$ApiBaseUrl/$documentPath/codex-package" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $requestBody

$allowedNames = @(
    $package.output_schema.properties.candidates.items.properties.field_name.enum
)
if ($allowedNames.Count -eq 0) {
    Write-Output "No remaining $FormCode fields require Codex analysis."
    return
}

$resolvedCodexExecutable = Resolve-CodexExecutable -ExplicitPath $CodexExecutable
$systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$runDirectory = Join-Path $systemTemp ("land-valuation-codex-" + [Guid]::NewGuid())
$resolvedRunDirectory = [IO.Path]::GetFullPath($runDirectory)
if (-not $resolvedRunDirectory.StartsWith(
    $systemTemp + '\',
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "Refusing to use a temporary directory outside the system temp path."
}

New-Item -ItemType Directory -Path $resolvedRunDirectory | Out-Null
$schemaPath = Join-Path $resolvedRunDirectory "field-analysis-schema.json"
$resultPath = Join-Path $resolvedRunDirectory "field-analysis-result.json"
$utf8NoBom = [Text.UTF8Encoding]::new($false)

try {
    [IO.File]::WriteAllText(
        $schemaPath,
        ($package.output_schema | ConvertTo-Json -Depth 20),
        $utf8NoBom
    )

    $promptPayload = $package.prompt | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace([string]$promptPayload.ocr_text)) {
        throw "Codex package did not contain OCR text."
    }
    $codexResult = Invoke-CodexStructuredAnalysis `
        -Prompt $package.prompt `
        -SchemaPath $schemaPath `
        -ResultPath $resultPath `
        -ModelId $ModelId `
        -CodexExecutable $resolvedCodexExecutable `
        -WorkingDirectory $resolvedRunDirectory
    $repairCount = Repair-CandidateEvidence `
        -Result $codexResult `
        -OcrText $promptPayload.ocr_text
    if ($repairCount -gt 0) {
        Write-Output "Aligned $repairCount Codex evidence fragment(s) to exact OCR text."
    }
    $selection = Select-UnambiguousCandidates `
        -Result $codexResult `
        -OcrText $promptPayload.ocr_text
    if ($selection.SkippedDuplicateCount -gt 0) {
        Write-Output "Skipped $($selection.SkippedDuplicateCount) duplicate Codex candidate(s) after exact OCR validation."
    }
    $evidenceErrors = @($selection.Errors)
    $verifiedCandidates = @($codexResult.candidates)
    if ($evidenceErrors.Count -gt 0) {
        Write-Output "Codex evidence format did not match OCR exactly; retrying once."
        $retryPrompt = @{
            task = "修正上一輪候選的 OCR 逐字證據格式"
            original_request = $promptPayload
            previous_output = $codexResult
            validation_errors = $evidenceErrors
            correction_rules = @(
                "重新從 original_request.ocr_text 複製 source_text，不得自行重打或整理"
                "source_text 必須是 ocr_text 中逐字且連續存在的子字串，保留換行與標點"
                "extracted_value 必須是 source_text 中逐字且連續存在的子字串"
                "不得轉換民國年、日期格式、數字逗號、全半形或 OCR 字樣"
                "無法提供逐字證據的欄位必須刪除，不得推測或創造資料"
                "只輸出既定 JSON Schema"
            )
        } | ConvertTo-Json -Depth 30
        $codexResult = Invoke-CodexStructuredAnalysis `
            -Prompt $retryPrompt `
            -SchemaPath $schemaPath `
            -ResultPath $resultPath `
            -ModelId $ModelId `
            -CodexExecutable $resolvedCodexExecutable `
            -WorkingDirectory $resolvedRunDirectory
        $repairCount = Repair-CandidateEvidence `
            -Result $codexResult `
            -OcrText $promptPayload.ocr_text
        if ($repairCount -gt 0) {
            Write-Output "Aligned $repairCount retried evidence fragment(s) to exact OCR text."
        }
        $selection = Select-UnambiguousCandidates `
            -Result $codexResult `
            -OcrText $promptPayload.ocr_text
        if ($selection.SkippedDuplicateCount -gt 0) {
            Write-Output "Skipped $($selection.SkippedDuplicateCount) retried duplicate candidate(s) after exact OCR validation."
        }
        $retryErrors = @($selection.Errors)
        $combinedResult = [pscustomobject]@{
            candidates = @($verifiedCandidates) + @($codexResult.candidates)
        }
        $combinedSelection = Select-UnambiguousCandidates `
            -Result $combinedResult `
            -OcrText $promptPayload.ocr_text
        if ($combinedSelection.SkippedDuplicateCount -gt 0) {
            Write-Output "Merged $($combinedSelection.SkippedDuplicateCount) duplicate verified candidate(s)."
        }
        $codexResult = $combinedResult
        $evidenceErrors = @($retryErrors) + @($combinedSelection.Errors)
    }
    if ($evidenceErrors.Count -gt 0) {
        Write-Output "Skipped $($evidenceErrors.Count) unverified or conflicting Codex candidate result(s)."
    }
    if (@($codexResult.candidates).Count -eq 0) {
        Write-Output "Codex analysis completed. No candidate passed exact OCR verification; nothing was imported."
        return
    }

    $importBody = @{
        form_code = $FormCode
        model_id = $ModelId
        candidates = @($codexResult.candidates)
    } | ConvertTo-Json -Depth 20
    $saved = Invoke-RestMethod `
        -Uri "$ApiBaseUrl/$documentPath/import-codex-candidates" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $importBody

    $codexCandidateCount = @(
        $saved.candidates | Where-Object { $_.analysis_provider -eq "CODEX" }
    ).Count
    Write-Output "Codex analysis completed. Saved CODEX candidates: $codexCandidateCount"
    Write-Output "Review and confirm candidates in Swagger before any form write."
}
finally {
    if (
        (Test-Path -LiteralPath $resolvedRunDirectory) -and
        $resolvedRunDirectory.StartsWith(
            $systemTemp + '\',
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        Remove-Item -LiteralPath $resolvedRunDirectory -Recurse -Force
    }
}
