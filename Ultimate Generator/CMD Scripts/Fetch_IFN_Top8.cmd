@REM Usage:
@REM   py -3.12 fetch_startgg_top8.py <event-slug> [--name "My Tournament"] [--link "https://start.gg/..."] [--top 8] [--out path.txt]

@echo off
cd /d "%~dp0.."
py -3.12 "Python Scripts\fetch_startgg_top8.py" tournament/ultimate-immortal-fight-night-274/event/rivals-2-singles --name "Immortal Fight Night 274" --link "https://start.gg/UIFN274" --out "Top_8_Texts\Immortal Fight Night Top 8 HTML.txt"
pause
