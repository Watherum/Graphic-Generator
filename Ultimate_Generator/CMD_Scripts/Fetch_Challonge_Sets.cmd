@REM Usage:
@REM   Fetch_Challonge_Sets.cmd <tournament-slug> ["Tournament Name"]  (the bracket must be on challonge.com; it reports no characters)
@REM
@REM The GUI's Fetch Data tab is the usual way in; this wrapper is for a
@REM one-off fetch from the command line.

@echo off
cd /d "%~dp0.."
if "%~1"=="" (
  echo Usage: %~nx0 my-weekly-42 "My Weekly 42"
  pause
  exit /b 1
)
set "EVENT_NAME=%~2"
if "%EVENT_NAME%"=="" set "EVENT_NAME=%~1"
py -3.12 "Python_Scripts\fetch_challonge_sets.py" %1 --name "%EVENT_NAME%" --out "Vod_Names\%EVENT_NAME% Names.txt"
pause
