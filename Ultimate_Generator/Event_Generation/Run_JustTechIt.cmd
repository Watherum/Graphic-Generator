@echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
py -3.12 "Python_Scripts\generate_ultimate_thumbnails.py" -e "AWG Just Tech It 16" -o missing.log
type missing.log
pause
