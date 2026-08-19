$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspaceRoot ".venv/Scripts/python.exe"
$nodeNpm = "E:/Environment_f/nvm_f/v22.13.0/npm.cmd"
$runtimeRoot = Join-Path $workspaceRoot "runtime-data"
$pidPath = Join-Path $runtimeRoot "native-pids.json"

if (-not (Test-Path -LiteralPath (Join-Path $workspaceRoot ".env.local"))) {
    throw "Missing .env.local. Run scripts/setup-native-secrets.ps1 first."
}
if (-not (Test-Path -LiteralPath $pythonPath)) { throw "Python venv not found: $pythonPath" }
$null = New-Item -ItemType Directory -Path $runtimeRoot -Force

if (Test-Path -LiteralPath $pidPath) {
    $existing = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
    foreach ($item in $existing) {
        $process = Get-Process -Id $item.pid -ErrorAction SilentlyContinue
        if ($process) { throw "A native process is already recorded: $($item.role) ($($item.pid))" }
    }
}

$processes = @()
function Start-NativeRole([string]$Role, [string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory) {
    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru
    $script:processes += [pscustomobject]@{ role = $Role; pid = $process.Id; started_at = (Get-Date).ToUniversalTime().ToString("o") }
}

Start-NativeRole "api" $pythonPath @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000") $workspaceRoot
Start-NativeRole "web" $nodeNpm @("run", "dev") (Join-Path $workspaceRoot "frontend")
Start-NativeRole "outbox-relay" $pythonPath @("-m", "backend.runtime.worker", "relay") $workspaceRoot
Start-NativeRole "agent-worker" $pythonPath @("-m", "backend.runtime.worker", "agent") $workspaceRoot
Start-NativeRole "ingestion-worker" $pythonPath @("-m", "backend.runtime.ingestion") $workspaceRoot

$processes | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding utf8
Write-Output "Started $($processes.Count) native roles. API: http://127.0.0.1:8000; Web: http://127.0.0.1:3000"
