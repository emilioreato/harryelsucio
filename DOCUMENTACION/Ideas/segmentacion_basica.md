# Propuesta inicial: área afectada y perímetro

## Qué pide el reto básico

El PDF del reto define como básico identificar la región con evidencias de haber sido afectada por el incendio y representar su perímetro sobre una imagen original. La detección de zonas con posible fuego activo es el reto avanzado. Este MVP aborda únicamente la superficie candidata a afectada; no etiqueta llamas ni puntos calientes.

## Qué información tenemos realmente

Los ficheros disponibles son JPEG RGB de las composiciones True Color y SWIR, con la misma anchura y altura por pareja. No incluyen el raster multibanda original, metadatos de CRS/transformada, escalas radiométricas ni la asignación documentada de las bandas SWIR a los tres canales del JPEG. El reto indica que ambas imágenes son de la misma adquisición; por ello, la diferencia de color entre ambas composiciones **no es un cambio temporal**.

Sentinel-2 MSI mide radiación reflejada en trece bandas, no temperatura de llama. En la composición True Color estándar, los canales RGB suelen asignarse a B04/B03/B02. Como referencia física, B2 (azul, 490 nm) corresponde a unos 612 THz; B3 (verde, 560 nm), 535 THz; B4 (rojo, 665 nm), 451 THz. Las bandas SWIR B11 (1610 nm) y B12 (2190 nm) corresponden aproximadamente a 186 y 137 THz. B11/B12 son sensibles a propiedades de humedad y materiales de la superficie, mientras que visible/NIR aportan otras respuestas de vegetación y suelo. Las bandas SWIR de Sentinel-2 tienen 20 m de resolución nominal, frente a 10 m para las bandas RGB visibles.

Esos números describen las bandas del sensor, **no se pueden recuperar con certeza de estos JPEG**. Un color rojo en la composición SWIR es un color elegido para visualizar valores de canal; no es luz roja que el sensor haya medido en esa longitud de onda. Sentinel-2 no tiene banda térmica, y esta aplicación no deduce temperatura ni fuego activo.

## Diseño

- La interfaz permite seleccionar una escena o cargar una pareja de imágenes, configurar el análisis y revisar el progreso.
- El backend valida y alinea la pareja, calcula señales, clasifica píxeles y forma regiones espaciales.
- Los resultados incluyen máscara, contorno, medidas y exportaciones. Las capas conservan la misma rejilla de píxeles.
- El detector de humo se aplica antes de clasificar el terreno y marca zonas de visibilidad dudosa.
- Los detectores de superficie se pueden intercambiar; la formación de regiones y las mediciones usan contratos compartidos.

Al ampliar la aplicación, conserva el recorrido `entrada → procesamiento → mediciones/resultados` y las reglas del motor fuera de la página web. Añade un detector registrable para otra estrategia semántica; reserva un contrato y una etapa propios para la futura detección de fuego activo, porque no es la misma salida que la superficie afectada.

Esta separación mantiene el área afectada como resultado propio. En una fase avanzada, el detector de actividad de fuego debe ser otro módulo con su propia máscara/puntuación; los focos activos no se deben sumar al área quemada ni tratar como la misma clase.

## Dos problemas distintos: semántica y geometría

La solución combina dos etapas, porque cada una responde a una pregunta diferente:

1. **Observabilidad y clasificación semántica (qué se ve y qué evidencia representa).** Primero `detectar_humo_probable` obtiene un núcleo con la firma cian/azulada de SWIR y luminosidad/neutralidad de True Color. Después amplía el núcleo sobre velo claro y neutro con textura local muy baja, solo dentro de componentes conectados y una distancia máxima al núcleo. El límite reduce la propagación a campos claros lejanos, aunque puede dejar partes tenues del penacho fuera. El usuario puede elegir entre K-Means, que agrupa señales de ambas imágenes, y V2, que usa un doble umbral SWIR con crecimiento por histéresis; True Color aporta contexto para vetar agua posible y vegetación muy verde. En ambos casos se aparta antes el humo probable. Los píxeles bajo esa máscara quedan indeterminados y no reciben el mismo criterio cromático que el terreno despejado.
2. **Segmentación espacial (qué píxeles forman una región).** `segmentar_regiones_espaciales` aplica limpieza morfológica, tamaño mínimo, componentes conectados y distancia al foco principal. Así elimina puntos aislados y manchas remotas sin cambiar el significado espectral de la primera etapa.

La máscara semántica previa queda disponible en `ResultadoAreaAfectada.mascara_clasificada`, el humo en `mascara_humo` y la confianza visual en `confianza_humo`; `mascara` es el resultado espacial final. El mapa `clase_por_pixel` asigna agua posible, superficie candidata y humo probable; el resto queda indeterminado. La ontología reserva vegetación y posible fuego activo, pero la primera versión no los clasifica. En una fase avanzada el detector de fuego activo tendrá sus propias máscaras/puntuaciones y no se sumará a la superficie afectada.

## Ontología y política de humo

| Clase/capa | Significado actual |
|---|---|
| Humo probable | Capa atmosférica estimada con las dos composiciones; implica visibilidad degradada, no una clase de superficie. |
| Agua posible | Señal auxiliar conservadora para reducir falsos positivos; no equivale a un inventario validado de masas de agua. |
| Superficie afectada candidata | Evidencia cromática compatible con el reto básico; puede incluir suelo desnudo u otras cubiertas parecidas. |
| Vegetación | Clase prevista; el verdor de un JPEG solo puede ser relativo al render y no es NDVI ni una medida física. |
| Posible fuego activo | Clase reservada para el reto avanzado; este flujo no la detecta ni estima temperatura. |
| Indeterminado | No hay evidencia suficiente o la superficie está ocluida. |

El humo se trata primero porque es una capa delante del terreno: cuando oculta el suelo, la clase de la superficie bajo él no es observable de forma directa. En las parejas de ejemplo la composición SWIR muestra humo con tonos cian/azulados y las cicatrices con otros colores; NASA describe un caso donde una composición visible+NIR+SWIR muestra la cicatriz bajo humo y representa el humo en azul claro ([NASA Earth Observatory](https://science.nasa.gov/earth/earth-observatory/seeing-through-smoke-79233/)). Eso justifica usar la firma de ambas vistas, pero **no** permite asumir que cualquier SWIR atraviesa todo humo ni que el código RGB del JPEG corresponda a una banda concreta.

La máscara es un candidato visual, no una máscara atmosférica calibrada. Los píxeles cubiertos se excluyen del ajuste de K-Means y del crecimiento de V2; quedan indeterminados y se dibujan en cian en la vista. El núcleo SWIR se prolonga por velo contiguo con baja textura local para recuperar partes grises o tenues; aun así puede dejar huecos o confundir humo con nubes/veladuras. No se interpola terreno oculto ni se corrigen colores SWIR sin reflectancias originales, asignación de bandas, información de calidad atmosférica y ejemplos anotados.

## Algoritmo del MVP

1. Carga una pareja RGB ya alineada y comprueba que sus dimensiones coinciden. Si no coinciden, falla con un mensaje claro: no inventa una alineación mediante `resize`.
2. Reduce ambas composiciones con el mismo factor para que la imagen grande de Madrid-Ávila se pueda analizar con rapidez.
3. **Etapa de observabilidad:** detecta el núcleo con el patrón cian relativo de SWIR y lo amplía solo sobre regiones conectadas de True Color claras, neutras y muy lisas, dentro de un radio máximo respecto al núcleo. Los umbrales se adaptan a la escena. La salida es una máscara de humo probable con puntuación de confianza visual.
4. **Etapa semántica:** con K-Means, calcula ocho características conjuntas, estandariza con estadísticas robustas de píxeles despejados y ajusta `MiniBatchKMeans`; la puntuación por grupo combina señales SWIR y contexto True Color. La alternativa V2 calcula umbrales adaptados a la escena para la evidencia SWIR, marca semillas de evidencia alta y las expande por componentes contiguos que superan umbrales más bajos. True Color aporta vetos conservadores de posible agua y vegetación muy verde. Los dos métodos excluyen la máscara de humo probable y devuelven candidatos, no etiquetas confirmadas.
5. **Etapa espacial:** aplica morfología y componentes conectados para quitar ruido, y vuelve a retirar agua y humo para que la limpieza no pinte lagos ni reclasifique humo como terreno. Descarta componentes menores al tamaño mínimo. Por defecto toma el componente mayor como ancla y filtra candidatos remotos; la opción **Conservar regiones desconectadas** mantiene los demás componentes que superen el tamaño mínimo, para escenas con focos independientes.
6. Dibuja la superficie candidata y el contorno sobre True Color, además de la máscara de humo probable. Las máscaras semánticas y espaciales quedan disponibles para comparación y descarga.

No se fijan umbrales de reflectancia: los histogramas de un JPEG dependen de la composición, el estiramiento de visualización y la compresión. El agrupamiento se reajusta para cada escena y la sensibilidad deja que el equipo revise el compromiso entre omisiones y falsos positivos.

## Rejilla de imagen, GSD y mediciones web

Cada punto, máscara y futura capa auxiliar vive en `SistemaCoordenadasImagen`: una rejilla con anchura/altura, origen en la esquina superior izquierda y ejes de píxel hacia la derecha y hacia abajo. `CapaImagen` exige que sus datos tengan las mismas dimensiones. Antes de combinar datos meteorológicos o cartográficos habrá que alinearlos o remuestrearlos a esta rejilla; igualdad de dimensiones por sí sola no demuestra que dos fuentes estén geográficamente alineadas. Con una imagen georreferenciada, `coordenadas_crs_a_pixel` permite proyectar puntos de otra fuente al CRS de la imagen y llevarlos a la misma rejilla.

La interfaz web permite medir distancias y dibujar polígonos sobre la rejilla de análisis. La herramienta **Regla** solo se habilita cuando se proporciona un GSD en metros por píxel y se ejecuta el análisis; calcula la distancia en metros usando el GSD ajustado a la rejilla reducida. Sin GSD no presenta una distancia en píxeles como si fuera métrica y la regla queda deshabilitada. Los perímetros y áreas también usan unidades métricas cuando el resultado incluye GSD; sin escala, se expresan en píxeles.

GSD (*Ground Sampling Distance*) es la distancia sobre el terreno entre centros de píxeles adyacentes. No debe adivinarse a partir del tamaño de un JPEG: depende del producto, la banda y el remuestreo aplicado al exportar. Sentinel-2 tiene bandas con resolución espacial nominal de 10, 20 y 60 m; las bandas SWIR B11/B12 son de 20 m, mientras que las bandas visibles B2/B3/B4 son de 10 m. Algunas entregas remuestrean varias bandas a una resolución de salida común. Estos valores son referencias por banda, no una escala inferida para cualquier JPG; la aplicación solo convierte si se introduce el GSD correspondiente a la imagen de entrada, y la fiabilidad de las unidades métricas depende de que ese dato y el remuestreo sean correctos.

El GSD habilita distancias y áreas métricas **locales**, pero no determina dónde está la imagen en la Tierra. Para asociar puntos o capas con viento, humedad o temperatura geolocalizados se necesitan además el CRS y la transformación entre píxel y coordenada geográfica (por ejemplo, una transformación affine de GeoTIFF). El JSON exportado conserva el sistema y las marcas en coordenadas de imagen para que puedan vincularse posteriormente.

## Confusores y límites

- Vegetación densa suele separarse por el verdor visible y su respuesta relativa en la composición SWIR. El agua suele tener poca señal en SWIR y se excluye parcialmente por oscuridad.
- Suelo desnudo, canteras, zonas urbanas, sombras y superficies previamente quemadas pueden tener colores parecidos al incendio. El clasificador no puede probar por sí solo que el suelo haya cambiado debido a este episodio.
- El filtro espacial prioriza por defecto el componente principal y puede descartar regiones candidatas separadas. Para preservar otros focos potenciales, activa la opción de conservar regiones desconectadas; esto también puede retener falsos positivos y requiere revisión.
- El humo degrada u oculta el terreno. True Color y la firma cromática SWIR ayudan a proponer una máscara; en paralelo, el detector conserva como hipótesis aparte la evidencia compatible con superficie afectada que persiste bajo el humo. Esa hipótesis no se suma al área/perímetro observados. Los JPEG no contienen bandas calibradas para recuperar el suelo oculto: la máscara puede confundir otras veladuras y el perímetro bajo humo queda sin resolver.
- La imagen `Wildfires` del repositorio resalta puntos/frentes activos; no se usa para segmentar el área afectada ni equivale a una verdad terreno de superficie quemada.
- No se calcula NBR: hacen falta los valores originales B08 y B12, no los canales RGB de una imagen SWIR renderizada. Tampoco se calculan hectáreas o coordenadas: los JPEG no tienen georreferenciación disponible.
- La máscara es una propuesta de visión por computador para revisión humana. Hay que validarla con una delimitación independiente en escenas de entrenamiento y reservar otras escenas para medir IoU, precision, recall y F1.

## Referencias espectrales

- [Manual de usuario Sentinel-2 de ESA](https://sentinels.copernicus.eu/documents/247904/685211/Sentinel-2_User_Handbook): bandas, longitudes de onda y resoluciones del instrumento MSI.
- [Guía de observación de la Tierra de ESA](https://business.esa.int/newcomers-earth-observation-guide): define GSD como la distancia entre centros de píxeles consecutivos medida en el terreno.
- [Datos técnicos Sentinel-2 de ESA](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2/Facts_and_figures): resoluciones espaciales de 10, 20 y 60 m según la banda.
- [Ejemplo oficial True Color Sentinel-2 L2A](https://docs.sentinel-hub.com/api/latest/data/sentinel-2-l2a/examples/): asignación RGB habitual B04/B03/B02.

## Ejecutar

Desde la raíz del repositorio:

```powershell
python app.py
```

Selecciona una de las escenas de ejemplo o carga tu propia pareja True Color/SWIR. Comprueba el perímetro sobre ambas composiciones y ajusta la sensibilidad antes de guardar la superposición. Para medir, usa las herramientas de clic de la web; las mediciones se mostrarán en píxeles mientras no se hayan validado la escala y la georreferenciación. La aplicación no inventa superficie terrestre ni geolocalización si faltan CRS y transformación.
