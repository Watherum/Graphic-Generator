echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
py -3.12 "Python Scripts\generate_rivals_thumbnail.py" -e "Straight Into The Abyss 51" -o missing.log
type missing.log
pause
