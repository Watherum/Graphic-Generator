@REM Usage:
@REM   py -3.12 fetch_parrygg_sets.py <tournament-slug> [--event 0] [--name "My Tournament"] [--out sets.txt]

@echo off
cd /d "%~dp0.."
py -3.12 "Python Scripts\fetch_parrygg_sets.py" al-rivals-2-4-2-2026-019d4e84/bracket/main --name "AL Rivals 2 2-26-2026" --out "Vod_Names\AL Rivals 2 2-26-2026 Names (Parrygg).txt"
pause
