@echo off
setlocal
cd /d "%~dp0"

echo Iniciando Lumbre. Si ya esta abierta, se reutilizara esa instancia y se abrira su pagina.
echo Deja esta ventana abierta mientras uses la aplicacion. Pulsa Ctrl+C para detenerla.
echo.

where py >nul 2>nul
if not errorlevel 1 (
    rem Usar cualquier Python 3.11+ instalado, sin exigir una version menor fija.
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

echo No se encontro Python 3.11 o posterior que pueda ejecutarse.
echo Instala la version actual de Python desde:
echo   https://www.python.org/downloads/
echo En Windows, activa "Add python.exe to PATH" durante la instalacion.
echo Despues abre esta ventana de nuevo e instala las dependencias desde esta carpeta:
echo   python -m pip install -r requirements.txt
echo.
pause
exit /b 1

:usar_py
echo Usando el Python 3.11 o posterior seleccionado por el lanzador de Windows.
py -3 "%~dp0app.py"
if errorlevel 2 goto ya_activa
goto final

:usar_python_predeterminado
echo Usando el Python 3.11 o posterior disponible en PATH.
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
