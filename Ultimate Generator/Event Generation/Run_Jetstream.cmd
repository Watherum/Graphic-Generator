@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
python "Python Scripts\create_thumbnail.py" -e "Quarantainment 90" -o missing.log
type missing.log
pause
