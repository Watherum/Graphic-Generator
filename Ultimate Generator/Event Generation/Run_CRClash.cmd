@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
python "Python Scripts\create_thumbnail.py" -e "CR Clash Monthly 9" -o missing.log
type missing.log
pause
