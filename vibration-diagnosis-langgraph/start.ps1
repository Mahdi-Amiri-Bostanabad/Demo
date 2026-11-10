# Starts the Vibration Diagnosis Agents app on http://localhost:8090
# First run: creates the Python venv (needs uv) and builds the UI (needs Node).
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

if (-not (Test-Path "$root\backend\.venv")) {
    Write-Host "Creating Python 3.12 environment..."
    Push-Location "$root\backend"
    uv venv --python 3.12 .venv
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
    Pop-Location
}
if (-not (Test-Path "$root\frontend\dist\index.html")) {
    Write-Host "Building UI..."
    Push-Location "$root\frontend"
    npm install
    npm run build
    Pop-Location
}

# Free the port if an older instance is still running
Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Push-Location "$root\backend"
Write-Host "Open http://localhost:8090"
& .venv\Scripts\python.exe -m uvicorn app.server:app --host 127.0.0.1 --port 8090
Pop-Location
