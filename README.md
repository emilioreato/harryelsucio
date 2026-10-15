# harryelsucio

Proyecto harryelsucio para el análisis y la segmentación de imágenes satelitales de incendios. La orientación técnica y los supuestos iniciales están en [`DOCUMENTACION/Ideas/inicial.md`](DOCUMENTACION/Ideas/inicial.md).

## Preparación del entorno de desarrollo

### Programas

- **Python 3.12 (64 bits)**, recomendado; Python 3.11 también es válido. En Windows, instala Python desde [python.org](https://www.python.org/downloads/windows/) y activa la opción para añadir Python al `PATH`. No hace falta Conda, crear entornos virtuales ni usar Docker.
- **Visual Studio Code**, junto con **Git for Windows** ([descarga oficial](https://git-scm.com/download/win)).
- **QGIS LTR**, para inspeccionar rásteres, CRS, bandas, relieve y superposiciones ([descarga oficial para Windows](https://qgis.org/download/)). No es necesario configurar el Python interno de QGIS ni usarlo para ejecutar este proyecto.

En VS Code conviene instalar las extensiones oficiales **Python** (Microsoft) y **Pylance** (Microsoft). **Jupyter** es opcional si se van a usar notebooks.

### Instalar las dependencias

Abre una terminal de PowerShell en la carpeta del repositorio y ejecuta:

```powershell
python -m pip install -r requirements.txt
```

Si `python` no encuentra Python o selecciona otra versión, usa el lanzador de Windows con la versión explícita:

```powershell
py -3.12 -m pip install -r requirements.txt
```

Esto instala las bibliotecas en el Python indicado. En Windows, si pip informa de falta de permisos para la instalación global, prueba:

```powershell
python -m pip install --user -r requirements.txt
```

No mezcles `python` y `py -3.12` entre instalación y ejecución: deben apuntar al mismo intérprete.

### Elegir Python en VS Code

1. Abre la carpeta del repositorio en VS Code.
2. Pulsa `Ctrl+Mayús+P` y ejecuta **Python: Select Interpreter**.
3. Elige Python 3.12, o Python 3.11 si esa es la versión usada para instalar los paquetes. Si no aparece, selecciona **Enter interpreter path** e indica la ruta de `python.exe`.
4. Abre una terminal nueva en VS Code y ejecuta `python -c "import sys; print(sys.executable)"` para confirmar qué intérprete está usando.

### Comprobar la instalación

Desde la raíz del repositorio, ejecuta:

```powershell
python -c "import numpy, pandas, scipy, rasterio, skimage, cv2, sklearn, PIL, geopandas, shapely, pyproj, streamlit, plotly, requests; print('Dependencias principales: OK')"
python -m streamlit --version
python -m pytest
```

El último comando ejecuta las pruebas disponibles. Si todavía no hay tests, pytest lo indicará con su código de salida habitual; eso no sustituye a crear pruebas cuando el proyecto empiece a tener código.

La primera versión de la aplicación, centrada en el reto básico, se ejecuta desde la raíz así:

```powershell
python -m streamlit run app.py
```

Permite elegir una escena de ejemplo o cargar una pareja alineada True Color/SWIR. El diseño de módulos, algoritmo y sus supuestos se explican en [`DOCUMENTACION/Ideas/segmentacion_basica.md`](DOCUMENTACION/Ideas/segmentacion_basica.md).

### Servicios de datos externos

- **Copernicus Data Space Browser**: [dataspace.copernicus.eu/browser](https://dataspace.copernicus.eu/browser/). Crear una cuenta gratuita y verificar el correo para buscar, visualizar y descargar productos. El acceso programático a ciertas APIs puede requerir credenciales propias.
- **Open-Meteo Historical Weather API**: [documentación](https://open-meteo.com/en/docs/historical-weather-api). Las consultas públicas no comerciales normalmente no requieren cuenta ni clave; las funciones comerciales reservadas requieren clave. Hay que respetar las condiciones de uso y citar la fuente.
- **IGN/CNIG**: [Centro de Descargas](https://centrodedescargas.cnig.es/CentroDescargas/). Los datos son gratuitos; una cuenta permite descargas ilimitadas y consultar el historial. Para consultas o descargas puntuales, comprobad los requisitos de cada producto.
- **Google Earth Engine**, previsto para una fase posterior: requiere una cuenta de Google, un proyecto de Google Cloud registrado para Earth Engine, permisos y autenticación. El acceso no comercial requiere registrar y acreditar el uso no comercial; el uso comercial necesita la configuración y plan comercial correspondientes. No se instala en este entorno inicial.

Para cada fuente se deben guardar fecha, resolución, licencia y procedencia de los datos. Las reconstrucciones meteorológicas y las capas de vegetación son estimaciones/contexto, no mediciones exactas del incendio.
