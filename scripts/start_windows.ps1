$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
$env:PYTHONPATH = Join-Path $root "src"

$url = "http://127.0.0.1:8765"
$dist = Join-Path $root "dist"
if (!(Test-Path $dist)) {
  New-Item -ItemType Directory -Path $dist | Out-Null
}
$log = Join-Path $dist "start_windows.log"

Write-Host "API PureCheck v1.0.0"
Write-Host "Root: $root"
Write-Host "URL:  $url"
Write-Host "Log:  $log"
Write-Host ""

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
  "Python was not found. Please install Python 3.11+ and add it to PATH." | Set-Content -Encoding UTF8 -Path $log
  Write-Host "Python was not found. Please install Python 3.11+ and add it to PATH." -ForegroundColor Red
  Read-Host "Press Enter to exit"
  exit 1
}

$portOpen = $false
try {
  $client = New-Object System.Net.Sockets.TcpClient
  $async = $client.BeginConnect("127.0.0.1", 8765, $null, $null)
  $portOpen = $async.AsyncWaitHandle.WaitOne(300, $false)
  $client.Close()
} catch {
  $portOpen = $false
}

if ($portOpen) {
  Write-Host "Port 8765 is already open. Opening existing API PureCheck page." -ForegroundColor Yellow
  Start-Process $url
  Read-Host "Press Enter to exit"
  exit 0
}

Write-Host "Starting local API PureCheck server..."
Write-Host "Keep this window open while using the web page."
Write-Host "If the browser does not open, visit $url manually."
Write-Host ""

Start-Process -FilePath "cmd.exe" -ArgumentList "/c timeout /t 2 /nobreak >nul & start """" ""$url""" -WindowStyle Hidden

python -m api_purecheck serve --host 127.0.0.1 --port 8765 2>&1 | Tee-Object -FilePath $log

if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "API PureCheck failed to start. Error log:" -ForegroundColor Red
  Get-Content $log -ErrorAction SilentlyContinue
  Read-Host "Press Enter to exit"
  exit $LASTEXITCODE
}
