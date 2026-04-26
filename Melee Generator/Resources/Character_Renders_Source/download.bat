@echo off
:loop
set /p fighter=Enter Fighter Name (use underscores for spaces like donkey_kong) or type "exit" to exit: 
if /I "%fighter%" EQU "exit" goto :end
set number=main
powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%fighter%/%number%.png -OutFile %fighter%_%number%.png"
set number=main2
powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%fighter%/%number%.png -OutFile %fighter%_%number%.png"
set number=main3
powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%fighter%/%number%.png -OutFile %fighter%_%number%.png"
set number=main4
powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%fighter%/%number%.png -OutFile %fighter%_%number%.png"
set number=main5
powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%fighter%/%number%.png -OutFile %fighter%_%number%.png"
set number=main6
powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%fighter%/%number%.png -OutFile %fighter%_%number%.png"
set number=main7
powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%fighter%/%number%.png -OutFile %fighter%_%number%.png"
set number=main8
powershell -Command "Invoke-WebRequest https://www.smashbros.com/assets_v2/img/fighter/%fighter%/%number%.png -OutFile %fighter%_%number%.png"
goto :loop
:end