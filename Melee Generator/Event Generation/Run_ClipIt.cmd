@echo off
cd /d "%~dp0.."
py -3.9 "Python Scripts\generate_melee_thumbnails.py" -e "Clip It 3" -o missing.log
type missing.log
pause
