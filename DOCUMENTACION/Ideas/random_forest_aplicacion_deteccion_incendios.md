# Random Forest en Python y su aplicación al programa de detección de incendios, humo y agua

## 1. ¿Qué es Random Forest?

Random Forest (bosque aleatorio) es un algoritmo de aprendizaje automático supervisado disponible en Python, por ejemplo mediante la clase \`RandomForestClassifier\` de \`scikit-learn\`. Se utiliza para clasificar observaciones en categorías a partir de ejemplos etiquetados. También existe \`RandomForestRegressor\` para predecir valores numéricos.

Un bosque reúne muchos árboles de decisión. Cada árbol aprende reglas a partir de una muestra aleatoria de los datos de entrenamiento y, en clasificación, el bosque combina sus votos para decidir la clase. La aleatoriedad de las muestras y de las variables consideradas ayuda a que los árboles no sean todos iguales y puede mejorar la generalización frente a un único árbol.

En este proyecto, las clases posibles podrían ser:

- vegetación o suelo sin quemar;
- fuego activo o zona compatible con fuego;
- humo;
- agua;
- nube o bruma;
- suelo o superficie urbana;
- zona quemada, si se dispone de etiquetas adecuadas.

Estas clases son una propuesta de diseño, no categorías que el algoritmo pueda identificar automáticamente sin ejemplos etiquetados.

## 2. ¿Qué aprende el modelo?

Random Forest no «entiende» por sí solo una imagen como lo haría una persona. Aprende asociaciones entre variables de entrada y etiquetas que se le proporcionan durante el entrenamiento.

Para cada píxel o segmento de imagen se podría construir un vector de características con:

- valores R, G y B de la imagen True Color;
- valores de la imagen SWIR, si está disponible y alineada correctamente;
- índices espectrales calculados a partir de bandas originales, cuando se disponga de ellas;
- brillo, saturación, matiz y diferencias de color;
- contexto espacial, como vecindad, textura o distancia a la zona de fuego;
- variables auxiliares como tipo de vegetación, humedad o topografía, si se dispone de cartografía fiable.

**Limitación importante:** un JPG True Color o SWIR ya renderizado no necesariamente conserva las reflectancias originales de las bandas. Los colores de una composición SWIR pueden estar transformados, estirados o asignados a canales RGB. Por tanto, no deben tratarse automáticamente como mediciones espectrales físicas. Hay que documentar cómo se generó cada composición.

## 3. ¿Cómo se aplicaría al programa?

### Paso 1. Crear datos de entrenamiento

Preparar imágenes representativas y etiquetar manualmente muestras de píxeles o regiones. Las etiquetas deben distinguir al menos fuego, humo, agua, vegetación/suelo y nubes cuando estén presentes. Las muestras deberían cubrir distintos lugares, estaciones, tipos de vegetación, iluminación, sensores y etapas del incendio.

Es importante que las etiquetas las revise una persona y que no se generen exclusivamente con las mismas reglas heurísticas que luego se pretende mejorar: si el modelo solo aprende etiquetas producidas por una regla defectuosa, puede reproducir sus errores.

### Paso 2. Alinear y preparar las imágenes

Antes de combinar True Color y SWIR, comprobar que proceden de la misma adquisición o de fechas compatibles, que cubren la misma zona y que están georreferenciadas. Llevarlas a una cuadrícula común mediante metadatos y un remuestreo documentado. No asumir que tienen la misma resolución ni cambiar su tamaño sin considerar el tamaño de píxel y la proyección.

Los valores ausentes deben marcarse y gestionarse explícitamente. No se deben inventar bandas o características que no estén disponibles.

### Paso 3. Extraer características

Transformar los datos disponibles en una tabla: cada fila corresponde a un píxel o segmento y cada columna a una característica. La variable objetivo es la etiqueta de referencia (por ejemplo, «agua» o «humo»).

Un enfoque por píxel es sencillo para un prototipo, pero puede producir máscaras granuladas. Un enfoque por segmentos puede aprovechar regiones homogéneas y contexto espacial, a costa de requerir una etapa adicional de segmentación.

### Paso 4. Entrenar y evaluar

Dividir los datos en conjuntos de entrenamiento, validación y prueba. Cuando haya varias imágenes de una misma zona o del mismo incendio, separar preferiblemente por escena, fecha o incendio, no solo al azar por píxel: los píxeles vecinos son muy parecidos y una división aleatoria puede dar una evaluación excesivamente optimista.

Entrenar un \`RandomForestClassifier\`, ajustar hiperparámetros con validación y medir, por clase:

- precisión (precision): de las detecciones de una clase, qué proporción es correcta;
- exhaustividad (recall): de los ejemplos reales de esa clase, cuántos detecta;
- F1: equilibrio entre precisión y exhaustividad;
- matriz de confusión: clases que el modelo confunde;
- IoU para máscaras, si se convierte la clasificación en regiones.

La exactitud global por sí sola puede ser engañosa, ya que los píxeles de vegetación suelen ser muchos más que los de fuego o humo. Hay que revisar especialmente los falsos positivos de agua como fuego y de nubes como humo.

### Paso 5. Predecir y generar máscaras

Una vez evaluado, el modelo asigna una clase a cada píxel o segmento. \`predict_proba\` puede aportar probabilidades estimadas por clase; no deben interpretarse como probabilidades perfectamente calibradas sin comprobarlo. Se pueden exportar máscaras separadas de agua, fuego, humo y otras clases, junto con una imagen de confianza.

### Paso 6. Integrarlo con las reglas actuales

La opción recomendada es combinar Random Forest con reglas explícitas y controles espaciales:

- **Agua frente a fuego:** utilizar las características de True Color y las etiquetas de agua para reducir falsos positivos en la máscara SWIR. No clasificar automáticamente todos los píxeles oscuros como agua.
- **Fuego:** exigir evidencia aprendida en las características disponibles y aplicar filtros espaciales o temporales; la ausencia de rojo/naranja visible no descarta necesariamente un incendio.
- **Humo:** entrenar una clase específica con ejemplos de humo, nubes y bruma; no confiar solo en el criterio de brillo alto y saturación baja.
- **Máscaras finales:** aplicar operaciones morfológicas y análisis de componentes conectados con parámetros documentados, evitando borrar señales pequeñas que puedan ser relevantes.
- **Simulación de la pluma:** utilizar la máscara de fuego como posible localización de la fuente y la máscara de humo como observación para comparar con la pluma simulada. Random Forest no sustituye el modelo de dispersión atmosférica ni calcula por sí solo la dirección del viento.

El sistema debe mantener diferenciadas tres salidas: detección observada por el clasificador, reglas de corrección y simulación física/heurística de dispersión.

## 4. Ejemplo mínimo de entrenamiento en Python

El ejemplo muestra la estructura general. Presupone que ya se ha construido una matriz \`X\` de características numéricas y un vector \`y\` de etiquetas revisadas manualmente. No incluye la lectura, alineación ni etiquetado de imágenes, que dependen de los datos reales del proyecto.

\`\`\`python
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import GroupShuffleSplit

# X: matriz (n_muestras, n_caracteristicas)
# y: etiqueta de cada muestra, por ejemplo "agua", "humo" o "fuego"
# groups: identificador de escena/incendio para evitar fuga entre conjuntos

splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.25,
    random_state=42,
)
train_idx, test_idx = next(splitter.split(X, y, groups=groups))

model = RandomForestClassifier(
    n_estimators=300,
    class_weight="balanced",
    min_samples_leaf=2,
    random_state=42,
    n_jobs=-1,
)

model.fit(X[train_idx], y[train_idx])

pred = model.predict(X[test_idx])
print(classification_report(y[test_idx], pred, zero_division=0))
print(confusion_matrix(y[test_idx], pred, labels=model.classes_))

# Para obtener puntuaciones estimadas por clase:
probabilities = model.predict_proba(X[test_idx])
\`\`\`

Este fragmento es ilustrativo: \`X\`, \`y\` y \`groups\` deben construirse antes de ejecutarlo. Las dimensiones, etiquetas y características tienen que ser consistentes. La división por grupos evita que muestras de una misma escena aparezcan a la vez en entrenamiento y prueba.

## 5. Ventajas y limitaciones

### Ventajas

- funciona bien como línea base con datos tabulares de características;
- admite características de distinta naturaleza y relaciones no lineales;
- suele requerir menos normalización que algunos modelos;
- permite estimar importancia de características, aunque esta medida puede sesgarse y no demuestra causalidad;
- permite clasificar varias categorías en un único modelo.

### Limitaciones

- necesita etiquetas representativas y de calidad;
- puede fallar en condiciones que no aparecen en el entrenamiento;
- las clases poco frecuentes requieren atención especial;
- no aprovecha automáticamente la estructura espacial completa como una red neuronal convolucional;
- las probabilidades pueden estar mal calibradas;
- la importancia de características no indica por sí sola qué variable causa una detección;
- no convierte imágenes renderizadas en reflectancias fiables ni resuelve una mala alineación entre sensores.

## 6. Plan recomendado para este repositorio

1. **Inventariar las escenas** y documentar sensor, fecha, resolución, composición de color y georreferenciación.
2. **Crear un conjunto de referencia** con polígonos o muestras revisadas para fuego, humo, agua, nubes y fondo.
3. **Implementar una línea base** de características por píxel y Random Forest, manteniendo las heurísticas actuales como comparación.
4. **Separar la evaluación por escenas/incendios** y registrar métricas por clase y falsos positivos concretos.
5. **Analizar errores** especialmente en agua frente a fuego y humo frente a nubes.
6. **Guardar modelo y configuración** con versiones de bibliotecas, lista y orden de características, clases, umbrales y fecha de entrenamiento.
7. **Aplicar al lote completo** solo después de evaluar en escenas no usadas durante el entrenamiento.
8. **Conectar con la pluma gaussiana** únicamente después de obtener una máscara de fuego revisada; conservar la distinción entre humo detectado y humo simulado.

## 7. Criterio de aceptación

La integración inicial se considerará prometedora si mejora las métricas por clase frente a la línea base heurística en escenas independientes, reduce de forma medible los falsos positivos de agua como fuego sin perder demasiados incendios reales y mantiene un registro reproducible de datos, características y parámetros.

Hasta que exista un conjunto de prueba representativo y una evaluación documentada, el resultado debe presentarse como experimental. No se debe utilizar la clasificación como única fuente para decisiones de emergencia.
