@echo off
cd /d "%~dp0"
py -3.12 create_release.py --out "Rivals2Generator.zip"
