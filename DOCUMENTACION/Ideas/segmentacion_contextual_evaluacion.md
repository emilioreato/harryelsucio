# Segmentación contextual: evaluación del 15/10/2026

Implementación experimental sobre HEAD `a9cfe602a40ddfba56e9b371a74eae8d91468bb0`. Se comprobaron mediante `git ls-remote` los HEAD de harryelsucio y del remoto local malackathon: ambos coincidían. Se preservaron cambios previos de React, mediciones y servidor. Sin commits ni push. No se modificó entrenamiento, etiquetas ni modelos Random Forest.

## Implementación y parámetros

`regiones_contextuales.py` recibe pareja RGB alineada, máscara candidata, agua, humo y evidencia opcional finita [0,1]. Los scores son heurísticos, no probabilidades. Admite cualquier clasificador; sin scores conserva detalle por píxel. `evidencia_contextual.py` adapta los umbrales reales de V2. El adaptador `detectores/contextual.py` evita semillas degeneradas en escenas neutras uniformes. V2 solo añade un campo opcional para reutilizar características; su clasificación permanece igual.

SLIC usa seis canales RGB normalizados por cuantiles 2–98, `convert2lab=False`, `channel_axis=-1`, compactness=.12, sigma=.6 y área objetivo de 144 píxeles. Se compararon True Color, SWIR y conjunta: no hay verdad terreno que permita declarar una representación ganadora. Se conserva conjunta para atender fronteras de ambas vistas.

El contexto son todos los candidatos y un halo de 24 píxeles. Se procesan sus recortes conectados sin remuestrearlos; el nodo exterior cero no puede fusionar cicatrices. La opción de máscara interna SLIC resultó más lenta y se descartó. Se calculan medias, medianas, dispersión, fracciones de evidencia fuerte/moderada, agua, humo, gradiente y vecinos. Los superpíxeles mixtos conservan la decisión individual de sus píxeles.

RAG exige evidencia moderada en ambos lados, similitud cromática y borde compartido débil, salvo evidencia muy alta en ambos lados; agua/humo penalizan la unión. Crecimiento por componentes con semillas, distancia máxima de 8 píxeles desde la evidencia original, veto de verdor contradictorio y fronteras fuertes. Nunca se usan incorporaciones como nuevas anclas de distancia. Watershed actúa solo en bandas de 2 píxeles con al menos tres marcadores de cada signo; mantiene fallback si cambia más del 15% de la banda o añade píxeles sin soporte suficiente.

El híbrido conserva componentes independientes sobre el tamaño mínimo y agujeros internos, omitiendo apertura/cierre adicional. La corrección común de proximidad acepta o rechaza componentes completos, sin recortarlos al radio. Los métodos anteriores conservan su morfología y su opción de regiones separadas.

`estimacion_bajo_humo.py` separa evidencia espectral, continuidad e indeterminación. Continuidad exige dos extremos observados y tramos rectos cortos en cuatro direcciones; agua y contradicciones bloquean. La ruta espectral crece un número acotado de pasos desde superficie visible. Límite de aplicación: `max(3,min(24,round(lado_menor*.015)))` píxeles de trabajo. No reconstruye nubes extensas y ninguna hipótesis suma al área/perímetro observados.

## Comparación controlada: todas las variantes a 1800 × 1113

No existen máscaras de referencia válidas. Los JPEG Wildfires son composiciones, no etiquetas. Estos recuentos no son accuracy ni superficie terrestre.

| Escena | V2 baseline px | SLIC px | RAG px | Watershed px | Tiempo espacial WS + semántica |
|---|---:|---:|---:|---:|---:|
| La Mierla | 176623 | 193011 | 193027 | 193027 | 9.23 + 1.73 s |
| Madrid–Ávila | 70717 | 88361 | 88369 | 88506 | 10.19 + 1.35 s |
| Niebla | 94390 | 99421 | 99429 | 99443 | 8.68 + 1.17 s |

RAG realizó 955/316/520 uniones, cambiando 16/8/8 píxeles finales frente a SLIC. Watershed cambió 14/159/36 píxeles frente a RAG; igual recuento de área no significa máscara idéntica. Las diferencias grandes frente al baseline proceden principalmente del filtro geométrico y de conservar regiones independientes. La prolongación suroeste de La Mierla es visualmente compatible con SWIR, pero requiere anotación independiente. No se ha demostrado una mejora de precisión atribuible a RAG/Watershed.

Los recortes redujeron el tiempo espacial aproximadamente 19–23% frente a SLIC sobre toda la imagen en esta ejecución. Las mediciones varían con la carga concurrente; no son un benchmark aislado.

Hipótesis bajo humo anterior → nueva: La Mierla 432→31 px; Madrid 349→68; Niebla 16024→2058. Desglose espectral/continuidad: 27/4, 20/48 y 1617/441. Es una abstención mucho mayor: puede perder suelo verdaderamente afectado. La nube amplia de Niebla queda mayoritariamente desconocida. No se presenta esto como recuperación validada de humo real.

## Aplicación final: resolución y exportación

El modo contextual usa 2500 de lado; La Mierla/Niebla mantienen los JPEG nativos y Madrid se reduce desde 9930×6141. Los métodos anteriores mantienen 1800 y K-Means continúa predeterminado. El clasificador semántico examina toda la escena; el recorte espacial no puede recuperar una cicatriz completamente omitida por él. Focos activos futuros deben poder operar a nivel de píxel sin SLIC.

La prueba HTTP final cargó las tres escenas, analizó y descargó las 22 capas por escena, comprobando tamaño de rejilla, exclusión entre superficie observada y humo, hipótesis contenida en humo, separación espectral/continuidad y desconocido, y área sin hipótesis. Sin GSD, unidades px².

| Escena | Rejilla | Superficie visible px | Hipótesis bajo humo px | HTTP con exportaciones |
|---|---|---:|---:|---:|
| La Mierla | 2500×1546 | 360797 | 58 | 32.07 s |
| Madrid–Ávila | 2500×1546 | 164103 | 140 | 30.19 s |
| Niebla | 2500×1546 | 185269 | 3351 | 24.67 s |

No comparar directamente estos recuentos con los de 1800. Se verificó en navegador el selector, análisis completo de La Mierla y Niebla, resultado y acceso a capas. Vite compiló correctamente. El fucsia se pinta después del humo; el desconocido usa trama gris.

## Archivos y reproducción

- Nuevos motores: `pyroscope/regiones_contextuales.py`, `estimacion_bajo_humo.py`, `evidencia_contextual.py`, `detectores/contextual.py`.
- Integración: `modelos_segmentacion.py`, `segmentacion.py`, `geometria_segmentacion.py`, `detectores/registro.py`, `detectores/swir_histeresis.py` (caché opcional de características), `interfaz/configuracion.py`, `interfaz/procesamiento.py`.
- Presentación/exportación: `visualizacion.py`, `servidor_web.py`, `frontend/src/App.jsx`, paquete Vite en `web/`.
- Verificación: `tests/`, `scripts/comparar_contextual.py`, `scripts/verificar_http_contextual.py`, `scripts/evaluar_humo_sintetico.py`.
- Uso/documentación: README y exclusión de `resultados_contextual/` en `.gitignore`.

Ver comandos en README. Artefactos locales excluidos de Git:

- `resultados_contextual/baseline/`: nueve ejecuciones originales y métricas.
- `resultados_contextual/hibrido/`: experimento completo inicial y representaciones.
- `resultados_contextual/contextual_mask/`: intento parcial descartado por coste.
- `resultados_contextual/contextual_roi/`: comparaciones finales, diagnósticos, perímetros, marcadores y humo por escena.
- `resultados_contextual/http/`: PNG finales a2500, `verificacion.json` y captura `niebla_interfaz.png`.
- `resultados_contextual/sintetico/`: oclusiones conocidas, métricas y paneles reproducibles.

Pruebas focales cubren ausencia de semillas, agua, vegetación incompatible, cicatrices independientes, agujeros, componente completo por proximidad, reproducibilidad, scores inválidos, contexto remoto y fallback Watershed. Las pruebas sintéticas verifican lógica, no reconstrucción de humo real. Escena gris uniforme sin incendio: cero superficie e hipótesis.

Pendiente principal: anotar ejemplos independientes de suelo y fronteras (incluidas falsas alarmas) para IoU, precisión, recall, F1 y frontera reales. Mantener experimental hasta demostrar mejora; ampliar luego datos georreferenciados y fechas mediante adaptadores, sin inferir NBR/dNBR, temperaturas ni georreferenciación de JPEG.

## Perfil inicial y matriz de regresión — 15/10/2026

El perfil inicial arrancaba con sensibilidad 5, área mínima 0,15 %, radio máximo 10 %, focos separados desactivados y Random Forest desactivado. No se persiste el estado manual del usuario en el navegador. En sensibilidad 5, la semilla SWIR usa percentil rojo 0,922 y el crecimiento 0,900; además, se exige dominancia roja mínima 0,05 para semillas y -0,02 para crecer. El umbral alto anterior elegía solo el extremo cromático más fuerte y, en una escena sintética con un incendio y una mancha naranja remota, podía sembrar la mancha y omitir el incendio. El nuevo cuantil y el filtro espacial conservaron el incendio y eliminaron esa mancha en el caso construido. El perfil vigente se reajustó a sensibilidad 6 en la sección de recalibración inferior.

La ruta de agua se hizo conservadora ante rejillas uniformes o con muy poco contraste para no clasificar todo como agua. Su percentil de relación rojo/verde SWIR por defecto es 0,85: la prueba de lago azul oscuro se detecta en ambas vistas, donde 0,55 no lo hacía porque la vegetación verde dominaba el histograma. El filtro de distancia vuelve a aplicarse en el método contextual; activar «Conservar focos separados» permite mantener componentes remotos.

La pasada de estabilidad sobre las ocho parejas disponibles, reducidas todas a 900 píxeles de lado, produjo estos conteos con radio 10 % y área mínima 0,15 %:

| Escena | Sens. 4 | Sens. 5 | Sens. 6 |
|---|---:|---:|---:|
| Cinco Villas | 54 343 px | 57 626 px | 60 267 px |
| La Vall d'Uixó | 46 258 px | 49 490 px | 52 969 px |
| Fermoselle | 14 674 px | 15 759 px | 18 355 px |
| Pinzio | 53 525 px | 54 700 px | 55 570 px |
| Valpaços | 10 750 px | 11 162 px | 12 220 px |
| La Mierla | 46 002 px | 49 382 px | 51 908 px |
| Madrid–Ávila | 25 111 px | 26 481 px | 28 238 px |
| Niebla | 21 703 px | 23 041 px | 24 352 px |

En las ocho rejillas el área candidata creció al subir la sensibilidad de 4 a 6; el número de componentes varió entre escenas. En ese primer ajuste se eligió 5 como punto de partida, sin afirmar mejor IoU ni que los conteos fueran áreas reales. La siguiente sección documenta el ajuste posterior a 6. Cada ejecución a 900 píxeles tardó aproximadamente 2,9–4,8 s en esta máquina.

Pruebas focales nuevas:

```powershell
python -m pytest tests/test_agua.py tests/test_calibracion_segmentacion.py -q
python -m pytest tests/test_lumbre_evidencias.py tests/test_geometria_contextual.py tests/test_regiones_contextuales.py tests/test_estimacion_bajo_humo.py -q
python scripts/evaluar_estabilidad_escenas.py --max-lado 900 --sensibilidades 5,6,7
```

Estas pruebas puntúan escenarios sintéticos con etiquetas conocidas. No equivalen a validación con ground truth de La Mierla, Madrid–Ávila o Niebla y no justifican afirmar que el perfil sea óptimo para esas imágenes.

## Recalibración del perfil por omisiones visibles — 15/10/2026

La revisión visual del resultado mostró parches de SWIR rojizos que quedaban fuera del contorno. No son etiquetas de referencia verificadas, pero motivaron probar sensibilidades 5, 6 y 7 en las mismas ocho parejas, en rejillas de 900 píxeles, manteniendo el área mínima en 0,15 % y el radio máximo en 10 %.

| Escena | Sens. 5 | Sens. 6 | Sens. 7 |
|---|---:|---:|---:|
| Cinco Villas | 57 626 px | 60 267 px | 62 962 px |
| La Vall d'Uixó | 49 490 px | 52 969 px | 55 335 px |
| Fermoselle | 15 759 px | 18 355 px | 19 558 px |
| Pinzio | 54 700 px | 55 570 px | 57 005 px |
| Valpaços | 11 162 px | 12 220 px | 26 308 px |
| La Mierla | 49 382 px | 51 908 px | 55 147 px |
| Madrid–Ávila | 26 481 px | 28 238 px | 30 368 px |
| Niebla | 23 041 px | 24 352 px | 27 167 px |

Se establece **sensibilidad 6/10** como nuevo perfil de arranque. Frente a 5, añade entre 1,6 % y 16,5 % de píxeles candidatos en estas escenas. La sensibilidad 7 se descarta como valor inicial porque en Valpaços más que duplica la máscara respecto a 6 (12 220 → 26 308 píxeles), señal de que el umbral relativo puede incorporar mucho fondo en algunas composiciones. Permanecen los vetos de agua y humo, el filtro espacial de 10 % y el área mínima de 0,15 %.

Con sensibilidad 6, la semilla SWIR queda en percentil rojo 0,913 y el crecimiento en 0,890. La prueba sintética de ruido sin incendio sigue vacía incluso a sensibilidad 10; el caso sintético con artefacto remoto conserva la cicatriz y descarta ese componente tanto a sensibilidad 5 como a 6. Esto valida regresiones controladas, no precisión en las escenas reales. Falta comparar contra máscaras manuales o cartografía independiente correctamente alineada antes de medir IoU, precisión o recall reales.
