param(
    [string]$MysqlUser = "company_agent_app",
    [string]$MysqlDatabase = "company_agent",
    [switch]$SkipModelKeys
)

$ErrorActionPreference = "Stop"
$workspaceRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $workspaceRoot ".env.local"

if (Test-Path -LiteralPath $envPath) {
    $confirm = Read-Host ".env.local already exists. Replace it? (type REPLACE)"
    if ($confirm -cne "REPLACE") {
        Write-Output "Cancelled without changing .env.local."
        exit 0
    }
}

function Read-SecretText([string]$Prompt) {
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Escape-UrlPart([string]$Value) {
    return [Uri]::EscapeDataString($Value)
}

$mysqlPassword = Read-SecretText "MySQL password for $MysqlUser"
$agnesKey = ""
$siliconFlowKey = ""
if (-not $SkipModelKeys) {
    $agnesKey = Read-SecretText "Agnes API Key (leave blank to configure later)"
    $siliconFlowKey = Read-SecretText "SiliconFlow API Key (leave blank to configure later)"
}

$randomBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($randomBytes)
$appSecret = [Convert]::ToBase64String($randomBytes)
$storageRoot = Join-Path $workspaceRoot "runtime-data\storage"

$lines = @(
    "APP_ENV=native-dev",
    "APP_SECRET_KEY=$appSecret",
    "MYSQL_URL=mysql+asyncmy://${MysqlUser}:$(Escape-UrlPart $mysqlPassword)@127.0.0.1:3306/$MysqlDatabase",
    "REDIS_URL=redis://127.0.0.1:6379/3",
    "ELASTICSEARCH_URL=http://127.0.0.1:9200",
    "ELASTICSEARCH_INDEX_PREFIX=company-agent-knowledge",
    "LOCAL_STORAGE_ROOT=$($storageRoot.Replace('\', '/'))",
    "AGNES_API_KEY=$agnesKey",
    "SILICONFLOW_API_KEY=$siliconFlowKey",
    "ALLOW_EXTERNAL_CHAT=true",
    "ALLOW_EXTERNAL_VISION=true",
    "ALLOW_EXTERNAL_EMBEDDING=true",
    "WEB_ORIGINS=http://127.0.0.1:3000,http://localhost:3000"
)

Set-Content -LiteralPath $envPath -Value $lines -Encoding utf8 -NoNewline
Write-Output ".env.local created at $envPath"
Write-Output "It is ignored by Git; do not paste its contents into chat or commit it."
