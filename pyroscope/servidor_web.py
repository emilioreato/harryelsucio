"""Servidor HTTP local para la interfaz propia de PyroScope."""

from __future__ import annotations

import base64
import binascii
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import mimetypes
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlsplit
import uuid
import webbrowser

import numpy as np
from PIL import Image

from .interfaz.configuracion import RAIZ_REPOSITORIO, listar_escenas_disponibles
from .interfaz.procesamiento import preparar_pareja, procesar_pareja
from .detectores import listar_detectores_superficie, obtener_detector_superficie
from .detectores.kmeans import PESOS_SCORE_POR_DEFECTO
from .agua import UMBRALES_AGUA_POR_DEFECTO
from .humo import PESOS_CONFIANZA_HUMO_POR_DEFECTO
from .visualizacion import crear_superposicion, crear_vista_clasificacion


_WEB = RAIZ_REPOSITORIO / "web"
_MAX_BODY_BYTES = 120 * 1024 * 1024
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.RLock()
_ANALYSIS_LOCK = threading.Lock()
_INSTANCIA_LOCK: Any | None = None


class _ServidorWebExclusivo(ThreadingHTTPServer):
    """Impide que Windows permita dos procesos en el mismo puerto local."""

    # HTTPServer permite reutilizar direcciones por defecto. En Windows eso
    # puede dejar dos app.py escuchando a la vez y repartir conexiones de forma
    # impredecible. Si el puerto está ocupado, se elige otro en ejecutar_servidor.
    allow_reuse_address = False
    allow_reuse_port = False


def _adquirir_bloque_instancia() -> bool:
    """Evita que varios clics al lanzador creen servidores y pestañas duplicados."""
    global _INSTANCIA_LOCK
    ruta = Path(tempfile.gettempdir()) / "pyroscope-local-web.lock"
    archivo = ruta.open("a+b")
    archivo.seek(0, os.SEEK_END)
    if archivo.tell() == 0:
        archivo.write(b"\0")
        archivo.flush()
    archivo.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        archivo.close()
        return False
    _INSTANCIA_LOCK = archivo
    return True


def _liberar_bloque_instancia() -> None:
    global _INSTANCIA_LOCK
    if _INSTANCIA_LOCK is None:
        return
    archivo = _INSTANCIA_LOCK
    _INSTANCIA_LOCK = None
    try:
        if os.name == "nt":
            import msvcrt

            archivo.seek(0)
            msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)
    finally:
        archivo.close()


def _png_bytes(imagen: np.ndarray) -> bytes:
    salida = BytesIO()
    datos = np.asarray(imagen)
    if datos.dtype == np.bool_:
        datos = datos.astype(np.uint8) * 255
    Image.fromarray(datos).save(salida, format="PNG")
    return salida.getvalue()


def _actualizar_trabajo(job_id: str, **cambios: Any) -> None:
    with _JOBS_LOCK:
        trabajo = _JOBS.get(job_id)
        if trabajo is not None:
            trabajo.update(cambios)
            trabajo["updated_at"] = time.time()


def _resumen_trabajo(trabajo: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": trabajo["id"],
        "state": trabajo["state"],
        "stage": trabajo["stage"],
        "progress": trabajo["progress"],
        "error": trabajo.get("error"),
        "metrics": trabajo.get("metrics"),
        "grid": trabajo.get("grid"),
    }


def _validar_ajustes(datos: dict[str, Any]) -> dict[str, Any]:
    metodo = str(datos.get("method", "kmeans"))
    detector = obtener_detector_superficie(metodo)

    def entero(clave: str, minimo: int, maximo: int, defecto: int) -> int:
        valor = datos.get(clave, defecto)
        if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
            raise ValueError(f"El valor de {clave} debe ser un entero entre {minimo} y {maximo}.")
        return valor

    def decimal(clave: str, minimo: float, maximo: float, defecto: float) -> float:
        valor = datos.get(clave, defecto)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"El valor de {clave} debe ser un número entre {minimo} y {maximo}.")
        valor = float(valor)
        if not np.isfinite(valor) or not minimo <= valor <= maximo:
            raise ValueError(f"El valor de {clave} debe estar entre {minimo} y {maximo}.")
        return valor

    gsd = datos.get("gsd_m_per_px")
    if gsd in (None, ""):
        gsd = None
    else:
        if isinstance(gsd, bool) or not isinstance(gsd, (int, float)):
            raise ValueError("El GSD debe ser un número positivo en metros por píxel.")
        gsd = float(gsd)
        if not np.isfinite(gsd) or gsd <= 0:
            raise ValueError("El GSD debe ser un número positivo en metros por píxel.")

    conservar = datos.get("keep_separate", False)
    if not isinstance(conservar, bool):
        raise ValueError("La opción para conservar focos separados debe ser booleana.")

    avanzado_entrada = datos.get("advanced", {})
    if not isinstance(avanzado_entrada, dict):
        raise ValueError("Los ajustes avanzados deben ser un objeto.")

    pesos_entrada = avanzado_entrada.get("kmeans_weights", {})
    if not isinstance(pesos_entrada, dict):
        raise ValueError("Los pesos de K-Means deben ser un objeto.")
    pesos_kmeans: dict[str, float] = {}
    for nombre, predeterminado in PESOS_SCORE_POR_DEFECTO.items():
        valor = pesos_entrada.get(nombre, predeterminado)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"El peso K-Means '{nombre}' debe ser un número.")
        valor = float(valor)
        if not np.isfinite(valor) or not -3.0 <= valor <= 3.0:
            raise ValueError(f"El peso K-Means '{nombre}' debe estar entre -3 y 3.")
        pesos_kmeans[nombre] = valor
    if metodo in ("kmeans", "fusion_ponderada") and not any(pesos_kmeans.values()):
        raise ValueError("Al menos un peso de K-Means debe ser distinto de cero.")

    pesos_humo_entrada = avanzado_entrada.get("smoke_weights", {})
    if not isinstance(pesos_humo_entrada, dict):
        raise ValueError("Los pesos de humo deben ser un objeto.")
    pesos_humo: dict[str, float] = {}
    for nombre, predeterminado in PESOS_CONFIANZA_HUMO_POR_DEFECTO.items():
        valor = pesos_humo_entrada.get(nombre, predeterminado)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"El peso de humo '{nombre}' debe ser un número.")
        valor = float(valor)
        if not np.isfinite(valor) or not 0.0 <= valor <= 1.0:
            raise ValueError(f"El peso de humo '{nombre}' debe estar entre 0 y 1.")
        pesos_humo[nombre] = valor
    if not any(pesos_humo.values()):
        raise ValueError("Al menos un peso de confianza de humo debe ser mayor que cero.")

    umbrales_agua_entrada = avanzado_entrada.get("water_thresholds", {})
    if not isinstance(umbrales_agua_entrada, dict):
        raise ValueError("Los percentiles de agua deben ser un objeto.")
    umbrales_agua: dict[str, float] = {}
    for nombre, predeterminado in UMBRALES_AGUA_POR_DEFECTO.items():
        valor = umbrales_agua_entrada.get(nombre, predeterminado)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"El percentil de agua '{nombre}' debe ser un número.")
        valor = float(valor)
        if not np.isfinite(valor) or not 0.01 <= valor <= 0.99:
            raise ValueError(f"El percentil de agua '{nombre}' debe estar entre 0,01 y 0,99.")
        umbrales_agua[nombre] = valor

    umbrales_entrada = avanzado_entrada.get("swir_thresholds", {})
    if not isinstance(umbrales_entrada, dict):
        raise ValueError("Los percentiles SWIR deben ser un objeto.")
    rangos_percentiles = {
        "seed_red": (0.80, 0.9999),
        "grow_red": (0.50, 0.98),
        "seed_red_green": (0.40, 0.99),
        "grow_red_green": (0.30, 0.98),
        "vegetation_max": (0.50, 1.0),
    }
    umbrales_swir: dict[str, float | None] = {}
    for nombre, (minimo, maximo) in rangos_percentiles.items():
        valor = umbrales_entrada.get(nombre)
        if valor in (None, ""):
            umbrales_swir[nombre] = None
            continue
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"El percentil SWIR '{nombre}' debe ser un número.")
        valor = float(valor)
        if not np.isfinite(valor) or not minimo <= valor <= maximo:
            raise ValueError(
                f"El percentil SWIR '{nombre}' debe estar entre {minimo} y {maximo}."
            )
        umbrales_swir[nombre] = valor

    semilla_roja = umbrales_swir["seed_red"]
    crecimiento_rojo = umbrales_swir["grow_red"]
    if crecimiento_rojo is None:
        crecimiento_rojo = 0.94 - (entero("sensitivity", 1, 10, 5) - 1) * 0.010
    if semilla_roja is None:
        semilla_roja = 0.994 - (entero("sensitivity", 1, 10, 5) - 1) * 0.006
    if crecimiento_rojo > semilla_roja:
        raise ValueError("El percentil SWIR de crecimiento debe ser menor o igual al de semilla.")

    semilla_rg = umbrales_swir["seed_red_green"]
    crecimiento_rg = umbrales_swir["grow_red_green"]
    sensibilidad = entero("sensitivity", 1, 10, 5)
    if crecimiento_rg is None:
        crecimiento_rg = 0.68 - (sensibilidad - 1) * 0.012
    if semilla_rg is None:
        semilla_rg = 0.82 - (sensibilidad - 1) * 0.005
    if crecimiento_rg > semilla_rg:
        raise ValueError("El percentil rojo/verde de crecimiento debe ser menor o igual al de semilla.")

    def decimal_avanzado(clave: str, minimo: float, maximo: float, defecto: float) -> float:
        valor = avanzado_entrada.get(clave, defecto)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ValueError(f"El ajuste '{clave}' debe ser un número.")
        valor = float(valor)
        if not np.isfinite(valor) or not minimo <= valor <= maximo:
            raise ValueError(f"El ajuste '{clave}' debe estar entre {minimo} y {maximo}.")
        return valor

    peso_fusion_kmeans = decimal_avanzado("fusion_kmeans_weight", 0.0, 1.0, 0.5)
    peso_fusion_swir = decimal_avanzado("fusion_swir_weight", 0.0, 1.0, 0.5)
    umbral_fusion = decimal_avanzado("fusion_threshold", 0.0, 1.0, 0.55)
    umbral_humo = decimal_avanzado("smoke_threshold", 0.0, 1.0, 0.55)
    if metodo == "fusion_ponderada" and peso_fusion_kmeans + peso_fusion_swir <= 0:
        raise ValueError("En la fusión, al menos un peso de algoritmo debe ser mayor que cero.")

    return {
        "detector": detector,
        "sensitivity": entero("sensitivity", 1, 10, 5),
        "num_classes": entero("num_classes", 4, 10, 7),
        "minimum_area_pct": decimal("minimum_area_pct", 0.01, 1.0, 0.15),
        "max_distance_pct": entero("max_distance_pct", 3, 20, 10),
        "keep_separate": conservar,
        "gsd_m_per_px": gsd,
        "advanced": {
            "kmeans_weights": pesos_kmeans,
            "swir_thresholds": umbrales_swir,
            "smoke_weights": pesos_humo,
            "smoke_threshold": umbral_humo,
            "water_thresholds": umbrales_agua,
            "fusion_kmeans_weight": peso_fusion_kmeans,
            "fusion_swir_weight": peso_fusion_swir,
            "fusion_threshold": umbral_fusion,
        },
    }


def _iniciar_analisis(job_id: str, true_bytes: bytes, swir_bytes: bytes, ajustes: dict[str, Any]) -> None:
    try:
        _actualizar_trabajo(job_id, stage="En cola para iniciar el análisis", progress=1)
        with _ANALYSIS_LOCK:
            _actualizar_trabajo(
                job_id,
                state="running",
                stage="Leyendo y comprobando la pareja de imágenes",
                progress=3,
            )
            pareja = preparar_pareja(true_bytes, swir_bytes, ajustes["gsd_m_per_px"])

            def progreso(etapa: str, porcentaje: int) -> None:
                _actualizar_trabajo(
                    job_id,
                    stage=str(etapa),
                    progress=max(0, min(100, int(porcentaje))),
                )

            tc, swir, resultado = procesar_pareja(
                pareja.true_color,
                pareja.swir,
                ajustes["sensitivity"],
                ajustes["num_classes"],
                ajustes["minimum_area_pct"],
                ajustes["max_distance_pct"],
                pareja.gsd_x_m,
                pareja.gsd_y_m,
                ajustes["detector"].id,
                ajustes["keep_separate"],
                progreso,
                ajustes["advanced"],
            )

            sistema = resultado.sistema_coordenadas
            pixeles = int(np.count_nonzero(resultado.mascara))
            area, unidad_area = sistema.area_de_pixeles(pixeles)
            perimetro = 0.0
            unidad_perimetro = "m" if sistema.gsd_x_m is not None else "px"
            for contorno in resultado.contornos:
                vertices = [tuple(map(float, punto[0])) for punto in contorno]
                longitud, unidad_perimetro = sistema.longitud_de_linea(vertices, cerrar=True)
                perimetro += longitud

            outputs = {
                "true-color": _png_bytes(tc),
                "swir": _png_bytes(swir),
                "overlay-true-color": _png_bytes(crear_superposicion(tc, resultado)),
                "overlay-swir": _png_bytes(crear_superposicion(swir, resultado)),
                "candidates": _png_bytes(crear_vista_clasificacion(tc, resultado)),
                "mask": _png_bytes(resultado.mascara),
            }
            metrics = {
                "detector": ajustes["detector"].nombre,
                "coverage_pct": float(resultado.proporcion * 100),
                "area": float(area),
                "area_unit": unidad_area,
                "perimeter": float(perimetro),
                "perimeter_unit": unidad_perimetro,
                "smoke_pct": float(np.mean(resultado.mascara_humo) * 100),
                "pixel_count": pixeles,
                "water_excluded": int(resultado.pixeles_agua_excluidos),
                "remote_regions_discarded": int(resultado.componentes_remotos_descartados),
                "grid_width": int(sistema.ancho_px),
                "grid_height": int(sistema.alto_px),
                "gsd_x_m": sistema.gsd_x_m,
                "gsd_y_m": sistema.gsd_y_m,
            }
            with _JOBS_LOCK:
                trabajo = _JOBS.get(job_id)
                if trabajo is not None:
                    trabajo.update(
                        state="complete",
                        stage="Análisis completado",
                        progress=100,
                        metrics=metrics,
                        grid=sistema.a_dict(),
                        outputs=outputs,
                        updated_at=time.time(),
                    )
    except Exception as exc:
        _actualizar_trabajo(
            job_id,
            state="error",
            stage="No se pudo completar el análisis",
            error=str(exc) or exc.__class__.__name__,
        )


class PyroScopeHandler(BaseHTTPRequestHandler):
    """Sirve el frontend y la API local de análisis."""

    server_version = "PyroScope/1.0"

    def do_GET(self) -> None:  # noqa: N802 - nombre requerido por BaseHTTPRequestHandler
        ruta = urlsplit(self.path).path
        if ruta == "/api/scenes":
            escenas = [
                {"id": escena.nombre, "label": escena.etiqueta, "name": escena.nombre, "date": escena.fecha}
                for escena in listar_escenas_disponibles()
            ]
            self._json(200, {"scenes": escenas})
            return
        if ruta == "/api/detectors":
            self._json(
                200,
                {
                    "detectors": [
                        {
                            "id": detector.id,
                            "name": detector.nombre,
                            "description": detector.descripcion,
                            "uses_num_classes": detector.usa_numero_clases,
                        }
                        for detector in listar_detectores_superficie()
                    ]
                },
            )
            return

        coincidencia = re.fullmatch(r"/api/jobs/([a-f0-9-]{36})", ruta)
        if coincidencia:
            with _JOBS_LOCK:
                trabajo = _JOBS.get(coincidencia.group(1))
                resumen = _resumen_trabajo(trabajo) if trabajo else None
            if resumen is None:
                self._json(404, {"error": "No se encontró ese análisis."})
            else:
                self._json(200, resumen)
            return

        imagen = re.fullmatch(r"/api/jobs/([a-f0-9-]{36})/layers/([a-z-]+)\.png", ruta)
        if imagen:
            job_id, nombre = imagen.groups()
            with _JOBS_LOCK:
                trabajo = _JOBS.get(job_id)
                datos = trabajo.get("outputs", {}).get(nombre) if trabajo else None
            if datos is None:
                self._json(404, {"error": "La capa todavía no está disponible."})
            else:
                self._bytes(200, datos, "image/png")
            return

        if ruta.startswith("/api/"):
            self._json(404, {"error": "Ruta no encontrada."})
            return

        if ruta == "/":
            self._servir_archivo(_WEB / "index.html")
            return

        archivo = _WEB / ruta.lstrip("/")
        try:
            archivo_resuelto = archivo.resolve(strict=True)
            archivo_resuelto.relative_to(_WEB.resolve())
            es_archivo = archivo_resuelto.is_file()
        except (OSError, ValueError):
            es_archivo = False
        if es_archivo:
            self._servir_archivo(archivo)
            return

        # Las rutas de cliente sin extensión pertenecen a la SPA de React.
        if not Path(ruta).suffix:
            self._servir_archivo(_WEB / "index.html")
            return

        self._json(404, {"error": "Archivo no encontrado."})

    def do_POST(self) -> None:  # noqa: N802
        ruta = urlsplit(self.path).path
        if ruta != "/api/analyze":
            self._json(404, {"error": "Ruta no encontrada."})
            return
        try:
            datos = self._leer_json()
            settings = datos.get("settings", {})
            if not isinstance(settings, dict):
                raise ValueError("Los ajustes del análisis deben ser un objeto.")
            ajustes = _validar_ajustes(settings)
            source = datos.get("source", "preloaded")
            if source == "preloaded":
                escena_id = datos.get("scene")
                escena = next(
                    (item for item in listar_escenas_disponibles() if item.nombre == escena_id),
                    None,
                )
                if escena is None:
                    raise ValueError("Selecciona una escena precargada válida.")
                true_bytes = escena.true_color.read_bytes()
                swir_bytes = escena.swir.read_bytes()
            elif source == "upload":
                true_encoded = datos.get("true_color", "")
                swir_encoded = datos.get("swir", "")
                if not isinstance(true_encoded, str) or not isinstance(swir_encoded, str):
                    raise ValueError("Las imágenes cargadas no tienen un formato válido.")
                true_bytes = base64.b64decode(true_encoded, validate=True)
                swir_bytes = base64.b64decode(swir_encoded, validate=True)
                if not true_bytes or not swir_bytes:
                    raise ValueError("Carga las dos imágenes: True Color y SWIR.")
            else:
                raise ValueError("El origen de las imágenes no es válido.")

            job_id = str(uuid.uuid4())
            now = time.time()
            with _JOBS_LOCK:
                expirados = [
                    key
                    for key, item in _JOBS.items()
                    if item["state"] in ("complete", "error") and now - item["updated_at"] > 3600
                ]
                for key in expirados:
                    _JOBS.pop(key, None)
                if len(_JOBS) >= 12:
                    raise ValueError("Hay demasiados análisis guardados en esta sesión. Reinicia la aplicación.")
                _JOBS[job_id] = {
                    "id": job_id,
                    "state": "queued",
                    "stage": "Preparando análisis",
                    "progress": 0,
                    "updated_at": now,
                }
            worker = threading.Thread(
                target=_iniciar_analisis,
                args=(job_id, true_bytes, swir_bytes, ajustes),
                name=f"pyroscope-{job_id[:8]}",
                daemon=True,
            )
            worker.start()
            self._json(202, {"job_id": job_id})
        except (ValueError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"No se pudo iniciar el análisis: {exc}"})

    def _leer_json(self) -> dict[str, Any]:
        try:
            longitud = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("La solicitud tiene un tamaño no válido.") from exc
        if longitud < 1 or longitud > _MAX_BODY_BYTES:
            raise ValueError("El tamaño de la solicitud no es válido o supera el límite local.")
        try:
            datos = json.loads(self.rfile.read(longitud))
        except json.JSONDecodeError as exc:
            raise ValueError("El cuerpo de la solicitud no contiene JSON válido.") from exc
        if not isinstance(datos, dict):
            raise ValueError("La solicitud debe ser un objeto JSON.")
        return datos

    def _servir_archivo(self, ruta: Path) -> None:
        try:
            ruta_resuelta = ruta.resolve(strict=True)
            ruta_resuelta.relative_to(_WEB.resolve())
        except (OSError, ValueError):
            self._json(404, {"error": "Archivo no encontrado."})
            return
        tipo = mimetypes.guess_type(ruta_resuelta.name)[0] or "application/octet-stream"
        self._bytes(200, ruta_resuelta.read_bytes(), tipo)

    def _json(self, codigo: int, datos: dict[str, Any]) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._bytes(codigo, cuerpo, "application/json; charset=utf-8")

    def _bytes(self, codigo: int, datos: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(datos)


def ejecutar_servidor(host: str = "127.0.0.1", puerto: int = 8501, abrir_navegador: bool = True) -> bool:
    """Inicia una sola instancia y elige puerto libre si el principal está ocupado.

    Devuelve ``False`` si ya hay una instancia de PyroScope activa.
    """
    if not _adquirir_bloque_instancia():
        print("PyroScope ya está ejecutándose; no se abrió otra instancia.")
        return False

    servidor = None
    try:
        for candidato in range(puerto, min(puerto + 20, 65536)):
            try:
                servidor = _ServidorWebExclusivo((host, candidato), PyroScopeHandler)
                break
            except OSError:
                continue
        if servidor is None:
            raise OSError(
                f"No se encontró un puerto libre entre {puerto} y {min(puerto + 19, 65535)}."
            )

        servidor.daemon_threads = True
        puerto_real = servidor.server_address[1]
        url = f"http://{host}:{puerto_real}/"
        print(f"PyroScope disponible en {url}")
        print("Mantén esta ventana abierta mientras usas la aplicación. Ctrl+C detiene el servidor.")
        if abrir_navegador:
            threading.Timer(0.8, webbrowser.open, args=(url,)).start()
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            print("\nCerrando PyroScope…")
    finally:
        if servidor is not None:
            servidor.server_close()
        _liberar_bloque_instancia()
    return True


__all__ = ["ejecutar_servidor"]
