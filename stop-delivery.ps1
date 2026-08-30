$root = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
& (Join-Path $root "scripts\stop-dev.ps1")
