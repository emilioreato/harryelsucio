@echo off
setlocal
cd /d "%~dp0"

echo Iniciando PyroScope. Se abrira en el navegador cuando Streamlit este listo.
echo Deja esta ventana abierta mientras uses la aplicacion. Pulsa Ctrl+C para detenerla.
echo.

where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -m streamlit --version >nul 2>nul
    if not errorlevel 1 goto usar_python312

    py -3.11 -m streamlit --version >nul 2>nul
    if not errorlevel 1 goto usar_python311
)

python -m streamlit --version >nul 2>nul
if not errorlevel 1 goto usar_python_predeterminado

echo No se encontro Streamlit en Python 3.12, 3.11 ni en el Python predeterminado.
echo Instala Python y las dependencias desde esta carpeta con:
echo   py -3.12 -m pip install -r requirements.txt
echo Si usas Python 3.11, cambia 3.12 por 3.11.
echo.
pause
exit /b 1

:usar_python312
echo Usando Python 3.12.
py -3.12 -m streamlit run app.py --server.address 127.0.0.1
goto final

:usar_python311
echo Usando Python 3.11.
py -3.11 -m streamlit run app.py --server.address 127.0.0.1
goto final

:usar_python_predeterminado
echo Usando el Python predeterminado del sistema.
python -m streamlit run app.py --server.address 127.0.0.1

:final
echo.
echo PyroScope se ha detenido.
pause
endlocal
