@echo off
setlocal
cd /d "%~dp0"

echo Iniciando Lumbre. Se abrira la pagina de analisis satelital.
echo Deja esta ventana abierta mientras uses la aplicacion. Pulsa Ctrl+C para detenerla.
echo.

where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 --version >nul 2>nul
    if not errorlevel 1 goto usar_python312

    py -3.11 --version >nul 2>nul
    if not errorlevel 1 goto usar_python311
)

python --version >nul 2>nul
if not errorlevel 1 goto usar_python_predeterminado

echo No se encontro Python 3.12, 3.11 ni un Python predeterminado.
echo Instala Python y las dependencias desde esta carpeta con:
echo   py -3.12 -m pip install -r requirements.txt
echo Si usas Python 3.11, cambia 3.12 por 3.11.
echo.
pause
exit /b 1

:usar_python312
echo Usando Python 3.12.
py -3.12 app.py
if errorlevel 2 goto ya_activa
goto final

:usar_python311
echo Usando Python 3.11.
py -3.11 app.py
if errorlevel 2 goto ya_activa
goto final

:usar_python_predeterminado
echo Usando el Python predeterminado del sistema.
python app.py
if errorlevel 2 goto ya_activa
goto final

:ya_activa
echo Lumbre ya esta abierto. No se inicio otra ventana de servidor.
endlocal
exit /b 0

:final
echo.
echo Lumbre se ha detenido.
pause
endlocal
