# Resultados elegidos para conservar

Usa una carpeta por ejecución o entrega, por ejemplo `resultados/guardados/revision-niebla-2026-10-16/`. Guarda aquí solo imágenes, máscaras o métricas que alguien haya decidido conservar; no es el destino predeterminado de la aplicación ni de las pruebas.

Los scripts de evaluación aceptan `--salida` para conservar sus artefactos en una ruta explícita:

```sh
python scripts/evaluar_lumbre.py --salida resultados/guardados/revision-niebla-2026-10-16
```

Las rutas relativas de `--salida` se interpretan desde la raíz del repositorio.

Para inspeccionar una prueba y eliminarla después, usa `.tmp/pruebas/<id-de-prueba>/`. En pytest, prefiere `tmp_path`; los scripts sin `--salida` generan en `.tmp/salidas/` y limpian esa carpeta al terminar.

Incluye en cada carpeta conservada un `README.md` o un manifiesto con las escenas e imágenes fuente, la fecha/adquisición si se conoce, el comando, los parámetros, la versión o commit y cualquier limitación relevante. No llames “verdad terreno” a referencias visuales sin validar.
