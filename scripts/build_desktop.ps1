$ErrorActionPreference='Stop'
$jarvisRoot=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $jarvisRoot
$version='1.0.4258.31'
$sdk=Join-Path $jarvisRoot '.runtime/webview2'
$out=Join-Path $jarvisRoot '.runtime/desktop'
New-Item -ItemType Directory -Force -Path $sdk,$out | Out-Null
$package=Join-Path $sdk 'sdk.nupkg'
if (!(Test-Path -LiteralPath $package)) {
    & curl.exe -fL --connect-timeout 30 --retry 3 --output "$package.part" "https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/$version/microsoft.web.webview2.$version.nupkg"
    if ($LASTEXITCODE -ne 0) { throw 'WebView2 SDK download failed.' }
    Move-Item -LiteralPath "$package.part" -Destination $package
}
if ((Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLower() -ne '56f7f4b8bf9aee4b8efefbbdd4f67d5f74ebd1b100ed0806da71bf76af481aa9') { throw 'WebView2 SDK checksum mismatch.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$extract=Join-Path $sdk 'package'
if (!(Test-Path -LiteralPath $extract)) { [IO.Compression.ZipFile]::ExtractToDirectory($package,$extract) }
Copy-Item -LiteralPath (Join-Path $extract 'lib/net462/Microsoft.Web.WebView2.Core.dll'),(Join-Path $extract 'lib/net462/Microsoft.Web.WebView2.WinForms.dll'),(Join-Path $extract 'runtimes/win-x64/native/WebView2Loader.dll') -Destination $out -Force
$compiler=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (!(Test-Path -LiteralPath $compiler)) { throw '.NET Framework 4.8 is required (included in supported Windows 10/11).' }
& $compiler /nologo /target:winexe /platform:x64 /optimize+ ("/out:"+(Join-Path $out "Jarvis.exe")) ("/win32icon:"+(Join-Path $jarvisRoot "web\assets\jarvis.ico")) /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll ("/reference:"+(Join-Path $out "Microsoft.Web.WebView2.Core.dll")) ("/reference:"+(Join-Path $out "Microsoft.Web.WebView2.WinForms.dll")) (Join-Path $jarvisRoot "desktop\Jarvis.cs")
if ($LASTEXITCODE -ne 0) { throw 'Native desktop build failed.' }
Copy-Item -LiteralPath (Join-Path $extract 'LICENSE.txt') -Destination (Join-Path $out 'WebView2-LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $extract 'NOTICE.txt') -Destination (Join-Path $out 'WebView2-NOTICE.txt') -Force
Write-Output 'Native Jarvis window built.' 
