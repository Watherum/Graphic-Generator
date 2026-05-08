@REM Usage:
@REM   python fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]

@echo off
cd /d "%~dp0.."
python "Python Scripts\fetch_sets.py" tournament/ultimate-immortal-fight-night-272/event/ultimate-singles --name "IFN 272" --out Sets.txt
pause
