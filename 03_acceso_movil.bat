@echo off
setlocal EnableExtensions
for %%I in ("%~dp0.") do set "ROOT=%%~fI"
cd /d "%ROOT%"
title Configurar acceso opcional desde movil - Lumbre

set "CONFIG_DIR=%ROOT%\.lumbre"
set "CONFIG_FILE=%CONFIG_DIR%\mobile-access.txt"

echo ============================================================
echo   ACCESO MOVIL OPCIONAL DE LUMBRE
echo ============================================================
echo.

if exist "%CONFIG_FILE%" (
  findstr /X /I /C:"enabled" "%CONFIG_FILE%" >nul 2>&1
  if not errorlevel 1 (
    echo Estado actual: ACTIVADO.
  ) else (
    echo Estado actual: DESACTIVADO.
  )
) else (
  echo Estado actual: DESACTIVADO.
)
echo.
echo [1] Activar acceso desde un movil de la misma Wi-Fi
echo [2] Desactivar acceso movil
echo [3] Salir sin cambios
echo.
choice /C 123 /N /M "Elige una opcion: "
if errorlevel 3 goto salir
if errorlevel 2 goto desactivar
if errorlevel 1 goto activar

:activar
echo.
echo Al activar, otros dispositivos de tu red privada podran abrir Lumbre.
echo No se modificara el firewall, el router ni la configuracion de Windows.
echo Windows podria mostrar su propio aviso de firewall; si no quieres permitir
echo conexiones entrantes, pulsa Cancelar. Lumbre seguira funcionando localmente.
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%" 2>nul
if not exist "%CONFIG_DIR%" goto error_configuracion
>"%CONFIG_FILE%" echo enabled
findstr /X /I /C:"enabled" "%CONFIG_FILE%" >nul 2>&1
if errorlevel 1 goto error_configuracion
echo.
echo Acceso movil ACTIVADO para el proximo inicio de Lumbre.
echo Cierra la aplicacion si esta abierta y ejecuta 02_iniciar_lumbre.bat.
goto fin

:desactivar
echo.
if exist "%CONFIG_FILE%" del /Q "%CONFIG_FILE%" >nul 2>&1
if exist "%CONFIG_FILE%" goto error_configuracion
echo Acceso movil DESACTIVADO.
echo Cierra la aplicacion si esta abierta y ejecuta 02_iniciar_lumbre.bat.
goto fin

:salir
echo.
echo No se han realizado cambios.
goto fin

:error_configuracion
echo.
echo ERROR: No se pudo actualizar la configuracion local de Lumbre.
echo Comprueba que la carpeta del proyecto no sea de solo lectura.
echo.
pause
exit /b 1

:fin
echo.
pause
exit /b 0
