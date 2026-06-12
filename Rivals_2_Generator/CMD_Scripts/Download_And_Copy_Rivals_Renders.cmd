echo off
cd /d "%~dp0.."
call ..\venv\Scripts\activate.bat
echo Downloading renders from dragdown wiki...
py -3.12 "Python_Scripts\download_rivals_renders.py"
echo.
echo Copying renders to Rivals_2_Full_Renders...
py -3.12 "Python_Scripts\copy_rivals_renders_to_full.py"
pause
