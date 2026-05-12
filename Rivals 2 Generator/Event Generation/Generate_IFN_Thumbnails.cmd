echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
python "Python Scripts\generate_rivals_thumbnail.py" -e "Immortal Fight Night 275" -o missing.log
type missing.log
pause
