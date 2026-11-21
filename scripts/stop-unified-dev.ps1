Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

function Stop-PortProcess([int]$Port) {
  $conns = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq $Port }
  foreach ($conn in $conns) {
    try {
      Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
      Write-Host "[unified-dev] Stopped PID $($conn.OwningProcess) on port $Port"
    } catch {
      Write-Host "[unified-dev] Could not stop PID $($conn.OwningProcess) on port ${Port}: $($_.Exception.Message)"
    }
  }
}

Stop-PortProcess -Port 5173
Stop-PortProcess -Port 8000
Stop-PortProcess -Port 5000

Write-Host "[unified-dev] Local frontend/backend stop completed."
Write-Host "[unified-dev] Docker DB remains running on localhost:55432."
