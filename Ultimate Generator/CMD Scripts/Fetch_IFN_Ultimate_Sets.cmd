@REM Usage:
@REM   py -3.9 fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]

@echo off
cd /d "%~dp0.."
py -3.9 "Python Scripts\fetch_sets.py" tournament/ultimate-immortal-fight-night-272/event/ultimate-singles --name "IFN 272" --out "Vod_Names\Immortal Fight Night 272 Names.txt"
pause
