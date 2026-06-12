@REM Usage:
@REM   py -3.12 fetch_startgg_top8.py <event-slug> [--name "My Tournament"] [--link "https://start.gg/..."] [--top 8] [--out path.txt]

@echo off
cd /d "%~dp0.."
py -3.12 "Python_Scripts\fetch_startgg_top8.py" tournament/straight-into-the-abyss-47/event/rivals-2-singles --name "Straight Into The Abyss 47" --link "https://start.gg/SITA47" --out "Top_8_Texts\Straight Into The Abyss Top 8 HTML.txt"
pause
