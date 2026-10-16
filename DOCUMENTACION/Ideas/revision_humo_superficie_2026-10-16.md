# Revisión de humo, superficie y focos — 16/10/2026

Se revisaron los chats «Mejora detección bajo el humo» y «Integra modo avanzado de incendios» con dos subagentes `gpt-6-luna`, razonamiento `max`. Sus informes se contrastaron con el código actual en `lumbre/`, el historial de `main` y el paquete `lumbre_paquete_ia_41dbafca.zip`.

## Qué había cambiado y qué fallaba

- El cambio `4149993` sustituyó la hipótesis antigua bajo humo por una comparación independiente de firmas SWIR. También retiró la compatibilidad SWIR como veto del crecimiento de humo y bajó su corte de `.58` a `.50`. La motivación era recuperar humo sobre suelo rojizo: SWIR puede mostrar el suelo mientras True Color muestra el aerosol. Restaurar ciegamente ese veto volvería a perderlo.
- El adaptador contextual ampliaba el humo hasta un 16 % del lado menor desde sus semillas fuertes, además de una ampliación previa. La evidencia bajo humo toleraba diferencias de hasta `.60` en predominio rojo y `.40` en rojo/verde respecto a firmas visibles; admitía componentes fuertes de solo cuatro píxeles. Esto podía sembrar manchas dispersas y permitir crecimiento a su alrededor.
- SLIC recibía todos los candidatos iniciales. El filtro de tamaño y proximidad llegaba después: el ruido remoto ya había generado grandes regiones de contexto. SLIC conservaba la máscara inicial, por lo que organizar superpíxeles no corregía por sí solo una clasificación incorrecta.
- La estimación bajo humo se producía después de SLIC/RAG/Watershed. No recibía ese refinamiento sobre la textura SWIR.
- La pestaña «Clases» dibujaba candidatos anteriores al filtro final. Mostraba manchas descartadas de la máscara final y agua heurística dispersa. El problema de visualización era adicional al del detector.

## Focos y Wildfires: flujo distinto

Los chats documentan la transición del detector visual True Color + SWIR a la extracción de marcas cálidas y brillantes de la composición Wildfires. El detector anterior excluía humo y limitaba los puntos a ocho píxeles de la superficie candidata: eso explicaba omisiones bajo humo. Hubo una variante incorrecta que conservaba componentes enteros por tener un solo píxel cercano; el código actual del detector visual recorta píxeles por distancia euclídea antes de agruparlos.

Sin embargo, **ese filtro de ocho píxeles no interviene en el camino avanzado activo actual**: el servidor llama a `detectar_focos_wildfires`. Wildfires no es una máscara de etiquetas ni una medida térmica; se extraen marcas de su RGB. El hilo de humo documentó en Niebla 4.758 píxeles/44 componentes, incluidos 2.421 coincidentes con la máscara de humo de esa ejecución. Son pruebas históricas de recuperación de marcas y funcionamiento HTTP, no validación de incendios reales.

## Ajuste implementado en el básico

El servidor básico activa explícitamente el perfil `basic-unified-v1`. El avanzado conserva su ruta y parámetros anteriores, incluida la extracción Wildfires.

1. Ampliación previa de humo más conservadora: radio `.03` en lugar de `.06`, cromaticidad máxima `.32` en lugar de `.38` y textura máxima `.06` en lugar de `.085`.
2. Expansión por niveles limitada a `.04` del lado menor, con puntuación mínima `.60`. No se repone el veto SWIR sobre humo real.
3. Firma oculta calibrada con el cuartil inferior visible, tolerancias moderadas `.30` y `.20`, mínimos cromáticos positivos y componentes fuertes de al menos 16 píxeles.
4. Filtro de tamaño/proximidad antes de SLIC. La selección de regiones separadas sigue respetándose.
5. Estimación oculta restringida por proximidad a la superficie final, seguida de SLIC/RAG/Watershed sobre SWIR. Se descartan componentes ocultos pequeños con un mínimo proporcional al área mínima seleccionada. Un checkpoint y capas diagnósticas muestran ese refinamiento.
6. El agua necesita respaldo cromático y un componente coherente en el perfil básico. Los antiguos píxeles rechazados como agua no se convierten automáticamente en semillas quemadas. Su clasificación sigue siendo heurística.
7. La capa `estimated-surface` une la superficie final y la estimación oculta. El visor, selección de regiones, contorno y descarga de máscara utilizan esa unión. Los controles son «Detección» y «Humo», además del borde; se retiran «Bajo humo» y la pestaña redundante «Clases». El humo se superpone y puede ocultarse sin perder el suelo estimado.
8. El paquete conserva las capas fuente y su procedencia. `mask`, área y perímetro observados conservan su significado; `estimated-surface` y `estimated_surface_pixels` describen la unión estimada. No se rellenan huecos sin evidencia para fabricar conectividad.

## Verificación actual

Reproducción inicial exacta del paquete de Niebla: rejilla de **2500 × 1546**, sensibilidad 6, área mínima `.15 %`, proximidad `10 %`, regiones separadas desactivadas. Los recuentos iniciales coinciden con el manifiesto adjunto.

| Capa o etapa | Inicial | Ajustada |
|---|---:|---:|
| Superficie visible final | 160.195 | 168.492 |
| Superficie estimada bajo humo | 143.221 | 74.368 |
| Humo probable | 674.303 | 595.307 |
| Contexto SLIC visible | 2.254.258 | 271.931 |
| Agua posible | 68.723 | 2.523 |

La unión final contiene **242.860 píxeles**. No equivale al área observada. La reducción de recuentos no demuestra automáticamente mejora de precisión ni valida el nuevo mapa de agua.

Se inició Niebla desde la interfaz local en el puerto 8516. Se verificaron finalización, controles independientes, máscaras PNG por HTTP y generación real del ZIP. La máscara exportada coincide exactamente con `mask OR smoke-candidates`; la hipótesis oculta permanece dentro del humo. Las anotaciones originales no se reinterpretaron como polígonos exhaustivos de verdad terreno.

Se ejecutaron también La Mierla y Madrid–Ávila a **1200 × 742** y se inspeccionaron las imágenes resultantes. Completaron el análisis, conservaron los contratos de unión y oclusión y no fallaron. Esto no demuestra ausencia de omisiones ni permite comparar directamente sus recuentos con Niebla a 2500 px.

Pasaron 42 pruebas focales sobre estimación, regiones, capas, exportación, checkpoints y Wildfires; se repitieron después los controles afectados por los últimos ajustes de observabilidad/exportación. La compilación Vite y los imports Python pasaron. No se instalaron dependencias.

Las salidas de revisión están en `.tmp/pruebas/humo-41dbafca/`, ignoradas por Git. No se guardaron resultados de ejecución en `resultados/` ni se hicieron commits o push. Se preservó la reorganización preexistente `pyroscope/` → `lumbre/` y los cambios ajenos.

## Límites y siguiente revisión

La mejora visual de Niebla es revisable en `final-exportado.png`, pero aún hay fragmentos y bordes inciertos. Hace falta revisar omisiones y falsos positivos en más escenas, con especial atención a agua oscura, terreno rojizo y humo tenue. No hay máscaras independientes suficientes para publicar precisión, recall o IoU. La composición RGB SWIR no permite recuperar bandas físicas ni convertir estos scores en probabilidades.

## Segunda revisión: orígenes del humo y microhuecos

El paquete `lumbre_paquete_ia_e91a51fb.zip` reproduce el perfil v1 y aporta tres trazos de revisión sobre Niebla. El perfil `basic-unified-v2-local-refinement` añade dos pasos posteriores a la segmentación:

- Continuidad de superficie mediante cierre local de radio máximo 3 px y huecos de hasta 113 px en la rejilla de Niebla. Cada píxel añadido necesita firma SWIR compatible; agua, verdor contradictorio y huecos grandes se conservan. Se añaden 3.493 px a la unión estimada. Los microhuecos pasan de 120 a 74; quedan los tres componentes principales.
- Refinamiento de humo sobre la superficie estimada y un margen máximo de 6 px. Exige contraste con suelo despejado cercano, cromaticidad baja, equilibrio de canales compatible con velo, textura admisible y conexión al humo previo dentro de un radio acotado. No convierte automáticamente suelo quemado en humo ni realimenta la clasificación de superficie. Se añaden 19.515 px de humo, de los que 5.946, 1.870 y 4.316 están dentro de las tres regiones aproximadas marcadas por la persona.

Las marcas son regiones de revisión, no máscaras exhaustivas de humo real. Los recuentos indican qué cambia; no son precisión o recall. Todavía quedan bordes y fuentes de humo incompletos.

La continuidad nueva se exporta en `surface-continuity` y en el diagnóstico `surface-local-refinement`; el humo añadido se identifica en `smoke-local-refinement`. `estimated-surface` incluye esa continuidad; `mask`, el área visible y la evidencia espectral oculta original permanecen separadas. El nuevo humo no se utiliza para recalcular ni ampliar la superficie: no hay un bucle de confirmación entre ambas capas.

Se aprobaron 31 pruebas focales, incluidas pruebas negativas de suelo amarillo, manchas desconectadas, agua, vegetación y huecos grandes. Las salidas de esta revisión están en `.tmp/pruebas/refinamiento-e91a51fb/`.

La ejecución completa sobre las matrices exactas de 2500 × 1546 del paquete terminó en 49,86 s y exportó un ZIP verificable con `surface-continuity`. Se comprobó que superficie visible (168.492 px) y evidencia oculta original (74.368 px) permanecen idénticas al paquete; la unión estimada suma 246.353 px y el humo 614.822 px. Se publican doce checkpoints, incluido el refinamiento local. Estas cifras no sustituyen una validación independiente.

### Corrección del hueco central del humo

La revisión visual posterior señaló una omisión evidente que no debió aceptarse: el centro luminoso del penacho pasaba las condiciones atmosféricas, pero quedaba fuera del margen de la máscara de superficie. La oclusión interrumpía la firma SWIR y esa ausencia de suelo clasificado se reutilizaba indebidamente como veto de humo. También bloqueaba la conexión hacia el origen inferior.

El perfil `basic-unified-v3-smoke-context` construye un contexto espacial que atraviesa interrupciones y huecos interiores de la superficie antes de evaluar el velo. Ese contexto no cambia la clasificación de suelo ni rellena humo por sí solo: siguen exigiéndose contraste, color, textura, distancia y conexión al humo previo. La conectividad admite vecinos diagonales. En el mismo recorte, el hueco central queda cubierto; el refinamiento añade 28.298 px respecto al paquete v1, conservando la superficie estimada de la revisión anterior. Se añadió una prueba específica de oclusión sobre huecos de suelo, con una isla verde que debe seguir excluida.

## Madrid–Ávila: revisión del paquete 521bbec5

La persona distingue humo omitido con rosa y superficie omitida con amarillo. Se interpretan como regiones de revisión, no como etiquetas exhaustivas. En la región amarilla grande el predominio rojo SWIR tiene mediana −0,241 y rojo/verde −0,222: el corte positivo anterior descartaba casi todo aunque sobreviva información de la superficie en la composición.

El perfil `basic-unified-v4-swir-cyan` introduce una pista residual solo dentro de humo: compara R con el exceso de G respecto a B. Exige cian real, un mínimo de rojo absoluto y señal residual separable; se abstiene en azul dominante, cian sin señal de suelo, agua oscura y verde contradictorio. La fuente residual no puede crear semillas aisladas ni avanzar sin límite: se comprueban conexión a superficie visible o señal roja directa y distancia a esas fuentes originales. Es una heurística RGB; no recupera bandas originales ni elimina físicamente el aerosol. Los primeros ensayos más permisivos se restringieron al comparar también Niebla.

La detección de velo conectado fuera del quemado pasa a ejecutarse antes de estimar suelo bajo humo. Usa True Color y apoyo azul SWIR, sin una máscara de incendio como condición. El refinamiento posterior sobre suelo mantiene su función local y no se realimenta la etapa inicial. También se conservan componentes ocultos pequeños cuando tienen firma fuerte y contacto directo con un borde visible; el resto mantiene el filtro de tamaño.

| Región marcada | Tipo | Píxeles dentro de la región | Antes | Perfil v4 |
|---|---|---:|---:|---:|
| Rosa grande | Humo | 54.153 | 483 | 11.592 |
| Rosa pequeña | Humo | 11.428 | 1.131 | 8.160 |
| Amarilla grande izquierda | Superficie | 50.307 | 3.158 | 16.807 |
| Amarilla central inferior | Superficie | 3.899 | 470 | 732 |
| Amarilla central superior | Superficie | 2.216 | 357 | 1.119 |
| Amarilla con verde intenso | Superficie | 7.788 | 2.825 | 2.825 |

Hay omisiones pendientes: no se fuerza todo el contorno amarillo a quemado ni todo el rosa a humo. Se conserva el verde contradictorio de la última región. La superficie visible cambia solo 20 píxeles de frontera (9 añadidos y 11 retirados); la mayor diferencia está en las hipótesis ocultas. El resultado total de Madrid–Ávila es 223.240 px de superficie estimada y 446.544 px de humo, en la rejilla de 2500 × 1546 del paquete.

Se aprobaron 35 pruebas focales y después 23 específicas de evidencia, distancia y superficie unificada, incluida una prueba que impide que una cadena de candidatos cian se resembrase hasta cubrir todo el penacho. Se ejecutaron Madrid–Ávila y Niebla a resolución completa y se revisaron sus imágenes. Niebla conserva los nueve puntos comprobados del hueco central anterior, pero su hipótesis bajo humo también crece (114.587 px frente a 74.368 del perfil v1): requiere revisión visual independiente; no se presenta como precisión demostrada ni ausencia de falsos positivos.

Las fuentes se exponen mediante `diagnostic-under-smoke-cyan-evidence` y `diagnostic-smoke-contextual-veil`. Los recortes, datos del ensayo y salida final están en `.tmp/pruebas/revision-521bbec5/`. El modo avanzado mantiene su comportamiento anterior.

## Corrección v5 y retirada del filtro de componente principal

La revisión posterior invalida aceptar v4 como mejora general: la compensación del cian ampliaba la superficie sobre terreno ajeno a la cicatriz. En `basic-unified-v5-evidence-only` esa señal queda únicamente como diagnóstico. Bajo humo se exige apoyo rojo directo y conexión acotada a superficie visible; las propuestas anteriores que el humo contextual oculta dejan de contarse automáticamente como observaciones visibles.

Se ensayó después una apertura morfológica y selección del componente mayor para eliminar los excesos restantes. **Ese ensayo falló**: retiraba superficie quemada real, especialmente la cicatriz oriental de Madrid–Ávila (la unión caía a 82.422 píxeles). La persona identificó las omisiones en las imágenes completas. Se retiró íntegramente ese filtro, incluida su variante con anclas, y se añadió una prueba que obliga al refinamiento local a conservar ramas delgadas y cicatrices separadas ya detectadas. No se entrega la selección del componente mayor ni se considera una mejora de precisión.

Tras retirarlo, las dos regiones negativas de Niebla mantienen cero superficie detectada frente a 33.761 y 28.772 píxeles de v4. La Mierla recupera 63.065 píxeles respecto al ensayo restrictivo y queda en 393.216 píxeles de unión (367.033 visibles y 20.870 ocultos). En las regiones amarillas evaluadas quedan 5.745 píxeles detectados frente a 30.618 de v4: **persisten falsos positivos**, por tanto el algoritmo no se declara resuelto ni fiable de forma general. Las marcas son controles locales, no etiquetas exhaustivas ni una medida de precisión global.

Las tres escenas se procesaron a 2500 × 1546 con sensibilidad 6, siete clases, área mínima 0,15 %, distancia 10 % y método contextual híbrido. Los datos y comparaciones de esta ejecución están en `.tmp/pruebas/precision-negativos/`. La batería focal de ocho archivos aprueba 37 pruebas. Sus resultados no sustituyen la aceptación visual ni una evaluación de omisiones con máscaras independientes.
