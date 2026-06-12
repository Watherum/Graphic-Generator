echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
py -3.12 "Python_Scripts\generate_rivals_thumbnail.py" -e "Clip It V" -o missing.log
type missing.log
pause
