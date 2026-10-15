# Training Random Forest

Imágenes de referencia aportadas para preparar el conjunto de entrenamiento del detector de incendios.

## Referencias disponibles

Se conservan cinco imágenes aportadas con sus nombres originales:

- `WhatsApp Image 2026-10-15 at 15.24.47.jpeg`
- `WhatsApp Image 2026-10-15 at 15.24.47 (1).jpeg`
- `WhatsApp Image 2026-10-15 at 15.24.47 (2).jpeg`
- `WhatsApp Image 2026-10-15 at 15.24.47 (3).jpeg`
- `WhatsApp Image 2026-10-15 at 15.24.48.jpeg`

## Clases de referencia

Las referencias distinguen vegetación sin afectar, área quemada, focos activos y humo. El foco activo no se etiqueta como área quemada; el humo tampoco se cuenta como superficie. Una composición SWIR renderizada ayuda a interpretar el aspecto, pero no es una etiqueta ni conserva necesariamente bandas o reflectancias originales.

Para crear las máscaras alineadas, usa estos valores de píxel en un PNG o TIFF de un canal:

| Valor | Clase | Regla de anotación |
|---:|---|---|
| 0 | Sin etiqueta | Ambiguo, borde incierto, oculto o no revisado; se excluye al entrenar. |
| 1 | Vegetación | Vegetación conocida como no quemada. |
| 2 | Agua | Agua confirmada; útil para reducir confusión con superficies oscuras. |
| 3 | Humo | Humo observado, separado de nube o bruma. |
| 4 | Área quemada | Superficie ya quemada, respaldada por referencia fiable; no equivale a fuego activo. El borde dibujado en una referencia delimita esta clase, no es otra clase de píxel. |
| 5 | Fuego activo | Llama o foco activo confirmado o visible; no se suma al área quemada. |
| 6 | Nube o bruma | Nube o neblina, para separar de humo. |
| 7 | Suelo desnudo o urbano | Cuando aparezca en las escenas de entrenamiento. |

Estas IDs corresponden a las clases de la ontología del proyecto. Las capturas WhatsApp ayudan a definir qué distinguir, pero sus leyendas, contornos, escalas y controles de interfaz no están alineados como máscaras con los píxeles de entrada. **No las uses para entrenar directamente.** Tampoco generes etiquetas con las mismas reglas heurísticas que el modelo busca mejorar.

## Preparar el conjunto

Crea una carpeta por escena o incendio con una pareja True Color/SWIR de la misma adquisición y una máscara de etiquetas con exactamente la misma dimensión:

~~~
training Random Forest/
└── dataset/
    ├── incendio_01/
    │   ├── true_color.jpg
    │   ├── swir.jpg
    │   └── labels.png
    └── incendio_02/
        ├── true_color.jpg
        ├── swir.jpg
        └── labels.png
~~~

labels.png debe guardar los IDs de clase como intensidades (0–7), no como colores. Dibuja polígonos revisados en QGIS u otra herramienta de anotación y rasterízalos sobre la cuadrícula exacta de la imagen; una dimensión idéntica no prueba que dos capas estén alineadas. Verifica CRS, transformada y extensión si existen metadatos, o confirma explícitamente la cuadrícula común al exportar composiciones sin georreferenciación. El entrenador no reproyecta ni corrige desalineaciones. Las celdas de borde dudoso pueden permanecer en 0. Añade escenas de distintos entornos, estaciones, iluminación y etapas; incluye ejemplos de agua, nubes o bruma y suelo cuando existan. El entrenador exige al menos dos incendios/grupos independientes y reserva grupos completos para evaluación; escenas del mismo incendio deben compartir un archivo opcional group.txt con el mismo ID para evitar que aparezcan en entrenamiento y prueba a la vez. Si no se proporciona, cada carpeta cuenta como un grupo.

## Entrenar e integrar

Desde la raíz del repositorio, con las dependencias instaladas:

~~~
python -m pyroscope.entrenar_random_forest
~~~

Se informa precision/recall/F1 y matriz de confusión en grupos reservados y se guarda random_forest.joblib. Después, reinicia Lumbre: **Random Forest supervisado** aparecerá como método en el selector. Puedes cambiar rutas con --dataset y --model, y limitar muestras por clase/escena con --samples-per-class. Si guardas el modelo fuera de la ruta predeterminada, define LUMBRE_RF_MODEL a esa ruta antes de iniciar Lumbre.

El modelo usa RGB de ambas composiciones, cromaticidad y textura local. Los JPEG y PNG renderizados no son mediciones de reflectancia; no se calculan NBR/dNBR. Las clases predichas de área quemada, humo, agua, fuego activo posible, nube o bruma y vegetación se muestran por separado; solo el área quemada entra en el área y perímetro candidatos. Las puntuaciones del bosque no están calibradas como probabilidades. Hasta disponer de etiquetas y una evaluación independiente representativa, trátalo como experimental.

El conjunto dataset/ y el modelo se mantienen fuera de Git porque contienen datos y artefactos locales, que pueden ocupar mucho espacio.
