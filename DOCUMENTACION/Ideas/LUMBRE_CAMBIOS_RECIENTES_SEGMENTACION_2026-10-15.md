# Lumbre — Cambios recientes de segmentación, tratamiento del humo y arquitectura para el reto avanzado

**Fecha:** 15 de octubre de 2026  
**Repositorio:** [`emilioreato/harryelsucio`](https://github.com/emilioreato/harryelsucio)  
**Referencia revisada:** `main`, commit `cadac708ed45f078a21ca9efde6ee9a503509989`  
**Alcance:** decisiones tomadas durante las últimas iteraciones, implementación que efectivamente aparece en el código, verificaciones documentadas, limitaciones y próximos pasos.  
**Importante:** se inspeccionó el repositorio y su informe de evaluación. Los resultados experimentales que figuran abajo son **los registrados en el repositorio**; no se han repetido en esta revisión.

## 1. Resumen ejecutivo

El sistema pasó de depender principalmente de una **clasificación por píxel**, con filtrado espacial posterior, a disponer también de un **motor híbrido contextual**, capaz de estudiar píxeles y regiones a distintas escalas. Paralelamente, el humo dejó de tratarse como una clase de terreno excluyente: se formalizó una **capa atmosférica independiente**, con hipótesis de superficie afectada bajo humo y áreas explícitamente desconocidas.

La decisión central es **separar semántica, organización espacial y geometría**, sin confundir las señales del sensor con clases científicas confirmadas:

1. **Semántica:** qué evidencias en True Color y SWIR son compatibles con terreno afectado.
2. **Espacio:** cómo se agrupan esos píxeles en regiones coherentes, conectadas o independientes.
3. **Fronteras:** dónde debe quedar el límite de cada región.
4. **Oclusión:** qué suelo está observado, qué puede inferirse bajo humo y qué continúa siendo desconocido.
5. **Validación:** qué cambios efectivamente ayudan, distinguiendo geometría y tiempos de **exactitud**.

La nueva ruta ya está integrada y es ejecutable, pero **continúa marcada como experimental**: no se dispone aún de verdad terreno independiente y suficientemente alineada para demostrar una mejora de IoU, F1 o precisión real.

## 2. Por qué cambiamos la estrategia

### Enfoque anterior

- **K-Means** clasificaba por patrones cromáticos de las dos composiciones; después se elegían candidatos con heurísticas.
- **SWIR + histéresis (V2)** obtenía semillas de contraste fuerte y extendía candidaturas por píxeles conectados con señales más débiles.
- Una **fusión ponderada** combinaba máscaras binarias. Con pesos 0,5/0,5 y umbral 0,55, en la práctica requería coincidencia de ambos clasificadores, de modo que podía perder regiones encontradas por uno solo.
- La etapa espacial limpiaba ruido y podía concentrarse en el componente más grande, perjudicando incendios independientes. Su antiguo tratamiento de la proximidad podía recortar parte de un mismo componente, y `RETR_EXTERNAL` omitía agujeros interiores.
- Se detectaba humo, pero el resultado visible excluía los píxeles ocluidos y la hipótesis bajo humo dependía demasiado de mantener la firma espectral a pesar del velo.

### Decisión nueva

No conviene elegir entre «primero todos los píxeles» o «primero todas las regiones» como único modelo. El enfoque adoptado usa **dos escalas complementarias**:

- **Por píxel**, para señales espectrales, focos pequeños, zonas mixtas y precisión de frontera.
- **Por región**, para estabilidad espacial, continuidad, vecindad y decisiones sobre superficies completas.

SLIC no sustituye el reconocimiento semántico. Organiza la imagen en superpíxeles; los detectores aportan la evidencia sobre su contenido. Un superpíxel de apariencia uniforme puede contener categorías distintas, por lo que los píxeles originales siguen disponibles y se preservan las decisiones en regiones mixtas.

## 3. Nuevo pipeline híbrido contextual, implementado

```text
True Color + SWIR (misma escena y adquisición)
        |
        v
Características comunes + detección de agua y humo
        |
        v
V2 SWIR/histéresis: evidencia semántica por píxel
        |
        +------------------------------+
        |                              |
        v                              v
Semillas y score ordinal        SLIC en representación conjunta
        |                              |
        +--------------+---------------+
                       v
       Estadísticas y clases de superpíxeles
                       |
                       v
         RAG: vecindad y uniones restringidas
                       |
                       v
          Crecimiento espacial limitado
                       |
                       v
       Watershed local si hay marcadores útiles
                       |
                       v
      Limpieza geométrica, máscaras y perímetros
                       |
              +--------+---------+
              v                  v
     Superficie visible   Inferencia bajo humo
              |                  |
              +--------+---------+
                       v
         Capas, métricas y exportaciones
```

### 3.1. Semántica actual: V2 como entrada

La ruta `contextual_hibrida` utiliza actualmente **SWIR V2** como clasificador inicial, mediante `pyroscope/detectores/contextual.py`. El adaptador `pyroscope/evidencia_contextual.py` produce scores **ordinales**, no probabilidades calibradas, aprovechando los umbrales de V2. Corrige además el caso degenerado de una escena uniforme gris sin señales de incendio: los percentiles por sí solos no deben inventar semillas.

**Consecuencia importante:** el motor regional puede organizar y perfeccionar una propuesta, pero **no garantiza recuperar una cicatriz completamente omitida por V2**. Random Forest podría mejorar esta etapa cuando se disponga de entrenamiento fiable; no es una dependencia del nuevo motor.

### 3.2. SLIC: creación de superpíxeles

Nuevo módulo: `pyroscope/regiones_contextuales.py`.

- Usa una representación conjunta de **seis canales RGB renderizados** (True Color + SWIR), normalizados por cuantiles 2–98; no son seis reflectancias físicas originales.
- Parámetros registrados: `convert2lab=False`, `channel_axis=-1`, `compactness=0.12`, `sigma=0.6` y tamaño objetivo aproximado de **144 píxeles por superpíxel**.
- La ejecución se concentra en recortes de contexto alrededor de **todos** los candidatos y un halo de **24 píxeles**, sin perder las cicatrices alejadas.
- Se probaron representaciones de True Color, SWIR y conjunta; se dejó la conjunta por aprovechar ambas vistas, **no porque haya demostrado mayor precisión frente a etiquetas reales**.

### 3.3. Estadísticas regionales y RAG

Para cada superpíxel se calculan medias, medianas, dispersión, fracciones de píxeles candidatos y de evidencia fuerte/moderada, agua, humo, gradiente y vecindad. Las regiones se describen como exterior, interior fiable, ambigua o parcialmente ocluida.

Un **Region Adjacency Graph (RAG)** permite fusionar vecinos únicamente cuando hay evidencia moderada en ambos lados, compatibilidad cromática y una frontera compartida suficientemente débil; las contradicciones de agua/humo penalizan la unión. El nodo exterior no puede actuar como puente para unir incendios.

**Decisión esencial:** una unión geométrica no equivale a decir automáticamente que toda la región sea suelo quemado; se conserva la evidencia por píxel.

### 3.4. Crecimiento espacial restringido

- Parte de semillas fuertes y propuestas existentes.
- Puede ampliar candidatos en regiones respaldadas por evidencia moderada.
- El crecimiento no se propaga indefinidamente: la distancia máxima al candidato original es de **8 píxeles** de trabajo.
- Rechaza verdor fuertemente incompatible y saltos a través de bordes marcados sin evidencia suficiente.
- Los píxeles recién incorporados **no** se convierten en nuevas anclas para seguir extendiendo el crecimiento.

### 3.5. Watershed localizado

- No se aplica ciegamente a toda la escena: analiza bandas de **2 píxeles** alrededor de bordes dudosos.
- Exige al menos **tres marcadores positivos y tres negativos** en cada región refinable.
- Rechaza cambios superiores al **15 %** de la banda o que añadan píxeles sin soporte suficiente; en esos casos conserva el borde previo.
- En las pruebas registradas introdujo cambios pequeños. **No se ha demostrado aún que mejore la exactitud real.**

**GrabCut** queda como experimento eventual, no forma parte necesaria de la ruta contextual implementada; tampoco se incorpora SAM como motor principal ni se añade una red neuronal pesada sin evidencia de valor.

## 4. Cambios de geometría

En `pyroscope/geometria_segmentacion.py` se introdujeron correcciones que ahora figuran en el código:

- El filtro de distancia acepta o descarta **componentes conectados completos**: ya no corta artificialmente el perímetro de un componente que cruza el radio.
- El modo contextual usa `conservar_regiones_separadas=True` para preservar incendios independientes que superen el tamaño mínimo.
- Utiliza `preservar_geometria=True` para evitar apertura/cierre morfológicos adicionales que alterarían bordes ya refinados.
- En ese modo, extrae contornos con `RETR_LIST`, incluidos bordes interiores/agujeros. Los métodos clásicos conservan `RETR_EXTERNAL` y sus opciones históricas.

Este trabajo corrige defectos geométricos identificables **sin afirmar por ello una mejora de clasificación semántica**.

## 5. Cambio conceptual principal: humo y suelo son capas diferentes

La observación que impulsó esta parte fue correcta: **el humo está por encima del terreno; no transforma el suelo en una clase «humo»**. Una misma posición puede tener humo atmosférico y, simultáneamente, suelo potencialmente quemado debajo.

Ahora hay una separación explícita:

| Capa | Qué significa | Efecto sobre el área observada |
|---|---|---|
| Superficie afectada visible | Evidencia de suelo candidato donde hay observación disponible | **Sí**, integra la máscara principal |
| Humo probable | Oclusión atmosférica | No determina por sí solo el tipo de suelo |
| Bajo humo: evidencia espectral | Señal compatible con superficie afectada que sobrevive a parte de la oclusión | **No** se suma al área observada |
| Bajo humo: continuidad espacial | Puente corto sustentado por región visible en ambos extremos | **No** se suma al área observada |
| Terreno indeterminado | Suelo bajo humo para el que no se justifica ninguna hipótesis | Permanece desconocido |

### 5.1. Detección del velo en True Color

Se incorporó `pyroscope/humo_visible.py` como ampliación del humo anclado en SWIR. Busca velo visible cercano utilizando luminosidad, neutralidad y textura atenuada; impone una distancia limitada al humo original. Evita declarar automáticamente humo toda superficie clara y no convierte la máscara de incendio en semilla atmosférica.

### 5.2. Estimador independiente bajo humo

Nuevo módulo: `pyroscope/estimacion_bajo_humo.py`, con tres salidas diferenciadas:

- `mascara_espectral`
- `mascara_continuidad`
- `mascara_indeterminada`

**Ruta espectral:** exige señal compatible y crecimiento limitado desde áreas visibles con evidencia fiable; agua y contradicciones bloquean la expansión.

**Ruta de continuidad:** busca huecos **cortos** cubiertos por humo, con dos extremos observados, en direcciones horizontal, vertical y diagonales. Las hipótesis inferidas no se reutilizan como nuevas anclas, evitando encadenar extrapolaciones. El límite principal empleado en la integración es `max(3, min(24, round(lado_menor * 0.015)))` píxeles de la rejilla de trabajo; la ruta espectral puede tener otro radio, también limitado.

**Abstención:** una nube amplia sin evidencias suficientes permanece desconocida; no se rellena arbitrariamente como quemada. Esto puede **reducir considerablemente** la cantidad de píxeles fucsia, incluso dejando fuera terreno verdaderamente afectado; la reducción no es una mejora de exactitud demostrada.

### 5.3. Capas y representación gráfica

`pyroscope/visualizacion.py`, `pyroscope/servidor_web.py` y el frontend React exponen el resultado sin confundir atmósfera y terreno. En la superposición actual, **rojo/borde amarillo** representa la suma visual de área candidata visible e hipótesis bajo humo, mientras una **capa azul translúcida** queda por encima indicando humo; la capa `mask` exportada y las métricas de área observada contienen **solo** superficie visible. Las capas bajo humo se pueden descargar por separado. Es importante no interpretar el contorno combinado de la superposición como el perímetro medido de terreno observado.

Se habilitaron, entre otras, capas `smoke`, `smoke-candidates`, `smoke-unknown`, `smoke-spectral`, `smoke-continuity` y diagnósticos del proceso contextual. La interfaz añade **«Capas de humo y diagnóstico»** con vistas y exportación PNG.

## 6. Integración real en la aplicación

- Detector nuevo registrado: **`contextual_hibrida`**, nombre visible «Segmentación contextual híbrida (experimental)».
- Se mantienen **K-Means**, **SWIR + histéresis V2** y **fusión ponderada** para comparación.
- El clasificador anterior y Random Forest quedan desacoplados del motor espacial mediante máscaras y scores opcionales. En el HEAD revisado el modo contextual se alimenta de V2; **no hay que afirmar que Random Forest ya esté conectado**.
- El pipeline contextual utiliza hasta **2500 píxeles de lado**, frente a **1800** para los modos previos. La Mierla y Niebla pueden conservar su tamaño nativo; Madrid–Ávila se reduce desde su resolución original mayor.
- El backend Python (`pyroscope/servidor_web.py`) entrega las nuevas capas y métricas; React (`frontend/src/App.jsx`) permite seleccionarlas y descargarlas.
- Según el README del commit revisado, **K-Means aún continúa predeterminado**, aunque el nuevo modo contextual aparece como primera opción del registro. No dar por cambiado el valor efectivo por defecto sin inspeccionar el comportamiento de la UI correspondiente.
- Se mantienen las invariantes de escala: las mediciones físicas requieren GSD fiable; JPEG True Color/SWIR no son bandas originales, ni proporcionan automáticamente georreferenciación.

## 7. Resultados documentados de las tres escenas

### 7.1. Comparación controlada a **1800 × 1113** píxeles

Los siguientes datos proceden de `DOCUMENTACION/Ideas/segmentacion_contextual_evaluacion.md`, no de una nueva ejecución. Son **tamaños de máscaras**, no precisión ni hectáreas.

| Escena | V2 anterior | SLIC | SLIC + RAG | + Watershed | Tiempo semántico + espacial WS |
|---|---:|---:|---:|---:|---:|
| La Mierla | 176 623 px | 193 011 px | 193 027 px | 193 027 px | 1,73 + 9,23 s |
| Madrid–Ávila | 70 717 px | 88 361 px | 88 369 px | 88 506 px | 1,35 + 10,19 s |
| Niebla | 94 390 px | 99 421 px | 99 429 px | 99 443 px | 1,17 + 8,68 s |

Interpretación prudente:

- Los cambios de tamaño frente a V2 proceden **principalmente de la geometría y de conservar regiones separadas**, no de que RAG y Watershed hayan probado su superioridad.
- RAG registró **955 / 316 / 520 uniones** en La Mierla, Madrid–Ávila y Niebla, pero las diferencias finales respecto a SLIC fueron de **16 / 8 / 8 píxeles**.
- Watershed introdujo **14 / 159 / 36 cambios de píxel** frente a RAG. Un número parecido de píxeles totales no significa idéntica geometría.
- El uso de recortes contextuales redujo el tiempo espacial aproximadamente **19–23 %** frente a ejecutar SLIC sobre toda la imagen en aquella prueba, con variabilidad de ejecución concurrente.

### 7.2. Hipótesis bajo humo a resolución de comparación

| Escena | Hipótesis anterior | Nueva hipótesis | Nueva: espectral / continuidad |
|---|---:|---:|---:|
| La Mierla | 432 px | 31 px | 27 / 4 |
| Madrid–Ávila | 349 px | 68 px | 20 / 48 |
| Niebla | 16 024 px | 2 058 px | 1 617 / 441 |

La reducción refleja una **política mucho más conservadora**. Parte importante del humo de Niebla permanece indeterminado. No significa que el algoritmo haya encontrado todo el suelo quemado debajo del humo.

### 7.3. Verificación HTTP final, modo contextual a **2500 × 1546**

| Escena | Superficie visible | Hipótesis bajo humo | Recorrido HTTP informado |
|---|---:|---:|---:|
| La Mierla | 360 797 px | 58 px | 32,07 s |
| Madrid–Ávila | 164 103 px | 140 px | 30,19 s |
| Niebla | 185 269 px | 3 351 px | 24,67 s |

El informe del repo indica que se verificaron carga, análisis, **22 capas por escena**, coherencia de rejilla, exclusión humo/superficie observada, separación de la hipótesis bajo humo y exportaciones PNG; también se comprobó parte de la UI en navegador y la compilación Vite. **No comparar numéricamente estas áreas con las de 1800 píxeles**, pues la rejilla es distinta.

## 8. Tests, scripts y herramientas añadidas

| Archivo | Uso |
|---|---|
| `scripts/comparar_contextual.py` | Baselines y comparación SLIC / RAG / Watershed; máscaras, diagnósticos y tiempos |
| `scripts/comparar_capas_humo.py` | Comparar y revisar visualmente capas de humo |
| `scripts/evaluar_humo_sintetico.py` | Seis oclusiones conocidas; valida puentes, ausencia de incendios y abstención |
| `scripts/verificar_http_contextual.py` | Prueba carga, API, capas, exportaciones y coherencia |
| `tests/test_regiones_contextuales.py` | Comportamiento de SLIC, RAG y crecimiento |
| `tests/test_geometria_contextual.py` | Regiones independientes, agujeros, proximidad y limpieza |
| `tests/test_estimacion_bajo_humo.py` | Huecos estrechos, columnas extensas, obstáculos, inferencia espectral y validación de entrada |
| `tests/test_capas_suelo_humo.py` | Separación y coherencia de capas de superficie, humo e incertidumbre |

Comandos relevantes desde la raíz del repositorio:

```powershell
python -m pytest tests/test_regiones_contextuales.py tests/test_geometria_contextual.py tests/test_estimacion_bajo_humo.py tests/test_capas_suelo_humo.py -q
python scripts/comparar_contextual.py --fase baseline
python scripts/comparar_contextual.py --fase contextual_roi
python scripts/evaluar_humo_sintetico.py
python scripts/verificar_http_contextual.py --url http://127.0.0.1:8501
```

Los experimentos producen artefactos en `resultados_contextual/`, que permanece excluida de Git. El informe enumera comparativas, diagnósticos, máscaras, exportaciones y pruebas sintéticas. Las pruebas sintéticas comprueban corrección lógica **en sus escenarios definidos**, no la exactitud de reconstruir una escena real oculta por humo.

## 9. Trabajo concurrente: Random Forest

Otro colaborador trabaja con Random Forest. Se decidió evitar conflictos y mantener los módulos nuevos independientes del entrenamiento:

- **Random Forest sería un clasificador supervisado de evidencias**, no el encargado exclusivo de delimitar superficies y fronteras.
- El motor SLIC/RAG/crecimiento/Watershed recibe máscaras y, opcionalmente, scores; en el futuro podrá consumir resultados de RF a través de un adaptador.
- No confundir etiquetas de humo con etiquetas de terreno: un mismo lugar puede estar ocluido y tener suelo de una clase todavía desconocida.
- El entrenamiento requiere máscaras de referencia reales y alineadas. Las capturas ilustrativas en `training Random Forest/` no equivalen por sí solas a etiquetas por píxel.
- **En el commit revisado no se observa una integración de Random Forest en el registro de detectores**. No se deben editar ni sobreescribir los archivos de entrenamiento ajenos sin coordinación.

## 10. Preparación para el reto avanzado

El reto básico trata de delimitar **superficie candidata afectada**; el avanzado busca **posible fuego activo**. Son objetivos distintos y pueden coexistir en distintas capas.

Arquitectura acordada:

- Reutilizar el cargador de escenas, características, agua, humo, coordenadas, diagnóstico y exportación.
- Mantener un **detector independiente de fuego activo** con capacidad de trabajar por píxel y no quedar obligado a SLIC: un foco pequeño puede diluirse dentro de un superpíxel grande.
- Cuando se disponga de productos originales, admitir bandas espectrales reales Sentinel-2, metadatos, georreferenciación y otras fechas. No calcular NBR/dNBR ni temperaturas físicas a partir de JPEG RGB renderizados.
- No modelar automáticamente toda la superficie quemada como frente en combustión.
- Conservar incertidumbres diferenciadas de clasificación, oclusión, inferencia y simulación eventual.

**No consta todavía implementado un detector validado de fuego activo**, ni un pipeline físico multibanda/temporal completo.

## 11. Qué sigue pendiente y cómo decidir

### Prioridad alta: demostrar mejora real

1. Crear pequeñas **máscaras de referencia independientes** para cada escena: interiores afectados, exteriores inequívocos, fronteras, falsos positivos y zonas ocluidas etiquetadas como desconocidas donde corresponda.
2. Contrastar posibles perímetros oficiales (Copernicus EMS / EFFIS) **solo después de verificar fecha de adquisición, AOI y alineación geográfica**. Perímetros producidos después del incendio no son verdad del instante del JPEG.
3. Calcular IoU, precision, recall, F1/Dice y error de frontera en píxeles válidos, manteniendo regiones/escenas de prueba separadas de las usadas para calibrar.
4. Comprobar especialmente que no se confunde rojo SWIR asociado a posible actividad con toda la cicatriz quemada, y que vegetación, agua y suelo oscuro no generan falsos positivos sistemáticos.
5. Comparar tres variantes con la **misma resolución**: V2 histórica, V2 con geometría corregida y contextual SLIC/RAG/Watershed. Separar claramente qué ganancia procede de cada etapa.
6. En el humo, validar precisión y cobertura de la inferencia frente a casos anotados o multitemporales; **abstenerse** cuando no sea posible ver o deducir la superficie.

### Prioridad media: evolución controlada

- Integrar Random Forest mediante un adaptador cuando esté entrenado y evaluado.
- Ajustar SLIC y las reglas RAG solo cuando exista un error concreto reproducible; RAG y Watershed actualmente modifican pocos píxeles, por lo que su complejidad debe justificarse.
- Conservar y mejorar el sistema de **diagnóstico etapa por etapa**; las máscaras intermedias y exportaciones ya existen, pero cualquier visor más avanzado debe alimentarse de estas salidas sin reescribir los algoritmos.
- Definir las fuentes y contratos del avanzado para fuego activo, sin confundirlo con superficie quemada.

### Lo que NO debe afirmarse todavía

- Que la V3 sea más exacta que la V2 en términos científicos; **faltan etiquetas independientes**.
- Que una reducción de candidatos bajo humo pruebe mejor recuperación del suelo.
- Que un score heurístico sea una probabilidad calibrada.
- Que el color de un JPEG SWIR tenga un significado físico idéntico en todas las exportaciones.
- Que el tamaño del JPEG demuestre escala, GSD efectivo o alineación geográfica.
- Que Random Forest o el detector avanzado estén integrados si no aparecen efectivamente en el código.

## 12. Archivos principales modificados o introducidos

**Motores nuevos:**

- `pyroscope/regiones_contextuales.py`
- `pyroscope/evidencia_contextual.py`
- `pyroscope/detectores/contextual.py`
- `pyroscope/estimacion_bajo_humo.py`
- `pyroscope/humo_visible.py`

**Integración del motor, geometría y contratos:**

- `pyroscope/segmentacion.py`
- `pyroscope/geometria_segmentacion.py`
- `pyroscope/modelos_segmentacion.py`
- `pyroscope/detectores/registro.py`
- `pyroscope/detectores/swir_histeresis.py` (reutilización opcional de características)
- `pyroscope/interfaz/configuracion.py`
- `pyroscope/interfaz/procesamiento.py`

**Resultados y UI:**

- `pyroscope/visualizacion.py`
- `pyroscope/servidor_web.py`
- `frontend/src/App.jsx`
- paquete estático compilado en `web/`

**Comprobación y documentación:**

- `DOCUMENTACION/Ideas/segmentacion_contextual_evaluacion.md`
- `scripts/comparar_contextual.py`, `scripts/comparar_capas_humo.py`, `scripts/evaluar_humo_sintetico.py`, `scripts/verificar_http_contextual.py`
- `tests/test_regiones_contextuales.py`, `tests/test_geometria_contextual.py`, `tests/test_estimacion_bajo_humo.py`, `tests/test_capas_suelo_humo.py`
- `README.md` y `.gitignore`

## 13. Síntesis final

**Antes:** buscar píxeles con apariencia compatible con incendio, unirlos mediante filtros espaciales y excluir el humo del resultado observado.

**Ahora:** detectar evidencia semántica por píxel, dividir y estudiar regiones mediante SLIC, conectar regiones compatibles con RAG, crecer con límites estrictos, corregir fronteras localmente y representar el humo como una capa atmosférica distinta de la superficie. Bajo humo se distinguen evidencia espectral, continuidad corta y terreno desconocido. Todo ello se expone en el motor, la API y la interfaz, con comparativas reproducibles.

**El avance demostrado es arquitectónico, geométrico y funcional. El avance en exactitud científica sigue pendiente de validación independiente.** Esta distinción es la guía para seguir mejorando sin añadir complejidad que solo haga que el resultado parezca más sofisticado.

---

**Fuente primaria de esta síntesis:** código del commit `cadac708ed45f078a21ca9efde6ee9a503509989` y documento del propio repositorio [`segmentacion_contextual_evaluacion.md`](https://github.com/emilioreato/harryelsucio/blob/main/DOCUMENTACION/Ideas/segmentacion_contextual_evaluacion.md). Es un informe de consolidación; no ejecuta ni modifica el proyecto.
