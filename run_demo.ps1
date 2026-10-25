# One command for judges and for you: creates the venv on first run, installs the pinned Flet, starts Khapa.
#   .\run_demo.ps1            desktop window
#   .\run_demo.ps1 -Web       browser at http://localhost:8550
#   .\run_demo.ps1 -Phone     desktop window sized like a phone
param([switch]$Web, [switch]$Phone)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) { python -m venv .venv }
. .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt
if ($Phone) { $env:KHAPA_PREVIEW_PHONE = "1" }
if ($Web) { flet run --web --port 8550 src\main.py } else { flet run src\main.py }
