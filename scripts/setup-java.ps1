$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw '请先安装并启动 Docker Desktop（Compose v2）。手动Java/Node环境见 docs/RUNBOOK.md。' }
& docker compose version
if (-not (Test-Path -LiteralPath '.env.java')) { Write-Output '请复制 .env.example 为 .env.java，并设置独立强密码，然后运行 启动系统.cmd。'; exit 0 }
& docker compose --env-file .env.java build
if ($LASTEXITCODE -ne 0) { throw '镜像构建失败，请检查输出。现有数据卷未修改。' }
Write-Output 'Java和Vue镜像已构建。运行 启动系统.cmd 启动。'
