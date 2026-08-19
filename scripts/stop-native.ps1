$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $workspaceRoot "runtime-data/native-pids.json"
if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Output "No native PID file found."
    exit 0
}
$processes = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
foreach ($item in $processes) {
    $process = Get-Process -Id $item.pid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $item.pid -Force
        Write-Output "Stopped $($item.role) ($($item.pid))"
    }
}
Remove-Item -LiteralPath $pidPath -Force
