param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeRoot = Join-Path $repoRoot ".runtime"
$statePath = Join-Path $runtimeRoot "dev-processes.json"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$envFile = Join-Path $repoRoot ".env"
$apiRoot = Join-Path $repoRoot "apps\api"
$webRoot = Join-Path $repoRoot "apps\web"
$nextBin = Join-Path $webRoot "node_modules\next\dist\bin\next"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python virtual environment is missing: $pythonPath"
}
if (-not (Test-Path -LiteralPath $nextBin)) {
    throw "Frontend dependencies are missing. Run npm install in apps/web first."
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

Push-Location $apiRoot
try {
    New-Item -ItemType Directory -Path (Join-Path $apiRoot "data") -Force | Out-Null
    & $pythonPath -c "from app.db import Base, engine; Base.metadata.create_all(bind=engine)"
    if ($LASTEXITCODE -ne 0) { throw "Database initialization failed." }
} finally {
    Pop-Location
}

function Test-Endpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-Endpoint([string]$Name, [string]$Url) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Test-Endpoint $Url) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name failed to become ready. Check .runtime logs."
}

function Get-ListenerPid([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    return $listener.OwningProcess
}

function Save-ProcessRecords {
    if ($processRecords.Count -gt 0) {
        $processRecords | Sort-Object id -Unique | ConvertTo-Json |
            Set-Content -LiteralPath $statePath -Encoding UTF8
    }
}

$processRecords = @()
if (Test-Path -LiteralPath $statePath) {
    $savedRecords = Get-Content -Raw -Encoding UTF8 -LiteralPath $statePath | ConvertFrom-Json
    foreach ($record in $savedRecords) {
        $recordedProcess = Get-Process -Id $record.id -ErrorAction SilentlyContinue
        if ($recordedProcess -and $recordedProcess.StartTime.ToString("O") -eq $record.started_at) {
            $processRecords += $record
        }
    }
}
$startedWeb = $false
$apiUrl = "http://127.0.0.1:$ApiPort/health"
$webUrl = "http://127.0.0.1:$WebPort"

if (-not (Test-Endpoint $apiUrl)) {
    if (Get-ListenerPid $ApiPort) {
        throw "Port $ApiPort is occupied by a service that is not this API."
    }
    $apiProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--env-file", ('"{0}"' -f $envFile), "--host", "127.0.0.1", "--port", $ApiPort `
        -WorkingDirectory $apiRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeRoot "api.out.log") `
        -RedirectStandardError (Join-Path $runtimeRoot "api.err.log")
    $processRecords += [pscustomobject]@{
        name = "api"
        id = $apiProcess.Id
        started_at = $apiProcess.StartTime.ToString("O")
    }
    Save-ProcessRecords
}
Wait-Endpoint "API" $apiUrl

$apiListenerPid = Get-ListenerPid $ApiPort
$ownsApi = @($processRecords | Where-Object { $_.name -like "api*" }).Count -gt 0
if ($ownsApi -and $apiListenerPid -and -not ($processRecords.id -contains $apiListenerPid)) {
    $apiListenerProcess = Get-Process -Id $apiListenerPid -ErrorAction Stop
    $processRecords += [pscustomobject]@{
        name = "api-listener"
        id = $apiListenerProcess.Id
        started_at = $apiListenerProcess.StartTime.ToString("O")
    }
    Save-ProcessRecords
}

if (-not (Test-Endpoint $webUrl)) {
    if (Get-ListenerPid $WebPort) {
        throw "Port $WebPort is occupied by a service that is not this frontend."
    }
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    $quotedNextBin = '"{0}"' -f $nextBin
    $webProcess = Start-Process -FilePath $nodePath `
        -ArgumentList $quotedNextBin, "dev", "--hostname", "127.0.0.1", "--port", $WebPort `
        -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeRoot "web.out.log") `
        -RedirectStandardError (Join-Path $runtimeRoot "web.err.log")
    $processRecords += [pscustomobject]@{
        name = "web-launcher"
        id = $webProcess.Id
        started_at = $webProcess.StartTime.ToString("O")
    }
    $startedWeb = $true
    Save-ProcessRecords
}
Wait-Endpoint "Frontend" $webUrl

$webListenerPid = Get-ListenerPid $WebPort
if ($startedWeb -and $webListenerPid -and -not ($processRecords.id -contains $webListenerPid)) {
    $listenerProcess = Get-Process -Id $webListenerPid -ErrorAction Stop
    $processRecords += [pscustomobject]@{
        name = "web-listener"
        id = $listenerProcess.Id
        started_at = $listenerProcess.StartTime.ToString("O")
    }
    Save-ProcessRecords
}

Save-ProcessRecords
Write-Host "API ready:      $apiUrl"
Write-Host "Frontend ready: $webUrl"
