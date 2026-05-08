@echo off
cd /d "%~dp0.."
python "Python Scripts\generate_melee_thumbnails.py" -e "CR Arcadian" -o missing.log
type missing.log
pause
