@echo off
cd /d "%~dp0"
py -3.12 create_release.py --game ultimate --include-renders --out "UltimateGenerator.zip"
