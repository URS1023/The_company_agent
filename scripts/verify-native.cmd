@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify-native.ps1" %*
exit /b %ERRORLEVEL%
