# Propuesta inicial: fuego, humo y agua

Nota histórica de las primeras reglas por color (15/10/2026). No describe exactamente el detector actual: consulta el [README principal](../../README.md) y el [informe experimental](segmentacion_contextual_evaluacion.md) para el estado vigente.

## Hipótesis que se conservaron

- Tratar el agua como una señal auxiliar/veto conservador; no clasificar toda superficie oscura como agua.
- Mantener el humo como oclusión atmosférica y la superficie del terreno como una capa distinta.
- No equiparar una cicatriz o superficie afectada con fuego activo.
- Tratar toda regla cromática aplicada a JPEG/PNG como heurística dependiente del renderizado.

La idea original de confirmar fuego mediante colores cálidos coincidentes en SWIR y True Color no es un detector validado ni la fuente actual de los focos. La app extrae candidatos de las marcas brillantes de `Wildfires` cuando esa composición está disponible; no mide temperatura. Nubes, bruma, suelo claro y otras superficies pueden confundirse con humo.

## Datos necesarios para avanzar

Las vistas deben corresponder a la misma adquisición y estar alineadas con metadatos fiables. Las máscaras requieren anotaciones independientes, escenas de varios incendios y evaluación por caso. Ni los umbrales ni las composiciones `Wildfires` constituyen verdad terreno o probabilidades de incendio.
