# Propuesta: muestreo de humo y pluma gaussiana

**Estado:** idea no implementada. Lumbre muestra una máscara visual de humo probable, pero no estima emisiones ni simula una concentración atmosférica.

## Separar observación y simulación

La máscara de humo permite resumir píxeles, forma, centroide y confianza aparente. Su área solo es métrica con un GSD fiable; su brillo no mide masa ni concentración. En varias fechas, las escenas deben ser comparables y conservar hora, fuente e incertidumbre.

Una simulación futura necesitaría un foco activo y una tasa de emisión estimados, viento a una altura/fecha conocida, estabilidad atmosférica, relieve, combustible y una rejilla geográfica métrica. Si faltan datos, cualquier resultado debe mostrarse como escenario ilustrativo con supuestos explícitos.

Como referencia conceptual, una pluma gaussiana estacionaria depende de la emisión `Q`, viento a sotavento `u` y dispersiones lateral/vertical `σy`, `σz`; la altura efectiva de la fuente y la estabilidad modifican el campo. Este modelo idealizado no representa por sí solo el viento variable, la flotabilidad de la columna, el terreno complejo ni el frente móvil de un incendio.

## Etapas sugeridas

1. Resumir las máscaras observadas y guardar metadatos.
2. Mostrar una pluma sintética con foco y viento introducidos por el usuario, rotulada como simulación.
3. Incorporar meteorología y combustible con procedencia, unidades y valores ausentes explícitos.
4. Contrastar resultados con observaciones independientes y analizar incertidumbre antes de cualquier uso operativo.

La máscara observada, la simulación y el área afectada deben seguir siendo capas distintas. No usar el área quemada completa como si fuese un frente activo.
