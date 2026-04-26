echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "Fro Fridays 33" -o missing.log
type missing.log
pause