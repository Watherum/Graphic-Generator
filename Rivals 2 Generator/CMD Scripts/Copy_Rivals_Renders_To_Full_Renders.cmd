echo off
cd /d "%~dp0.."
call ..\venv\Scripts\activate.bat
python "Python Scripts\copy_rivals_renders_to_full.py"
pause
