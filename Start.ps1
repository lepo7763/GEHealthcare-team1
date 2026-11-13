
# Start.ps1
# Launch backend and frontend

$root = $PSScriptRoot

# Backend
$backendPath = Join-Path $root "backend"
$pythonPath = Join-Path $backendPath ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonPath)) {
    Write-Error "Python virtual environment not found: $pythonPath"
    exit 1
}

Start-Process powershell.exe `
    -WorkingDirectory $backendPath `
    -ArgumentList @(
        "-NoExit",
        "-Command",
        "& '$pythonPath' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
    )

# Frontend
$frontendPath = Join-Path $root "frontend"

Start-Process powershell.exe `
    -WorkingDirectory $frontendPath `
    -ArgumentList @(
        "-NoExit",
        "-Command",
        "npm run dev"
    )

Write-Host "Backend and Frontend launched."

