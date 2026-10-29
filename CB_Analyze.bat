@echo off
setlocal DisableDelayedExpansion
rem All label input is handled in Python, never expanded by cmd.exe.
pushd "%~dp0"
if errorlevel 1 exit /b 1
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 "%~dp0scripts\analyze_launcher.py"
set "CB_EXIT=%ERRORLEVEL%"
goto finish

:use_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python "%~dp0scripts\analyze_launcher.py"
set "CB_EXIT=%ERRORLEVEL%"
goto finish

:missing_python
echo Python 3 is required. Install it and enable its Python launcher or PATH option.
set "CB_EXIT=1"

:finish
popd
pause
exit /b %CB_EXIT%
