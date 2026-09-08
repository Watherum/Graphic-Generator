@REM Usage:
@REM   Fetch_Parrygg_Top8.cmd <tournament-slug> ["Tournament Name"] ["https://parry.gg/..."]
@REM   (add --event N for a tournament's second bracket)
@REM
@REM The third argument is the link printed on the Top 8 graphic; leave it off
@REM and the graphic shows no link.
@REM
@REM The GUI's Fetch Data tab is the usual way in; this wrapper is for a
@REM one-off fetch from the command line.

@echo off
cd /d "%~dp0.."
if "%~1"=="" (
  echo Usage: %~nx0 my-tournament-019c9aeb "My Tournament 5" "https://parry.gg/my-tournament-019c9aeb"
  pause
  exit /b 1
)
set "EVENT_NAME=%~2"
if "%EVENT_NAME%"=="" set "EVENT_NAME=%~1"
py -3.12 "Python_Scripts\fetch_parrygg_top8.py" %1 --name "%EVENT_NAME%" --link "%~3" --out "Top_8_Texts\%EVENT_NAME% Top 8 HTML.txt"
pause
