function Get-NativePython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceRoot
    )

    $candidates = @()
    $configured = [Environment]::GetEnvironmentVariable("COMPANY_AGENT_PYTHON", "Process")
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        $candidates += $configured
    }
    $candidates += (Join-Path $WorkspaceRoot ".conda/python.exe")
    $candidates += "E:/Environment_f/conda_envs/company-agent/python.exe"
    $candidates += (Join-Path $WorkspaceRoot ".venv/Scripts/python.exe")

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return [IO.Path]::GetFullPath($candidate)
        }
    }

    throw "No native Python runtime found. Create the Conda environment at E:/Environment_f/conda_envs/company-agent or set COMPANY_AGENT_PYTHON."
}
