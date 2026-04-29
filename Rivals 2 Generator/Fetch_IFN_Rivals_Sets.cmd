@REM Usage:
@REM   python fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]


@echo off
python "%~dp0fetch_sets.py" tournament/ultimate-immortal-fight-night-273/event/rivals-2-singles --name "Immortal Fight Night 273" --out "Vod_Names\Immortal Fight Night 273 Names".txt
pause
