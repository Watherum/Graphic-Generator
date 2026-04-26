echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "Big Forehead Plays 4" -o missing.log
type missing.log
pause