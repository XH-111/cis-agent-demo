$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$backendDir = Join-Path $repoRoot "backend"

if (-not (Test-Path $pythonExe)) {
    throw "Root Python 3.12 virtualenv not found: $pythonExe"
}

Write-Host "Using backend Python:" $pythonExe
& $pythonExe --version

Push-Location $backendDir
try {
    & $pythonExe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
}
