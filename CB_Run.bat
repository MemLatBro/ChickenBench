@echo off
setlocal DisableDelayedExpansion
rem ChickenBench 1.0.8: capture runner requests elevation for PresentMon.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0runner\cb_runner.ps1"
set "CB_EXIT=%ERRORLEVEL%"
if not "%CB_EXIT%"=="0" pause
exit /b %CB_EXIT%
