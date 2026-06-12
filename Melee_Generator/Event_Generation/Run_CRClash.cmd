@echo off
cd /d "%~dp0.."
py -3.12 "Python_Scripts\generate_melee_thumbnails.py" -e "CR Clash 77" -o missing.log
type missing.log
pause
