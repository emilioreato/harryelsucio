@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 goto usar_python312

    py -3.11 --version >nul 2>nul
    if not errorlevel 1 goto usar_python311
)

python --version >nul 2>nul
if not errorlevel 1 goto usar_python_predeterminado

echo No se encontro Python para cerrar Lumbre.
pause
endlocal
exit /b 1

:usar_python312
py -3.12 app.py --close
goto resultado

:usar_python311
py -3.11 app.py --close
goto resultado

:usar_python_predeterminado
python app.py --close

:resultado
set "RESULTADO=%ERRORLEVEL%"
if "%RESULTADO%"=="0" goto cerrado
echo No se pudo cerrar Lumbre. Consulta el mensaje anterior.
pause
endlocal
exit /b %RESULTADO%

:cerrado
pause
endlocal
exit /b 0
