@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
py -3.9 "Python Scripts\generate_ultimate_thumbnails.py" -e "Big Forehead Plays 4" -o missing.log
type missing.log
pause
