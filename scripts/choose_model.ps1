param([string]$Model)
$ErrorActionPreference='Stop'
$jarvisRoot=Split-Path $PSScriptRoot -Parent
$catalog=Get-Content -Raw -LiteralPath (Join-Path $jarvisRoot 'config/models.json') | ConvertFrom-Json
if ($Model) { Write-Output $Model; return }
$ram=0;$vram=0
try { $ram=[math]::Round(((Get-CimInstance Win32_PhysicalMemory | Measure-Object Capacity -Sum).Sum/1GB)) } catch {}
try { $gpu=& nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null; $vram=[math]::Round(([double]($gpu | Select-Object -First 1)/1024),1) } catch {}
$recommended=if($ram -ge 48 -and $vram -ge 24){5}elseif($ram -ge 24 -and $vram -ge 8){4}elseif($ram -ge 16){3}elseif($ram -ge 8){2}else{1}
Write-Host ''
Write-Host 'PERSONAL JARVIS / Choose your local brain' -ForegroundColor Yellow
Write-Host "Detected: $ram GB RAM / $vram GB NVIDIA VRAM"
Write-Host 'Memory suggestions include headroom; other applications and context length affect fit.'
for($i=0;$i -lt $catalog.Count;$i++){
    $m=$catalog[$i];$hint=if($i+1 -eq $recommended){' [recommended]'}else{''}
    Write-Host "$($i+1). $($m.label) - ~$($m.download_gb) GB download$hint"
    Write-Host "   $($m.description)"
}
Write-Host '7. Enter another local Ollama model (must support tools and non-thinking replies)'
do { $choice=Read-Host "Choose 1-7 [Enter = $recommended]";if(!$choice){$choice="$recommended"} } while($choice -notmatch '^[1-7]$')
if($choice -eq '7'){
    $custom=Read-Host 'Ollama model name'
    if(!$custom -or $custom -match '[/\\\r\n ]' -or $custom -match 'cloud'){throw 'Use a local model name from the Ollama library.'}
    Write-Output $custom
}else{Write-Output $catalog[[int]$choice-1].source}
