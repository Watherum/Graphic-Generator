echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "Clip It V" -o missing.log
type missing.log
pause