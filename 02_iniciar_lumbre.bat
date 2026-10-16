@echo off
setlocal EnableExtensions
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
cd /d "%ROOT%"
title Lumbre - Iniciar

echo ============================================================
echo   INICIAR APLICACION WEB
echo ============================================================
echo.

if not exist "%ROOT%\lumbre\__main__.py" (
  echo ERROR: No encuentro el backend de Lumbre en la carpeta del proyecto.
  echo.
  echo Mantén completa la carpeta del proyecto y vuelve a abrir este acceso.
  echo.
  pause
  exit /b 1
)
if not exist "%ROOT%\requirements.txt" (
  echo ERROR: No encuentro requirements.txt en esta carpeta.
  echo Descarga y extrae el proyecto completo antes de iniciar.
  echo.
  pause
  exit /b 1
)

set "PYTHON_CHECK=import os, struct, sys; compatible = (sys.implementation.name == 'cpython' and sys.version_info >= (3, 11) and sys.version_info.releaselevel == 'final' and struct.calcsize('P') == 8 and sys.prefix == sys.base_prefix and not os.environ.get('CONDA_PREFIX') and not os.path.isdir(os.path.join(sys.prefix, 'conda-meta'))); sys.exit(0 if compatible else 1)"
set "PYTHON="
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "%PYTHON_CHECK%" >nul 2>&1
  if not errorlevel 1 set "PYTHON=py -3"
  if not defined PYTHON (
    for %%V in (3.14 3.13 3.12 3.11) do (
      py -%%V -c "%PYTHON_CHECK%" >nul 2>&1
      if not errorlevel 1 if not defined PYTHON set "PYTHON=py -%%V"
    )
  )
)
if not defined PYTHON (
  where python >nul 2>&1
  if not errorlevel 1 (
    python -c "%PYTHON_CHECK%" >nul 2>&1
    if not errorlevel 1 set "PYTHON=python"
  )
)
if not defined PYTHON (
  echo ERROR: Windows no encuentra CPython estable de 64 bits compatible.
  echo Se requiere Python 3.11 o posterior, fuera de Conda/venv.
  echo Ejecuta 01_instalar_lumbre.bat para ver el diagnostico.
  echo.
  pause
  exit /b 1
)

echo Python seleccionado: %PYTHON%
%PYTHON% --version
echo.

echo Comprobando las bibliotecas necesarias...
%PYTHON% -c "import numpy, scipy, skimage, cv2, sklearn, PIL, pyproj, joblib" >nul 2>&1
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
%PYTHON% -m pip install --user --only-binary=:all: --upgrade-strategy only-if-needed -r "%ROOT%\requirements.txt"
if errorlevel 1 goto error_dependencias
%PYTHON% -c "import numpy, scipy, skimage, cv2, sklearn, PIL, pyproj, joblib" >nul 2>&1
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

set "MOBILE_ARGS="
if exist "%ROOT%\.lumbre\mobile-access.txt" (
  findstr /X /I /C:"enabled" "%ROOT%\.lumbre\mobile-access.txt" >nul 2>&1
  if not errorlevel 1 set "MOBILE_ARGS=--host 0.0.0.0"
)
if defined MOBILE_ARGS echo Acceso movil activado: el servidor escuchara en la red local.
%PYTHON% -m lumbre --project-root "%ROOT%" %MOBILE_ARGS% %*
set "APP_EXIT=%ERRORLEVEL%"
if "%APP_EXIT%"=="2" (
  echo.
  echo Lumbre ya estaba abierta. Se reutiliza la instancia existente.
  exit /b 0
)
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
