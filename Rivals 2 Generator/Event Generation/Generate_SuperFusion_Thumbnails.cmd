echo off
cd /d "%~dp0.."
call ..\..\venv\Scripts\activate.bat
python "Python Scripts\generate_rivals_thumbnail.py" -e "Super Fusion" -o missing.log
type missing.log
pause
