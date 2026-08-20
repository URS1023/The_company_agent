@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-native-smoke.ps1" %*
exit /b %ERRORLEVEL%
