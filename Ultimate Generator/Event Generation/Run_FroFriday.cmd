@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
py -3.12 "Python Scripts\generate_ultimate_thumbnails.py" -e "Fro Fridays 33" -o missing.log
type missing.log
pause
