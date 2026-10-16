@echo off
setlocal
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
cd /d "%ROOT%"
title Lumbre - Cerrar

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 goto usar_py
)

for /f "delims=" %%P in ('where python 2^>nul') do (
    "%%P" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=%%P"
        goto usar_python_predeterminado
    )
)

echo No se encontro un runtime de Python ejecutable. Se intentara cerrar procesos identificables de Lumbre.
goto cierre_procesos

:usar_py
py -3 -m lumbre --project-root "%ROOT%" --close
goto resultado

:usar_python_predeterminado
echo Usando el Python 3.11 o posterior disponible en PATH.
"%PYTHON_EXE%" -m lumbre --project-root "%ROOT%" --close

:resultado
set "RESULTADO=%ERRORLEVEL%"
if not "%RESULTADO%"=="0" echo El cierre normal no confirmo la salida. Buscando procesos de Lumbre.

:cierre_procesos
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\cerrar_procesos_lumbre.ps1"
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
