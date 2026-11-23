$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $root 'backend\ai_config.json'
$settings = if (Test-Path -LiteralPath $configPath) { Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } else { $null }
$provider = $env:RAMANCLOUD_AI_PROVIDER
if (-not $provider -and $settings) { $provider = $settings.provider }
if ($provider -and $provider -ne 'ollama') { exit 0 }

foreach ($name in @('OLLAMA_MODELS', 'OLLAMA_NO_CLOUD')) {
    if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
        [Environment]::SetEnvironmentVariable($name, [Environment]::GetEnvironmentVariable($name, 'User'), 'Process')
    }
}
$env:OLLAMA_NO_CLOUD = '1'
$base = if ($env:RAMANCLOUD_AI_BASE_URL) { $env:RAMANCLOUD_AI_BASE_URL } elseif ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL } elseif ($settings.provider -eq 'ollama' -and $settings.base_url) { $settings.base_url } else { 'http://127.0.0.1:11434' }
$uri = [Uri]$base
if ($uri.Scheme -ne 'http' -or $uri.Host -notin @('localhost', '127.0.0.1', '[::1]', '::1') -or $uri.UserInfo -or $uri.Query -or $uri.Fragment -or $uri.AbsolutePath -ne '/') {
    Write-Warning 'Only a local Ollama endpoint is supported.'
    exit 0
}
try {
    $null = Invoke-RestMethod -Uri "$($base.TrimEnd('/'))/api/tags" -TimeoutSec 2
    Write-Output 'Ollama is running.'
    exit 0
} catch {}

$command = Get-Command ollama.exe -ErrorAction SilentlyContinue
$executable = if ($command) { $command.Source } else { $null }
if (-not $executable) {
    $userPaths = [Environment]::GetEnvironmentVariable('Path', 'User') -split ';'
    foreach ($directory in $userPaths) {
        if (-not $directory) { continue }
        $candidate = Join-Path ([Environment]::ExpandEnvironmentVariables($directory)) 'ollama.exe'
        if (Test-Path -LiteralPath $candidate) { $executable = $candidate; break }
    }
}
if (-not $executable) {
    Write-Warning 'Ollama was not found. Install Ollama and run: ollama pull qwen3:4b-instruct-2507-q4_K_M. Local rules remain available.'
    exit 0
}
$logs = Join-Path $root 'logs'
$null = New-Item -ItemType Directory -Path $logs -Force
$env:OLLAMA_HOST = $uri.Authority
$null = Start-Process -FilePath $executable -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'ollama.log') -RedirectStandardError (Join-Path $logs 'ollama-error.log') -PassThru
Write-Output 'Ollama started in the background. Download the model once: ollama pull qwen3:4b-instruct-2507-q4_K_M'
