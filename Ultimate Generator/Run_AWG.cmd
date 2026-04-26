echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "AWG Spring Split 1" -o missing.log
type missing.log
pause