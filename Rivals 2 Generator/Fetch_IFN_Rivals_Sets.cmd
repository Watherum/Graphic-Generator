@REM Usage:
@REM   python fetch_sets.py <event-slug> [--name "My Tournament"] [--station N] [--out sets.txt]


@echo off
python "%~dp0fetch_sets.py" tournament/ultimate-immortal-fight-night-272/event/rivals-2-singles --name "IFN 272" --out "Vod_Names\Immortal Fight Night 272 Names".txt
pause
