$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$candidates = @()
if ($env:BACKEND_PYTHON) { $candidates += $env:BACKEND_PYTHON }
$candidates += Join-Path $root '.venv\Scripts\python.exe'
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($version in @('3.8', '3.9', '3.10')) {
        try {
            $found = & py "-$version" -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $found) { $candidates += $found }
        } catch { continue }
    }
}
$candidates += @(Get-Command python -All -CommandType Application -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -notmatch '\\WindowsApps\\' } | ForEach-Object { $_.Source })
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    try {
        $found = & $candidate -I -c 'import sys; sys.exit(2) if not ((3,8) <= sys.version_info[:2] <= (3,10)) else print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $found) {
            Write-Output $found
            exit 0
        }
    } catch { continue }
}
[Console]::Error.WriteLine('No compatible backend Python found. Install Python 3.8, 3.9 or 3.10. Python 3.12 is reserved for the isolated model environment.')
exit 1
