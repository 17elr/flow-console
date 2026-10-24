$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& docker compose --env-file .env.java stop
if ($LASTEXITCODE -ne 0) { throw '停止失败，请检查Compose状态。不要执行 down -v。' }
Write-Output '服务已停止，数据库卷和素材卷均保留。'
