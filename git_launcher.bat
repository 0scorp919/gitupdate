@echo off
:: UA: Встановлюємо кодування UTF-8 для коректного відображення кирилиці
chcp 65001 >nul
setlocal

:: ============================================================
:: GIT PORTABLE MANAGER — GitHub-ready Launcher
:: UA: Портативний лаунчер для публікації проекту на GitHub.
::     Auto-detect CAPSULE_ROOT від %~dp0 (два рівні вгору).
::     Без хардкодованих шляхів — працює з будь-якого розташування.
:: ============================================================

:: --- 1. ПЕРЕВІРКА ПРАВ АДМІНІСТРАТОРА ---
NET SESSION >nul 2>&1
if %errorLevel% neq 0 (
    echo [INFO] Запит прав адміністратора...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
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
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [CRITICAL ERROR] Python not found at:
        echo   %PYTHON_EXE%
        echo.
        echo [HINT] Переконайся що Python встановлено у:
        echo   %CAPSULE_ROOT%\apps\python\current\python\
        echo   Запусти: Win+R -^> python
        pause
        exit /b 1
    )
)

:: --- 4. SCRIPT PATH ---
set "MANAGER=%LAUNCHER_DIR%\git_manager.py"

:: --- 5. ВІЗУАЛІЗАЦІЯ ---
echo ========================================================
echo   GIT PORTABLE MANAGER (Admin Mode)
echo   (c) Oleksii Rovnianskyi System
echo   Root: %CAPSULE_ROOT%
echo ========================================================

:: --- 6. ПЕРЕВІРКА СКРИПТА ---
if not exist "%MANAGER%" (
    echo [CRITICAL ERROR] Script not found at:
    echo   %MANAGER%
    pause
    exit /b 1
)

:: --- 7. ЗАПУСК СКРИПТА ---
echo [INFO] Запуск Python скрипта...
cd /d "%CAPSULE_ROOT%"
"%PYTHON_EXE%" "%MANAGER%" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Скрипт завершився з помилкою %ERRORLEVEL%.
    echo Перевір лог-файл у: %CAPSULE_ROOT%\logs\gitlog\
    pause
) else (
    echo.
    echo [OK] Успішно завершено.
)

endlocal
exit /b 0
