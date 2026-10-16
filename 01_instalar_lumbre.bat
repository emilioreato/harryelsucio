@echo off
setlocal EnableExtensions
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
cd /d "%ROOT%"
title Instalar Lumbre

echo ============================================================
echo   INSTALADOR DE LUMBRE
echo ============================================================
echo.

if not exist "%ROOT%\lumbre\__main__.py" goto error_estructura
if not exist "%ROOT%\requirements.txt" goto error_estructura

echo [1/4] Comprobando Python y PATH...
where py >nul 2>&1
if errorlevel 1 (
  echo No se encontro el lanzador py en PATH.
) else (
  echo Lanzador py detectado:
  where py
)
where python >nul 2>&1
if errorlevel 1 (
  echo No se encontro python en PATH.
) else (
  echo python detectado:
  where python
)
echo.

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
if not defined PYTHON goto error_python

echo Interprete seleccionado: %PYTHON%
%PYTHON% -c "import platform, sys; print('Ejecutable: ' + sys.executable); print('Python ' + sys.version.split()[0] + ' (' + platform.machine() + ')')"
if errorlevel 1 goto error_python
echo.

echo [2/4] Comprobando pip en ese mismo Python...
%PYTHON% -m pip --version >nul 2>&1
if errorlevel 1 (
  echo pip no esta disponible. Intentando habilitarlo con ensurepip...
  %PYTHON% -m ensurepip --upgrade
  if errorlevel 1 goto error_pip
)
%PYTHON% -m pip --version
if errorlevel 1 goto error_pip
echo.

echo [3/4] Instalando las dependencias del proyecto...
echo Se instalaran en el perfil de usuario, sin permisos de administrador.
echo No se compilaran paquetes desde codigo fuente.
echo.
%PYTHON% -m pip install --user --only-binary=:all: --upgrade-strategy only-if-needed -r "%ROOT%\requirements.txt"
if errorlevel 1 goto error_instalacion
echo.

echo [4/4] Verificando imports y arranque de la aplicacion...
%PYTHON% -c "import cv2, joblib, numpy, pyproj, scipy, sklearn, skimage; from PIL import Image; print('Imports correctos: numpy=' + numpy.__version__ + ', scipy=' + scipy.__version__ + ', opencv=' + cv2.__version__ + ', scikit-image=' + skimage.__version__ + ', scikit-learn=' + sklearn.__version__ + ', pyproj=' + pyproj.__version__)"
if errorlevel 1 goto error_imports
%PYTHON% -m lumbre --help
if errorlevel 1 goto error_arranque

echo.
echo Instalacion terminada. Para iniciar Lumbre, ejecuta 02_iniciar_lumbre.bat.
echo No se modificaron PATH, firewall ni configuracion global del ordenador.
echo.
pause
exit /b 0

:error_estructura
echo ERROR: No encuentro lumbre\__main__.py o requirements.txt en la carpeta del proyecto.
echo Descarga y extrae el repositorio completo antes de usar el instalador.
goto error_final

:error_python
echo ERROR: No encontre CPython estable de 64 bits compatible en PATH.
echo Se requiere CPython estable 3.11 o posterior, de 64 bits y fuera de Conda/venv.
echo Instala Python desde https://www.python.org/downloads/windows/,
echo marca Python Launcher y Add Python to PATH, y vuelve a ejecutar este archivo.
goto error_final

:error_pip
echo ERROR: No se pudo habilitar pip en el Python seleccionado.
echo Repara esa instalacion de Python y vuelve a ejecutar el instalador.
goto error_final

:error_instalacion
echo ERROR: pip no pudo instalar las dependencias.
echo Revisa el mensaje anterior, la conexion, el proxy o el antivirus.
echo Si no hay una rueda compatible para tu Python, usa una version estable 3.11-3.14.
goto error_final

:error_imports
echo ERROR: La instalacion termino, pero fallaron imports de las bibliotecas.
echo El traceback anterior puede indicar un problema de rueda, arquitectura o DLL.
goto error_final

:error_arranque
echo ERROR: Las bibliotecas importan, pero Lumbre no pudo iniciar.
echo Revisa el error que aparece arriba y comparte esa salida para diagnosticarlo.
goto error_final

:error_final
echo.
echo La ventana quedara abierta para que puedas leer o copiar el error.
pause
exit /b 1
