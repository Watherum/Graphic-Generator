echo off 
call ..\venv\Scripts\activate.bat
python create_thumbnail.py -e "Straight Into The Abyss 47" -o missing.log
type missing.log
pause