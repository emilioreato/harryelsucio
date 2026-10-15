@echo off
setlocal
cd /d "%~dp0"

echo Iniciando Lumbre. Si ya esta abierta, se reutilizara esa instancia y se abrira su pagina.
echo Deja esta ventana abierta mientras uses la aplicacion. Pulsa Ctrl+C para detenerla.
echo.

where py >nul 2>nul
if not errorlevel 1 (
    rem Comprobar que el runtime puede ejecutar codigo; --version puede pasar
    rem aunque el Python Install Manager no tenga esa version instalada.
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

echo No se encontro un runtime de Python que pueda ejecutarse.
echo Si aparece el comando "py", instala un runtime con:
echo   py install 3.12
echo Despues instala las dependencias desde esta carpeta con:
echo   py -3.12 -m pip install -r requirements.txt
echo Tambien puedes instalar Python 3.12 o 3.11 desde python.org y volver a ejecutar este archivo.
echo.
pause
exit /b 1

:usar_python312
echo Usando Python 3.12.
py -3.12 "%~dp0app.py"
if errorlevel 2 goto ya_activa
goto final

:usar_python311
echo Usando Python 3.11.
py -3.11 "%~dp0app.py"
if errorlevel 2 goto ya_activa
goto final

:usar_python_predeterminado
echo Usando el Python disponible en PATH.
"%PYTHON_EXE%" "%~dp0app.py"
if errorlevel 2 goto ya_activa
goto final

:ya_activa
echo Lumbre ya estaba abierto. Se ha intentado abrir la pagina existente en el navegador.
endlocal
exit /b 0

:final
echo.
echo Lumbre se ha detenido.
pause
endlocal
