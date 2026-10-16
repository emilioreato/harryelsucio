# Imágenes de referencia y validación

Investigación archivada del 15/10/2026. Los enlaces son puntos de partida; no se ha actualizado aquí la disponibilidad de los portales ni se han descargado nuevos perímetros.

## Material del repositorio

Hay ocho parejas True Color/SWIR: La Mierla, Madrid–Ávila, Niebla y cinco escenas de prueba, identificadas como `test1` a `test5`. Las parejas están en `imagenes_muestra/`; las copias exactas que estaban en `DOCUMENTACION/Presentacion reto/` se quitaron para mantener una sola fuente. La carpeta de presentación conserva los enunciados y las referencias `Wildfires` disponibles.

Los nombres de archivo no prueban el producto Sentinel-2, la hora de adquisición, la resolución ni el renderizado. `Wildfires` es una composición de visualización, no una máscara validada. El repositorio no contiene etiquetas externas independientes de superficie quemada.

## Fuentes para buscar referencias

- **Copernicus EMS Rapid Mapping:** activaciones [EMSR898, La Mierla](https://mapping.emergency.copernicus.eu/activations/EMSR898/), [EMSR900, España central](https://mapping.emergency.copernicus.eu/activations/EMSR900/) y [EMSR913, Huelva](https://mapping.emergency.copernicus.eu/activations/EMSR913/). Revisar AOI, versión y fecha de adquisición del producto antes de comparar.
- **EFFIS:** [datos y servicios](https://forest-fire.emergency.copernicus.eu/applications/data-and-services). Los perímetros sirven como referencia geográfica de escala, pero su resolución y fecha no equivalen a etiquetas perfectas por píxel.
- **NASA FIRMS:** [fuegos activos](https://firms.modaps.eosdis.nasa.gov/active_fire) y [archivo histórico](https://firms.modaps.eosdis.nasa.gov/download/). Detecciones MODIS/VIIRS son un contraste de proximidad; no se deben rasterizar como verdad a 10–20 m.
- **Copernicus Browser:** [catálogo](https://browser.dataspace.copernicus.eu/) y [manual](https://documentation.dataspace.copernicus.eu/Applications/Browser.html). Registrar ID de producto, hora UTC, tesela, nubes, bandas, área exportada y parámetros de visualización.
- Contexto de escenas: [ESA, Madrid–Ávila 26/07](https://www.esa.int/ESA_Multimedia/Images/2026/07/Raging_wildfires_near_Madrid_Spain), [cartografía de La Mierla](https://cartografia.castillalamancha.es/noticias/el-sistema-copernicus-proporciona-imagenes-y-cartografia-del-incendio-de-la-mierla-para) y [activación EMSR913](https://mapping.emergency.copernicus.eu/news/wildfire-in-huelva-spain-emsr913/).

## Protocolo mínimo

1. Buscar la misma adquisición y extensión; una fecha coincidente no garantiza el mismo producto.
2. Alinear la referencia mediante CRS y transformación geográfica, no con `resize()`.
3. Comparar superficie quemada con perímetros de fecha compatible; comparar focos activos por proximidad y hora; revisar humo visualmente hasta tener anotaciones independientes.
4. Separar entrenamiento y evaluación por incendio/adquisición. Guardar fuente, licencia, fecha, resolución, CRS, producto y procedencia de cada máscara.

Un desfase temporal, una referencia derivada de la misma imagen o una composición `Wildfires` puede sesgar la evaluación. Informar IoU, precisión, recall y F1 solo después de alinear la rejilla y explicar esas limitaciones.
