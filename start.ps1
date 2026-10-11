# start.ps1 — one command on demo day (SPEC §39): build the web app, prepare the database, serve app + API on :8000.
#   .\start.ps1          # this laptop only (127.0.0.1)
#   .\start.ps1 -Lan     # phones on the team hotspot: http://<laptop-hotspot-ip>:8000
param([switch]$Lan, [switch]$NoBuild)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $NoBuild) {
  Push-Location web
  if (-not (Test-Path node_modules)) { npm install }
  npm run build
  Pop-Location
}

Push-Location backend
if (-not (Test-Path .venv)) {
  py -3.12 -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
.\.venv\Scripts\python.exe -m railflow.manage init-db
.\.venv\Scripts\python.exe -m railflow.manage seed-demo      # passwords from ..\.env (see .env.example)
$env:RAILFLOW_SERVE_WEB = "1"
$bind = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
Write-Host "RailFlow on http://$($bind):8000  (phones: http://<laptop-hotspot-ip>:8000)"
.\.venv\Scripts\python.exe -m uvicorn railflow.main:app --host $bind --port 8000
Pop-Location
