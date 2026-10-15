# Training Random Forest

Imágenes de referencia aportadas para preparar el conjunto de entrenamiento del detector de incendios.

## Referencias disponibles

Se conservan cinco imágenes aportadas con sus nombres originales:

- `WhatsApp Image 2026-10-15 at 15.24.47.jpeg`
- `WhatsApp Image 2026-10-15 at 15.24.47 (1).jpeg`
- `WhatsApp Image 2026-10-15 at 15.24.47 (2).jpeg`
- `WhatsApp Image 2026-10-15 at 15.24.47 (3).jpeg`
- `WhatsApp Image 2026-10-15 at 15.24.48.jpeg`

## Uso para entrenamiento

Estas imágenes sirven como referencias visuales, pero las capturas anotadas no sustituyen por sí solas a etiquetas por píxel georreferenciadas. Para entrenar el Random Forest, conviene conservar las imágenes originales multibanda alineadas y crear máscaras de etiquetas para fuego/área quemada, humo, vegetación y otras clases relevantes.

**Pendiente:** identificar qué clase y escena representa cada referencia y crear máscaras de etiquetas alineadas con las imágenes originales. No usar las capturas como si fueran etiquetas por píxel.
