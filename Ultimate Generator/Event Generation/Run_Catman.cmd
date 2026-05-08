@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
python "Python Scripts\generate_ultimate_thumbnails.py" -e "Catman Invitational" -o missing.log
type missing.log
pause
