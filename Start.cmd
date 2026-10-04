@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  "%~dp0runtime\python.exe" "%~dp0app.py"
) else (
  "%~dp0runtime\python.exe" "%~dp0app.py" %*
)
if errorlevel 1 pause
