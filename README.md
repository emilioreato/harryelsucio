# Maracatón 2026

Lumbre es una aplicación local para revisar escenas satelitales de incendios. Analiza una pareja de composiciones True Color y SWIR, muestra capas de diagnóstico y permite exportar resultados. El backend procesa las imágenes en el ordenador; la interfaz funciona en el navegador.

## Origen del proyecto

Lumbre nació como prototipo para el reto de **Indra Espacio** en el III Malackathon 2026, desarrollado por cuatro estudiantes de primer curso de la UMA. La [historia del proyecto](DOCUMENTACION/historia_del_proyecto.md) reúne el objetivo, la composición del equipo y la evolución técnica; completaremos allí la cronología cuando quede recogido el relato de las jornadas.

## Instalación e inicio

Se necesita CPython estable de 64 bits, versión 3.11 o posterior. Python 3.14 es una opción actual; el lanzador no queda atado a Python 3.12. Los paquetes se instalan desde ruedas binarias compatibles, sin exigir compiladores. El instalador rechaza versiones preliminares y entornos Conda/venv para evitar instalar en un Python distinto del que luego usa la app.

En Windows, instala Python desde [python.org](https://www.python.org/downloads/windows/) si aún no está instalado; activa **Python Launcher** y **Add Python to PATH**. Desde la raíz del repositorio, ejecuta `01_instalar_lumbre.bat` una vez y luego `02_iniciar_lumbre.bat` para abrir la aplicación. `03_acceso_movil.bat` configura el acceso opcional desde el teléfono y `04_cerrar_lumbre.bat` cierra Lumbre. El instalador detecta un Python compatible, comprueba pip e instala las dependencias desde el único `requirements.txt` en el perfil del usuario. No modifica PATH ni requiere permisos de administrador. Si falla, conserva la ventana abierta con el error.

En macOS o Linux, desde la raíz del repositorio:

```sh
python3 -m pip install --user -r requirements.txt
python3 -m lumbre
```

El paquete web ya está incluido; Node.js solo hace falta para desarrollar la interfaz. Para cerrar Lumbre, usa `04_cerrar_lumbre.bat` en Windows o pulsa `Ctrl+C` en la ventana del servidor.

## Uso

Elige una escena precargada o carga imágenes propias. Lumbre permite comparar composiciones, revisar la segmentación y sus capas de humo, ver focos cuando hay una imagen Wildfires disponible, medir sobre la rejilla de análisis y descargar resultados. La documentación explica [el flujo, los detectores y sus límites](DOCUMENTACION/Ideas/README.md).

Las capas de una ejecución se mantienen en memoria y se descartan al cerrar Lumbre. No se guardan imágenes automáticamente: usa las acciones de exportación para descargar al ordenador solo las que quieras conservar.

En el visor, **Anotar** permite dibujar a mano, añadir líneas, flechas, rectángulos, elipses y textos sobre la imagen. El botón circular junto a **Guardar resultado** descarga un ZIP con las entradas True Color/SWIR preparadas en la misma rejilla, las capas y máscaras semánticas disponibles, bordes, parámetros, métricas y un mapa anotado. Incluye las anotaciones por separado en JSON y SVG para que otra herramienta pueda leerlas y alinearlas por coordenadas de píxel. El paquete registra GSD y rejilla cuando están disponibles; no inventa CRS ni reproyecta imágenes desalineadas.

Las escenas precargadas están en `imagenes_muestra/`, con una carpeta por caso y una imagen True Color y otra SWIR. Ambas deben corresponder a la misma adquisición y estar alineadas. Para cargas propias se admiten JPG, PNG y TIFF. Tener el mismo ancho y alto no demuestra que dos imágenes estén alineadas geográficamente.

Los resultados son candidatos para revisión, no confirmaciones de superficie quemada o fuego activo. Las ocho escenas precargadas usan una escala de catálogo de 10 m/píxel, aplicada automáticamente y ajustada a la rejilla de análisis; no se solicita al usuario. Las parejas propias sin escala conocida se miden en píxeles. Las composiciones JPEG/PNG no conservan necesariamente las bandas originales, la reflectancia ni la georreferenciación, así que esa escala es nominal y no crea coordenadas terrestres. Lumbre no calcula NBR/dNBR a partir de esos renderizados. La máscara de humo representa oclusión probable; una hipótesis de terreno bajo humo se mantiene separada del área observada. `Wildfires` sirve para extraer marcas visuales de focos, pero no es verdad terreno ni mide temperatura.

## Acceso móvil opcional

El acceso desde un teléfono está desactivado por defecto. Para activarlo o desactivarlo, ejecuta `03_acceso_movil.bat` desde la raíz y elige una opción; después inicia o reinicia Lumbre. La preferencia se guarda localmente en `.lumbre/` y no se sube al repositorio.

Al activarlo, el servidor escucha también en la red local y muestra un QR en el panel izquierdo. No se cambian el firewall ni el router; Windows podría pedir permiso para conexiones entrantes y, si se bloquean, el teléfono no podrá conectarse. Los dispositivos de la misma red podrían alcanzar la aplicación si el firewall lo permite, así que úsalo solo en una Wi‑Fi privada de confianza. No configures redirección de puertos ni lo expongas a Internet.

## Diseño adaptable a pantallas estrechas

La interfaz cambia automáticamente su distribución cuando el navegador se hace estrecho o vertical. Para comprobarlo en el portátil, reduce el ancho de la ventana o usa las herramientas de diseño adaptable del navegador. Esto funciona aunque el acceso móvil esté desactivado.

## Desarrollo

### Ramas y clones

`main` es la única rama activa y la fuente de verdad del proyecto. Las otras ramas remotas se conservan por su valor histórico; no contienen trabajo vigente ni deben usarse como base salvo que alguien lo pida expresamente.

Para obtener únicamente la rama activa en una copia nueva:

```sh
git clone --single-branch --branch main https://github.com/emilioreato/malackathon2026.git
```

Un `git clone` normal también descarga las referencias de las demás ramas y los objetos que solo existen en ellas. La opción `--single-branch` evita ese contenido histórico en las copias nuevas, sin borrar las ramas del remoto.

Para ejecutar las pruebas disponibles, instala las dependencias del proyecto y luego ejecuta pytest:

```sh
python -m pip install --user -r requirements.txt
python -m pytest -c tests/pytest.ini tests
```

Las pruebas que generan imágenes o archivos deben escribirlos en `tmp_path`; pytest los elimina al finalizar. Para inspeccionar una salida manual entre procesos, usa `.tmp/pruebas/<nombre-de-la-prueba>/` (ignorada por Git), nunca `resultados/`. Los scripts de evaluación limpian su carpeta temporal automáticamente por defecto; si necesitas conservar una ejecución, pásales `--salida .tmp/pruebas/<nombre-de-la-prueba>`. Solo los resultados elegidos para conservar a largo plazo van en `resultados/guardados/<nombre-descriptivo>/`, acompañados de sus parámetros y procedencia.

La interfaz React/Vite está en `frontend/`; el paquete estático servido por la app se guarda en `web/`. Para desarrollarla, inicia el backend con `python -m lumbre --no-browser` y, en otra terminal:

```sh
cd frontend
npm ci
npm run dev
```

Vite usa Node.js `^20.19.0` o `>=22.12.0` (Node 22 reciente es una opción sencilla). Para regenerar el paquete de producción, ejecuta `npm run build` en `frontend/`. Si el backend usa otro puerto, configura `LUMBRE_API_TARGET` con su URL.

`requirements.txt` es el único archivo de dependencias e incluye pytest para que la instalación de desarrollo y la de uso no se contradigan. Para entrenar el detector Random Forest, preparar etiquetas y consultar las limitaciones, sigue la [guía de entrenamiento](<training/random_forest/README.md>); el repositorio no incluye un modelo entrenado.

## Estructura del proyecto

- Los accesos numerados de Windows para instalar, iniciar, configurar el móvil y cerrar Lumbre están en la raíz del repositorio.
- `lumbre/` contiene el backend Python; `python -m lumbre` lo inicia.
- `frontend/` contiene la interfaz editable y `web/` su versión servida por el backend.
- `imagenes_muestra/` contiene escenas de ejemplo.
- `training/random_forest/` reúne la guía y referencias para preparar datos de entrenamiento.
- `resultados/` contiene informes y resultados seleccionados para conservar; consulta su [política de almacenamiento](resultados/README.md).
- `scripts/` contiene herramientas de evaluación y el auxiliar de cierre de Windows.

El estado de ejecución se guarda en `.lumbre/` y se excluye de Git. La configuración de pytest está dentro de `tests/` para mantener las herramientas de desarrollo fuera de la vista inicial.

## Documentación

- [Índice de documentación](DOCUMENTACION/README.md)
- [Ideas, decisiones y evolución](DOCUMENTACION/Ideas/README.md)
- [Imágenes y escenas de prueba](imagenes_muestra/README.md)
- [Guía de entrenamiento Random Forest](<training/random_forest/README.md>)
