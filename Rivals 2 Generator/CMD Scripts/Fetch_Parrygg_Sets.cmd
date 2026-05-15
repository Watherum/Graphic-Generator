@REM Usage:
@REM   python fetch_parrygg_sets.py <tournament-slug> [--event 0] [--name "My Tournament"] [--out sets.txt]

@echo off
cd /d "%~dp0.."
python "Python Scripts\fetch_parrygg_sets.py" al-rivals-2-2-26-2026-019c9aeb --name "AL Rivals 2 2-26-2026" --out "Vod_Names\AL Rivals 2 2-26-2026 Names (Parrygg).txt"
pause
