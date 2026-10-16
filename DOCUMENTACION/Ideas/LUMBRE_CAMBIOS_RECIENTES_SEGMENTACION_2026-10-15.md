# Evolución reciente de la segmentación

Registro resumido de decisiones y aprendizajes de las iteraciones del 15/10/2026. El detalle numérico y los comandos de aquella evaluación están en [`segmentacion_contextual_evaluacion.md`](segmentacion_contextual_evaluacion.md); el uso vigente está en el [README principal](../../README.md).

## Cambios y aprendizajes

1. **De candidatos a regiones:** K-Means y el detector SWIR con histéresis aportan propuestas semánticas; la geometría organiza componentes y controla regiones separadas. Un contorno más completo no demuestra mayor exactitud.
2. **Método contextual híbrido:** se incorporaron superpíxeles SLIC, relaciones entre regiones (RAG), crecimiento limitado y Watershed local. Se dejó como método experimental y actualmente aparece seleccionado al abrir la aplicación.
3. **Humo separado del terreno:** la máscara de oclusión, la superficie observada, las hipótesis espectrales/de continuidad bajo humo y el terreno desconocido se representan por separado. Reducir la hipótesis bajo humo es una abstención más conservadora, no prueba que el terreno se haya reconstruido mejor.
4. **Perfil de sensibilidad:** la revisión visual motivó pasar de 5 a 6. La sensibilidad 7 duplicó aproximadamente los candidatos de Valpaços en la rejilla comparada, así que no se eligió como valor inicial.
5. **Random Forest:** idea iniciada durante el Malackathon; se prepararon características, entrenador e integración, pero nunca se completó el etiquetado manual y alineado de píxeles. Se acabó el tiempo antes de crear el dataset, entrenar y evaluar el modelo. Está desactivado en la aplicación actual y no interviene en sus resultados; véase el [estado detallado](random_forest_aplicacion_deteccion_incendios.md).

## Qué falta demostrar

Las comparaciones existentes usan recuentos de píxeles y casos sintéticos. No hay máscaras reales independientes que permitan afirmar precisión, recall, IoU o mejora científica en La Mierla, Madrid–Ávila o Niebla. Tampoco deben mezclarse los recuentos de rejillas de distinto tamaño ni presentarse la estimación bajo humo como superficie observada.

El siguiente paso de mayor valor es obtener referencias fechadas y georreferenciadas, alinearlas con cada escena y revisar falsos positivos y omisiones. Mantener separados observación, clasificación, simulación y riesgo mientras se valida.
