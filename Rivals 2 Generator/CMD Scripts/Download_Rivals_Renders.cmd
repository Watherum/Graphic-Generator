echo off
cd /d "%~dp0.."
call ..\venv\Scripts\activate.bat
py -3.12 "Python Scripts\download_rivals_renders.py"
pause
