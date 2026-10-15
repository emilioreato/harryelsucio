@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys; sys.exit(0)" >nul 2>nul
    if not errorlevel 1 goto usar_python312

    py -3.11 -c "import sys; sys.exit(0)" >nul 2>nul
    if not errorlevel 1 goto usar_python311
)

for /f "delims=" %%P in ('where python 2^>nul') do (
    "%%P" -c "import sys; sys.exit(0)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=%%P"
        goto usar_python_predeterminado
    )
)

echo No se encontro un runtime de Python ejecutable. Se intentara cerrar procesos identificables de Lumbre.
goto cierre_procesos

:usar_python312
py -3.12 "%~dp0app.py" --close
goto resultado

:usar_python311
py -3.11 "%~dp0app.py" --close
goto resultado

:usar_python_predeterminado
echo Usando el Python disponible en PATH.
"%PYTHON_EXE%" "%~dp0app.py" --close

:resultado
set "RESULTADO=%ERRORLEVEL%"
if not "%RESULTADO%"=="0" echo El cierre normal no confirmo la salida. Buscando procesos de Lumbre.

:cierre_procesos
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0cerrar_procesos_lumbre.ps1"
set "RESULTADO=%ERRORLEVEL%"
if not "%RESULTADO%"=="0" goto error
goto cerrado

:error
echo No se pudo confirmar el cierre. Revisa los mensajes anteriores.
pause
endlocal
exit /b %RESULTADO%

:cerrado
echo Lumbre esta cerrada.
pause
endlocal
exit /b 0
