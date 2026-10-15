# Lumbre — evaluación conservadora del detector de agua

## Estado del código

El checkout actual está en `HEAD 47bfc7a` (merge). La referencia de las máscaras vigentes es `90dd412`; el código experimental está en `pyroscope/agua.py` desde `1ff1c73`. `detectar_agua_probable()` mantiene la lógica vigente y la alternativa privada `_detectar_agua_probable_experimental()` no está conectada a K-Means, SWIR ni contextual, porque la prueba de incendio encontró una regresión.

## Método y límites

- Se compararon parejas True Color/SWIR alineadas y reducidas conjuntamente a 1800 px de lado máximo en La Vall d'Uixó, La Mierla, Madrid–Ávila y Niebla.
- Se guardaron máscaras antes/después, píxeles retirados y añadidos, y resultados de incendio. Los paneles y matrices NPZ están en `antes/`, `despues/` y `sensibilidad_6/`.
- El perfil contextual de la interfaz se comprobó con sensibilidad 6, área mínima 0,15 % y distancia 10 %.
- No hay máscaras independientes de agua alineadas. Los recuentos y la inspección visual no permiten calcular precisión, recall o IoU ni demostrar precisión real.

## Máscara de agua

Recuentos directos del detector con el perfil de sensibilidad 6:

| Escena | Vigente | Experimental | Retirados | Añadidos | Lectura visual, no anotada |
|---|---:|---:|---:|---:|---|
| La Vall d'Uixó | 36.239 | 35.965 | 274 | 0 | Conserva la detección principal del mar; el cambio es pequeño. |
| La Mierla | 13.093 | 9.124 | 4.531 | 562 | Reduce parches sobre vegetación; quedan detecciones en partes de los embalses visibles. |
| Madrid–Ávila | 62.336 | 3.375 | 58.961 | 0 | Elimina amplias manchas sobre zonas verdes; no se identificó una masa de agua visible que explique la máscara antigua. |
| Niebla | 36.069 | 9.970 | 26.099 | 0 | Mantiene detecciones parciales en la zona del embalse; la máscara antigua cubría más terreno. |

En La Mierla, el percentil 85 de rojo/verde SWIR es `−0,0137` y el 85 % de los píxeles despejados tiene esa relación negativa. Usar `relación <= percentil` convierte un valor más negativo —predominio verde— en evidencia favorable y deja fuera valores neutros. No se interpreta la ausencia de rojo como evidencia suficiente de agua.

La alternativa pone en cero los máximos cromáticos cuando el percentil de predominio rojo o rojo/verde es negativo. Después veta vegetación solo si coinciden predominio verde en True Color, predominio verde rojo/verde en SWIR y cromaticidad SWIR alta respecto de la escena. Para los candidatos oscuros pide además cromaticidad baja o apoyo azul de True Color con poco verde. Una vecindad 3×3 descarta candidatos aislados sin imponer un tamaño mínimo, por lo que los cuerpos pequeños coherentes pueden permanecer.

Se midió desviación estándar local de luminancia SWIR con una ventana 7×7, pero no se usó como umbral: la textura del agua, las orillas y el terreno se solapan; un corte habría quitado agua real y favorecido algunos parches homogéneos de terreno. La coherencia vecinal se limita a retirar motas.

## Regresión en la segmentación de incendio

Con contextual a sensibilidad 6, Madrid–Ávila cambia de 77.044 a 78.937 píxeles finales de incendio: 1.920 añadidos y 27 retirados. El 53,65 % de los añadidos tiene predominio verde visible `> 0,15`; el 90,52 % tiene relación rojo/verde SWIR `< −0,1`. La máscara intermedia añade 2.125 píxeles; 99,2 % estaba dentro de la máscara antigua de agua. El panel muestra candidatos nuevos sobre terreno verde.

La causa inmediata está en `pyroscope/detectores/swir_histeresis.py`: las semillas y el crecimiento aceptan estos píxeles mientras su señal verde visible no supere el percentil 90. K-Means también mostró un cambio final de +1.260 píxeles en Madrid–Ávila a sensibilidad 5, aunque su máscara candidata solo cambió en 2 píxeles, lo que apunta a interacción con la etapa geométrica.

Por esta regresión, la alternativa queda experimental. No se conecta a los detectores activos ni se etiqueta vegetación como agua para ocultar los falsos incendios. El criterio de ausencia de regresiones importantes aún no se cumple.

## Random Forest y pruebas

No está presente `training Random Forest/random_forest.joblib`; el registro no expone el detector sin ese modelo, así que no se pudieron reproducir sus predicciones ni inspeccionar etiquetas reales. No se cambió su entrenamiento ni el clasificador. Las pruebas sintéticas de integración de RF sí se ejecutaron.

Pruebas ejecutadas sobre el checkout actual:

- `python -m pytest tests/test_agua.py tests/test_calibracion_segmentacion.py`: **41 pasaron**.
- `python -m pytest tests/test_random_forest_integracion.py`: **7 pasaron**.

Los casos sintéticos cubren agua neutra pequeña con percentil rojo/verde negativo, vegetación intensa y oscura, suelo quemado, humo, escena uniforme y escena sin agua. Sirven para comprobar la lógica, no su precisión en imágenes reales.

Panel contextual a sensibilidad 6: `sensibilidad_6/panel_contextual_sensibilidad_6.png`. Comparación de incendio para los cuatro detectores: `despues/panel_antes_despues_agua_e_incendio.png`.
