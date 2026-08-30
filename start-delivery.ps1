$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$venv = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venv) -or -not (Test-Path (Join-Path $root "apps\web\.next"))) { throw "尚未安装，请先运行 安装环境.cmd" }
& (Join-Path $root "scripts\start-dev.ps1")
Start-Process "http://localhost:3000"
