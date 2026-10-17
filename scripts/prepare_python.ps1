$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $root
New-Item -ItemType Directory -Force -Path '.runtime/uv','data' | Out-Null
$uv=Join-Path $root '.runtime/uv/uv.exe'
if (!(Test-Path -LiteralPath $uv)) {
    $release=Invoke-RestMethod 'https://api.github.com/repos/astral-sh/uv/releases/latest'
    $asset=$release.assets | Where-Object name -eq 'uv-x86_64-pc-windows-msvc.zip'
    $archive=Join-Path $root '.runtime/uv.zip'
    & curl.exe -fsSL --retry 3 --output $archive $asset.browser_download_url
    if ($LASTEXITCODE -ne 0) { throw 'uv download failed' }
    if (!$asset.digest -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $asset.digest.Replace('sha256:','')) { throw 'uv checksum mismatch' }
    Expand-Archive -LiteralPath $archive -DestinationPath '.runtime/uv' -Force
    $asset | Select-Object name,browser_download_url,digest | ConvertTo-Json | Set-Content -LiteralPath 'data/uv-release.json'
}
$env:UV_PYTHON_INSTALL_DIR=Join-Path $root '.runtime/python'
$env:UV_PYTHON_BIN_DIR=Join-Path $root '.runtime/python-bin'
$env:UV_CACHE_DIR=Join-Path $root '.runtime/uv-cache'
& $uv python install 3.12 --no-bin --no-registry
if ($LASTEXITCODE -ne 0) { throw 'Python download failed' }
$python=& $uv python find 3.12 --managed-python --system --resolve-links
$python | Set-Content -LiteralPath 'data/standalone-python.txt'
Write-Output "Standalone Python ready at $python"
