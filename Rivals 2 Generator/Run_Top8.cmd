echo off 
call ..\venv\Scripts\activate.bat
python create_top8_graphic.py
type missing.log
pause