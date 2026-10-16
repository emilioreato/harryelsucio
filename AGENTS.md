# AGENTS.md — Guía para agentes

## Criterio

- **Primero que funcione:** priorizar el recorrido completo cargar → analizar → visualizar → exportar. Iterar en cambios pequeños, ejecutables y fáciles de corregir.
- **Pensar desde el problema:** identificar entradas reales, objetivo, supuestos, invariantes y prueba de éxito. Cuestionar propuestas, detectar contradicciones y corregir la causa; no añadir complejidad por inercia.
- **Elegir lo suficiente:** reutilizar librerías probadas; evitar abstracciones prematuras, refactors ajenos, integraciones especulativas y documentación burocrática. No sacrificar corrección por rapidez.
- **Autonomía:** resolver detalles reversibles sin interrumpir. Consultar solo cuando falte una decisión material o exista riesgo de perder trabajo.

## Contexto y código

- Leer solo archivos y secciones pertinentes. `DOCUMENTACION/historia_del_proyecto.md` recoge el origen y el relato del equipo en el III Malackathon; `README.md` documenta uso e instalación y enlaza esa historia. `DOCUMENTACION/Ideas/inicial.md` orienta el análisis científico; no sustituye los datos reales ni constituye un contrato infalible. `requirements.txt` enumera las dependencias.
- Stack preferente: Python, NumPy, Rasterio, OpenCV/scikit-image, SciPy y scikit-learn para el motor; interfaz propia HTML/CSS/JavaScript servida por una API HTTP local ligera. Evitar frameworks de presentación que añadan controles ajenos a la aplicación. QGIS sirve para inspección, no es requisito del runtime.
- Desarrollo en Windows/VS Code; usar el Python existente y `pip`, sin imponer entornos virtuales, Conda o Docker. Registrar dependencias nuevas en `requirements.txt` y comandos relevantes en README. Evitar instalaciones pesadas o cambios globales innecesarios.
- Modularizar por responsabilidades **cuando haga falta**. Código simple y legible, validación de entradas, errores comprensibles y datos de demo reproducibles. Si falla una API, admitir entrada manual o caché con procedencia explícita.

## Invariantes científicos

- **Bandas:** True Color y SWIR corresponden al mismo instante, no a un antes/después. Verificar canales, metadatos y formato; no inferir bandas originales de una composición RGB. NBR exige bandas adecuadas y dNBR, observaciones de fechas distintas.
- **Georreferenciación:** alinear por CRS, transformada, extensión y resolución; `resize()` no equivale a reproyectar. No expresar áreas en m²/ha sin escala geográfica fiable.
- **Fenómenos:** distinguir fuego activo, área quemada y humo. No iniciar una simulación con toda la superficie quemada como si ardiera.
- **Tiempo y terreno:** consultar meteorología de la fecha/hora de adquisición; registrar fuente e incertidumbre. Humedad ambiental ≠ humedad del combustible. Calcular pendiente con distancias horizontales reales y distinguir viento «desde» de viento «hacia».
- **Modelos:** separar observación, clasificación, simulación y riesgo. Scores heurísticos no son probabilidades calibradas; escenarios simulados no son predicciones validadas. Nunca inventar datos, precisión ni resultados.

## Git y trabajo compartido

- Antes de editar, revisar `git status --short` y los cambios existentes en archivos afectados. Preservar trabajo ajeno y evitar reformateos masivos.
- No hacer `reset --hard`, `clean -fd`, `push --force`, pull, merge, rebase, commits o push sin petición expresa. No subir secretos, cachés ni imágenes pesadas.
- `main` es la única rama activa y la fuente de verdad. Todas las demás ramas remotas se conservan como referencias históricas; no iniciar trabajo, integrar cambios ni basarse en ellas salvo petición expresa del usuario.
- Para una copia nueva de trabajo usa `git clone --single-branch --branch main <URL-del-repositorio>`; así no se descargan los refs ni los objetos exclusivos de ramas históricas. No borrar ni renombrar esas ramas para reducir el tamaño local.

## Verificación y comunicación

- Verificar **cada cambio relevante con la prueba focal más barata**: imports, una función, un archivo real, un test o la UI ejecutada. Para errores, reproducir → localizar → corregir → volver a probar. No imponer gates globales ni suites largas por rutina.
- Comprobar un recorrido real de extremo a extremo en cuanto exista. Distinguir claramente lo probado de lo pendiente; no presentar un mock como integración real.
- Avances breves cuando aporten valor, con un emoji de fase: 🔎 diagnóstico, 🛠️ implementación, 🔧 corrección, ▶️ prueba, ✅ validado, ❌ fallo, 📦 entrega. No narrar cada comando.
- Al terminar, resumir **qué funciona, qué cambió, qué se probó y qué falta**. Priorizar el siguiente paso de mayor impacto.

## Salidas de la aplicación y pruebas

- Lumbre mantiene las capas de un análisis en memoria. No escribe las imágenes de cada ejecución en `resultados/`; al cerrar el proceso desaparecen. Solo se conserva un archivo cuando la persona pulsa una acción de exportación y lo guarda desde el navegador.
- En pruebas Python, usa `tmp_path` de pytest para imágenes y archivos generados; pytest gestiona su ciclo de vida. No copies entradas de `imagenes_muestra/` ni escribas salidas de pruebas dentro de `resultados/`.
- Los scripts que generan paneles o máscaras usan `scripts/_salidas.py`: sin `--salida` crean una carpeta en `.tmp/salidas/` y la eliminan al terminar; con `--salida RUTA` conservan los artefactos en la ruta solicitada.
- Para revisar manualmente una salida entre procesos, usa `.tmp/pruebas/<id-de-prueba>/` (ignorada por Git), por ejemplo `python scripts/evaluar_lumbre.py --salida .tmp/pruebas/revision-humo`. Elimina solo esa carpeta concreta al terminar. No uses `resultados/` como área de trabajo temporal.
- Guarda en `resultados/guardados/<nombre-descriptivo>/` únicamente resultados seleccionados para conservar; añade por ejecución un `README.md` o manifiesto con escena, fecha, comando, parámetros y procedencia. No sustituyas ni borres el informe histórico curado sin una petición expresa.
- Si Windows bloquea la carpeta temporal del sistema, ejecuta desde la raíz y mantén las pruebas dentro del alcance activo. Crea primero el padre ignorado por Git y luego usa una base exclusiva para pytest (pytest puede vaciar esa base al iniciar): `python -c "from pathlib import Path; Path('.tmp').mkdir(exist_ok=True)"` y `python -m pytest -c tests/pytest.ini tests --basetemp=.tmp/pytest-codex`. No apuntes `--basetemp` a `.tmp/` directamente, porque pytest podría borrar las salidas de inspección manual que haya dentro.
