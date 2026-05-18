@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
py -3.9 "Python Scripts\generate_ultimate_thumbnails.py" -e "Catman Invitational" -o missing.log
type missing.log
pause
