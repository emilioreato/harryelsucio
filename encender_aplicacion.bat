@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Espejo Ustorio / Lumbre - Inicio

echo ============================================================
echo   INICIAR APLICACION WEB
echo ============================================================
echo.

if not exist "%~dp0app.py" (
  echo ERROR: No encuentro app.py en esta carpeta.
  echo.
  echo Este archivo debe estar en la carpeta raiz del proyecto,
  echo junto a app.py y requirements.txt.
  echo.
  pause
  exit /b 1
)
if not exist "%~dp0requirements.txt" (
  echo ERROR: No encuentro requirements.txt en esta carpeta.
  echo Descarga y extrae el proyecto completo antes de iniciar.
  echo.
  pause
  exit /b 1
)

set "PYTHON="
where py >nul 2>&1
if not errorlevel 1 (
  py -3.12 --version >nul 2>&1
  if not errorlevel 1 set "PYTHON=py -3.12"
  if not defined PYTHON (
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=py -3.11"
  )
)
if not defined PYTHON (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
  echo ERROR: Windows no encuentra Python 3.12 ni 3.11.
  echo Instala Python de 64 bits desde https://www.python.org/downloads/windows/
  echo Durante la instalacion, marca "Add Python to PATH".
  echo Despues, vuelve a ejecutar este archivo.
  echo.
  pause
  exit /b 1
)

echo Python seleccionado: %PYTHON%
%PYTHON% --version
echo.

echo Comprobando las bibliotecas necesarias...
%PYTHON% -c "import numpy, pandas, scipy, rasterio, skimage, cv2, sklearn, PIL, geopandas, shapely, pyproj, plotly, requests" >nul 2>&1
if errorlevel 1 goto instalar_dependencias
goto arrancar

:instalar_dependencias
echo Faltan algunas bibliotecas. Intentando instalarlas ahora...
echo Este paso necesita conexion a Internet y puede tardar varios minutos.
echo.
%PYTHON% -m pip --version >nul 2>&1
if errorlevel 1 (
  %PYTHON% -m ensurepip --upgrade
  if errorlevel 1 goto error_dependencias
)
%PYTHON% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo.
  echo La instalacion normal no ha terminado. Probando instalacion para el usuario...
  %PYTHON% -m pip install --user -r "%~dp0requirements.txt"
  if errorlevel 1 goto error_dependencias
)
%PYTHON% -c "import numpy, pandas, scipy, rasterio, skimage, cv2, sklearn, PIL, geopandas, shapely, pyproj, plotly, requests" >nul 2>&1
if errorlevel 1 goto error_dependencias

echo.
echo Bibliotecas instaladas correctamente.
echo.

:arrancar
echo Iniciando el servidor web...
echo Deja esta ventana abierta mientras uses la aplicacion.
echo Si no se abre el navegador, prueba http://127.0.0.1:8501/
echo Para detener el servidor, pulsa Ctrl+C.
echo.
%PYTHON% "%~dp0app.py"
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
  echo.
  echo ERROR: La aplicacion se ha cerrado con codigo %APP_EXIT%.
  echo Copia o fotografia el mensaje de error que aparece encima.
  echo.
  pause
  exit /b %APP_EXIT%
)
echo.
echo La aplicacion se ha detenido.
pause
exit /b 0

:error_dependencias
echo.
echo ERROR: No se han podido instalar o verificar las bibliotecas.
echo Comprueba la conexion a Internet y que Python sea de 64 bits.
echo Vuelve a ejecutar este archivo. Si falla otra vez, fotografia esta ventana.
echo.
pause
exit /b 1
