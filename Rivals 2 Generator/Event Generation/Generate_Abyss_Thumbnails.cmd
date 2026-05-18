echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
py -3.9 "Python Scripts\generate_rivals_thumbnail.py" -e "Straight Into The Abyss 48" -o missing.log
type missing.log
pause
