# PyroScope — Fundamentos conceptuales

**Hackatón 2026 · Documento de orientación técnica y de producto · 15/10/2026**

> **Propósito:** conservar las concepciones que guían el diseño antes de implementar. No es una especificación cerrada, un modelo físico validado ni una predicción operativa de incendios. Complementa el manual de PyroScope, pero algunas decisiones de ese manual deberán revisarse.

## 1. Qué problema resolvemos

El material de partida incluye **dos composiciones de una misma escena Sentinel-2, adquiridas en el mismo instante** durante un incendio en la Comunidad de Madrid:

- **True Color:** representación visible semejante a una fotografía (bandas RGB).
- **SWIR / falso color:** composición con información del infrarrojo de onda corta, útil para diferenciar materiales, humedad, áreas quemadas y ciertos focos de alta temperatura, según las bandas y la composición empleadas.

**No son dos momentos distintos**: no se puede medir la evolución temporal del incendio comparándolas directamente. Antes de diseñar el detector hay que comprobar si se entregarán imágenes RGB ya renderizadas o bandas espectrales originales, junto con los metadatos: hora UTC, CRS, geotransformación, resolución, orden de bandas y valores `nodata`.

Sentinel-2 dispone de bandas visibles y NIR a 10 m/píxel y bandas SWIR B11/B12 a 20 m/píxel. Una composición RGB exportada no equivale necesariamente a las bandas originales; **el significado de un color depende de cómo se asignaron y escalaron los canales**.

Separar objetivos:

1. **Fuego activo:** lugares que podrían estar ardiendo durante la adquisición.
2. **Área quemada:** superficie ya afectada; no necesariamente con llama activa.
3. **Humo:** fenómeno atmosférico que puede ocultar la superficie y no debe confundirse con ella.

La detección de cada clase tiene errores distintos; no debe utilizarse toda el área quemada como si fuera un frente de fuego activo.

## 2. Enfoque de implementación

**Elegir Python como motor y QGIS como apoyo, sin rehacer algoritmos existentes.**

- **QGIS:** inspección de imágenes, coordenadas, bandas, superposición, recortes, relieve y control de calidad cartográfica.
- **Python:** `rasterio`, `numpy`, `scipy`, `scikit-image`/`opencv`, `scikit-learn` para procesamiento y análisis; `geopandas`/`shapely` cuando se necesiten geometrías.
- **Interfaz web:** HTML, CSS y JavaScript propios; Python sirve la página y mantiene el procesamiento en el backend.
- **Detección incremental:** índice espectral y umbral → limpieza morfológica y contornos → clasificación supervisada simple si hace falta. Otsu y K-Means pueden servir de línea base; Random Forest puede aprender con píxeles etiquetados. SAM es opcional, no imprescindible y no entiende automáticamente la semántica del fuego.

Si están disponibles **B08 (NIR) y B12 (SWIR)**, evaluar el índice **NBR = (B08 − B12) / (B08 + B12)** para estudiar superficies quemadas; no inventar un NBR exacto a partir de una imagen de falso color. Un **dNBR** temporal exige imágenes de fechas diferentes, preferiblemente antes y después del incendio.

**Regla geoespacial:** alinear por CRS, extensión, transformaciones y resolución mediante reproyección/remuestreo geográfico. Un simple `resize()` puede hacer que dos píxeles coincidan en pantalla sin representar el mismo terreno. Medir superficies con el tamaño real de celda en un sistema de unidades apropiado; evitar inventar metros por píxel si solo hay PNG sin referencia.

## 3. Una reconstrucción histórica coherente

El núcleo de la aplicación debería aceptar una **fecha/hora UTC de referencia y una ubicación geográfica**, idealmente tomadas automáticamente de los metadatos de la imagen. Todos los factores temporales deben buscarse para esa época, no para el día actual.

| Variable | Fuente candidata | Criterio de selección |
|---|---|---|
| Viento (velocidad/dirección), temperatura, humedad, lluvia | Open-Meteo Historical; Copernicus ERA5/ERA5-Land; estaciones de AEMET si procede | Fecha y hora del incendio, resolución espacial y procedencia verificables. También pueden interesar las horas previas. |
| Altitud, pendiente y orientación del terreno | Modelos digitales del terreno del IGN/CNIG | Elevaciones numéricas georreferenciadas, no capturas de Google Maps. El relieve suele ser reutilizable entre años, salvo cambios locales. |
| Cobertura vegetal histórica | Google Dynamic World; escenas Sentinel-2 previas; cartografía regional/ESA WorldCover | Preferir fecha anterior al fuego, sin humo ni superficie ya quemada. Una clase «bosque» no mide directamente cantidad ni humedad del combustible. |
| Imágenes históricas | Copernicus Data Space Browser | Seleccionar escena, hora, nubosidad, bandas originales y metadatos. |

**Matices:** ERA5/Open-Meteo aportan reconstrucciones meteorológicas mediante modelos y observaciones, no mediciones exactas del viento en cada ladera. La humedad relativa del aire **no es** la humedad del combustible. Los datos de vegetación pueden ser posteriores, más antiguos o estar alterados por humo/incendio: registrar estos límites.

Google Earth puede servir para inspección histórica informal, pero sus fechas no son arbitrariamente seleccionables y las imágenes de Google Maps no son una base adecuada para extracción automatizada de datos. Preferir capas y APIs con condiciones de uso explícitas.

**Dos modos futuros del mismo motor:**
- **Reconstrucción retrospectiva:** introducir datos históricos del episodio y contrastar resultados con evidencia independiente. Utilizar valores meteorológicos observados *después* del momento inicial sirve para reconstruir, no para presumir capacidad de pronóstico.
- **Escenario actual/pronóstico:** usar observaciones recientes y previsiones, explicitando su incertidumbre. Sentinel-2 no ofrece vigilancia continua en tiempo real.

## 4. Modelo mental físico: dos mapas acoplados

La idea principal es separar **condiciones locales de combustión** y **propagación direccional**, sin tratarlas como dos magnitudes físicas totalmente independientes.

### A. Potencial de combustión — campo escalar

`C(x, y, t)` representa un **índice interpretativo** de cuán favorables son las condiciones locales para la combustión según combustible, continuidad, humedad, etc. No confundir:
- probabilidad de ignición;
- capacidad de sostener combustión;
- velocidad de consumo;
- energía/intensidad liberada.

Son propiedades distintas. Si la interfaz muestra un valor `C` de 0–1, debe etiquetarse como **puntuación relativa/heurística** hasta calibrarlo contra observaciones; **no** como «probabilidad real de incendio».

### B. Propagación — campo direccional

El **viento** favorece una dirección de avance y la **pendiente** otra (a menudo cuesta arriba). El terreno también determina barreras y continuidad de combustibles. No basta con un vector fijo del viento: la rapidez de propagación depende del **ángulo de avance**.

- `V_max(x, y, t)`: vector ilustrativo de **dirección y rapidez de propagación máxima estimada**.
- `R(x, y, θ, t)`: función más general de **tasa de propagación del frente** en la dirección `θ`. Permite también avance lateral o contra viento, a menor velocidad.

Como organización conceptual, no como ley exacta:

`R(x, y, θ, t) ≈ R_base(combustible, humedad, ...) × F(θ, viento, pendiente, ...)`

El **modelo de Rothermel** es una referencia física conocida para propagación de fuego forestal de superficie. Su uso riguroso exige modelos y parámetros del combustible, calibración y validación: no sustituirlos por ponderaciones arbitrarias. Una alternativa de implementación rápida es un **autómata celular de escenarios exploratorios**, claramente rotulado como simplificación no validada.

Para derivar la pendiente de un DEM se necesitan diferencias de elevación **divididas por distancias horizontales reales** (`dz/dx`, `dz/dy`). A partir de ellas se obtiene magnitud y dirección de máxima pendiente. La dirección meteorológica del viento suele indicar *de dónde viene*; para simular desplazamiento hay que convertirla a *hacia dónde va*.

### C. Riesgo no es lo mismo que comportamiento del fuego

La intensidad del frente y la superficie quemada son medidas físicas/geométricas diferentes del **riesgo humano o ecológico**. Para evaluar este último hacen falta además **exposición** (viviendas, carreteras, personas, ecosistemas) y **vulnerabilidad**. Un índice 1–10 sin datos ni calibración es solo un score interno ilustrativo, no un nivel oficial de emergencia.

## 5. Producto y visualizaciones que tendría sentido demostrar

A partir de la escena y sus metadatos:

1. Mostrar True Color y SWIR correctamente alineados, con control del significado de bandas.
2. Detectar y superponer **máscaras diferenciadas** (quemado, focos activos si son discernibles, humo si se implementa), con posibilidad de **corregir regiones** a mano.
3. Obtener **área, perímetro, centroide y contornos georreferenciados** cuando la fuente permita esa medición.
4. Mostrar mapa de **potencial/condiciones del combustible** y flechas de **propagación direccional estimada**, con controles de viento y humedad.
5. Solo después, un módulo de **escenarios de propagación** desde un estado inicial defendible, con incertidumbre y limitaciones explícitas.
6. Exportar PNG/GeoJSON/CSV y un informe con **fuentes, fecha, resolución, supuestos y método**.

Para evaluar detección, utilizar ejemplos etiquetados y, cuando exista referencia, métricas como **IoU, precision, recall y F1**. Una puntuación calculada a partir de los propios colores usados por el algoritmo no demuestra por sí misma su precisión.

## 6. Riesgos detectados en el manual actual de PyroScope

- La mezcla ponderada de canales y su normalización generan una **puntuación heurística**, no una probabilidad estadística calibrada.
- El `resize` directo de SWIR a True Color puede crear **falsas coincidencias geográficas**.
- La simulación puede arrancar tomando toda la región detectada (incluida área ya quemada) como **combustión activa**.
- En la aplicación integrada, `slope_x` y `slope_y` están inicializados a **cero**, por lo que la pendiente no afecta al resultado inicial, aunque haya un módulo opcional de terreno.
- El gradiente del DEM debe calcularse respecto a **distancias horizontales**, no normalizarse por la altura absoluta o percentil de elevación.
- El adaptador meteorológico automático es todavía un **stub** y las constantes de propagación, riesgo y humo son **orientativas**, no un modelo calibrado.

Conservar del manual la estructura modular de Python y las pruebas; **validar primero el tratamiento de imágenes y las capas históricas antes de ampliar la simulación**.

## 7. Orden de trabajo propuesto

1. **Contrato de datos:** formatos reales, RGB frente a bandas crudas, metadatos, fecha/hora, CRS, referencia de verdad terreno y qué se evaluará en la demostración.
2. **MVP de detección:** carga, alineación geográfica, segmentación, corrección, medidas y exportación.
3. **Contexto histórico:** viento/humedad de la fecha, DEM y capa de vegetación anterior al incendio; preservar procedencia e incertidumbre.
4. **Dos mapas conceptuales:** condiciones de combustión y tasa/dirección de propagación.
5. **Escenarios y validación:** simular solo con hipótesis claras, comparar con casos conocidos y evitar presentar certeza espuria.

**Decisión central:** priorizar la caracterización **observable y verificable** del incendio sobre una animación vistosa sin fundamentos. Mantener separados **observación, estimación, simulación y riesgo**.

## Referencias y servicios para explorar

- [Copernicus Data Space Browser](https://dataspace.copernicus.eu/browser/)
- [Documentación Sentinel-2 — ESA](https://sentinels.copernicus.eu/web/sentinel/missions/sentinel-2)
- [QGIS](https://qgis.org/)
- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
- [Copernicus Climate Data Store — ERA5](https://cds.climate.copernicus.eu/)
- [IGN/CNIG — modelos digitales de elevaciones](https://centrodedescargas.cnig.es/CentroDescargas/modelos-digitales-elevaciones)
- [Google Dynamic World (Earth Engine)](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1)
- [ESA WorldCover](https://esa-worldcover.org/en/data-access)
- [Documentación scikit-image](https://scikit-image.org/docs/stable/)

---

**Estado:** documento conceptual, sujeto a revisión al conocer los archivos y criterios definitivos del proyecto. No sustituye evaluación científica, modelos oficiales ni sistemas de protección civil.

## 8. Estimación de superficie a partir de las imágenes del repositorio

### Inventario de imágenes localizadas

En `DOCUMENTACION/Presentacion reto/` se localizaron ocho imágenes JPG distribuidas en tres ubicaciones. Los tamaños siguientes son los tamaños de archivo, **no** las dimensiones en píxeles ni la superficie terrestre cubierta.

| Ubicación | Producto | Tamaño del archivo |
|---|---|---:|
| La Mierla (Guadalajara) | SWIR | 1.447.226 bytes |
| La Mierla (Guadalajara) | True Color | 1.306.634 bytes |
| La Mierla (Guadalajara) | Wildfires | 1.241.849 bytes |
| Madrid-Avila | SWIR | 19.302.978 bytes |
| Madrid-Avila | True Color | 21.325.480 bytes |
| Niebla (Huelva) | SWIR | 980.203 bytes |
| Niebla (Huelva) | True Color | 893.953 bytes |
| Niebla (Huelva) | Wildfires | 933.409 bytes |

Carpetas:
- [La Mierla (Guadalajara)](https://github.com/emilioreato/harryelsucio/tree/main/DOCUMENTACION/Presentacion%20reto/La%20Mierla%20(Guadalajara))
- [Madrid-Avila](https://github.com/emilioreato/harryelsucio/tree/main/DOCUMENTACION/Presentacion%20reto/Madrid-Avila)
- [Niebla (Huelva)](https://github.com/emilioreato/harryelsucio/tree/main/DOCUMENTACION/Presentacion%20reto/Niebla%20(Huelva))

### Conversión de píxeles a superficie

Para una imagen con resolución espacial conocida y píxeles cuadrados, la estimación nominal es:

`superficie por píxel = tamaño de píxel en el terreno × tamaño de píxel en el terreno`

| Resolución espacial nominal | Superficie nominal por píxel |
|---|---:|
| 10 m/píxel | 10 × 10 = 100 m² |
| 20 m/píxel | 20 × 20 = 400 m² |
| 60 m/píxel | 60 × 60 = 3.600 m² |

Como referencia inicial, una composición **True Color** basada en bandas visibles de Sentinel-2 suele asociarse a bandas de 10 m, mientras que las bandas SWIR B11/B12 son de 20 m. Esto solo permite usar 100 m²/píxel para True Color y 400 m²/píxel para SWIR **si la exportación conserva esa escala espacial**. Un JPG puede haberse reescalado o renderizado; el nombre del archivo no prueba por sí solo su resolución efectiva. No se ha confirmado aún la composición espectral exacta de los productos `Wildfires`.

Ejemplo ilustrativo: si una máscara clasifica 5.000 píxeles como quemados, el área nominal sería 500.000 m² (50 ha) a 10 m/píxel, o 2.000.000 m² (200 ha) a 20 m/píxel. El ejemplo no es una medición de las imágenes del repositorio.

### Referencia técnica y límites

El artículo adjunto, **“Ground Resolved Distance Estimation of Sentinel-2 Imagery Using Edge-based Scene-Driven Approach”** (PFG Journal, 2025), distingue GSD (distancia de muestreo terrestre entre centros de píxeles) de GRD (capacidad efectiva de resolución). Para las bandas visibles y NIR usa GSD nominal de 10 m; en las escenas estudiadas estima GRD media de aproximadamente 12,4–12,7 m. Por tanto, la superficie nominal de un píxel no debe confundirse con el tamaño mínimo de detalle que el sensor puede resolver.

Antes de dar una superficie real, hay que verificar dimensiones de cada JPG, bandas usadas, remuestreo, CRS/geotransformación y tamaño de celda. Si solo se dispone de una imagen renderizada sin referencia geográfica, puede contarse una máscara de píxeles, pero no debe afirmarse que cubre una superficie terrestre exacta. Para un resultado defendible, trabajar con bandas/raster georreferenciado y sumar las celdas clasificadas como quemadas; distinguir siempre área quemada de fuego activo.

**Siguiente paso:** inspeccionar metadatos y dimensiones de los ocho JPG, confirmar la composición de cada producto y documentar cualquier remuestreo antes de calcular hectáreas.
