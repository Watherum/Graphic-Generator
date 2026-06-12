@echo off
cd /d "%~dp0.."
py -3.12 "Python Scripts\generate_melee_thumbnails.py" -e "CR Arcadian" -o missing.log
type missing.log
pause
