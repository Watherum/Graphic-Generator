echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
python "Python Scripts\generate_rivals_thumbnail.py" -e "Twist of Fate" -o missing.log
type missing.log
pause
