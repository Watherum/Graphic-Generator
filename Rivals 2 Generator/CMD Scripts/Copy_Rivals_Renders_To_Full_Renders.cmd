echo off
cd /d "%~dp0.."
call ..\venv\Scripts\activate.bat
py -3.9 "Python Scripts\copy_rivals_renders_to_full.py"
pause
