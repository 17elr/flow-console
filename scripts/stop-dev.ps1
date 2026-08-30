$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$statePath = Join-Path $repoRoot ".runtime\dev-processes.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Host "No recorded development processes."
    exit 0
}

$records = Get-Content -Raw -Encoding UTF8 -LiteralPath $statePath | ConvertFrom-Json
foreach ($record in $records) {
    $process = Get-Process -Id $record.id -ErrorAction SilentlyContinue
    if (-not $process) { continue }
    try {
        if ($process.StartTime.ToString("O") -ne $record.started_at) {
            Write-Warning "Skipped reused PID $($record.id)."
            continue
        }
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        Write-Host "Stopped $($record.name) ($($process.Id))."
    } catch {
        # The process may exit between lookup and inspection.
        continue
    }
}

Remove-Item -LiteralPath $statePath -Force
