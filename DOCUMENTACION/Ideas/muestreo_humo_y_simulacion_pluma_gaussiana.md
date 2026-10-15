# Muestreo del humo y simulación de dispersión mediante pluma gaussiana

## 1. Objetivo

Definir una ampliación del sistema de segmentación para que, además de identificar píxeles compatibles con humo en imágenes, pueda:

1. muestrear y resumir las zonas de humo detectadas;
2. estimar un foco emisor asociado al incendio y caracterizar su entorno;
3. simular de forma orientativa el transporte y la difusión del humo con datos de viento, vegetación, superficie quemada y condiciones atmosféricas;
4. superponer sobre la imagen una pluma gaussiana en tonos morados: morado oscuro para mayor concentración estimada y morado claro para menor concentración.

**Alcance:** la máscara obtenida de JPG RGB/SWIR es una observación visual indirecta, no una medida física de concentración. La pluma sería inicialmente una simulación heurística, no una predicción validada ni una herramienta oficial de protección civil. Para convertirla en una estimación física se necesitan datos meteorológicos, de combustible, topografía y emisiones con calidad conocida.

## 2. Flujo de procesamiento propuesto

1. **Entrada y metadatos:** imagen True Color RGB, imagen SWIR, fecha/hora de adquisición, georreferenciación, tamaño de píxel y, si están disponibles, máscaras de agua, fuego y humo.
2. **Alineación:** comprobar que las imágenes correspondan a la misma adquisición y llevarlas a una cuadrícula común mediante sus metadatos geoespaciales. No asumir que tienen la misma resolución ni redimensionarlas sin control.
3. **Segmentación de humo:** seleccionar candidatos brillantes y poco saturados en RGB y SWIR, con exclusión de agua, nubes y zonas de fuego cuando sea posible. Con JPG renderizados, estas reglas son aproximadas.
4. **Muestreo:** calcular regiones conectadas, superficie de la máscara, centroide, extensión, confianza y evolución temporal si hay varias fechas.
5. **Estimación del foco:** usar la zona activa del incendio o el centroide de la máscara de fuego como origen aproximado. Registrar la incertidumbre espacial.
6. **Preparación ambiental:** obtener viento, dirección, velocidad, estabilidad atmosférica, altura de mezcla, humedad, topografía y combustible disponible.
7. **Simulación:** generar una concentración relativa sobre una cuadrícula geográfica y avanzar el campo en pasos temporales.
8. **Visualización:** superponer la concentración como un raster semitransparente morado y mostrar leyenda, hora de simulación, viento y parámetros empleados.

## 3. Muestreo del humo observado

Para cada imagen y cada componente conectado de la máscara de humo, guardar:

- número de píxeles clasificados como humo;
- área estimada en m² o ha, **solo** si se conoce el tamaño de píxel efectivo y la georreferenciación;
- centroide y caja delimitadora en coordenadas de imagen y, si es posible, geográficas;
- intensidad media y distribución de brillo/saturación en RGB y SWIR;
- puntuación de confianza del clasificador;
- relación espacial con las máscaras de fuego, agua y nubes;
- fecha/hora de adquisición y fuente de los datos.

En una serie temporal, comparar las regiones entre adquisiciones solo si se tienen en cuenta el intervalo temporal, la resolución, el ángulo de observación, las nubes y las diferencias de iluminación. La ausencia de humo en una imagen no implica necesariamente que no exista humo: puede ser demasiado tenue, estar oculto o haberse desplazado.

### Indicadores de seguimiento

- **Área aparente de humo:** área de la máscara observada en la imagen; no equivale a la huella completa de la pluma.
- **Desplazamiento del centroide:** cambio espacial entre adquisiciones.
- **Dirección de desplazamiento:** estimación visual que puede contrastarse con el viento, sin asumir que ambos coinciden exactamente.
- **Confianza:** calidad de la máscara según los umbrales y validación disponibles.
- **Cambio temporal:** variación de área y extensión entre observaciones comparables.

No interpretar el número de píxeles ni su brillo como masa de humo o concentración en mg/m³ sin una calibración radiométrica y un modelo de observación apropiados.

## 4. Variables para estimar la emisión

La intensidad de la fuente debe depender de varios factores, no únicamente del área quemada.

| Variable | Uso propuesto | Fuente o estimación |
|---|---|---|
| Área activa/quemada | Escala inicial de la fuente; distinguir área total quemada de frente activo | Máscara de fuego y perímetro, con incertidumbre |
| Tipo de vegetación | Diferenciar combustible herbáceo, matorral, arbolado y mezcla | Cartografía de coberturas o clasificación validada |
| Carga de combustible disponible | Aproximar la biomasa que puede arder por unidad de superficie | Inventario forestal, literatura local o producto especializado |
| Fracción consumida | Evitar suponer que toda la vegetación se consume | Modelo de combustible o supuesto documentado |
| Factor de emisión | Relacionar combustible consumido con masa de partículas/humo emitida | Factor específico del combustible y del contaminante |
| Humedad del combustible | Modificar la combustión y la emisión estimada | Observación, producto ambiental o escenario supuesto |
| Intensidad y evolución del fuego | Ajustar la variación temporal de la fuente | Frente activo, potencia térmica si existe, o proxy documentado |
| Viento a distintas alturas | Transporte y orientación de la pluma | Estación meteorológica, radiosondeo o modelo meteorológico |
| Estabilidad y altura de mezcla | Controlar la dispersión vertical y la dilución | Datos atmosféricos o escenario parametrizado |
| Humedad, temperatura y precipitación | Contextualizar evolución y posible deposición | Datos meteorológicos |
| Relieve y rugosidad | Identificar canalización del viento y limitaciones del modelo | Modelo digital del terreno y cobertura del suelo |

Una aproximación inicial para la tasa de combustible consumido puede escribirse como:

\[
\dot m_{comb}(t) = A_{activo}(t)\, L_{comb}\, f_{cons}\, r(t)
\]

donde el área activa se expresa en m², la carga de combustible en kg/m², la fracción consumida es adimensional y \(r(t)\) representa una tasa o perfil temporal compatible con las unidades elegidas. La emisión de partículas se aproximaría mediante:

\[
Q(t) = \dot m_{comb}(t)\, EF
\]

donde \(EF\) es un factor de emisión de partículas por unidad de combustible consumido. Estas ecuaciones son un esquema conceptual: las unidades y la definición de cada término deben comprobarse antes de implementarlas. No se debe inferir una tasa física fiable únicamente a partir de una imagen JPG.

Si faltan datos, ofrecer escenarios **bajo, central y alto** con parámetros explícitos, en vez de presentar una única cifra como medida real.

## 5. Modelo de pluma gaussiana

### 5.1 Sistema de coordenadas

- Situar el origen en el foco emisor estimado.
- Usar coordenadas métricas locales o una proyección cartográfica adecuada; no aplicar distancias euclidianas directamente a latitud/longitud.
- Rotar las coordenadas según la dirección del viento para obtener \(x\), distancia a sotavento, y \(y\), distancia transversal.
- Mantener la velocidad del viento y su dirección asociadas a una altura y hora conocidas.

La pluma se alarga principalmente a sotavento. El viento observado a nivel de superficie puede no representar el viento a la altura de la columna de humo.

### 5.2 Concentración gaussiana de referencia

Para una fuente continua y un terreno idealizado, una forma clásica de referencia es:

\[
C(x,y,z)=\frac{Q}{2\pi u\sigma_y\sigma_z}
\exp\!\left(-\frac{y^2}{2\sigma_y^2}\right)
\left[
\exp\!\left(-\frac{(z-H)^2}{2\sigma_z^2}\right)
+
\exp\!\left(-\frac{(z+H)^2}{2\sigma_z^2}\right)
\right]
\]

donde:

- \(Q\): tasa de emisión del material modelado;
- \(u\): velocidad del viento a la altura representativa de la pluma;
- \(\sigma_y\) y \(\sigma_z\): dispersión lateral y vertical, dependientes de la distancia y de la estabilidad atmosférica;
- \(H\): altura efectiva de la fuente, que puede incluir la altura de la columna;
- \(x,y,z\): coordenadas alineadas con el viento.

La expresión es una referencia para una fuente continua bajo hipótesis simplificadoras. **No basta por sí sola para simular un incendio real**: el foco cambia, la emisión es variable, la columna puede elevarse por flotabilidad y el viento cambia con el tiempo. La concentración calculada tampoco debe etiquetarse como concentración real si \(Q\), el viento y los coeficientes de dispersión son supuestos.

### 5.3 Avance temporal

En cada paso temporal:

1. actualizar el foco y el perfil de emisión con la evolución estimada del incendio;
2. leer la velocidad y dirección del viento válidas para ese intervalo;
3. calcular el desplazamiento advectivo aproximado \(\Delta s = u\,\Delta t\);
4. actualizar el tamaño lateral y vertical de la pluma con los parámetros de dispersión;
5. acumular, transportar o recalcular la contribución de las emisiones anteriores;
6. aplicar límites de dominio y controles de estabilidad numérica;
7. guardar el campo de concentración relativa y sus metadatos.

Si no se dispone de meteorología temporal, usar un viento constante explícitamente marcado como supuesto. Una pluma gaussiana estacionaria con viento constante es útil como primera visualización, pero no representa bien cambios de viento, terreno complejo, incendios móviles ni evolución turbulenta.

## 6. Estilo visual morado

Representar el campo simulado como una capa raster georreferenciada, alineada con la imagen base:

- **Morado muy oscuro:** concentración relativa más alta.
- **Morado medio:** concentración intermedia.
- **Morado claro:** concentración relativa más baja.
- **Transparente:** valor nulo o por debajo del umbral de visualización.

Usar una escala monotónica y una leyenda continua, por ejemplo de «baja» a «alta concentración estimada». Ajustar la opacidad para que se sigan viendo el terreno y las máscaras observadas. Evitar que el color morado tape el contorno del incendio o se confunda con la máscara de humo detectada.

La normalización de color debe ser consistente entre fotogramas si se comparan tiempos. Si cada fotograma se autoescala por separado, un mismo tono puede representar concentraciones distintas. Mostrar por separado:

- máscara de humo observada;
- pluma simulada;
- perímetro o máscara de fuego;
- dirección y velocidad del viento;
- instante simulado y datos usados;
- indicación visible de «simulación orientativa» y nivel de incertidumbre.

## 7. Arquitectura funcional propuesta

Separar el programa en módulos para poder validar cada parte por separado:

- sample_smoke_mask(image, smoke_mask, metadata): extrae estadísticas de la máscara.
- estimate_source(fire_mask, vegetation, burn_area, parameters): construye una fuente estimada y devuelve también sus incertidumbres.
- load_meteorology(timestamp, location): entrega viento y variables atmosféricas con unidades y procedencia; no debe inventar datos ausentes.
- simulate_gaussian_plume(source, meteorology, grid, time_steps): devuelve campos numéricos por instante.
- render_purple_overlay(base_image, concentration, georeferencing, scale): reproyecta y dibuja la capa morada.
- export_run(metadata, samples, concentration, assumptions): guarda parámetros, resultados y avisos.

Cada salida debería registrar la versión del algoritmo, parámetros, unidades, resolución espacial, intervalo temporal, procedencia de datos y supuestos. Si no existe georreferenciación fiable, permitir una previsualización en coordenadas de imagen, pero impedir que se presenten distancias, superficies o concentraciones físicas como si fueran precisas.

## 8. Validación y control de errores

Antes de usar la simulación para decisiones operativas:

1. validar la segmentación de humo con anotaciones manuales independientes;
2. evaluar precisión, exhaustividad, F1 e IoU de la máscara;
3. contrastar dirección y extensión simuladas con imágenes sucesivas, estaciones y/o observaciones independientes;
4. hacer análisis de sensibilidad de viento, emisión, altura de la fuente y estabilidad;
5. documentar el error espacial y temporal;
6. probar casos de viento débil o variable, fuentes múltiples, nubes, humo tenue y topografía compleja.

La salida debe indicar claramente qué parte procede de la observación y qué parte del modelo. Si faltan viento, datos de combustible o una fuente temporal defendible, la visualización se presentará como **escenario ilustrativo**, no como pronóstico. No utilizar esta versión orientativa como única base para evacuaciones, cierres o decisiones de emergencia.

## 9. Plan de implementación incremental

**Fase 1 — Muestreo:** guardar estadísticas y geometría de las máscaras de humo, con control de metadatos.

**Fase 2 — Pluma visual:** crear una pluma gaussiana bidimensional sintética a partir de un foco, dirección y velocidad de viento introducidos por el usuario; mostrar gradiente morado y leyenda, claramente rotulados como simulación.

**Fase 3 — Variables ambientales:** integrar datos meteorológicos y de vegetación con unidades, fechas, procedencia y gestión de valores ausentes.

**Fase 4 — Fuente de emisión:** incorporar carga de combustible, fracción consumida y factores de emisión apropiados; calcular escenarios y rangos de incertidumbre.

**Fase 5 — Evolución temporal y validación:** introducir viento variable, emisiones por intervalo, comparación con observaciones y pruebas cuantitativas.

### Criterio de aceptación inicial

La primera versión será aceptable como prototipo si permite inspeccionar la máscara de humo observada, configurar foco y viento, generar una capa morada georreferenciada o claramente referida a píxeles, conservar una leyenda coherente y exportar los parámetros y supuestos. No se considerará un modelo predictivo validado hasta completar las fases de calibración y contraste independiente.
