@REM Usage:
@REM   python fetch_parrygg_top8.py <tournament-slug> [--event 0] [--name "My Tournament"] [--link "https://parry.gg/..."] [--top 8] [--out path.txt]

@echo off
cd /d "%~dp0.."
python "Python Scripts\fetch_parrygg_top8.py" al-rivals-2-2-26-2026-019c9aeb --name "AL Rivals 2" --link "https://parry.gg/al-rivals-2-2-26-2026-019c9aeb" --out "Top_8_Texts\AL Rivals Top 8 HTML.txt"
pause
