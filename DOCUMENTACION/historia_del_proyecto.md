# Origen y evolución del proyecto

## El reto

Lumbre nació en el III Malackathon 2026, organizado por la Escuela Técnica Superior de Ingeniería Informática de la Universidad de Málaga. El equipo eligió el reto de **Indra Espacio**, «Detección y caracterización de un incendio mediante imágenes de satélite». El enunciado planteaba un prototipo de 48 horas que analizara imágenes Sentinel-2 de una misma adquisición: delimitar la superficie afectada y detectar posibles zonas de fuego activo, teniendo en cuenta elementos que pueden causar falsos positivos.

Éramos cuatro estudiantes de primer curso de la UMA: tres de Ciberseguridad e Inteligencia Artificial y uno de Informática. Empezamos sin un algoritmo resuelto, investigamos el problema y probamos distintos enfoques para llegar a una aplicación que pudiera mostrar y exportar resultados.

## Lo que conserva el repositorio

La aplicación actual, Lumbre, es el resultado de la evolución del prototipo después del reto; no es una reconstrucción exacta de lo que había al final de las jornadas. El repositorio conserva exploraciones con reglas visuales, K-Means, señales SWIR y segmentación contextual, además de propuestas que no llegaron a implementarse. Random Forest se inició durante el Malackathon, pero no se completaron las etiquetas de píxeles, el entrenamiento ni la evaluación, por lo que está desactivado en la aplicación.

La documentación técnica distingue las funciones vigentes, los experimentos y las ideas pendientes. Sus métricas y composiciones de referencia no equivalen a validación independiente del área quemada o del fuego activo.

## Relato de las jornadas

La cronología y las anécdotas del 15 y 16 de octubre se completarán a partir del relato del equipo.

## Fuentes

- [Noticia oficial de la UMA sobre la III edición](https://www.uma.es/sala-de-prensa/noticias/320-estudiantes-de-informatica-participan-en-la-iii-edicion-del-malackathon/).
- [Información de la ETSI Informática sobre el Malackathon](https://www.uma.es/etsi-informatica/).
- [Enunciado en español del reto de Indra Espacio](<Presentacion reto/Enunciado_ES.pdf>).
