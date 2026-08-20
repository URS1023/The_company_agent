@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-native.ps1" %*
exit /b %ERRORLEVEL%
