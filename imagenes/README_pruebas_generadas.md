# Escenas adicionales de prueba

Las carpetas con prefijo `00_PRUEBA` contienen cinco escenas añadidas desde
`trios_generados.rar`. Cada una incluye las imágenes **True Color** y **SWIR**
que usa el análisis, además de `metadatos.json` con fecha de adquisición,
procedencia, CRS, transformación, dimensiones y GSD nominal declarados.

La app las descubre como escenas precargadas. En `referencias/` se conserva la
composición **Wildfires** del trío y la app permite verla como referencia visual.
No se utiliza para segmentar ni debe tratarse como verdad terreno o etiqueta de
entrenamiento: el propio catálogo advierte que sus colores son una composición
aproximada y que no constituye una delimitación validada.

El catálogo y resumen del archivo están en `catalogo_pruebas_generadas.csv` y
`resumen_pruebas_generadas.json`. Las escenas añadidas son:

- `00_PRUEBA 01 - Cinco Villas Zaragoza` (16/07/2026)
- `00_PRUEBA 02 - La Vall d'Uixo Castellon` (28/07/2026)
- `00_PRUEBA 03 - Fermoselle Zamora` (29/07/2026)
- `00_PRUEBA 04 - Pinzio Portugal` (29/07/2026; cobertura declarada 90,2 %)
- `00_PRUEBA 05 - Valpacos Portugal` (29/07/2026)

El GSD nominal del catálogo es 10 m/píxel. Confirma la georreferenciación y la
escala efectiva antes de presentar mediciones de superficie como exactas.
