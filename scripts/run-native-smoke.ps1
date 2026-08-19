param(
    [string]$Username = "workspace-admin",
    [int]$TimeoutSeconds = 600
)

$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspaceRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) { throw "Python venv not found: $pythonPath" }
Push-Location $workspaceRoot
try {
    & $pythonPath -m backend.scripts.native_smoke --username $Username --timeout $TimeoutSeconds
    if ($LASTEXITCODE -ne 0) { throw "Native smoke failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
}
