@echo off
:: ============================================================
:: Git Portable Manager — GitHub-ready Launcher
:: UA: Портативний лаунчер для публікації проекту на GitHub.
::     Auto-detect CAPSULE_ROOT від %~dp0 (два рівні вгору).
::     Без хардкодованих шляхів — працює з будь-якого розташування.
:: ============================================================

setlocal EnableDelayedExpansion

:: --- 1. AUTO-DETECT CAPSULE ROOT ---
:: UA: %~dp0 = папка цього .bat файлу (gitupdate\)
::     Два рівні вгору: gitupdate\ → devops\ → CAPSULE_ROOT\
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%A in ("%SCRIPT_DIR%\..") do set "DEVOPS_DIR=%%~fA"
for %%A in ("%DEVOPS_DIR%\..") do set "CAPSULE_ROOT=%%~fA"

echo [INFO] Capsule: %CAPSULE_ROOT%

:: --- 2. PYTHON EXE ---
set "PYTHON_EXE="
for /d %%D in ("%CAPSULE_ROOT%\apps\python\current\python-*") do (
    if exist "%%D\python.exe" set "PYTHON_EXE=%%D\python.exe"
)
if not defined PYTHON_EXE (
    where python >nul 2>&1 && set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    echo [ERROR] Python не знайдено. Встанови Python або запусти Win+R ^> python
    pause
    exit /b 1
)

:: --- 3. SCRIPT PATH ---
set "MANAGER=%SCRIPT_DIR%\git_manager.py"
if not exist "%MANAGER%" (
    echo [ERROR] git_manager.py не знайдено: %MANAGER%
    pause
    exit /b 1
)

:: --- 4. UAC ELEVATION ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Запит прав адміністратора...
    powershell -NoProfile -Command ^
        "Start-Process cmd -Verb RunAs -ArgumentList '/c cd /d ""%CAPSULE_ROOT%"" && ""%PYTHON_EXE%"" ""%MANAGER%"" %*'"
    exit /b 0
)

:: --- 5. RUN MANAGER ---
echo [INFO] GIT PORTABLE MANAGER (Admin Mode)
cd /d "%CAPSULE_ROOT%"
"%PYTHON_EXE%" "%MANAGER%" %*
if %errorlevel% neq 0 (
    echo [ERROR] git_manager.py завершився з помилкою (code %errorlevel%).
    pause
    exit /b %errorlevel%
)

echo [OK] Успішно завершено.
endlocal
exit /b 0
