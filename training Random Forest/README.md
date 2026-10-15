# Training Random Forest

Imágenes de referencia aportadas para preparar el conjunto de entrenamiento del detector de incendios.

## Archivos previstos

- \`Fuego, vegetación y focos.png\`: interpretación de vegetación, área quemada y focos de mayor intensidad.
- \`Humo.png\`: delimitación visual del humo.
- \`Fuego y vegetación.png\`: área quemada frente a vegetación no afectada.
- \`Original True Color.PNG\`: imagen original en color verdadero.
- \`Original SWIR.PNG\`: imagen original en composición SWIR.

## Uso para entrenamiento

Estas imágenes sirven como referencias visuales, pero las capturas anotadas no sustituyen por sí solas a etiquetas por píxel georreferenciadas. Para entrenar el Random Forest, conviene conservar las imágenes originales multibanda alineadas y crear máscaras de etiquetas para fuego/área quemada, humo, vegetación y otras clases relevantes.

**Pendiente:** añadir aquí los cinco archivos de imagen originales. Este archivo README solo documenta la estructura y el propósito del conjunto.
