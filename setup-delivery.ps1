param([switch]$SkipModel)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$log = Join-Path $root "install.log"
Start-Transcript -LiteralPath $log -Append | Out-Null
try {
$api = Join-Path $root "apps\api"
$web = Join-Path $root "apps\web"
$python = Get-Command python -ErrorAction Stop
$node = Get-Command node -ErrorAction Stop
$pyVersion = (& $python.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ([version]$pyVersion -lt [version]'3.10') { throw "Python 3.10 or newer is required. Found $pyVersion" }
$nodeVersion = (& $node.Source --version).Trim().TrimStart('v')
if ([version]$nodeVersion -lt [version]'20.0') { throw "Node.js 20 or newer is required. Found $nodeVersion" }
$venv = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { & $python.Source -m venv (Join-Path $root ".venv") }
Write-Host "[1/4] Creating Python environment..."
if (-not (Test-Path $venv)) { & $python.Source -m venv (Join-Path $root ".venv") }
Write-Host "[2/4] Installing Python dependencies. This can take a while..."
& $venv -m pip install -r (Join-Path $api "requirements.txt") --disable-pip-version-check --index-url "https://pypi.tuna.tsinghua.edu.cn/simple" --trusted-host pypi.tuna.tsinghua.edu.cn
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed. See install.log" }
if (-not (Test-Path (Join-Path $root ".env"))) { Copy-Item (Join-Path $api ".env.example") (Join-Path $root ".env") }
Write-Host "[3/4] Installing and building frontend..."
Push-Location $web
try {
    $nextEntry = Join-Path $web "node_modules\next\dist\bin\next"
    if (-not (Test-Path $nextEntry)) {
        npm.cmd install --registry "https://registry.npmmirror.com" --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed. See install.log" }
    } else {
        Write-Host "Frontend dependencies already exist; skipping reinstall."
    }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed. See install.log" }
} finally { Pop-Location }
Write-Host "[4/4] Initializing database..."
New-Item -ItemType Directory -Path (Join-Path $api "data") -Force | Out-Null
Push-Location $api
try {
    # Create the SQLite schema directly for portable first-run installs.
    & $venv -c "from app.db import Base, engine; Base.metadata.create_all(bind=engine)"
    if ($LASTEXITCODE -ne 0) { throw "Database initialization failed. See install.log" }
} finally { Pop-Location }
Write-Host "Installation complete. Double-click start system.cmd and open http://localhost:3000."
Write-Host "Third-party services require keys in .env. Local SQLite and storage are enabled by default."
} catch { Write-Host "`nInstallation failed: $($_.Exception.Message)" -ForegroundColor Red; Write-Host "Full log: $log"; Read-Host "Press Enter to close" } finally { Stop-Transcript | Out-Null }
