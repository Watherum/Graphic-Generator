@echo off
cd /d "%~dp0.."
py -3.12 "Python_Scripts\generate_melee_thumbnails.py" -e "Immortal Fight Night 145" -o missing.log
type missing.log
pause
