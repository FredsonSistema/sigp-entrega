$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$adapterDir = Join-Path $PSScriptRoot "output\qwen2.5-0.5b-lora"
$secretFile = Join-Path $repoRoot "docs\entrega-academica\sqlserver\.env.academic"
$composeFile = Join-Path $repoRoot "docs\entrega-academica\sqlserver\compose.academic.yml"
$loraComposeFile = Join-Path $repoRoot "docs\entrega-academica\sqlserver\compose.lora.yml"
$loraContainer = "sigp_academic_lora"
$composeArgs = @("--env-file", $secretFile, "-f", $composeFile, "-f", $loraComposeFile)
$baselineComposeArgs = @("--env-file", $secretFile, "-f", $composeFile)
$composeStarted = $false

foreach ($path in @(
    $adapterDir,
    (Join-Path $adapterDir "adapter_model.safetensors"),
    (Join-Path $adapterDir "adapter_config.json"),
    $secretFile,
    $composeFile,
    $loraComposeFile
)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required LoRA integration file not found: $path"
    }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI is not available."
}

& docker compose @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "The academic Compose configuration is invalid."
}

try {
    & docker compose @composeArgs up -d --build --force-recreate academic-lora academic-ai
    if ($LASTEXITCODE -ne 0) {
        throw "Could not build or start the LoRA model service and academic API."
    }
    $composeStarted = $true

    $modelHealth = $null
    for ($attempt = 0; $attempt -lt 180; $attempt++) {
        try {
            $healthJson = & docker exec $loraContainer python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:5011/health', timeout=2).read().decode())" 2>$null
            $execExitCode = $LASTEXITCODE
        }
        catch {
            $healthJson = $null
            $execExitCode = 1
        }
        if ($execExitCode -eq 0 -and $healthJson) {
            try {
                $modelHealth = $healthJson | ConvertFrom-Json
            }
            catch {
                $modelHealth = $null
            }
            if ($modelHealth -and $modelHealth.status -eq "ok") {
                break
            }
        }
        Start-Sleep -Seconds 5
    }
    if ($null -eq $modelHealth -or $modelHealth.status -ne "ok") {
        throw "The LoRA model service did not become healthy within 15 minutes."
    }

    $apiHealth = $null
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $apiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:5010/health" -TimeoutSec 5
            if ($apiHealth.status -eq "ok") {
                break
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }
    if (
        $null -eq $apiHealth -or
        $apiHealth.model_backend -ne "transformers" -or
        $apiHealth.model_profile -ne "experimental-lora" -or
        $apiHealth.model -ne $modelHealth.model
    ) {
        throw "The academic API health check did not confirm the experimental LoRA model."
    }

    Write-Host "LoRA inference service is healthy: $($modelHealth.model)"
    Write-Host "Academic API is using profile '$($apiHealth.model_profile)'."
    Write-Host "The previous Ollama model and local secrets were not changed."
}
catch {
    if ($composeStarted) {
        Write-Warning "Integration failed; restoring the academic API to the baseline Ollama configuration."
        & docker compose @baselineComposeArgs up -d --force-recreate academic-ai
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not automatically restore the baseline academic API."
        }
        & docker compose @composeArgs stop academic-lora
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not stop the LoRA model service after rollback."
        }
    }
    throw
}
