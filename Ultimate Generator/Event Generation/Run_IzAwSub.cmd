@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
python "Python Scripts\generate_ultimate_thumbnails.py" -e "Big Forehead Plays 4" -o missing.log
type missing.log
pause
