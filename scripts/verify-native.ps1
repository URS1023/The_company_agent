param(
    [string]$AdminUsername = "workspace-admin",
    [switch]$SkipBootstrap
)

$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspaceRoot ".venv/Scripts/python.exe"
$envPath = Join-Path $workspaceRoot ".env.local"

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing .env.local. Run scripts/setup-native-secrets.ps1 first."
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python venv not found: $pythonPath"
}

Push-Location $workspaceRoot
try {
    Write-Output "[1/5] Applying Alembic migrations..."
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }

    if (-not $SkipBootstrap) {
        Write-Output "[2/5] Creating the first administrator (interactive password prompt)..."
        & $pythonPath -m backend.scripts.bootstrap_admin --username $AdminUsername
        if ($LASTEXITCODE -ne 0) { throw "Admin bootstrap failed." }
    } else {
        Write-Output "[2/5] Skipping administrator bootstrap."
    }

    Write-Output "[3/5] Probing Agnes Chat..."
    & $pythonPath -m backend.scripts.provider_probe agnes --live
    if ($LASTEXITCODE -ne 0) { throw "Agnes probe failed." }
    Write-Output "[4/5] Probing SiliconFlow Vision..."
    & $pythonPath -m backend.scripts.provider_probe siliconflow-vision --live
    if ($LASTEXITCODE -ne 0) { throw "SiliconFlow Vision probe failed." }
    Write-Output "[5/5] Probing SiliconFlow Embedding..."
    & $pythonPath -m backend.scripts.provider_probe siliconflow-embedding --live
    if ($LASTEXITCODE -ne 0) { throw "SiliconFlow Embedding probe failed." }

    Write-Output "Native verification passed. No Secret values were printed by this script."
} finally {
    Pop-Location
}
