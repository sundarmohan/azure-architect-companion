Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section([string]$Title) {
  Write-Host ""
  Write-Host "=== $Title ==="
}

Write-Section "Docker Containers"
docker ps --format "table {{.Names}}`t{{.Image}}`t{{.Status}}`t{{.Ports}}"

Write-Section "Compose Projects"
docker compose ls

Write-Section "Key Listening Ports"
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 5000,5173,8000,5432,55432 } |
  Sort-Object LocalPort, OwningProcess |
  Select-Object LocalAddress, LocalPort, OwningProcess |
  Format-Table -AutoSize

Write-Section "Owning Processes"
$pids = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $_.LocalPort -in 5000,5173,8000,5432,55432 } |
  Select-Object -ExpandProperty OwningProcess -Unique

if ($pids) {
  Get-Process -Id $pids -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName, StartTime |
    Sort-Object Id |
    Format-Table -AutoSize
} else {
  Write-Host "No matching listeners found."
}
