@echo off
setlocal

:: %~dp0 = C:\!Oleksii_Rovnianskyi\devops\gitupdate\
set "LAUNCHER_DIR=%~dp0"
for %%A in ("%LAUNCHER_DIR%\..") do set "DEVOPS_DIR=%%~fA"
for %%A in ("%DEVOPS_DIR%\..") do set "CAPSULE_ROOT=%%~fA"

set "PYTHON_EXE=%CAPSULE_ROOT%\apps\python\current\python.exe"
set "SCRIPT_PY=%LAUNCHER_DIR%git_manager.py"

echo Capsule: %CAPSULE_ROOT%
echo Syncing...

"%PYTHON_EXE%" "%SCRIPT_PY%" --sync %*

if %ERRORLEVEL% NEQ 0 pause
localexit
