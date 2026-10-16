# Área afectada y perímetro

Resumen del enfoque del reto básico. La aplicación actual y sus opciones se describen en el [README principal](../../README.md); los parámetros y resultados experimentales están en [`segmentacion_contextual_evaluacion.md`](segmentacion_contextual_evaluacion.md).

## Flujo

1. Cargar una pareja True Color/SWIR de la misma adquisición y comprobar que pueda analizarse sobre una rejilla común.
2. Mantener el humo como capa de oclusión independiente. Si hay evidencia bajo humo, mostrarla como hipótesis aparte; no sumarla a la superficie observada.
3. Proponer píxeles candidatos con el detector elegido y formar regiones con filtros espaciales documentados.
4. Mostrar máscara, contorno y capas para revisión; exportar las salidas en la rejilla del análisis.

La clasificación responde qué píxeles tienen señales compatibles con una clase; la geometría decide qué regiones conservar. Unir regiones no confirma que sean suelo quemado. Agua probable ayuda como veto, pero no es un mapa validado de agua. La capa opcional de focos proviene de `Wildfires`, no de la máscara de superficie.

## Medidas y límites

Las escenas precargadas aplican automáticamente el GSD fijado en el catálogo (10 m/píxel), ajustado a la rejilla reducida que usa el análisis. La regla mide la distancia dibujada; el área selecciona una región de la máscara y mide sus píxeles, no un polígono trazado a mano. Las imágenes propias sin escala se siguen pudiendo medir en píxeles. El GSD da medidas locales nominales, pero no coordenadas terrestres: para eso hacen falta CRS y transformación geográfica. Las composiciones renderizadas pueden haber sido remuestreadas, por lo que no deben confundirse estas medidas con una georreferenciación precisa.

Suelo desnudo, sombras, nubes, agua y cicatrices antiguas pueden confundirse con candidatos. Sin bandas originales, etiquetas independientes y metadatos, el resultado no confirma un incendio, no recupera el terreno oculto y no permite afirmar exactitud. No calcular NBR/dNBR desde canales RGB renderizados.
