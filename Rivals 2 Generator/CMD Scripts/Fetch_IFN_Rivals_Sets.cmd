@REM Usage:
@REM   python fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]

@echo off
cd /d "%~dp0.."
python "Python Scripts\fetch_sets.py" tournament/ultimate-immortal-fight-night-274/event/rivals-2-singles --name "Immortal Fight Night 274" --out "Vod_Names\Immortal Fight Night 274 Names.txt"
pause
