echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "CR Clash Monthly 9" -o missing.log
type missing.log
pause