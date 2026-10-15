# Focos visuales candidatos

## Alcance

La capa **Focos** resalta en amarillo eléctrico, con halo magenta, regiones pequeñas que reúnen tres señales: tonos cálidos en True Color, tonos cálidos en SWIR y contraste local positivo respecto a un fondo suavizado. Veta agua posible y humo probable. El recuento de componentes y píxeles se mantiene separado del área/perímetro clasificados.

Es una ayuda visual para revisión, no una medición de temperatura ni una confirmación de fuego activo. Las entradas habituales son JPG renderizados: su color depende de la asignación de canales, el contraste y la exportación. Un foco puede ser subpíxel, estar oculto o no verse naranja; a la inversa, roca, suelo, construcciones o reflejos cálidos pueden pasar el filtro. Los umbrales iniciales no están calibrados y la puntuación de contraste no es intensidad radiativa.

## Integración actual

- Python: `pyroscope/focos.py`, ejecutado junto con la segmentación de cada análisis.
- Capa API: `fire-hotspots`, disponible como PNG separado; no altera la máscara de superficie afectada.
- Interfaz: botón `Focos: sí/no` en el visor y recuento de componentes candidatos.
- Datos: True Color y SWIR deben tener la misma rejilla; el módulo vuelve a comprobar dimensiones y excluye las máscaras existentes de agua y humo.

## Validación y evolución

Validar con máscaras independientes y ejemplos anotados de fuego, cicatriz quemada, suelo claro, agua, humo, nube, sombra y superficies artificiales. Reservar escenas enteras para evaluación y medir precisión/recall por escena; no ajustar los umbrales para que una captura se vea atractiva.

Para hablar de actividad térmica real hacen falta productos radiométricos apropiados y metadatos. NASA FIRMS distribuye detecciones activas MODIS/VIIRS; el producto VIIRS I-band citado tiene resolución de 375 m, usa varios canales y declara detección, pero no caracterización subpíxel cuando hay saturación. Una detección de esa escala no se debe ampliar como si fuera una máscara detallada de la imagen Lumbre. Comparar fecha/hora y posición con el producto original y conservar su incertidumbre y resolución.

Fuentes oficiales:

- [NASA Earthdata: producto VIIRS/JPSS1 Active Fires 375 m](https://www.earthdata.nasa.gov/data/catalog/lancemodis-vj114img-nrt-2)
- [NASA FIRMS: datos de incendios activos](https://firms.modaps.eosdis.nasa.gov/content/active_fire/)
- [NASA Earthdata: guía del producto VIIRS 375 m](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf)
