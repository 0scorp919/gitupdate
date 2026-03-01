@echo off
setlocal

:: Get script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: Resolve CAPSULE_ROOT
for %%I in ("%SCRIPT_DIR%\..\..") do set "CAPSULE_ROOT=%%~fI"

:: Set python path
set "PYTHON_EXE=%CAPSULE_ROOT%\apps\python\current\python\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at: %PYTHON_EXE%
    echo Please install Python locally first.
    pause
    exit /b 1
)

:: Run script
echo [INFO] Starting SSH Migration Tool...
"%PYTHON_EXE%" "%SCRIPT_DIR%\migrate_ssh.py" %*

pause
endlocal
