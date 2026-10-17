param([string]$Model='qwen3.5:4b')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
New-Item -ItemType Directory -Force -Path '.runtime','data','models' | Out-Null
$zip = Join-Path $root '.runtime/ollama.zip'
if (!(Test-Path -LiteralPath '.runtime/ollama/ollama.exe')) {
    $url = 'https://github.com/ollama/ollama/releases/download/v0.40.5/ollama-windows-amd64.zip'
    if (!(Test-Path -LiteralPath $zip)) {
        $partial = "$zip.part"
        & curl.exe -fL --connect-timeout 30 --retry 4 --retry-all-errors -C - --output $partial $url
        if ($LASTEXITCODE -ne 0) { throw 'Ollama download failed. Rerun setup to resume.' }
        Move-Item -LiteralPath $partial -Destination $zip
    }
    $expected = '5134ce7e3bc8e94d0494721c799ec293b429450d0c52461b0ee3647dd3bb4bb7'
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower() -ne $expected) {
        throw 'Ollama checksum mismatch. Remove .runtime/ollama.zip and retry.'
    }
    Expand-Archive -LiteralPath $zip -DestinationPath '.runtime/ollama' -Force
}
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path $root 'models/ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
try { $null = Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 2 } catch {
    $process = Start-Process -FilePath (Join-Path $root '.runtime/ollama/ollama.exe') -ArgumentList 'serve' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'data/ollama.stdout.log') -RedirectStandardError (Join-Path $root 'data/ollama.stderr.log')
    $process.Id | Set-Content -LiteralPath 'data/ollama.pid'
    Start-Sleep -Seconds 3
}
& '.venv/Scripts/python.exe' 'scripts/pull_model.py' $Model
if ($LASTEXITCODE -ne 0) { throw 'Model download failed. Rerun setup to resume.' }
