# Malackathon · Indra — Imágenes equivalentes y datos para validar la segmentación

**Investigación realizada:** 15 de octubre de 2026  
**Repositorio consultado:** [emilioreato/malackathon](https://github.com/emilioreato/malackathon), rama `main`  
**Objetivo:** encontrar más imágenes de los mismos incendios —idealmente la misma adquisición Sentinel-2— y referencias externas con las que evaluar la segmentación sin depender solo de una inspección visual.

## 1. Resumen ejecutivo

**Conclusión:** no se ha demostrado que existan en otras webs los *mismos archivos JPEG, byte por byte*, ni se ha comparado todavía su contenido mediante hash o alineación de píxeles. **Sí existen imágenes públicas de los mismos incendios y fechas**, incluidas imágenes oficiales de ESA para el 26/07, imágenes Sentinel-2 de La Mierla del 21/07, registros del caso de Niebla del 08/08 y, sobre todo, **perímetros vectoriales de incendios** de Copernicus EMS/EFFIS que pueden funcionar como referencias de evaluación, respetando su fecha y resolución.

Hallazgos ordenados por utilidad:

1. **Copernicus EMS Rapid Mapping:** activaciones [EMSR898 (La Mierla)](https://mapping.emergency.copernicus.eu/activations/EMSR898/), [EMSR913 (Huelva/Niebla)](https://mapping.emergency.copernicus.eu/activations/EMSR913/) y [EMSR900 (incendios de España central)](https://mapping.emergency.copernicus.eu/activations/EMSR900/). Permiten buscar productos de delimitación y evaluación de daños. La coincidencia espacial de cada área de interés (AOI) y la fecha exacta del producto **deben comprobarse** antes de evaluarlo contra un JPEG concreto.
2. **[EFFIS — perímetros de área quemada](https://forest-fire.emergency.copernicus.eu/applications/data-and-services):** ofrece bases de áreas quemadas y descargas Shapefile/SpatiaLite; también un [visor](https://forest-fire.emergency.copernicus.eu/apps/effis.csv/) con capas MODIS/Sentinel-2. Complemento útil para comparar contornos y casos adicionales.
3. **[ESA — imagen amplia Madrid–Ávila del 26/07](https://www.esa.int/ESA_Multimedia/Images/2026/07/Raging_wildfires_near_Madrid_Spain)** y [recorte sobre Cebreros del mismo día](https://www.esa.int/ESA_Multimedia/Images/2026/07/Wildfires_near_Cebreros_ground_station_Spain). Ambas confirman imágenes Sentinel-2 disponibles de la misma zona y fecha que el reto; **no se ha probado que tengan el mismo recorte ni idéntico renderizado**.
4. **[Copernicus Browser](https://browser.dataspace.copernicus.eu/):** permite recuperar la adquisición satelital original, obtener fechas vecinas y exportar composiciones o bandas espectrales. Es la mejor vía para generar un conjunto homogéneo de prueba.
5. **[Script QuickFire de Pierre Markuse](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/markuse_fire/):** receta pública y reproducible de visualización de incendios con bandas Sentinel-2. Puede servir para generar ejemplos del mismo tipo, sin asumir que coincida con la composición `Wildfires.jpg` del reto.

**Recomendación para una hackathon de ~10 horas:** obtener primero **una** referencia vectorial válida para un caso; generar una evaluación básica de IoU/F1; después añadir escenas nuevas. No invertir horas en recopilar decenas de JPEG periodísticos ni en una infraestructura de descarga masiva.

## 2. Inventario comprobado del repositorio

Dentro de `DOCUMENTACION/Presentacion reto/` aparecen estos archivos:

| Caso | Fecha expresada por el nombre del archivo | Ficheros |
|---|---|---|
| La Mierla, Guadalajara | 21/07/2026 | `*_True_color.jpg`, `*_SWIR.jpg`, `*_Wildfires.jpg` |
| Madrid-Avila | 26/07/2026 | `*_True_color.jpg`, `*_SWIR.jpg` |
| Niebla, Huelva | 08/08/2026 | `*_True_color.jpg`, `*_SWIR.jpg`, `*_Wildfires.jpg` |

**Total: 8 JPEG.** Todos llevan `Sentinel-2_L2A` en el nombre. El patrón completo es `AAAA-MM-DD-00_00_AAAA-MM-DD-23_59_Sentinel-2_L2A_<visualización>.jpg`.

**Precaución importante:** el intervalo `00:00–23:59` del nombre parece ser una *ventana de búsqueda/exportación* de un día; **no identifica necesariamente la hora real de adquisición ni el producto satelital exacto**. Incluso dos renderizados con igual fecha podrían proceder de mosaicos o parámetros de visualización diferentes. Para afirmar identidad de escena hacen falta metadatos del producto —identificador, hora UTC, geometría, resolución y composición—, o una comprobación de coincidencia espacial y radiométrica.

La presencia de un archivo `Wildfires.jpg` **no lo convierte en ground truth** ni en una máscara binaria validada. Es una visualización; si se construye por umbrales espectrales, evaluarse contra ella puede producir resultados artificialmente buenos.

## 3. Hallazgos sobre cada uno de los tres incendios

### A. La Mierla (Guadalajara) — 21 de julio

**Coincidencias de fecha y zona encontradas:**

- [elDiario.es — antes/después del 13 y 21 de julio](https://www.eldiario.es/castilla-la-mancha/despues-incendio-mierla-visto-satelite_1_13398856.html). La página identifica imágenes de **Copernicus/Sentinel-2** del 21/07, la fecha del reto. Útiles para reconocer la zona, estudiar cambio temporal y comprobar visualmente perímetro/cicatriz. La imagen de prensa contiene tratamientos editoriales y **no debería usarse como máscara de píxeles directamente**.
- [Centro Cartográfico de Castilla-La Mancha — materiales del 21/07](https://cartografia.castillalamancha.es/noticias/el-sistema-copernicus-proporciona-imagenes-y-cartografia-del-incendio-de-la-mierla-para). El índice público anuncia «Imagen satélite La Mierla 21/07/2026» (9,24 MB) y «Imagen satélite Selas 21/07/2026» (4,23 MB), más mapas. **Muy prometedor para una imagen del mismo episodio**, pero no se han descargado esos archivos para cotejarlos.
- [poliedro.media — varias visualizaciones Sentinel-2 del 21/07](https://poliedro.media/es/exclusivas/incendio_mierla_satelite_2026): área quemada, focos activos y humo. Confirma existencia de vistas alternativas del mismo día; son material visual, no etiquetas de píxel contrastadas.
- [EMSR898 — Copernicus EMS](https://mapping.emergency.copernicus.eu/activations/EMSR898/). Fuente prioritaria de cartografía de delimitación/daños. Es necesario revisar los productos y escoger el más próximo temporalmente a la adquisición del reto.

**Acción recomendada:** abrir EMSR898, buscar productos `Delineation`/`Monitoring` con geometrías exportables y, paralelamente, recuperar la escena del 21/07 desde Copernicus Browser. Si las geometrías son posteriores a la adquisición, etiquetarlas como *referencia posterior*, no como verdad exacta a la hora del satélite.

### B. Madrid–Ávila — 26 de julio

**Este es el caso mejor respaldado para conseguir vistas de la misma fecha:**

- [ESA — Raging wildfires near Madrid](https://www.esa.int/ESA_Multimedia/Images/2026/07/Raging_wildfires_near_Madrid_Spain): imagen **Sentinel-2 captada el 26/07/2026**, vista general al oeste de Madrid. ESA indica que el infrarrojo cercano contribuye a destacar los frentes activos.
- [ESA — Wildfires near Cebreros ground station](https://www.esa.int/ESA_Multimedia/Images/2026/07/Wildfires_near_Cebreros_ground_station_Spain): recorte de la misma fecha, con color natural y falso color para marcar frentes. Buena prueba cualitativa sobre detección de focos.
- [EL PAÍS — análisis satelital de Ávila y Madrid](https://elpais.com/espana/2026-07-27/mapas-datos-e-imagenes-satelitales-muestran-como-el-viento-transformo-el-incendio-de-avila-y-madrid.html): composición SWIR Sentinel-2 **del 26/07 a las 13:07:11, hora peninsular según el medio**, con fuego activo, vegetación y áreas quemadas. También describe la evolución entre el 24 y el 26. Es una pista concreta para localizar el producto de origen, no una verificación de que el JPEG del reto se tomó a esa misma hora.
- [EMSR900 — Copernicus](https://mapping.emergency.copernicus.eu/activations/EMSR900/): emergencia de incendios de España central. **Advertencia:** la ficha menciona específicamente focos en Brieva (Segovia) y Almorox/Villa del Prado; no hay que suponer que cualquier AOI de EMSR900 cubra el incendio de Burgohondo/Cebreros. Confirmar intersección espacial antes de utilizar los vectores.

**Acción recomendada:** cotejar la imagen amplia de ESA y la del periódico con `Madrid-Avila/*SWIR.jpg`; luego obtener el producto Sentinel-2 de ese día con su `product ID`, bandas originales y límites geográficos. Buscar el perímetro concreto del incendio en EFFIS si el AOI de EMSR900 no corresponde.

### C. Niebla (Huelva) — 8 de agosto

- [Recopilación de grandes incendios 2026](https://edu.forestry.es/p/gif2026.html): registra explícitamente una visualización/perímetro sobre **Sentinel-2 del 08/08/2026, 13:06 h CEST**, asociada al incendio de Niebla y una estimación de 4.393 ha *en ese momento*. Es una pista temporal importante; procede de una recopilación no oficial y hay que contrastar sus geometrías antes de usarlas como referencia.
- [EMSR913 — incendio de Huelva](https://mapping.emergency.copernicus.eu/activations/EMSR913/): activación oficial solicitada para delineación y daños. [Ficha del servicio](https://mapping.emergency.copernicus.eu/news/wildfire-in-huelva-spain-emsr913/) confirma que el incidente empezó el 6/08 y motivó cartografía de respuesta.
- [Ficha del dataset EMSR913 en el JRC](https://doi.org/10.2905/JRC.AJ2A57G): documenta procedencia y condiciones de reutilización **CC BY 4.0** del conjunto identificado allí.
- [Wikimedia Commons — producto Copernicus de Huelva, 21/08](https://commons.wikimedia.org/wiki/File:Huelva_wildfire_among_Spain%E2%80%99s_worse_of_2026_(Copernicus_2026-08-21).webp): **imagen posterior**; permite comprobar extensión final/recuperación visual, pero **no debe tomarse como máscara del estado del 08/08**.

**Acción recomendada:** priorizar las versiones más tempranas de delineación de EMSR913 y comprobar la hora de la imagen que cada producto utiliza, no solo la fecha de entrega. Buscar la escena Sentinel-2 de las 13:06 h CEST para replicar los JPEG.

## 4. Nuevas imágenes de la misma familia: ejemplos ajenos al reto

### Gironde/Landes (Francia), 21 y 26 de julio

Dos archivos de Wikimedia Commons **verificados como existentes**, ambos Sentinel-2 L2A y de gran tamaño (**9.930 × 7.198 px**):

- [21/07/2026 — antes del fuego en Gironde](https://commons.wikimedia.org/wiki/File:Gironde_2026-07-21-00_00_2026-07-21-23_59_Sentinel-2_L2A_custom.jpg).
- [26/07/2026 — durante el incendio en Gironde](https://commons.wikimedia.org/wiki/File:Gironde_2026-07-26-00_00_2026-07-26-23_59_Sentinel-2_L2A_custom.jpg).

**Por qué destacan:** utilizan prácticamente el mismo patrón de nombres de archivos que vuestro repo, se exportaron desde **Copernicus Browser** y su ficha atribuye el procesamiento al **script QuickFire de Pierre Markuse**. Esto sugiere una vía concreta para generar visualizaciones compatibles por técnica de origen, aunque **no prueba** que Indra haya utilizado ese script ni los mismos ajustes.

No sirven para validar *el incendio de España* pero **sí para comprobar si el detector generaliza** a una región y una escena distintas; el 21/07 puede aportar un negativo visual previo y el 26/07 un positivo. Deben revisarse sus nubes/estado real y licencias/atribución antes de incorporarlas al dataset.

Otros materiales:

- [Wikimedia Commons — 25 archivos satelitales de incendios españoles de 2026](https://commons.wikimedia.org/wiki/Category:Satellite_pictures_of_2026_wildfires_in_Spain): catálogo para inspección y demos, mezclando imágenes Sentinel, NASA y productos divulgativos.
- [UE — incendios de la frontera Portugal–España, 29/07](https://eu-space.europa.eu/components/earth-observation-copernicus/image-of-the-day/wildfires-along-portugal-spain-border): imágenes en falso color adquiridas por Sentinel-2A/2B de varios focos; útil como caso adicional, **no idéntico al reto**.
- [ESA — Cebreros](https://www.esa.int/ESA_Multimedia/Images/2026/07/Wildfires_near_Cebreros_ground_station_Spain): especialmente útil para demostrar superposición de puntos calientes sobre color natural.

## 5. La fuente más importante: etiquetas externas y perímetros

### Copernicus Emergency Management Service — Rapid Mapping

Documentación oficial:

- [Explicación de datos, productos y API](https://mapping.emergency.copernicus.eu/about/how-to-harvest-cems-mapping-data/emergency-response-data/).
- [Formatos actuales, incluidos GeoPackage, GeoJSON y shapefiles](https://mapping.emergency.copernicus.eu/news/rapid-mapping-crisis-information-now-available-as-a-geopackage/).

La API oficial documenta un endpoint de detalle para una activación:

```text
https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR898
https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR913
https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=EMSR900
```

Para cada área (`aois[]`) y producto (`products[]`), los campos descritos incluyen **tipo**, **versión**, **fecha de adquisición de la imagen (`images[].acquisitionTime`)**, **sensor**, **enlaces de descarga (`downloadPath`)**, y capas publicadas. **Los endpoints están documentados, pero no se ha conseguido verificar aquí la respuesta JSON específica de estas activaciones ni sus enlaces ZIP individuales.** No conviene inventar rutas de descarga.

**Proceso mínimo en QGIS:** descargar el paquete vectorial o `.gpkg` desde la sección de descargas de la activación; identificar la capa de área quemada (`observedEventA` u otra según versión); seleccionar el producto cuya adquisición/observación más se acerque a la escena del reto; reproyectar y rasterizar sobre la rejilla geográfica del Sentinel-2. Conservar la máscara original, la fecha y el AOI.

### EFFIS — segunda fuente cartográfica

- [Página de descargas](https://forest-fire.emergency.copernicus.eu/applications/data-and-services) y [visor geográfico](https://forest-fire.emergency.copernicus.eu/apps/effis.csv/).
- [Metodología oficial de Rapid Damage Assessment](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/rapid-damage-assessment).

EFFIS obtiene perímetros de MODIS y los refina en parte con Sentinel-2 (20 m); los perímetros **no equivalen** a una anotación perfecta de cada píxel. El producto sirve como referencia geográfica para área quemada, especialmente para componentes grandes. Una máscara EFFIS puede estar basada parcialmente en los mismos datos ópticos del reto: es una **referencia externa de procesamiento**, no una medida experimental totalmente independiente.

### NASA FIRMS — validación complementaria de focos activos

- [NASA FIRMS — datos de fuego activo](https://firms.modaps.eosdis.nasa.gov/active_fire).
- [NASA FIRMS — archivo histórico](https://firms.modaps.eosdis.nasa.gov/download/).

Hay CSV, SHP y JSON de detecciones MODIS/VIIRS históricas. VIIRS aporta detecciones nominalmente a **375 m**, mucho más gruesas que las bandas de Sentinel-2; **no convertir sus puntos directamente en máscaras de fuego a 10–20 m**. Sí permiten verificar proximidad de focos activos, coherencia espacial y fechas/horas. Consultar las condiciones de autenticación de Earthdata o acceso con email para el histórico.

### Fuente adicional, menor prioridad

[Copernicus Land Monitoring — área quemada diaria a 300 m (2025–presente)](https://land.copernicus.eu/en/products/vegetation/burnt-area-v4-daily-300m). Contiene fecha de quemado/fracción afectada, pero su resolución es demasiado baja para juzgar límites finos de Sentinel-2. Útil solo como comprobación de escala regional o casos muy grandes.

## 6. Cómo conseguir *la misma adquisición* en Copernicus Browser

1. Abrir [Copernicus Browser](https://browser.dataspace.copernicus.eu/) e iniciar sesión si el flujo de exportación lo requiere.
2. Elegir **Sentinel-2 L2A**, no un mosaico trimestral ni Sentinel-2 L1C.
3. Buscar el área geográfica del JPEG: La Mierla, incendios de Ávila/Madrid o Niebla. Filtrar por **21/07, 26/07 o 08/08/2026** según el caso.
4. Abrir las adquisiciones de esa fecha y anotar **identificador del producto, hora UTC, nubosidad y mosaico/tesela**. Si hay varias, cotejar nubes, humo, carreteras, embalses y perímetro del recorte.
5. Probar las capas **True Color** y **SWIR**; para `Wildfires`, probar **QuickFire**, conservando el script y sus parámetros. Consultar [manual del Browser](https://documentation.dataspace.copernicus.eu/Applications/Browser.html).
6. Exportar usando **el mismo cuadro geográfico, proporción de aspecto y tamaño** para todas las capas. Idealmente obtener **GeoTIFF o bandas originales** cuando se vaya a evaluar por píxeles; guardar JPEG solo para visualización/demos.
7. Añadir escenas **anteriores al incendio y posteriores al incendio** sobre el mismo lugar; y al menos una región sin incendios como negativo.

**Criterios de equivalencia:**

- **Idéntico byte a byte:** mismo JPEG, igual `SHA-256`. No constatado fuera del repo.
- **Misma imagen satelital:** mismo producto/adquisición y misma área, aunque el JPEG tenga otro procesado de color. Objetivo realista.
- **Mismo incendio y fecha, otro sensor/producto:** útil para contraste, pero no debe considerarse el mismo dato.
- **Mismo tipo de imagen de otro incendio:** útil para generalización y negativos/positivos adicionales; nunca para validar la geometría de un caso original.

## 7. Protocolo mínimo de evaluación (sin engañarnos con métricas)

**Separar objetivos:**

- **Área quemada:** comparar máscara con un perímetro vectorial del mismo estado temporal (Copernicus EMS/EFFIS). Informar `IoU = |P∩G| / |P∪G|`, precisión, recall y F1/Dice. Si hay desfase de fechas, reportarlo y **no presentar la cifra como exactitud de ese instante**.
- **Fuego activo:** utilizar focos VIIRS de fecha/hora próxima, si existen, como control cualitativo o de proximidad. No medir IoU contra puntos de 375 m como si fueran máscaras de alta resolución. Evaluación de píxeles requiere etiquetado fiable a una resolución compatible.
- **Humo:** sin etiquetas independientes, limitarse a revisión visual por regiones; no mezclarlo con área quemada ni fuego activo.

**Cuidados técnicos imprescindibles:**

1. **Mismo sistema de coordenadas y transformación:** reproyectar/rasterizar la referencia a la malla original de la imagen con herramientas geoespaciales (`rasterio`, QGIS). **No hacer simplemente `cv2.resize` y calcular IoU.**
2. **Máscara válida:** excluir `nodata`, zonas fuera del AOI y, cuando corresponda, píxeles de nube/humo que impiden observar el suelo.
3. **Separación de entrenamiento y test por adquisición/incendio:** recortes del mismo mosaico NO cuentan como test independiente si se ajustaron los umbrales sobre esa escena.
4. **Negativos duros:** suelo desnudo, campos secos, zonas quemadas antiguas, sombras, nubes y humo. Medir falsos positivos.
5. **No ajustar parámetros mirando el resultado final de test.** Reservar al menos un incendio completo para comprobar generalización.
6. **Guardar metadatos** por muestra: fuente, licencia, fecha de adquisición UTC, ID de producto, AOI, CRS, resolución, composición, versión y procedencia de la máscara.

Para iterar, con 3 casos y pocos minutos: elegir un caso de ajuste, otro de validación y **uno reservado para la demo/evaluación final**. Los datasets externos pueden aportar más diversidad sin alterar el conjunto de referencia.

## 8. Plan de trabajo priorizado para el equipo

| Prioridad | Tiempo orientativo | Acción | Resultado esperado |
|---|---:|---|---|
| P0 | 15–30 min | Revisar los 8 JPEG: dimensiones, metadatos disponibles, coincidencia de encuadres | Saber exactamente qué datos entran al algoritmo |
| P0 | 20–40 min | Revisar EMSR898 y EMSR913; descargar **un** vector de área quemada y confirmar su fecha de adquisición | Una referencia externa utilizable |
| P0 | 30–60 min | Rasterizar sobre una imagen bien georreferenciada y computar IoU/F1 | Primer benchmark reproducible |
| P1 | 20–40 min | Abrir el mismo caso en Copernicus Browser; obtener bandas/otra fecha comparable | Más datos y menos dependencia del JPEG |
| P1 | 20–30 min | Probar negativos y un incendio no utilizado para ajustar | Medida básica de generalización |
| P2 | Solo si sobra tiempo | Incorporar Gironde, prensa o colecciones adicionales | Mayor cobertura para una demo robusta |

Los tiempos son estimaciones de organización, no tiempos verificados de cada servicio. **Si la descarga de EMS tarda o falla, cambiar pronto a EFFIS o etiquetar manualmente unas pocas regiones con procedencia clara**, antes que bloquear todo el MVP.

## 9. Estado de verificación y límites de esta investigación

**Verificado:** existencia y nombres de los 8 JPEG en `main`; existencia de páginas de imágenes Sentinel-2 de la fecha coincidente para La Mierla y Madrid–Ávila; imágenes oficiales ESA del 26/07; fichas de EMSR898/913/900; API oficial documentada para obtener productos y metadatos; existencia de fuentes EFFIS, FIRMS, Browser y QuickFire; los dos archivos de Gironde.

**No verificado:** identidad byte a byte de JPEG externos; que las imágenes externas compartan *exacto* producto/órbita/tesela, extensión, resolución y LUT con las del repo; contenido descargado y estructura de un GPKG específico; compatibilidad temporal de un producto EMS con cada JPEG; identidades de las bandas exactas usadas en cada composición `SWIR` o `Wildfires`.

**Importante:** la búsqueda por nombres completos de los ocho ficheros no proporcionó coincidencias públicas independientes inequívocas. No es prueba de que no existan: los archivos pueden estar dentro de visores, contenedores, servidores sin indexación o tener otro nombre. La vía robusta es **buscar la misma adquisición en el catálogo Sentinel-2, no el nombre del JPEG**.

## 10. Fuentes primarias y material de consulta

- **Datos originales / exportación:** [Copernicus Browser](https://browser.dataspace.copernicus.eu/) · [Manual del Browser](https://documentation.dataspace.copernicus.eu/Applications/Browser.html).
- **EMSR y vectores:** [La Mierla EMSR898](https://mapping.emergency.copernicus.eu/activations/EMSR898/) · [Huelva EMSR913](https://mapping.emergency.copernicus.eu/activations/EMSR913/) · [España central EMSR900](https://mapping.emergency.copernicus.eu/activations/EMSR900/) · [Documentación API Rapid Mapping](https://mapping.emergency.copernicus.eu/about/how-to-harvest-cems-mapping-data/emergency-response-data/) · [Anuncio de GeoPackage](https://mapping.emergency.copernicus.eu/news/rapid-mapping-crisis-information-now-available-as-a-geopackage/).
- **Control geográfico:** [EFFIS datos](https://forest-fire.emergency.copernicus.eu/applications/data-and-services) · [Metodología EFFIS](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/rapid-damage-assessment) · [NASA FIRMS histórico](https://firms.modaps.eosdis.nasa.gov/download/).
- **Escena Ávila/Madrid:** [ESA amplio](https://www.esa.int/ESA_Multimedia/Images/2026/07/Raging_wildfires_near_Madrid_Spain) · [ESA Cebreros](https://www.esa.int/ESA_Multimedia/Images/2026/07/Wildfires_near_Cebreros_ground_station_Spain) · [EL PAÍS 26/07](https://elpais.com/espana/2026-07-27/mapas-datos-e-imagenes-satelitales-muestran-como-el-viento-transformo-el-incendio-de-avila-y-madrid.html).
- **Escena La Mierla:** [elDiario.es 13/21 julio](https://www.eldiario.es/castilla-la-mancha/despues-incendio-mierla-visto-satelite_1_13398856.html) · [Centro Cartográfico CLM](https://cartografia.castillalamancha.es/noticias/el-sistema-copernicus-proporciona-imagenes-y-cartografia-del-incendio-de-la-mierla-para) · [poliedro.media](https://poliedro.media/es/exclusivas/incendio_mierla_satelite_2026).
- **Escena Niebla:** [Compilación del 08/08](https://edu.forestry.es/p/gif2026.html) · [Noticia EMSR913](https://mapping.emergency.copernicus.eu/news/wildfire-in-huelva-spain-emsr913/) · [JRC dataset](https://doi.org/10.2905/JRC.AJ2A57G).
- **Generalización / renderizados:** [QuickFire script](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-2/markuse_fire/) · [Gironde 21/07](https://commons.wikimedia.org/wiki/File:Gironde_2026-07-21-00_00_2026-07-21-23_59_Sentinel-2_L2A_custom.jpg) · [Gironde 26/07](https://commons.wikimedia.org/wiki/File:Gironde_2026-07-26-00_00_2026-07-26-23_59_Sentinel-2_L2A_custom.jpg) · [Commons incendios españoles 2026](https://commons.wikimedia.org/wiki/Category:Satellite_pictures_of_2026_wildfires_in_Spain).

---

**Decisión sugerida:** montar un pipeline mínimo **imagen → máscara estimada → máscara de referencia geográfica → métricas y overlay**. El valor de la búsqueda no es duplicar imágenes bonitas; es pasar de una segmentación convincente visualmente a una **detección cuya calidad pueda medirse y defenderse**.
