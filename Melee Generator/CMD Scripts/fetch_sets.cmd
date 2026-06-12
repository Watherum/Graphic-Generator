@REM Usage:
@REM   py -3.12 fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]


@echo off
py -3.12 "%~dp0fetch_sets.py" tournament/ultimate-immortal-fight-night-272/event/rivals-2-singles --name "IFN 272" --out "Vod_Names\Event 1 Names".txt
pause
