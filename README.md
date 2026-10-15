# Lumbre

Aplicación de análisis satelital para revisar incendios, humo y superficie afectada. La orientación técnica está en [`DOCUMENTACION/Ideas/inicial.md`](DOCUMENTACION/Ideas/inicial.md).

## Preparación del entorno de desarrollo

### Programas

- **Python 3.11 o posterior (64 bits)**. No se requiere una versión menor concreta. En Windows, instala la versión actual desde [python.org](https://www.python.org/downloads/) y activa **Add python.exe to PATH**. No hace falta Conda, crear entornos virtuales ni usar Docker.
- **Visual Studio Code**, junto con **Git for Windows** ([descarga oficial](https://git-scm.com/download/win)).
- **QGIS LTR**, para inspeccionar rásteres, CRS, bandas, relieve y superposiciones ([descarga oficial para Windows](https://qgis.org/download/)). No es necesario configurar el Python interno de QGIS ni usarlo para ejecutar este proyecto.

En VS Code conviene instalar las extensiones oficiales **Python** (Microsoft) y **Pylance** (Microsoft). **Jupyter** es opcional si se van a usar notebooks.

La interfaz está escrita con **React** y **Vite**. Para ejecutar la aplicación ya preparada no hace falta instalar Node.js: el lanzador sirve el paquete web incluido en `web/`. Si vas a modificar la interfaz, instala Node.js 20.19 o posterior y npm; en `frontend/`, ejecuta `npm ci` una vez y `npm run build` cada vez que quieras actualizar la versión servida por el lanzador.

### Instalar las dependencias

Abre una terminal de PowerShell en la carpeta del repositorio y ejecuta:

```powershell
python -m pip install -r requirements.txt
```

En Windows, si `python` no apunta al intérprete que quieres, usa el lanzador para elegir el Python 3 instalado:

```powershell
py -3 -m pip install -r requirements.txt
```

Esto instala las bibliotecas en el Python indicado. En Windows, si pip informa de falta de permisos para la instalación global, prueba:

```powershell
python -m pip install --user -r requirements.txt
```

Instala y ejecuta con el mismo intérprete: usa `python` en ambos casos, o `py -3` en ambos.

### Elegir Python en VS Code

1. Abre la carpeta del repositorio en VS Code.
2. Pulsa `Ctrl+Mayús+P` y ejecuta **Python: Select Interpreter**.
3. Elige el mismo Python 3.11 o posterior usado para instalar los paquetes. Si no aparece, selecciona **Enter interpreter path** e indica la ruta de `python.exe`.
4. Abre una terminal nueva en VS Code y ejecuta `python -c "import sys; print(sys.executable)"` para confirmar qué intérprete está usando.

### Comprobar la instalación

Desde la raíz del repositorio, ejecuta:

```powershell
python -c "import numpy, pandas, scipy, rasterio, skimage, cv2, sklearn, PIL, geopandas, shapely, pyproj, plotly, requests; print('Dependencias principales: OK')"
python -m pytest
```

El último comando ejecuta las pruebas disponibles. Si todavía no hay tests, pytest lo indicará con su código de salida habitual; eso no sustituye a crear pruebas cuando el proyecto empiece a tener código.

La primera versión de la aplicación, centrada en el reto básico, se ejecuta desde la raíz así:

```powershell
python app.py
```

En Windows puedes iniciarla con doble clic en [`encender_aplicacion.bat`](encender_aplicacion.bat), situado en la raíz del repositorio. El script usa el Python 3.11 o posterior seleccionado por el lanzador de Windows o disponible en `PATH`; no pide instalar una versión concreta. Si no encuentra Python, muestra un enlace de descarga y los comandos para instalarlo y sus dependencias. El lanzador abre la página local en el navegador. Si Lumbre ya está abierta, vuelve a abrir esa instancia en lugar de iniciar otro servidor. Para cerrarla desde otra ventana, ejecuta [`cerrar_aplicacion.bat`](cerrar_aplicacion.bat); también puedes pulsar `Ctrl+C` en la ventana del servidor. Si el servidor no responde, el cierre busca procesos Python asociados al `app.py` de esta copia y termina solo esos procesos.

Para desarrollar la interfaz React con recarga automática, abre dos terminales: en una inicia `python app.py --no-browser`; en la otra entra en `frontend/` y ejecuta `npm run dev`. Vite sirve la interfaz en `http://127.0.0.1:5173/` y reenvía `/api` al servidor Python local. Si el puerto 8501 está ocupado y Python anuncia otro puerto, configura `LUMBRE_API_TARGET` con esa dirección antes de arrancar Vite.

Se abre en el navegador. Permite elegir una escena precargada o subir una pareja True Color/SWIR. Las parejas precargadas se guardan en `imagenes/<nombre-de-escena>/`, una carpeta por escena con solo un archivo True Color y otro SWIR de la misma adquisición. La aplicación descubre esas carpetas al cargarse; admite JPEG, PNG y TIFF. El panel **Plano de análisis** alterna las composiciones, la superposición y la capa de candidatos/humo; también permite medir distancias y polígonos e inspeccionar píxeles. La herramienta **Regla** requiere introducir el GSD en metros por píxel y ejecutar el análisis; entonces muestra distancias en metros, ajustadas a la rejilla de trabajo. Si el resultado no incluye GSD, la regla queda deshabilitada en vez de presentar píxeles como distancia terrestre. El panel lateral resume área, perímetro, oclusión por humo y otros datos calculados, y ofrece descargas y notas temporales de campo. El progreso avanza al terminar etapas del algoritmo, no estima el tiempo restante. Las unidades métricas dependen de que el GSD introducido sea correcto; no se infiere la escala a partir del nombre o tamaño de un JPG.

### Detectores y tratamiento del humo

En **Detector de superficie** se puede comparar el K-Means conjunto (True Color + SWIR) con **Contraste SWIR + histéresis (V2)**. V2 busca semillas con contraste SWIR alto y crece por píxeles contiguos con evidencia menor; True Color contribuye a vetar agua probable y vegetación muy verde. Los dos detectores clasifican candidatos, no confirman por sí solos terreno quemado. El control **Grupos de color por escena** solo aplica a K-Means.

La aplicación estima humo probable con ambas composiciones alineadas: usa el núcleo cian de SWIR y lo amplía solo sobre velo muy liso, neutro y cercano al núcleo. El humo se conserva como capa de oclusión; en paralelo, el detector busca evidencia compatible con superficie afectada debajo. Esa hipótesis se muestra en fucsia y no se suma al área ni al perímetro observados. No reconstruye el terreno tapado: puede confundir humo con nubes o veladuras y no detecta fuego activo ni clasifica vegetación/suelo desnudo como clases separadas. Compara ambas vistas y revisa el resultado.

El filtro espacial prioriza por defecto el componente candidato más grande y puede descartar candidatos alejados. Si la escena puede contener focos independientes, activa **Conservar regiones desconectadas**; así se mantienen los componentes que superan el tamaño mínimo. Las coberturas mostradas son fracciones de píxeles candidatos, no una medida de precisión ni una estimación de fuego activo.

### Random Forest supervisado

El detector Random Forest aparece tras entrenar un modelo con máscaras revisadas por escena. Las instrucciones, IDs de clase y estructura del conjunto están en la [guía de entrenamiento](<training Random Forest/README.md>). El entrenamiento reserva escenas completas para evaluación, usa RGB renderizado y textura local, y mantiene separados fuego activo, área quemada, humo, agua, nube o bruma, suelo y vegetación. Las capturas de referencia no sustituyen máscaras alineadas; no se trata como validado hasta evaluar escenas independientes.

La interfaz React se desarrolla en `frontend/` y Vite compila el sitio estático en `web/`. El servidor Python local sirve la interfaz y la API de análisis; ejecuta los algoritmos, informa del progreso y entrega capas y exportaciones. Para usar la aplicación no hace falta abrir Vite ni desplegar nada: el lanzador inicia un único servidor local y una sola pestaña.

La aplicación y sus resultados usan una rejilla común de píxeles con origen arriba a la izquierda. Máscaras, marcas manuales y capas auxiliares deben compartir esa rejilla; para combinar en el futuro capas meteorológicas o geográficas será necesario transformarlas/alinearlas a la imagen y conservar su CRS y transformación geográfica. El GSD basta para mediciones métricas locales, pero no para obtener latitud/longitud. Los pasos del algoritmo y sus límites se explican en [`DOCUMENTACION/Ideas/segmentacion_basica.md`](DOCUMENTACION/Ideas/segmentacion_basica.md).

### Servicios de datos externos

- **Copernicus Data Space Browser**: [dataspace.copernicus.eu/browser](https://dataspace.copernicus.eu/browser/). Crear una cuenta gratuita y verificar el correo para buscar, visualizar y descargar productos. El acceso programático a ciertas APIs puede requerir credenciales propias.
- **Open-Meteo Historical Weather API**: [documentación](https://open-meteo.com/en/docs/historical-weather-api). Las consultas públicas no comerciales normalmente no requieren cuenta ni clave; las funciones comerciales reservadas requieren clave. Hay que respetar las condiciones de uso y citar la fuente.
- **IGN/CNIG**: [Centro de Descargas](https://centrodedescargas.cnig.es/CentroDescargas/). Los datos son gratuitos; una cuenta permite descargas ilimitadas y consultar el historial. Para consultas o descargas puntuales, comprobad los requisitos de cada producto.
- **Google Earth Engine**, previsto para una fase posterior: requiere una cuenta de Google, un proyecto de Google Cloud registrado para Earth Engine, permisos y autenticación. El acceso no comercial requiere registrar y acreditar el uso no comercial; el uso comercial necesita la configuración y plan comercial correspondientes. No se instala en este entorno inicial.

Para cada fuente se deben guardar fecha, resolución, licencia y procedencia de los datos. Las reconstrucciones meteorológicas y las capas de vegetación son estimaciones/contexto, no mediciones exactas del incendio.


### Segmentación contextual híbrida (experimental)

El nuevo modo conserva V2 como fuente semántica y añade SLIC conjunto, estadísticas regionales, un grafo de adyacencia (RAG), crecimiento limitado y Watershed local con marcadores y fallback. Sigue disponible K-Means, V2 y fusión; K-Means continúa como predeterminado. No modifica entrenamiento, etiquetas ni modelos Random Forest.

El híbrido analiza hasta 2500 píxeles de lado (La Mierla y Niebla conservan su resolución original), frente a 1800 en los modos anteriores. El esfuerzo espacial se concentra en recortes alrededor de **todos** los candidatos con margen de 24 píxeles, conservando cicatrices independientes. No se descarta una cicatriz por estar lejos de la principal. El motor semántico sigue examinando la escena completa: el recorte no recupera regiones que el clasificador omita.

La máscara visible conserva huecos y veta agua/humo. El humo es independiente de la hipótesis fucsia; la trama gris indica suelo desconocido bajo humo. Las hipótesis espectrales y de continuidad corta se exportan separadas en **Capas de humo y diagnóstico** y nunca se suman al área observada. Una columna extensa puede quedar sin inferencia; la menor superficie fucsia es una política de abstención, no prueba de mejor detección. Las distancias son píxeles de trabajo y el área solo es métrica con GSD fiable.

Ver [evaluación, parámetros y límites](DOCUMENTACION/Ideas/segmentacion_contextual_evaluacion.md). No se ha demostrado una mejora de exactitud con máscaras de referencia reales; el modo permanece experimental.

Comprobaciones y artefactos reproducibles (sin dependencias nuevas):

```powershell
python -m pytest tests -q
python scripts/comparar_contextual.py --fase baseline
python scripts/comparar_contextual.py --fase contextual_roi
python scripts/evaluar_humo_sintetico.py
# Con python app.py --no-browser ya iniciado:
python scripts/verificar_http_contextual.py --url http://127.0.0.1:8501
```

Las comparaciones controladas usan 1800 de lado en todos los métodos; la verificación HTTP usa la resolución real del modo (2500). Los resultados se guardan en `resultados_contextual/` (excluida de Git). El baseline histórico de esta intervención se guardó antes de corregir la geometría; volver a ejecutar `--fase baseline` lo sustituye por el comportamiento actual. No compares recuentos de píxeles de rejillas distintas como si fueran cambios de superficie.
