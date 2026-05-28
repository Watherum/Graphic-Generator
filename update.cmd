@echo off
setlocal

echo ============================================
echo  Graphic Generator - Update from GitHub
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

:: Move to the script's directory (repo root)
cd /d "%~dp0"

echo Checking for local changes...
git status --short
echo.

:: Stash any local changes so the pull doesn't conflict
git diff --quiet && git diff --cached --quiet
if errorlevel 1 (
    echo Local changes detected. Stashing them temporarily...
    git stash push --include-untracked -m "pre-update stash"
    set STASHED=1
) else (
    set STASHED=0
)

echo.
echo Pulling latest code from GitHub...
git pull origin main
if errorlevel 1 (
    echo.
    echo ERROR: Pull failed. See messages above.
    if "%STASHED%"=="1" (
        echo Restoring your local changes...
        git stash pop
    )
    pause
    exit /b 1
)

echo.
if "%STASHED%"=="1" (
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
echo  Update complete!
echo ============================================
echo.
pause
