@echo off
cd /d "%~dp0.."
python "Python Scripts\generate_melee_thumbnails.py" -e "CR Clash 77" -o missing.log
type missing.log
pause
