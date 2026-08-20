@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-native-secrets.ps1" %*
exit /b %ERRORLEVEL%
