echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "Clip It 3" -o missing.log
type missing.log
pause