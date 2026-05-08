@echo off
cd /d "%~dp0.."
python "Python Scripts\generate_melee_thumbnails.py" -e "Clip It 3" -o missing.log
type missing.log
pause
