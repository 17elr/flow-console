param([switch]$Build)
$ErrorActionPreference = 'Stop'
$flowRoot = Split-Path $PSScriptRoot -Parent
Set-Location $flowRoot
if (-not (Test-Path -LiteralPath '.env.java')) { throw '请先将 .env.example 复制为 .env.java，并设置独立强密码。旧 .env 无需修改。' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Java默认入口需要 Docker Compose。手动启动方式见 docs/RUNBOOK.md。' }
$flowArgs = @('compose','--env-file','.env.java','up','-d')
if ($Build) { $flowArgs += '--build' }
& docker @flowArgs
if ($LASTEXITCODE -ne 0) { throw 'Compose启动失败，请检查输出；不要删除数据库卷。' }
Write-Output '工作台 http://127.0.0.1:3000；初始账号 admin，密码来自 .env.java。'
