# Random Forest para clasificación de escenas

El detector y el entrenador se prepararon como infraestructura experimental. Esta nota conserva el propósito; la [guía de entrenamiento](<../../training/random_forest/README.md>) describe el formato que habría necesitado el conjunto de etiquetas.

## Estado real: desactivado; no se completó durante el Malackathon

Random Forest se propuso e inició durante el Malackathon, y se prepararon la extracción de características, el entrenador y la integración opcional con la segmentación contextual. **El trabajo esencial de etiquetado nunca se hizo:** no se marcaron manualmente los píxeles de las escenas sobre máscaras alineadas y revisadas. Las cinco imágenes de referencia conservadas ayudan a explicar las clases, pero son capturas ilustrativas, no etiquetas de píxel. Se acabó el tiempo del Malackathon antes de completar el conjunto de datos, entrenar un modelo real y evaluarlo en incendios independientes.

Por ese motivo, Random Forest está **desactivado en la aplicación actual**: no hay un modelo entrenado (`random_forest.joblib`), por lo que el registro no ofrece el detector y la opción de apoyo no se puede activar. No produce predicciones en los análisis actuales. La infraestructura de código está preparada para retomarlo, pero no debe presentarse como una función terminada ni como un resultado que haya intervenido en las segmentaciones existentes.

Para reactivarlo hará falta etiquetar píxeles de forma manual y revisada en escenas alineadas, incluir incendios/grupos independientes y completar el entrenamiento y una evaluación representativa antes de usar o valorar sus predicciones.

El modelo clasifica características de las composiciones renderizadas en clases separadas. Necesita máscaras revisadas y alineadas; las capturas de referencia no son etiquetas de píxel. Divide los datos por incendio o grupo, no por píxeles aleatorios de una misma escena, y reserva casos independientes para evaluación.

Aunque se complete ese trabajo, el prototipo usa características de composiciones RGB renderizadas: sus puntuaciones no son probabilidades calibradas, no recupera reflectancias originales ni corrige una desalineación. La guía de entrenamiento no sustituye el etiquetado ni la validación que faltaron durante el Malackathon.
