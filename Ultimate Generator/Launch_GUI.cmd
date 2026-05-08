@echo off
cd /d "%~dp0"
call ..\venv\Scripts\activate.bat
python "Python Scripts\ultimate_gui.py"
