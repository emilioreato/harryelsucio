"""Servidor HTTP local para la interfaz de Lumbre."""

from __future__ import annotations

import base64
import binascii
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import ipaddress
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
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
from .ontologia import ClaseSemantica
from .visualizacion import crear_superposicion, crear_vista_clasificacion, colorear_diagnostico
from .observabilidad_pipeline import CheckpointPipeline


_WEB = RAIZ_REPOSITORIO / "web"
_MAX_BODY_BYTES = 120 * 1024 * 1024
_MAX_JOBS = 12
_MAX_CHECKPOINTS_PER_JOB = 14
_MAX_CHECKPOINT_BYTES_PER_JOB = 8 * 1024 * 1024
_MAX_CHECKPOINT_IMAGE_BYTES = 1536 * 1024
_MAX_CHECKPOINTS_PER_IMAGE = 900
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.RLock()
_ANALYSIS_LOCK = threading.Lock()
_INSTANCIA_LOCK: Any | None = None
_ID_INSTANCIA: str | None = None
_TOKEN_INSTANCIA: str | None = None
_RUTA_ESTADO_INSTANCIA = RAIZ_REPOSITORIO / ".lumbre-instance.json"
_RUTA_BLOQUE_INSTANCIA = RAIZ_REPOSITORIO / ".lumbre-instance.lock"


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
    archivo = _RUTA_BLOQUE_INSTANCIA.open("a+b")
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


def _es_instancia_lumbre(url: str, id_instancia: str | None = None) -> bool:
    """Comprueba la identidad de una instancia sin confundir copias distintas."""
    try:
        with urlopen(f"{url.rstrip('/')}/api/health", timeout=0.6) as respuesta:
            estado = json.loads(respuesta.read().decode("utf-8"))
        if estado.get("app") != "Lumbre":
            return False
        if id_instancia is not None and estado.get("instance_id") != id_instancia:
            return False

        raiz_activa = estado.get("repository_root")
        if not isinstance(raiz_activa, str):
            # Las versiones anteriores no publicaban la carpeta. Solo las
            # aceptamos si su UUID coincide con el estado guardado en ESTA copia.
            return id_instancia is not None

        return (
            os.path.normcase(os.path.abspath(raiz_activa))
            == os.path.normcase(str(RAIZ_REPOSITORIO.resolve()))
        )
    except Exception:
        return False


def _instancia_habilita_movil(url: str) -> bool:
    try:
        with urlopen(f"{url.rstrip('/')}/api/mobile-access", timeout=0.6) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        return datos.get("enabled") is True
    except Exception:
        return False


def _buscar_instancia_activa(host: str, puerto: int) -> str | None:
    try:
        direccion = ipaddress.ip_address(host)
        host_local = host if direccion.is_loopback else "127.0.0.1"
    except ValueError:
        host_local = "127.0.0.1"
    host_url = f"[{host_local}]" if ":" in host_local else host_local
    for candidato in range(puerto, min(puerto + 20, 65536)):
        url = f"http://{host_url}:{candidato}"
        if _es_instancia_lumbre(url):
            return url
    return None


def _leer_estado_instancia() -> dict[str, Any] | None:
    try:
        datos = json.loads(_RUTA_ESTADO_INSTANCIA.read_text(encoding="utf-8"))
        url = str(datos["url"])
        partes = urlsplit(url)
        if partes.scheme != "http" or not partes.hostname or not partes.port:
            return None
        if not ipaddress.ip_address(partes.hostname).is_loopback:
            return None
        if not isinstance(datos.get("token"), str) or not isinstance(
            datos.get("instance_id"), str
        ):
            return None
        return datos
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _guardar_estado_instancia(url: str) -> None:
    global _ID_INSTANCIA, _TOKEN_INSTANCIA
    _ID_INSTANCIA = uuid.uuid4().hex
    _TOKEN_INSTANCIA = secrets.token_urlsafe(32)
    estado = {
        "pid": os.getpid(),
        "url": url,
        "instance_id": _ID_INSTANCIA,
        "token": _TOKEN_INSTANCIA,
    }
    temporal = _RUTA_ESTADO_INSTANCIA.with_name(f".lumbre-instance.{os.getpid()}.tmp")
    temporal.write_text(json.dumps(estado), encoding="utf-8")
    os.replace(temporal, _RUTA_ESTADO_INSTANCIA)


def _borrar_estado_instancia() -> None:
    if _TOKEN_INSTANCIA is None:
        return
    estado = _leer_estado_instancia()
    if estado and hmac.compare_digest(str(estado.get("token", "")), _TOKEN_INSTANCIA):
        try:
            _RUTA_ESTADO_INSTANCIA.unlink()
        except FileNotFoundError:
            pass


def _abrir_navegador(url: str) -> None:
    try:
        if webbrowser.open(url, new=2):
            return
    except Exception:
        pass
    if os.name == "nt":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return
        except OSError:
            pass
    print(f"No se pudo abrir el navegador automáticamente. Abre: {url}")


def _obtener_ip_lan() -> str | None:
    """Obtiene la IPv4 privada que Windows/Linux usaría para salir a la red."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conexion:
            conexion.connect(("8.8.8.8", 80))
            direccion = conexion.getsockname()[0]
        if ipaddress.ip_address(direccion).is_private:
            return direccion
    except OSError:
        pass

    try:
        candidatos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return None
    for candidato in candidatos:
        direccion = candidato[4][0]
        try:
            ip = ipaddress.ip_address(direccion)
        except ValueError:
            continue
        if ip.is_private and not ip.is_loopback and not ip.is_link_local:
            return direccion
    return None


def cerrar_servidor_local() -> bool:
    """Solicita el cierre solo a la instancia local de este repositorio."""
    estado = _leer_estado_instancia()
    if estado is None:
        url_antigua = _buscar_instancia_activa("127.0.0.1", 8501)
        if url_antigua:
            print(
                "Lumbre está abierta, pero no se encontró el estado de cierre de esta copia. "
                "Se buscará el proceso exacto del proyecto como último recurso."
            )
        else:
            print("Lumbre ya estaba cerrada.")
            return True
        return False

    url = str(estado["url"])
    instance_id = str(estado["instance_id"])
    if not _es_instancia_lumbre(url, instance_id):
        print("El servidor no responde; se comprobará el proceso registrado como último recurso.")
        return False

    solicitud = Request(
        f"{url.rstrip('/')}/api/shutdown",
        data=b"",
        headers={"X-Lumbre-Token": str(estado["token"])},
        method="POST",
    )
    try:
        with urlopen(solicitud, timeout=2) as respuesta:
            respuesta.read()
    except Exception as exc:
        print(f"No se pudo cerrar Lumbre: {exc}")
        return False

    limite = time.monotonic() + 5
    while time.monotonic() < limite:
        if not _es_instancia_lumbre(url, instance_id):
            print("Lumbre se ha cerrado.")
            return True
        time.sleep(0.15)
    print("La solicitud de cierre se envió, pero el servidor todavía responde.")
    return False


def _png_bytes(imagen: np.ndarray) -> bytes:
    salida = BytesIO()
    datos = np.asarray(imagen)
    if datos.dtype == np.bool_:
        datos = datos.astype(np.uint8) * 255
    Image.fromarray(datos).save(salida, format="PNG")
    return salida.getvalue()


def _capas_adicionales(resultado: Any) -> dict[str, bytes]:
    """Exporta observación y oclusión separadas sin exigir campos nuevos al detector."""
    capas = {}
    for nombre, campo in (
        ("smoke", "mascara_humo"),
        ("smoke-candidates", "mascara_candidata_bajo_humo"),
        ("visible-surface", "mascara_superficie_visible"),
        ("smoke-unknown", "mascara_indeterminada"),
        ("smoke-spectral", "mascara_bajo_humo_espectral"),
        ("smoke-continuity", "mascara_bajo_humo_continuidad"),
    ):
        datos = getattr(resultado, campo, None)
        if datos is not None:
            capas[nombre] = _png_bytes(np.asarray(datos, dtype=bool))
    for nombre, datos in (getattr(resultado, "diagnosticos_contextuales", None) or {}).items():
        nombre_seguro = re.sub(r"[^a-z]+", "-", str(nombre).lower()).strip("-")
        if nombre_seguro and datos is not None:
            capas[f"diagnostic-{nombre_seguro}"] = _png_bytes(colorear_diagnostico(datos))
    return capas


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
        "checkpoints": [dict(item) for item in trabajo.get("checkpoints", ())],
        "checkpoint_warnings": list(trabajo.get("checkpoint_warnings", ())),
    }


def _jpeg_checkpoint(imagen: np.ndarray) -> bytes:
    """Codifica una vista RGB ligera; se ejecuta fuera del bloqueo de trabajos."""
    datos = np.asarray(imagen)
    if datos.ndim != 3 or datos.shape[2] != 3 or datos.dtype != np.uint8 or not datos.size:
        raise ValueError("La imagen del checkpoint debe ser RGB uint8 y no estar vacía.")
    vista = Image.fromarray(datos, mode="RGB")
    vista.thumbnail(
        (_MAX_CHECKPOINTS_PER_IMAGE, _MAX_CHECKPOINTS_PER_IMAGE),
        Image.Resampling.LANCZOS,
    )
    salida = BytesIO()
    vista.save(salida, format="JPEG", quality=75, optimize=True)
    contenido = salida.getvalue()
    if len(contenido) > _MAX_CHECKPOINT_IMAGE_BYTES:
        salida = BytesIO()
        vista.save(salida, format="JPEG", quality=58, optimize=True)
        contenido = salida.getvalue()
    if len(contenido) > _MAX_CHECKPOINT_IMAGE_BYTES:
        raise ValueError("La previsualización supera el límite de memoria por checkpoint.")
    return contenido


def _jpeg_scene_preview(ruta: Path) -> bytes:
    """Crea una miniatura JPEG para el selector sin exponer la ruta del archivo."""
    with Image.open(ruta) as original:
        original.thumbnail((480, 300), Image.Resampling.LANCZOS)
        vista = original.convert("RGB")
    salida = BytesIO()
    vista.save(salida, format="JPEG", quality=76, optimize=True)
    return salida.getvalue()


def _registrar_aviso_checkpoint(job_id: str, error: Exception) -> None:
    mensaje = str(error).strip() or error.__class__.__name__
    logging.getLogger(__name__).warning("No se pudo guardar una captura de %s: %s", job_id, mensaje)
    with _JOBS_LOCK:
        trabajo = _JOBS.get(job_id)
        if trabajo is not None:
            avisos = trabajo.setdefault("checkpoint_warnings", [])
            avisos.append(mensaje[:240])
            del avisos[:-5]
            trabajo["updated_at"] = time.time()


def _publicar_checkpoint_trabajo(job_id: str, checkpoint: CheckpointPipeline) -> None:
    """Codifica fuera del lock y publica bytes + metadata en una sola sección crítica."""
    imagen = _jpeg_checkpoint(checkpoint.image)
    image_url = f"/api/jobs/{job_id}/checkpoints/{checkpoint.id}.jpg"
    metadata = checkpoint.metadata(image_url)
    with _JOBS_LOCK:
        trabajo = _JOBS.get(job_id)
        if trabajo is None or trabajo.get("state") not in ("running", "queued"):
            return
        imagenes = trabajo.setdefault("checkpoint_images", {})
        capturas = trabajo.setdefault("checkpoints", [])
        if checkpoint.id in imagenes:
            return
        imagenes[checkpoint.id] = imagen
        capturas.append(metadata)
        trabajo["checkpoint_bytes"] = int(trabajo.get("checkpoint_bytes", 0)) + len(imagen)
        while (
            len(capturas) > _MAX_CHECKPOINTS_PER_JOB
            or trabajo["checkpoint_bytes"] > _MAX_CHECKPOINT_BYTES_PER_JOB
        ):
            primera_id = capturas[0]["id"] if capturas else None
            candidatos = [
                item for item in capturas
                if item["id"] != primera_id and item["id"] != checkpoint.id
            ]
            if not candidatos:
                break
            obsoleta = candidatos[0]
            capturas.remove(obsoleta)
            trabajo["checkpoint_bytes"] -= len(imagenes.pop(obsoleta["id"], b""))
        trabajo.update(
            stage=checkpoint.label,
            progress=max(int(trabajo.get("progress", 0)), checkpoint.progress),
            updated_at=time.time(),
        )


def _validar_ajustes(datos: dict[str, Any]) -> dict[str, Any]:
    metodo = str(datos.get("method", "contextual_hibrida"))
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
    usar_random_forest = avanzado_entrada.get("use_random_forest", False)
    if not isinstance(usar_random_forest, bool):
        raise ValueError("La opción Random Forest debe ser booleana.")

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
        semilla_roja = 0.958 - (entero("sensitivity", 1, 10, 5) - 1) * 0.009
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
            "use_random_forest": usar_random_forest,
        },
    }


def _iniciar_analisis(
    job_id: str,
    true_bytes: bytes,
    swir_bytes: bytes,
    ajustes: dict[str, Any],
    referencia_wildfires_bytes: bytes | None = None,
) -> None:
    try:
        _actualizar_trabajo(job_id, stage="En cola para iniciar el análisis", progress=1)
        with _ANALYSIS_LOCK:
            _actualizar_trabajo(
                job_id,
                state="running",
                stage="Leyendo y comprobando la pareja de imágenes",
                progress=3,
            )
            from .interfaz.configuracion import MAX_LADO_ANALISIS, MAX_LADO_CONTEXTUAL
            pareja = preparar_pareja(
                true_bytes, swir_bytes, ajustes["gsd_m_per_px"],
                max_lado=MAX_LADO_CONTEXTUAL if ajustes["detector"].id == "contextual_hibrida" else MAX_LADO_ANALISIS,
            )

            def progreso(etapa: str, porcentaje: int) -> None:
                with _JOBS_LOCK:
                    trabajo = _JOBS.get(job_id)
                    if trabajo is not None:
                        trabajo.update(
                            stage=str(etapa),
                            progress=max(
                                int(trabajo.get("progress", 0)),
                                max(0, min(99, int(porcentaje))),
                            ),
                            updated_at=time.time(),
                        )

            def checkpoint_error(error: Exception) -> None:
                _registrar_aviso_checkpoint(job_id, error)

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
                on_checkpoint=lambda captura: _publicar_checkpoint_trabajo(job_id, captura),
                on_checkpoint_error=checkpoint_error,
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
            advertencia_referencia = None
            if referencia_wildfires_bytes:
                try:
                    with Image.open(BytesIO(referencia_wildfires_bytes)) as referencia:
                        proporcion_referencia = referencia.width / referencia.height
                        proporcion_rejilla = sistema.ancho_px / sistema.alto_px
                        if abs(proporcion_referencia - proporcion_rejilla) > 0.002:
                            advertencia_referencia = (
                                "La referencia Wildfires tiene una proporción distinta y no se mostró."
                            )
                        else:
                            referencia = referencia.convert("RGB").resize(
                                (sistema.ancho_px, sistema.alto_px),
                                Image.Resampling.LANCZOS,
                            )
                            outputs["reference-wildfires"] = _png_bytes(np.asarray(referencia))
                except Exception:
                    advertencia_referencia = "No se pudo leer la referencia Wildfires; el análisis sí terminó."
            outputs.update(_capas_adicionales(resultado))
            metrics = {
                "available_layers": list(outputs),
                "detector": ajustes["detector"].nombre,
                "warnings": list(resultado.avisos),
                "coverage_pct": float(resultado.proporcion * 100),
                "area": float(area),
                "area_unit": unidad_area,
                "perimeter": float(perimetro),
                "perimeter_unit": unidad_perimetro,
                "smoke_pct": float(np.mean(resultado.mascara_humo) * 100),
                "smoke_covered_candidates_px": int(
                    np.count_nonzero(resultado.mascara_candidata_bajo_humo)
                ),
                "smoke_unknown_px": int(np.count_nonzero(
                    getattr(resultado, "mascara_indeterminada", None)
                )),
                "pixel_count": pixeles,
                "water_excluded": int(resultado.pixeles_agua_excluidos),
                "active_fire_px": int(
                    np.count_nonzero(
                        resultado.clase_por_pixel == ClaseSemantica.FUEGO_ACTIVO_POSIBLE
                    )
                ),
                "remote_regions_discarded": int(resultado.componentes_remotos_descartados),
                "grid_width": int(sistema.ancho_px),
                "grid_height": int(sistema.alto_px),
                "gsd_x_m": sistema.gsd_x_m,
                "gsd_y_m": sistema.gsd_y_m,
            }
            if advertencia_referencia:
                metrics["reference_warning"] = advertencia_referencia
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


class LumbreHandler(BaseHTTPRequestHandler):
    """Sirve el frontend y la API local de análisis."""

    server_version = "Lumbre/1.0"

    def do_GET(self) -> None:  # noqa: N802 - nombre requerido por BaseHTTPRequestHandler
        ruta = urlsplit(self.path).path
        if ruta == "/api/health":
            self._json(
                200,
                {
                    "app": "Lumbre",
                    "instance_id": _ID_INSTANCIA,
                    "pid": os.getpid(),
                    "repository_root": str(RAIZ_REPOSITORIO.resolve()),
                },
            )
            return
        if ruta == "/api/mobile-access":
            host, puerto = self.server.server_address[:2]
            ip_lan = _obtener_ip_lan() if host in ("0.0.0.0", "::") else None
            self._json(
                200,
                {
                    "enabled": ip_lan is not None,
                    "url": f"http://{ip_lan}:{puerto}/" if ip_lan else None,
                },
            )
            return
        vista_escena = re.fullmatch(r"/api/scenes/([^/]+)/preview/(true-color|swir)", ruta)
        if vista_escena:
            escena_id, canal = vista_escena.groups()
            escena_id = unquote(escena_id)
            escena = next(
                (item for item in listar_escenas_disponibles() if item.nombre == escena_id),
                None,
            )
            if escena is None:
                self._json(404, {"error": "No se encontró esa escena."})
                return
            ruta_imagen = escena.true_color if canal == "true-color" else escena.swir
            try:
                miniatura = _jpeg_scene_preview(ruta_imagen)
            except (OSError, ValueError) as exc:
                logging.getLogger(__name__).warning(
                    "No se pudo crear la vista previa de %s (%s): %s",
                    escena_id,
                    canal,
                    exc,
                )
                self._json(422, {"error": "No se pudo leer la imagen de esta escena."})
                return
            self._bytes(200, miniatura, "image/jpeg")
            return
        if ruta == "/api/scenes":
            escenas = [
                {
                    "id": escena.nombre,
                    "label": escena.etiqueta,
                    "name": escena.nombre,
                    "date": escena.fecha,
                    "has_wildfires_reference": escena.referencia_wildfires is not None,
                    "gsd_m_per_px": escena.gsd_m_por_pixel,
                }
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
                            "uses_sensitivity": detector.usa_sensibilidad,
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

        captura = re.fullmatch(
            r"/api/jobs/([a-f0-9-]{36})/checkpoints/([a-z0-9][a-z0-9-]{0,63})\.jpg",
            ruta,
        )
        if captura:
            job_id, checkpoint_id = captura.groups()
            with _JOBS_LOCK:
                trabajo = _JOBS.get(job_id)
                datos = (
                    trabajo.get("checkpoint_images", {}).get(checkpoint_id)
                    if trabajo else None
                )
            if datos is None:
                self._json(404, {"error": "La captura todavía no está disponible."})
            else:
                self._bytes(200, datos, "image/jpeg")
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
        if ruta == "/api/shutdown":
            try:
                cliente_local = ipaddress.ip_address(self.client_address[0]).is_loopback
            except ValueError:
                cliente_local = False
            token_recibido = self.headers.get("X-Lumbre-Token", "")
            if (
                not cliente_local
                or _TOKEN_INSTANCIA is None
                or not hmac.compare_digest(token_recibido, _TOKEN_INSTANCIA)
            ):
                self._json(403, {"error": "Solicitud de cierre no autorizada."})
                return
            self._json(200, {"message": "Cerrando Lumbre."})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
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
                referencia_wildfires_bytes = (
                    escena.referencia_wildfires.read_bytes()
                    if escena.referencia_wildfires is not None
                    else None
                )
            elif source == "upload":
                true_encoded = datos.get("true_color", "")
                swir_encoded = datos.get("swir", "")
                if not isinstance(true_encoded, str) or not isinstance(swir_encoded, str):
                    raise ValueError("Las imágenes cargadas no tienen un formato válido.")
                true_bytes = base64.b64decode(true_encoded, validate=True)
                swir_bytes = base64.b64decode(swir_encoded, validate=True)
                referencia_wildfires_bytes = None
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
                if len(_JOBS) >= _MAX_JOBS:
                    # Las máscaras terminadas conservan imágenes en memoria. Cuando
                    # se alcanza el cupo, libera primero los resultados más antiguos
                    # y mantiene intactos todos los trabajos pendientes o activos.
                    terminados = sorted(
                        (
                            (key, item)
                            for key, item in _JOBS.items()
                            if item["state"] in ("complete", "error")
                        ),
                        key=lambda par: par[1]["updated_at"],
                    )
                    while len(_JOBS) >= _MAX_JOBS and terminados:
                        key, _ = terminados.pop(0)
                        _JOBS.pop(key, None)
                if len(_JOBS) >= _MAX_JOBS:
                    raise ValueError("Hay doce análisis activos o en cola. Espera a que termine alguno antes de iniciar otro.")
                _JOBS[job_id] = {
                    "id": job_id,
                    "state": "queued",
                    "stage": "Preparando análisis",
                    "progress": 0,
                    "updated_at": now,
                    "checkpoints": [],
                    "checkpoint_images": {},
                    "checkpoint_bytes": 0,
                    "checkpoint_warnings": [],
                }
            worker = threading.Thread(
                target=_iniciar_analisis,
                args=(job_id, true_bytes, swir_bytes, ajustes, referencia_wildfires_bytes),
                name=f"lumbre-{job_id[:8]}",
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

    Reutiliza la instancia activa y devuelve ``False`` si ya hay una instancia.
    """
    url_existente = _buscar_instancia_activa(host, puerto)
    if url_existente:
        if host == "0.0.0.0" and not _instancia_habilita_movil(url_existente):
            print(
                "Lumbre ya está abierta en modo local. Ciérrala con Ctrl+C en su ventana "
                "y vuelve a iniciar encender_movil.bat para mostrar el QR."
            )
            _abrir_navegador(f"{url_existente}/")
            return False
        if abrir_navegador:
            print(f"Lumbre ya está abierta en {url_existente}/. Abriendo esa instancia.")
            _abrir_navegador(f"{url_existente}/")
        else:
            print(f"Lumbre ya está abierta en {url_existente}/.")
        return False

    if not _adquirir_bloque_instancia():
        # Puede seguir viva una versión anterior de esta misma carpeta. Si el
        # archivo de estado y su UUID lo confirman, la cerramos limpiamente para
        # que el nuevo código Python pueda arrancar sin reutilizar otra copia.
        estado_local = None
        url_existente = None
        limite = time.monotonic() + 4
        while time.monotonic() < limite:
            estado = _leer_estado_instancia()
            if estado and _es_instancia_lumbre(
                str(estado["url"]), str(estado["instance_id"])
            ):
                estado_local = estado
                break
            url_existente = _buscar_instancia_activa(host, puerto)
            if url_existente:
                break
            time.sleep(0.15)

        if estado_local:
            print("He detectado una versión anterior de esta carpeta. Cerrándola para actualizar…")
            if not cerrar_servidor_local():
                print(
                    "No se pudo cerrar la instancia anterior automáticamente. "
                    "Pulsa Ctrl+C en la ventana negra anterior y vuelve a iniciar."
                )
                return False

            limite = time.monotonic() + 5
            while time.monotonic() < limite:
                if _adquirir_bloque_instancia():
                    break
                time.sleep(0.15)
            else:
                print(
                    "La versión anterior se cerró, pero Windows todavía mantiene "
                    "el bloqueo. Espera un momento y vuelve a ejecutar el lanzador."
                )
                return False
            print("Instancia anterior cerrada; iniciando la versión actualizada.")
        elif url_existente:
            if host == "0.0.0.0" and not _instancia_habilita_movil(url_existente):
                print(
                    "Lumbre ya está abierta en modo local. Ciérrala con Ctrl+C en su ventana "
                    "y vuelve a iniciar encender_movil.bat para mostrar el QR."
                )
                _abrir_navegador(f"{url_existente}/")
                return False
            if abrir_navegador:
                print(f"Lumbre ya está abierta en esta carpeta: {url_existente}/. Abriendo esa instancia.")
                _abrir_navegador(f"{url_existente}/")
            else:
                print(f"Lumbre ya está abierta en esta carpeta: {url_existente}/.")
            return False
        else:
            print(
                "Otra ejecución mantiene bloqueada esta carpeta, pero no he podido "
                "verificarla. No se ha cerrado ningún proceso. Pulsa Ctrl+C en la "
                "ventana negra que esté ejecutando esta misma carpeta y vuelve a iniciar."
            )
            return False

    servidor = None
    try:
        for candidato in range(puerto, min(puerto + 20, 65536)):
            try:
                servidor = _ServidorWebExclusivo((host, candidato), LumbreHandler)
                break
            except OSError:
                continue
        if servidor is None:
            raise OSError(
                f"No se encontró un puerto libre entre {puerto} y {min(puerto + 19, 65535)}."
            )

        servidor.daemon_threads = True
        puerto_real = servidor.server_address[1]
        host_control = "127.0.0.1" if host == "0.0.0.0" else host
        url = f"http://{host_control}:{puerto_real}/"
        _guardar_estado_instancia(url.rstrip("/"))
        print(f"Lumbre disponible en {url}")
        if host == "0.0.0.0":
            ip_lan = _obtener_ip_lan()
            if ip_lan:
                print(f"Acceso móvil: http://{ip_lan}:{puerto_real}/ (misma Wi-Fi).")
            else:
                print("Acceso móvil: consulta el QR que se mostrará en Lumbre.")
        print("Mantén esta ventana abierta mientras usas la aplicación. Ctrl+C detiene el servidor.")
        if abrir_navegador:
            temporizador = threading.Timer(0.8, _abrir_navegador, args=(url,))
            temporizador.daemon = True
            temporizador.start()
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            print("\nCerrando Lumbre…")
    finally:
        if servidor is not None:
            servidor.server_close()
        _borrar_estado_instancia()
        _liberar_bloque_instancia()
    return True


__all__ = ["cerrar_servidor_local", "ejecutar_servidor"]
