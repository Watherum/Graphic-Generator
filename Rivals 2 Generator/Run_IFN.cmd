echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "Immortal Fight Night 272" -o missing.log
type missing.log
pause