echo off
cd /d "%~dp0.."
call ..\venv\Scripts\activate.bat
python "Python Scripts\download_rivals_renders.py"
pause
