# Resultados

Esta carpeta es un archivo histórico de evaluaciones seleccionadas del proyecto, no el destino de los análisis de la aplicación. Lumbre conserva una ejecución temporalmente en memoria y solo descarga una imagen o un ZIP cuando la persona lo solicita; el navegador permite elegir dónde guardarlo. La aplicación no depende de esta carpeta.

- [`clasificacion/agua/90dd412/INFORME.md`](clasificacion/agua/90dd412/INFORME.md) conserva una evaluación histórica seleccionada y sus artefactos asociados.
- [`guardados/`](guardados/README.md) explica dónde y cómo conservar resultados elegidos.
- `experimentos/historico/` conserva materiales locales de revisiones anteriores; no añadas aquí salidas nuevas de pruebas.

## Salidas temporales

La aplicación no escribe cada análisis en esta carpeta: mantiene las capas en memoria y las descarta al cerrar. Solo una exportación solicitada por la persona genera una descarga en la ubicación que gestione el navegador.

Las pruebas automáticas deben escribir en `tmp_path` de pytest. Los scripts de evaluación usan una carpeta en `.tmp/salidas/` por defecto y la borran al terminar. Si necesitas abrir paneles entre procesos, indica `--salida .tmp/pruebas/<id-de-prueba>`; `.tmp/` está ignorada por Git y debe limpiarse al acabar la inspección. Guarda bajo `guardados/` solo lo que se haya decidido conservar.

Las antiguas salidas voluminosas de `clasificacion/contextual/` se retiraron porque eran artefactos de evaluación regenerables, no datos necesarios para ejecutar Lumbre.
