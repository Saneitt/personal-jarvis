$ErrorActionPreference='Stop'
$jarvisRoot=Split-Path $PSScriptRoot -Parent
$programFilesX86=[Environment]::GetFolderPath('ProgramFilesX86')
$found=@("$programFilesX86\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe","$env:ProgramFiles\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe","$env:LOCALAPPDATA\Microsoft\EdgeWebView\Application\*\msedgewebview2.exe") | Where-Object {Test-Path $_}
if($found){Write-Output 'WebView2 runtime is installed.';return}
$file=Join-Path $jarvisRoot '.runtime/WebView2Bootstrapper.exe'
& curl.exe -fL --connect-timeout 30 --retry 3 --output $file 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
if($LASTEXITCODE -ne 0){throw 'Could not download the Microsoft WebView2 installer.'}
$signature=Get-AuthenticodeSignature -LiteralPath $file
if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation'){throw 'The Microsoft installer signature could not be verified.'}
$process=Start-Process -FilePath $file -ArgumentList '/silent','/install' -WindowStyle Hidden -Wait -PassThru
if($process.ExitCode -ne 0){throw "WebView2 runtime installation failed ($($process.ExitCode))."}
