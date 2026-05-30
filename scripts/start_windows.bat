@echo off
setlocal

cd /d "%~dp0.."
if errorlevel 1 (
  echo Failed to enter API PureCheck directory.
  echo Please extract the zip first, then run scripts\start_windows.bat.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows.ps1"

if errorlevel 1 (
  echo.
  echo API PureCheck failed to start. See dist\start_windows.log if it exists.
  pause
  exit /b 1
)
