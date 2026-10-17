param([switch]$ServicesOnly)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\') + '\'
if (!$ServicesOnly) {
    $native=Join-Path $root '.runtime\desktop\Jarvis.exe'
    foreach($process in @(Get-CimInstance Win32_Process -Filter "Name='Jarvis.exe'" -ErrorAction SilentlyContinue)){
        if($process.ExecutablePath -and $process.ExecutablePath.Equals($native,[StringComparison]::OrdinalIgnoreCase)){
            $nativeProcess=Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
            if($nativeProcess){$null=$nativeProcess.CloseMainWindow();$null=$nativeProcess.WaitForExit(8000)}
        }
    }
}
foreach ($service in @('jarvis','ollama')) {
    $pidFile = Join-Path $root "data/$service.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $serviceId = [int](Get-Content -LiteralPath $pidFile)
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$serviceId" -ErrorAction SilentlyContinue
        if ($process -and $process.ExecutablePath -and $process.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
            # Include the venv child interpreter and the model runner.
            & taskkill.exe /PID $serviceId /T /F | Out-Null
        }
        Remove-Item -LiteralPath $pidFile
    }
}
Write-Output 'Jarvis services stopped.'
