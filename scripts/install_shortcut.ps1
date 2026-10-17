$ErrorActionPreference='Stop'
$jarvisRoot=Split-Path $PSScriptRoot -Parent
$programs=[Environment]::GetFolderPath('Programs')
$link=Join-Path $programs 'Jarvis.lnk'
$shell=New-Object -ComObject WScript.Shell
$shortcut=$shell.CreateShortcut($link)
$shortcut.TargetPath=Join-Path $jarvisRoot '.runtime/desktop/Jarvis.exe'
$shortcut.WorkingDirectory=$jarvisRoot
$shortcut.Description='Personal Jarvis — local voice assistant'
$shortcut.IconLocation=(Join-Path $jarvisRoot 'web/assets/jarvis.ico')+',0'
$shortcut.Save()
Write-Output "Start menu shortcut installed: $link"
