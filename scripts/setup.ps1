param([string]$Model)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
$env:PYTHONUTF8='1'
$Model=& "$PSScriptRoot/choose_model.ps1" -Model $Model
Write-Host "Setting up $Model. Downloads resume when possible."
try {

& "$PSScriptRoot/stop.ps1"
& "$PSScriptRoot/prepare_python.ps1"
$python=(Get-Content -Raw -LiteralPath 'data/standalone-python.txt').Trim()
# --upgrade preserves installed packages while fixing interpreter paths after relocation.
if (Test-Path -LiteralPath '.venv/pyvenv.cfg') {
    & $python -m venv --upgrade .venv
} else {
    & $python -m venv .venv
}
if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
$python=Join-Path $root '.venv/Scripts/python.exe'
$env:UV_CACHE_DIR=Join-Path $root '.runtime/uv-cache'
$uv=Join-Path $root '.runtime/uv/uv.exe'
& $uv pip install --python $python -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
& "$PSScriptRoot/install_runtime.ps1" -Model $Model
if ($Model -like 'qwen3.5:*') {
    $profile='jarvis-local:'+($Model -split ':')[1]
    & $python 'scripts/prepare_brain.py' $Model $profile
    if ($LASTEXITCODE -ne 0) { throw 'Local brain profile creation failed.' }
    $Model=$profile
}
& $python 'scripts/download_speech.py'
if ($LASTEXITCODE -ne 0) { throw 'Speech model download failed.' }
& $python 'scripts/download_voice.py'
if ($LASTEXITCODE -ne 0) { throw 'Voice model download failed.' }
& $python -c "from jarvis.config import Settings; import sys; s=Settings.load(); s.model=sys.argv[1]; Settings.model_validate(s.model_dump()).save()" $Model
if ($LASTEXITCODE -ne 0) { throw 'Configuration could not be saved.' }
& "$PSScriptRoot/build_desktop.ps1"
& "$PSScriptRoot/install_webview_runtime.ps1"
& "$PSScriptRoot/install_shortcut.ps1"
Write-Host 'Setup complete. Search Jarvis in Start, or open Launch Jarvis.cmd.'
} finally {
    & "$PSScriptRoot/stop.ps1"
}
