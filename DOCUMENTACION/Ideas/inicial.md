# Fundamentos conceptuales

Nota de orientación para distinguir lo que se observa de lo que se estima. El [README principal](../../README.md) describe el uso vigente; este documento resume los límites científicos que deben mantenerse al ampliar Lumbre.

## Qué muestran las imágenes

True Color y SWIR son composiciones de una misma adquisición, no un antes y un después. En los JPEG/PNG renderizados, los colores no permiten recuperar con certeza las bandas, reflectancias ni la georreferenciación originales. Sentinel-2 no es un sensor térmico.

Mantener separados:

- **Superficie afectada:** una clase de terreno; no implica que siga ardiendo.
- **Fuego activo:** focos observados; no equivale a toda el área quemada.
- **Humo:** fenómeno atmosférico que puede ocultar el terreno.

## Reglas para el análisis

- Alinear imágenes y capas por CRS, transformación, extensión y resolución. Igual tamaño de píxel no prueba alineación geográfica; `resize()` no sustituye una reproyección.
- Calcular NBR solo con bandas adecuadas, como B08 y B12 originales. dNBR requiere observaciones de fechas distintas.
- Convertir píxeles a metros o hectáreas solo con escala fiable. El GSD no proporciona por sí solo coordenadas geográficas.
- Consultar meteorología correspondiente a la adquisición y conservar fuente e incertidumbre. Humedad del aire no es humedad del combustible; distinguir viento «desde» de viento «hacia».
- Presentar puntuaciones heurísticas como puntuaciones, no como probabilidades calibradas. Distinguir detección, clasificación, simulación y riesgo.

## Evolución posible

El recorrido útil es cargar → analizar → revisar → medir con datos válidos → exportar. Una simulación futura necesitaría una fuente activa defendible, meteorología y combustible con procedencia, relieve alineado y evaluación independiente. No debe iniciarse suponiendo que toda la superficie quemada sigue ardiendo ni presentarse un escenario como pronóstico validado.

Para medir la calidad, separar entrenamiento y evaluación por incendio/adquisición y usar referencias independientes alineadas a la escena. Revisar falsos positivos y omisiones además de IoU, precisión, recall y F1.

## Fuentes para futuras ampliaciones

- [Manual Sentinel-2 de ESA](https://sentinels.copernicus.eu/documents/247904/685211/Sentinel-2_User_Handbook)
- [Copernicus Data Space Browser](https://browser.dataspace.copernicus.eu/)
- [Open-Meteo Historical Weather](https://open-meteo.com/en/docs/historical-weather-api)
- [Modelos digitales de elevación del IGN/CNIG](https://centrodedescargas.cnig.es/CentroDescargas/modelos-digitales-elevaciones)
