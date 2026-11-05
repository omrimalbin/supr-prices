@echo off
rem Prices app - connect this home computer (asks for administrator permission)
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $s=Invoke-RestMethod 'https://raw.githubusercontent.com/omrimalbin/supr-prices/main/home-setup/install.ps1' -UseBasicParsing; Invoke-Expression $s"
echo.
pause
