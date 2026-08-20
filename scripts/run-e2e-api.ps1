$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "get-native-python.ps1")
$pythonPath = Get-NativePython -WorkspaceRoot $workspaceRoot
Set-Location -LiteralPath $workspaceRoot
$e2eDatabase = Join-Path $workspaceRoot ".e2e.db"
$e2eStorage = Join-Path $workspaceRoot "runtime-data/e2e-storage"
if (Test-Path -LiteralPath $e2eDatabase) { Remove-Item -LiteralPath $e2eDatabase -Force }
if (Test-Path -LiteralPath $e2eStorage) { Remove-Item -LiteralPath $e2eStorage -Recurse -Force }
$env:APP_ENV = "test"
$env:MYSQL_URL = "sqlite+aiosqlite:///./.e2e.db"
$env:LOCAL_STORAGE_ROOT = "$workspaceRoot/runtime-data/e2e-storage"
$env:ALLOW_EXTERNAL_CHAT = "false"
$env:ALLOW_EXTERNAL_VISION = "false"
$env:ALLOW_EXTERNAL_EMBEDDING = "false"
& $pythonPath -m backend.scripts.e2e_server
