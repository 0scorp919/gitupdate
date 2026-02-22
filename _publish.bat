@echo off
setlocal DisableDelayedExpansion

set "GIT=c:\!Oleksii_Rovnianskyi\apps\git\bin\git.exe"
set "GH=c:\!Oleksii_Rovnianskyi\apps\bin\gh.exe"
set "REPO=c:\!Oleksii_Rovnianskyi\devops\gitupdate"
set "ENV_FILE=c:\!Oleksii_Rovnianskyi\devops\gitupdate\.env"

echo === GIT STATUS ===
"%GIT%" -C "%REPO%" status

echo.
echo === GIT ADD ===
"%GIT%" -C "%REPO%" add .

echo.
echo === GIT STATUS AFTER ADD ===
"%GIT%" -C "%REPO%" status

echo.
echo === GIT COMMIT ===
"%GIT%" -C "%REPO%" commit -m "feat: initial release v1.6 — GitHub-ready portable Git manager"

echo.
echo === READ GH_TOKEN_SECURITY FROM .env ===
for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    if "%%a"=="GH_TOKEN_SECURITY" set "GH_TOKEN=%%b"
)

if "%GH_TOKEN%"=="" (
    echo ERROR: GH_TOKEN_SECURITY not found in .env
    goto :end
)

echo GH_TOKEN loaded OK (first 8 chars): %GH_TOKEN:~0,8%...

echo.
echo === CREATE GITHUB REPO + PUSH ===
"%GH%" repo create gitupdate --public --description "Git for Windows Portable auto-update manager. Part of Autonomous Capsule." --source "%REPO%" --remote origin --push

echo.
echo === DONE ===

:end
endlocal
pause
