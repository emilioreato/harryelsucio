# Ideas y evolución técnica de Lumbre

Estas notas acompañan la evolución de Lumbre desde el reto de Indra Espacio en el III Malackathon 2026; el contexto está en la [historia del proyecto](../historia_del_proyecto.md). Este índice separa el estado actual de las propuestas y del registro histórico. Para instalar y usar la aplicación, consulta el [README principal](../../README.md). El código es la referencia del comportamiento actual; los informes fechados describen experimentos de su momento.

## Estado actual y evidencia

| Documento | Estado | Uso |
|---|---|---|
| [`segmentacion_contextual_evaluacion.md`](segmentacion_contextual_evaluacion.md) | Informe experimental, 15/10/2026 | Parámetros, comparaciones y límites de una ejecución concreta. No demuestra exactitud con etiquetas independientes. |
| [`../../resultados/clasificacion/agua/90dd412/INFORME.md`](../../resultados/clasificacion/agua/90dd412/INFORME.md) | Informe histórico, checkout 47bfc7a | Evaluación conservada del detector de agua y su regresión; el directorio mantiene matrices y paneles de esa ejecución. |
| [`LUMBRE_CAMBIOS_RECIENTES_SEGMENTACION_2026-10-15.md`](LUMBRE_CAMBIOS_RECIENTES_SEGMENTACION_2026-10-15.md) | Historial breve | Decisiones tomadas y aprendizajes que conviene conservar. |
| [`segmentacion_basica.md`](segmentacion_basica.md) | Fundamentos del flujo actual | Separación entre observación, clasificación, geometría y medición. |
| [`Malackathon_Indra_fuentes_imagenes_y_validacion.md`](Malackathon_Indra_fuentes_imagenes_y_validacion.md) | Investigación de fuentes, 15/10/2026 | Pistas para obtener imágenes y referencias externas; disponibilidad pendiente de comprobar. |

## Ideas y propuestas

| Documento | Estado | Uso |
|---|---|---|
| [`inicial.md`](inicial.md) | Fundamentos conceptuales | Invariantes científicas y alcance de posibles módulos futuros. |
| [`algoritmos_segmentacion_fuego_humo_agua.md`](algoritmos_segmentacion_fuego_humo_agua.md) | Propuesta inicial, no especificación del detector actual | Conserva las hipótesis y limitaciones de las primeras reglas por color. |
| [`random_forest_aplicacion_deteccion_incendios.md`](random_forest_aplicacion_deteccion_incendios.md) | **Desactivado:** durante el Malackathon no se etiquetaron píxeles ni se entrenó/evaluó un modelo | Se preparó la infraestructura, pero el trabajo quedó incompleto al agotarse el tiempo. No produce predicciones en la aplicación actual. |
| [`muestreo_humo_y_simulacion_pluma_gaussiana.md`](muestreo_humo_y_simulacion_pluma_gaussiana.md) | Propuesta no implementada | Idea de simulación; no representa una función disponible en la app. |

Las ideas antiguas se mantienen resumidas para conservar por qué se tomaron decisiones, sin repetir el manual de uso ni presentar propuestas como funciones implementadas. Los resultados reproducibles y sus límites se registran en el informe de evaluación.
