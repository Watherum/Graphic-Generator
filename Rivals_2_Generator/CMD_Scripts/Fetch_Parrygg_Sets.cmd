@REM Usage:
@REM   Fetch_Parrygg_Sets.cmd <tournament-slug> ["Tournament Name"]  (add --event N for a tournament's second bracket)
@REM
@REM The GUI's Fetch Data tab is the usual way in; this wrapper is for a
@REM one-off fetch from the command line.

@echo off
cd /d "%~dp0.."
if "%~1"=="" (
  echo Usage: %~nx0 my-tournament-019c9aeb "My Tournament 5"
  pause
  exit /b 1
)
set "EVENT_NAME=%~2"
if "%EVENT_NAME%"=="" set "EVENT_NAME=%~1"
py -3.12 "Python_Scripts\fetch_parrygg_sets.py" %1 --name "%EVENT_NAME%" --out "Vod_Names\%EVENT_NAME% Names.txt"
pause
