@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-native.ps1" %*
exit /b %ERRORLEVEL%
