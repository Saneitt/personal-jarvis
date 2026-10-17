param([switch]$NoWindow)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
if (!$NoWindow) {
    $native=Join-Path $root '.runtime/desktop/Jarvis.exe'
    if (!(Test-Path -LiteralPath $native)) { & "$PSScriptRoot/build_desktop.ps1" }
    Start-Process -FilePath $native -WorkingDirectory $root -WindowStyle Normal
    return
}
$env:PYTHONUTF8='1'
$python = Join-Path $root '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run Setup Jarvis first.' }
New-Item -ItemType Directory -Force -Path 'data' | Out-Null
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path $root 'models/ollama'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_CONTEXT_LENGTH = '4096'
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
try { $null = Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 2 } catch {
    $ollama = Join-Path $root '.runtime/ollama/ollama.exe'
    if (!(Test-Path -LiteralPath $ollama)) { throw 'Ollama is missing. Run Setup Jarvis.' }
    $process = Start-Process -FilePath $ollama -ArgumentList 'serve' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'data/ollama.stdout.log') -RedirectStandardError (Join-Path $root 'data/ollama.stderr.log')
    $process.Id | Set-Content -LiteralPath 'data/ollama.pid'
}
$running = $false
$health = $null
try {
    $health = Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 2
    if ($health.application -eq 'Personal Jarvis') { $running = $true }
} catch {}
if (!$running) {
    $process = Start-Process -FilePath $python -ArgumentList '-m','uvicorn','jarvis.server:app','--host','127.0.0.1','--port','8765','--no-access-log','--ws-max-size','65536' -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'data/jarvis.stdout.log') -RedirectStandardError (Join-Path $root 'data/jarvis.stderr.log')
    $process.Id | Set-Content -LiteralPath 'data/jarvis.pid'
}
for ($i=0; $i -lt 40; $i++) {
    try { $health=Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 1; if ($health.application -eq 'Personal Jarvis') { break } } catch {}
    Start-Sleep -Milliseconds 500
}
if ($health.application -ne 'Personal Jarvis') { throw 'Jarvis could not start. Check data/jarvis.stderr.log.' }
if (!$NoWindow) {
    $edge = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft/Edge/Application/msedge.exe'
    if (Test-Path -LiteralPath $edge) {
        Start-Process -FilePath $edge -ArgumentList '--app=http://127.0.0.1:8765','--new-window' -WindowStyle Normal
    } else {
        Start-Process 'http://127.0.0.1:8765'
    }
}
Write-Output 'Jarvis is running at http://127.0.0.1:8765'
