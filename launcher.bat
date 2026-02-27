@echo off
:: UA: Встановлюємо кодування UTF-8
chcp 65001 >nul
setlocal

:: ============================================================
:: GIT PORTABLE MANAGER — GitHub-ready Launcher (v2.0)
:: UA: Уніфікований лаунчер для оновлення та синхронізації.
:: ============================================================

:: --- 1. ПЕРЕВІРКА ПРАВ АДМІНІСТРАТОРА ---
NET SESSION >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Запит прав адміністратора...
    powershell -Command "Start-Process '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

:: --- 2. AUTO-DETECT CAPSULE ROOT ---
set "LAUNCHER_DIR=%~dp0"
if "%LAUNCHER_DIR:~-1%"=="\" set "LAUNCHER_DIR=%LAUNCHER_DIR:~0,-1%"

for %%A in ("%LAUNCHER_DIR%\..") do set "DEVOPS_DIR=%%~fA"
for %%A in ("%DEVOPS_DIR%\..") do set "CAPSULE_ROOT=%%~fA"

:: --- 3. PYTHON EXE ---
set "PYTHON_EXE=%CAPSULE_ROOT%\apps\python\current\python\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=%CAPSULE_ROOT%\apps\python\current\python.exe"
)
if not exist "%PYTHON_EXE%" (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [CRITICAL ERROR] Python not found.
        pause
        exit /b 1
    )
)

:: --- 4. SCRIPT PATH ---
set "MANAGER=%LAUNCHER_DIR%\git_manager.py"

:: --- 5. ЗАПУСК ---
cd /d "%CAPSULE_ROOT%"
"%PYTHON_EXE%" "%MANAGER%" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Скрипт завершився з помилкою %ERRORLEVEL%.
    pause
)

endlocal
exit /b %ERRORLEVEL%
