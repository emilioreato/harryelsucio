@echo off
setlocal
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
cd /d "%ROOT%"
title Lumbre - Cerrar

set "PYTHON_CHECK=import os, struct, sys, sysconfig; ok = (sys.implementation.name == 'cpython' and (3, 11) <= sys.version_info[:2] < (3, 15) and sys.version_info.releaselevel == 'final' and struct.calcsize('P') == 8 and sysconfig.get_config_var('Py_GIL_DISABLED') != 1 and sys.prefix == sys.base_prefix and not os.environ.get('CONDA_PREFIX') and not os.path.isdir(os.path.join(sys.prefix, 'conda-meta'))); sys.exit(0 if ok else 1)"
set "PYTHON="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "%PYTHON_CHECK%" >nul 2>nul
    if not errorlevel 1 set "PYTHON=py -3"
    if not defined PYTHON (
        for %%V in (3.14 3.13 3.12 3.11) do (
            py -%%V -c "%PYTHON_CHECK%" >nul 2>nul
            if not errorlevel 1 if not defined PYTHON set "PYTHON=py -%%V"
        )
    )
)
if defined PYTHON goto usar_py

for /f "delims=" %%P in ('where python 2^>nul') do (
    "%%P" -c "%PYTHON_CHECK%" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=%%P"
        goto usar_python_predeterminado
    )
)

echo No se encontro CPython estandar 3.11-3.14. Se intentara cerrar procesos identificables de Lumbre.
goto cierre_procesos

:usar_py
%PYTHON% -m lumbre --project-root "%ROOT%" --close
goto resultado

:usar_python_predeterminado
echo Usando CPython estandar 3.11-3.14 disponible en PATH.
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
