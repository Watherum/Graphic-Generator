@REM Usage:
@REM   py -3.12 fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]

@echo off
cd /d "%~dp0.."
py -3.12 "Python Scripts\fetch_sets.py" tournament/ultimate-immortal-fight-night-274/event/rivals-2-singles --name "Immortal Fight Night 274" --out "Vod_Names\Immortal Fight Night 274 Names.txt"
pause
