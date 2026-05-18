@REM Usage:
@REM   py -3.9 fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]

@echo off
cd /d "%~dp0.."
py -3.9 "Python Scripts\fetch_sets.py" tournament/straight-into-the-abyss-48/event/rivals-2-singles --name "Straight Into The Abyss 48" --out "Vod_Names\Straight Into The Abyss 48 Names.txt"
pause
