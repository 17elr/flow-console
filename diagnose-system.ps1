$ErrorActionPreference = "Continue"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$report = Join-Path $root "system-diagnostic-$stamp.log"

function Add-Line([string]$Text = "") {
    $Text | Out-File -LiteralPath $report -Encoding utf8 -Append
}
function Safe-Get([string]$Url) {
    try { return Invoke-RestMethod -Uri $Url -TimeoutSec 10 } catch { Add-Line "REQUEST FAILED: $Url :: $($_.Exception.Message)"; return $null }
}

Add-Line "Flow Console diagnostic"
Add-Line "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Add-Line "Root: $root"
Add-Line "Windows: $([Environment]::OSVersion.VersionString)"
Add-Line "PowerShell: $($PSVersionTable.PSVersion)"
Add-Line ""

foreach ($command in @("python", "node", "npm.cmd")) {
    $found = Get-Command $command -ErrorAction SilentlyContinue
    Add-Line "$command path: $(if ($found) { $found.Source } else { 'MISSING' })"
}
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$nextEntry = Join-Path $root "apps\web\node_modules\next\dist\bin\next"
Add-Line "venv python: $(Test-Path -LiteralPath $venvPython)"
Add-Line "frontend next: $(Test-Path -LiteralPath $nextEntry)"
Add-Line "frontend build: $(Test-Path -LiteralPath (Join-Path $root 'apps\web\.next'))"

Add-Line ""
Add-Line "ENV configuration (values redacted)"
$envPath = Join-Path $root ".env"
if (Test-Path -LiteralPath $envPath) {
    Get-Content -LiteralPath $envPath | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
            $key = $Matches[1].Trim(); $value = $Matches[2].Trim()
            Add-Line "$key configured=$([bool]$value) length=$($value.Length)"
        }
    }
} else { Add-Line ".env MISSING" }

Add-Line ""
Add-Line "Ports"
foreach ($port in @(8000, 3000)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    Add-Line "$port listening=$([bool]$listener) pid=$(if ($listener) {$listener.OwningProcess} else {'-'})"
}

Add-Line ""
Add-Line "API"
$health = Safe-Get "http://127.0.0.1:8000/health"
if ($health) { Add-Line "health: $($health | ConvertTo-Json -Compress -Depth 6)" }
$overview = Safe-Get "http://127.0.0.1:8000/api/automation/overview"
if ($overview) {
    Add-Line "stores:"
    foreach ($store in $overview.stores) {
        Add-Line "  id=$($store.id) platform=$($store.platform) mode=$($store.mode) external_shop_id_set=$([bool]$store.external_shop_id) automation_ready=$($store.automation_ready)"
    }
}
$packaging = Safe-Get "http://127.0.0.1:8000/api/packaging-presets"
if ($packaging) {
    foreach ($slot in $packaging) { Add-Line "packaging slot=$($slot.slot) configured=$([bool]$slot.image)" }
}
$products = Safe-Get "http://127.0.0.1:8000/api/products"
if ($products) {
    Add-Line ""
    Add-Line "Products and draft readiness"
    foreach ($product in ($products | Select-Object -First 20)) {
        $flow = Safe-Get "http://127.0.0.1:8000/api/products/$($product.id)/workflow"
        if (-not $flow) { continue }
        $review = $flow.review
        Add-Line "product id=$($product.id) spu=$($product.spu_code) status=$($flow.status) images=$($flow.output_count)/$($flow.expected_output_count) missing_sources=$($flow.missing_count)"
        Add-Line "  packaging_selected=$([bool]$flow.packaging_selection) blockers=$([string]::Join(' | ', @($flow.publish_blockers)))"
        Add-Line "  review_status=$($review.status) approved=$($review.approved) can_approve=$($review.can_approve) images_approved=$($review.approved_images)/$($review.expected_images) rejected=$($review.rejected_images) copies_reviewed=$($review.copies_reviewed)/$($review.expected_copies)"
        $failed = @($flow.outputs | Where-Object { $_.status -notin @('COMPLETED','READY_FOR_REVIEW') })
        foreach ($job in $failed) { Add-Line "  output role=$($job.role) sku_id=$($job.sku_id) status=$($job.status) error=$($job.error)" }
    }
}

Add-Line ""
Add-Line "Runtime error log tails"
foreach ($name in @("api.err.log", "web.err.log", "api.out.log", "web.out.log")) {
    $path = Join-Path $root ".runtime\$name"
    Add-Line "--- $name ---"
    if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Tail 80 | Out-File -LiteralPath $report -Encoding utf8 -Append } else { Add-Line "MISSING" }
}

Write-Host "Diagnostic complete: $report"
Start-Process explorer.exe -ArgumentList "/select,`"$report`""
