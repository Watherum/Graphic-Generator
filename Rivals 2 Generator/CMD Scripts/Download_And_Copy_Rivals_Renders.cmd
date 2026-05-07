echo off
cd /d "%~dp0.."
call ..\venv\Scripts\activate.bat
echo Downloading renders from dragdown wiki...
python "Python Scripts\download_rivals_renders.py"
echo.
echo Copying renders to Rivals 2 Full Renders...
python "Python Scripts\copy_rivals_renders_to_full.py"
pause
