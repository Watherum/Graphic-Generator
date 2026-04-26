echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "Quarantainment 90" -o missing.log
type missing.log
pause