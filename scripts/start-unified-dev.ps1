Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
  Write-Host "[unified-dev] $Message"
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeApp = Join-Path $root "docker-compose.yml"
$composeDb = Join-Path $root "docker-compose.dev-db.yml"
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

$pythonFromRoot = Join-Path (Split-Path $root -Parent) ".venv/Scripts/python.exe"
$pythonFromLocal = Join-Path $root ".venv/Scripts/python.exe"

if (Test-Path $pythonFromRoot) {
  $pythonExe = $pythonFromRoot
} elseif (Test-Path $pythonFromLocal) {
  $pythonExe = $pythonFromLocal
} else {
  throw "Could not find python executable in .venv. Expected either '$pythonFromRoot' or '$pythonFromLocal'."
}

Write-Step "Stopping legacy containerized app services (project monitorai-v22) if present"
# docker-compose.yml is now the production/EC2 stack, so stop the old dev project by name only.
try { docker compose -p monitorai-v22 stop 2>$null | Out-Null } catch { Write-Step "No legacy monitorai-v22 containers to stop" }

Write-Step "Starting Docker PostgreSQL only (monitorai-dev)"
docker compose -p monitorai-dev -f $composeDb up -d db | Out-Null

Write-Step "Stopping old local legacy backend on port 5000 if present"
$oldBackendConns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 5000 }
foreach ($conn in $oldBackendConns) {
  try {
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
    Write-Step "Stopped process on port 5000 (PID $($conn.OwningProcess))"
  } catch {
    Write-Step "Could not stop PID $($conn.OwningProcess) on port 5000: $($_.Exception.Message)"
  }
}

Write-Step "Stopping old local frontend on port 5173 if present"
$oldFrontendConns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 5173 }
foreach ($conn in $oldFrontendConns) {
  try {
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
    Write-Step "Stopped process on port 5173 (PID $($conn.OwningProcess))"
  } catch {
    Write-Step "Could not stop PID $($conn.OwningProcess) on port 5173: $($_.Exception.Message)"
  }
}

Write-Step "Starting local backend (uvicorn) on 127.0.0.1:8000"
$backendCommand = @(
  "$env:DATABASE_URL='postgresql+asyncpg://monitorai:monitorai_dev@localhost:55432/monitorai'",
  "& '$pythonExe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
) -join '; '
Start-Process -FilePath "powershell" -WorkingDirectory $backendDir -ArgumentList "-NoExit", "-Command", $backendCommand | Out-Null

Write-Step "Starting local frontend (vite) on 127.0.0.1:5173"
$frontendCommand = @(
  "$env:VITE_API_URL='http://127.0.0.1:8000/api'",
  "npm run dev -- --host 127.0.0.1 --port 5173"
) -join '; '
Start-Process -FilePath "powershell" -WorkingDirectory $frontendDir -ArgumentList "-NoExit", "-Command", $frontendCommand | Out-Null

Write-Step "Done. Unified dev mode is launching: local API/UI + Docker DB"
Write-Step "UI: http://127.0.0.1:5173"
Write-Step "API: http://127.0.0.1:8000/api"
Write-Step "DB : localhost:55432 (Docker container monitorai-dev-db-1)"