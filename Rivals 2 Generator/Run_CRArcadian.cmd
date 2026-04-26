echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "CR Arcadian" -o missing.log
type missing.log
pause