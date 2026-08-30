$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$api = Join-Path $root "apps\api"
$out = Join-Path (Split-Path $root -Parent) "Flow-Console-Delivery.zip"
if (Test-Path $out) { Remove-Item -LiteralPath $out -Force }
$excluded = @('.git','.venv','node_modules','.next','.runtime','data','output','outputs','tmp','temp')
$stage = Join-Path ([IO.Path]::GetTempPath()) ("flow-console-stage-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$files = Get-ChildItem -LiteralPath $root -Recurse -File -Force | Where-Object {
    $relative = $_.FullName.Substring($root.Length + 1)
    $parts = $relative -split '[\\/]'
    ($parts | Where-Object { $excluded -contains $_ }).Count -eq 0 -and
    $_.Name -notin @('.env','app.db','flow.db','flow_console.db') -and
    $_.Extension -ne '.onnx'
} | ForEach-Object {
    $relative = $_.FullName.Substring($root.Length + 1)
    $target = Join-Path $stage $relative
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $target -Force
}
$envSource = Join-Path $root ".env"
if (-not (Test-Path -LiteralPath $envSource)) { $envSource = Join-Path $api ".env.example" }
Copy-Item -LiteralPath $envSource -Destination (Join-Path $stage ".env")
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $out -CompressionLevel Optimal
Remove-Item -LiteralPath $stage -Recurse -Force
Write-Host "已生成: $out"
