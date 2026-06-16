@echo off
setlocal

echo ============================================
echo  Graphic Generator - Update This Generator
echo ============================================
echo.

:: Verify git is available
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git not found. Please install Git for Windows.
    echo Download: https://git-scm.com/download/win
    pause
    exit /b 1
)

:: Determine this generator's folder name (the folder this script lives in)
set "GEN_DIR=%~dp0"
set "GEN_DIR=%GEN_DIR:~0,-1%"
for %%I in ("%GEN_DIR%") do set "GEN_NAME=%%~nxI"

:: Move to the repo root (the parent of this generator folder)
cd /d "%~dp0.."

echo Updating only: %GEN_NAME%
echo.

echo Checking for local changes in %GEN_NAME%...
git status --short -- "%GEN_NAME%"
echo.

:: Stash any local changes inside this folder so the update doesn't clobber them
set STASHED=0
git diff --quiet -- "%GEN_NAME%" && git diff --cached --quiet -- "%GEN_NAME%"
if errorlevel 1 (
    echo Local changes detected. Stashing them temporarily...
    git stash push --include-untracked -m "pre-update stash (%GEN_NAME%)" -- "%GEN_NAME%"
    set STASHED=1
)

echo.
echo Fetching latest code from GitHub...
git fetch origin main
if errorlevel 1 (
    echo.
    echo ERROR: Fetch failed. See messages above.
    if "%STASHED%"=="1" (
        echo Restoring your local changes...
        git stash pop
    )
    pause
    exit /b 1
)

echo Applying updates to %GEN_NAME%...
git checkout FETCH_HEAD -- "%GEN_NAME%"
if errorlevel 1 (
    echo.
    echo ERROR: Update failed. See messages above.
    if "%STASHED%"=="1" (
        echo Restoring your local changes...
        git stash pop
    )
    pause
    exit /b 1
)

if "%STASHED%"=="1" (
    echo.
    echo Restoring your local changes...
    git stash pop
    if errorlevel 1 (
        echo.
        echo WARNING: Could not automatically restore local changes due to a conflict.
        echo Run "git stash pop" manually to review the conflicts.
    )
)

echo.
echo ============================================
echo  %GEN_NAME% update complete!
echo ============================================
echo.
pause
