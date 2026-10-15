# Propuesta inicial: área afectada y perímetro

## Qué pide el reto básico

El PDF del reto define como básico identificar la región con evidencias de haber sido afectada por el incendio y representar su perímetro sobre una imagen original. La detección de zonas con posible fuego activo es el reto avanzado. Este MVP aborda únicamente la superficie candidata a afectada; no etiqueta llamas ni puntos calientes.

## Qué información tenemos realmente

Los ficheros disponibles son JPEG RGB de las composiciones True Color y SWIR, con la misma anchura y altura por pareja. No incluyen el raster multibanda original, metadatos de CRS/transformada, escalas radiométricas ni la asignación documentada de las bandas SWIR a los tres canales del JPEG. El reto indica que ambas imágenes son de la misma adquisición; por ello, la diferencia de color entre ambas composiciones **no es un cambio temporal**.

Sentinel-2 MSI mide radiación reflejada en trece bandas, no temperatura de llama. En la composición True Color estándar, los canales RGB suelen asignarse a B04/B03/B02. Como referencia física, B2 (azul, 490 nm) corresponde a unos 612 THz; B3 (verde, 560 nm), 535 THz; B4 (rojo, 665 nm), 451 THz. Las bandas SWIR B11 (1610 nm) y B12 (2190 nm) corresponden aproximadamente a 186 y 137 THz. B11/B12 son sensibles a propiedades de humedad y materiales de la superficie, mientras que visible/NIR aportan otras respuestas de vegetación y suelo. Las bandas SWIR de Sentinel-2 tienen 20 m de resolución nominal, frente a 10 m para las bandas RGB visibles.

Esos números describen las bandas del sensor, **no se pueden recuperar con certeza de estos JPEG**. Un color rojo en la composición SWIR es un color elegido para visualizar valores de canal; no es luz roja que el sensor haya medido en esa longitud de onda. Sentinel-2 no tiene banda térmica, y esta aplicación no deduce temperatura ni fuego activo.

## Diseño modular

- `app.py` contiene la interfaz Streamlit y la selección/carga de escenas.
- `pyroscope/imagenes.py` lee imágenes RGB, valida que la pareja comparta dimensiones y reduce ambas con el mismo factor.
- `pyroscope/caracteristicas.py` calcula las señales por píxel de las dos composiciones.
- `pyroscope/segmentacion.py` estima únicamente el área afectada y devuelve su máscara, contornos y métricas en píxeles (`ResultadoAreaAfectada`).
- `pyroscope/visualizacion.py` pinta la máscara y el perímetro sobre True Color.

Esta separación mantiene el área afectada como resultado propio. En una fase avanzada, el detector de actividad de fuego debe ser otro módulo con su propia máscara/puntuación; los focos activos no se deben sumar al área quemada ni tratar como la misma clase.

## Algoritmo del MVP

1. Carga una pareja RGB ya alineada y comprueba que sus dimensiones coinciden. Si no coinciden, falla con un mensaje claro: no inventa una alineación mediante `resize`.
2. Reduce ambas composiciones con el mismo factor para que la imagen grande de Madrid-Ávila se pueda analizar con rapidez.
3. Para cada posición calcula seis características **conjuntas**: predominio rojizo, cromaticidad y luminancia SWIR; predominio verde, luminancia y cromaticidad True Color. Cada vector de píxel contiene señales de las dos imágenes.
4. Estandariza las señales con estadísticas robustas de la escena y ajusta `MiniBatchKMeans` sobre vectores conjuntos. Ordena los grupos con una puntuación que combina el predominio rojizo SWIR con el verdor, luminancia y cromaticidad True Color, además de una guarda contra zonas muy oscuras. La decisión no se calcula ejecutando dos segmentadores independientes ni mirando una sola imagen.
5. Permite ampliar o estrechar la selección con sensibilidad; limpia puntos pequeños y bordes de un píxel mediante operaciones morfológicas y componentes conectados.
6. Toma la mayor región candidata como foco principal y descarta componentes desconectados cuya distancia mínima supere un radio relativo al tamaño de la imagen. La interfaz permite ajustar ese radio. Así reduce falsos candidatos cromáticos lejanos, manteniendo manchas próximas del mismo incendio aunque las separe una zona de humo o píxeles omitidos.
7. Pinta una máscara translúcida y el contorno estimado sobre True Color. Permite descargar la vista y la máscara como PNG.

No se fijan umbrales de reflectancia: los histogramas de un JPEG dependen de la composición, el estiramiento de visualización y la compresión. El agrupamiento se reajusta para cada escena y la sensibilidad deja que el equipo revise el compromiso entre omisiones y falsos positivos.

## Confusores y límites

- Vegetación densa suele separarse por el verdor visible y su respuesta relativa en la composición SWIR. El agua suele tener poca señal en SWIR y se excluye parcialmente por oscuridad.
- Suelo desnudo, canteras, zonas urbanas, sombras y superficies previamente quemadas pueden tener colores parecidos al incendio. El clasificador no puede probar por sí solo que el suelo haya cambiado debido a este episodio.
- El filtro espacial asume un incendio principal. Si hay varios incendios independientes en el mismo encuadre, el radio debe ampliarse o el análisis debe ejecutarse por separado; no convierte por sí solo una clase de color en prueba de incendio.
- El humo oculta el terreno. La composición SWIR ayuda a verlo con color distinto en los ejemplos, pero el sistema no tiene una máscara fiable de humo y no puede reconstruir lo oculto.
- La imagen `Wildfires` del repositorio resalta puntos/frentes activos; no se usa para segmentar el área afectada ni equivale a una verdad terreno de superficie quemada.
- No se calcula NBR: hacen falta los valores originales B08 y B12, no los canales RGB de una imagen SWIR renderizada. Tampoco se calculan hectáreas o coordenadas: los JPEG no tienen georreferenciación disponible.
- La máscara es una propuesta de visión por computador para revisión humana. Hay que validarla con una delimitación independiente en escenas de entrenamiento y reservar otras escenas para medir IoU, precision, recall y F1.

## Referencias espectrales

- [Manual de usuario Sentinel-2 de ESA](https://sentinels.copernicus.eu/documents/247904/685211/Sentinel-2_User_Handbook): bandas, longitudes de onda y resoluciones del instrumento MSI.
- [Ejemplo oficial True Color Sentinel-2 L2A](https://docs.sentinel-hub.com/api/latest/data/sentinel-2-l2a/examples/): asignación RGB habitual B04/B03/B02.

## Ejecutar

Desde la raíz del repositorio:

```powershell
python -m streamlit run app.py
```

Selecciona una de las escenas de ejemplo o carga tu propia pareja True Color/SWIR. Comprueba el perímetro sobre ambas composiciones y ajusta la sensibilidad antes de guardar la superposición.
