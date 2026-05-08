@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
python "Python Scripts\generate_ultimate_thumbnails.py" -e "C2C Finale Winter 2021" -o missing.log
type missing.log
pause
