# Historia y evolución de Lumbre

Este documento conserva el relato del equipo sobre el origen de Lumbre, las decisiones que marcaron el trabajo durante la maratón y las ideas que quedaron abiertas. Es una memoria retrospectiva, no una cronología minuto a minuto ni una reproducción exacta de la entrega al cierre: el repositorio recoge también la evolución posterior del prototipo.

## De dónde salió el proyecto

Lumbre nació en la **maratón tecnológica III Malackathon 2026 de la Universidad de Málaga**, en el reto de **Indra Espacio: «Detección y caracterización de un incendio mediante imágenes de satélite»**. Éramos cuatro estudiantes de primer curso de la UMA: tres de Ciberseguridad e Inteligencia Artificial y uno de Informática. Nos agrupamos para afrontar un problema del que todavía no teníamos un algoritmo resuelto.

El reto proponía analizar imágenes satelitales para delimitar la superficie afectada y localizar indicios de fuego activo. Nuestro trabajo partió de composiciones True Color y SWIR. Desde el principio nos atrajo ampliar el análisis con temperatura, viento, humedad, relieve y otras fuentes públicas, pero pronto vimos que antes debíamos conseguir que funcionara el núcleo: cargar las escenas, analizarlas y revisar qué zonas proponían los detectores. Ese objetivo básico resultó bastante más difícil de lo que habíamos previsto.

## Empezar también por las herramientas

El día de la maratón no empezamos con un entorno de desarrollo y un flujo de equipo ya preparados. Tuvimos que configurar VS Code, Git, GitHub y las herramientas de IA, conectarlas y acordar cómo mantener una versión común para que los cuatro pudiéramos trabajar y compartir los cambios.

ChatGPT y Codex fueron parte importante de ese proceso. Nos ayudaron a explorar el problema, escribir y corregir código, ensamblar cambios entre versiones y organizar el trabajo con GitHub. La IA aceleró mucho la construcción del prototipo, pero el proyecto también dependió de las decisiones del equipo: probar resultados, detectar errores visibles, discutir qué convenía priorizar y aceptar que algunas ideas no cabían en el tiempo disponible.

## Aprender que ningún algoritmo resolvía todo

Empezamos probando diferentes algoritmos y reglas. El patrón que se repetía era claro: un método acertaba en algunas zonas y fallaba en otras; al cambiar de método, mejoraban ciertos casos y empeoraban los anteriores. No encontrábamos una regla única que delimitara bien todos los contornos y todas las escenas.

De ahí surgió la decisión de combinar señales y refinamientos complementarios. La mezcla buscaba conservar las partes convincentes de cada enfoque, precisar los bordes y prestar atención a las regiones conflictivas. Fue una evolución práctica, guiada por lo que veíamos en las imágenes, no una demostración de que la combinación tuviera precisión general. El código y los informes fechados documentan los experimentos y sus límites.

El humo fue uno de los problemas más persistentes. En las composiciones SWIR que teníamos, algunas zonas de humo se veían cian; ese color alteraba las señales rojizas que usábamos para reconocer suelo afectado y dificultaba interpretar qué había debajo de la oclusión. Nuestra idea fue detectar primero la superficie visible, estudiar por separado la posible superficie oculta por el humo y combinar las evidencias para obtener una delimitación más útil. La evolución del código afinó esa idea: la aplicación actual mantiene la superficie observada y la hipótesis bajo humo como capas distintas. No presenta lo hipotético como terreno observado ni lo suma automáticamente a la superficie medida. Las composiciones son imágenes renderizadas y sus colores son pistas heurísticas, no las bandas originales ni una reconstrucción física del terreno.

## De la integración ambiciosa a los datos que teníamos

Queríamos cruzar la escena con datos de atmósfera, temperatura, viento y otras fuentes. Para relacionarlos correctamente necesitábamos saber dónde y cuándo se adquirió cada imagen, además de contar con una referencia espacial fiable. Las composiciones disponibles para el prototipo no conservaban de forma utilizable toda esa información.

Con el tiempo vimos que deducir la ubicación y la fecha mirando los píxeles habría creado un problema adicional de nuestro material y de nuestro flujo. En un producto satelital geoespacial esas referencias normalmente se consultan en los metadatos o en la fuente que distribuye la escena; no conviene inventarlas a partir de una imagen RGB. En las jornadas priorizamos el análisis visual y la aplicación antes que construir una integración externa que no pudiéramos anclar con datos temporales y espaciales fiables.

Sí incorporamos una herramienta útil y más acotada: mediciones de distancias y áreas a partir del **GSD** (*Ground Sampling Distance*), que expresa cuánto terreno representa aproximadamente un píxel. Esa escala permite convertir ciertas mediciones del visor a unidades de distancia o superficie cuando es conocida. Por sí sola no da coordenadas terrestres ni sustituye un CRS y una transformación geográfica; la documentación de uso explica las condiciones y limitaciones de las escenas precargadas.

## Qué alcanzamos y qué no demuestra

El reto avanzado también llegó a convertirse en código con ayuda de la IA. La aplicación reúne análisis, capas de revisión, mediciones y exportación, y permite consultar marcas de focos cuando hay una composición `Wildfires`. El resultado es un prototipo que aporta indicios y herramientas para explorar una escena, pero no detecta todos los incendios con fiabilidad perfecta ni constituye un sistema operativo para emergencias. Las marcas `Wildfires` son referencias visuales, no medidas de temperatura ni verdad terreno; las segmentaciones tampoco han sido validadas contra etiquetas independientes suficientes.

Random Forest se exploró durante la maratón, pero no llegamos a completar el etiquetado manual y alineado de píxeles, entrenar el modelo y evaluarlo en incendios independientes. Por eso la aplicación actual lo mantiene desactivado. Las notas de `DOCUMENTACION/Ideas/` distinguen ese trabajo incompleto de las funciones que sí están disponibles y de las propuestas que siguen siendo ideas.

## Lo que nos gustaría explorar después

La idea original de combinar varias fuentes sigue teniendo sentido si primero se incorporan las referencias espaciales y temporales correctas. Con escenas georreferenciadas y datos de procedencia clara se podría estudiar cómo relacionar la imagen con meteorología histórica, relieve y otras capas públicas. Viento, pendiente, combustible y humedad del combustible pueden influir en la propagación; la humedad ambiental no es equivalente a la del combustible, y cualquier simulación necesitaría datos adecuados, una fuente de fuego activo defendible y validación.

También imaginamos calcular zonas de mayor riesgo o estudiar rutas de acceso para bomberos a partir del terreno y la red viaria. Son extensiones posibles, no capacidades actuales ni recomendaciones operativas. Para que llegaran a ser útiles habría que probarlas con datos geográficos fiables, referencias independientes y escenarios reales, y comunicar claramente la incertidumbre.

## Lectura recomendada

- [Enunciado en español del reto de Indra Espacio](<Presentacion reto/Enunciado_ES.pdf>).
- [Fundamentos y límites científicos](Ideas/inicial.md).
- [Índice de ideas, decisiones y estado actual](Ideas/README.md).
- [Flujo básico, GSD y mediciones](Ideas/segmentacion_basica.md).
- [Fuentes de imágenes y validación](Ideas/Malackathon_Indra_fuentes_imagenes_y_validacion.md).
- [Evolución experimental de la segmentación contextual](Ideas/segmentacion_contextual_evaluacion.md).

## Referencias del reto

- [Noticia de la UMA sobre la III edición](https://www.uma.es/sala-de-prensa/noticias/320-estudiantes-de-informatica-participan-en-la-iii-edicion-del-malackathon/).
- [Escuela Técnica Superior de Ingeniería Informática de la UMA](https://www.uma.es/etsi-informatica/).
