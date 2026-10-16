"""Construye paquetes autocontenidos para revisar resultados con una IA."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from io import BytesIO
import json
import math
import re
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageFont


_MAX_ANOTACIONES = 500
_MAX_PUNTOS_POR_ANOTACION = 5000
_TIPOS_ANOTACION = {"freehand", "line", "arrow", "rectangle", "ellipse", "text"}
_CAPAS_VISTA = {
    "true-color": "True Color alineado",
    "swir": "SWIR alineado",
    "candidates": "Clasificación combinada",
    "reference-wildfires": "Referencia Wildfires",
}
_DESCRIPCIONES_CAPA = {
    "estimated-surface": "Unión final de superficie visible, evidencia SWIR bajo humo y continuidad local respaldada por SWIR; zona quemada estimada, no confirmada.",
    "surface-continuity": "Continuidad inferida en huecos y separaciones pequeños con respaldo SWIR; no se suma al área observada.",
    "diagnostic-under-smoke-cyan-evidence": "Contraste residual SWIR bajo cian: solo diagnóstico; no alimenta la clasificación de superficie.",
    "diagnostic-smoke-contextual-veil": "Velo atmosférico conectado añadido antes de evaluar la superficie bajo humo, independientemente de la máscara quemada.",
    "true-color": "Entrada True Color preparada en la rejilla común del análisis.",
    "swir": "Entrada SWIR preparada en la rejilla común del análisis.",
    "overlay-true-color": "Vista combinada True Color con humo, superficies, clases y bordes.",
    "overlay-swir": "Vista combinada SWIR con humo, superficies, clases y bordes.",
    "candidates": "Vista coloreada de la clasificación estimada; no es verdad terreno.",
    "mask": "Máscara binaria de superficie candidata principal (0 = fuera, 255 = dentro).",
    "classified-candidates": "Máscara binaria candidata del detector antes del filtro geométrico final.",
    "visible-surface": "Máscara binaria de superficie candidata visible fuera del humo.",
    "visible-surface-border": "Borde interior de la máscara de superficie candidata visible, en píxeles.",
    "smoke": "Máscara binaria de humo probable; no representa humo confirmado.",
    "smoke-border": "Borde interior de la máscara de humo probable, en píxeles.",
    "smoke-candidates": "Hipótesis binaria de superficie candidata bajo humo; no confirmada.",
    "smoke-candidates-border": "Borde interior de la hipótesis de superficie candidata bajo humo.",
    "smoke-unknown": "Zonas bajo humo sin evidencia suficiente para clasificarlas.",
    "smoke-spectral": "Evidencia espectral candidata bajo humo.",
    "smoke-continuity": "Evidencia geométrica de continuidad bajo humo.",
    "semantic-classes": "Raster de identificadores de la ontología semántica; la tabla de clases está en manifest.json.",
    "class-undetermined": "Máscara binaria de píxeles indeterminados o sin clasificar.",
    "class-vegetation": "Máscara binaria de vegetación según la clasificación estimada.",
    "class-water": "Máscara binaria de agua posible según la clasificación estimada.",
    "class-smoke-probable": "Máscara binaria de humo probable según la clasificación semántica.",
    "class-affected-surface-candidate": "Máscara binaria de superficie afectada candidata según la clasificación.",
    "class-active-fire-possible": "Máscara binaria de posible fuego activo; no es detección térmica confirmada.",
    "class-cloud-haze": "Máscara binaria de nube o bruma según la clasificación estimada.",
    "class-bare-soil-urban": "Máscara binaria de suelo desnudo o zona urbana según la clasificación estimada.",
    "reference-wildfires": "Referencia visual Wildfires; no es verdad terreno ni una medición térmica.",
}


def validar_anotaciones(
    anotaciones: Any, ancho: int, alto: int
) -> list[dict[str, Any]]:
    """Valida y normaliza anotaciones expresadas en coordenadas de imagen."""
    if anotaciones is None:
        return []
    if not isinstance(anotaciones, list) or len(anotaciones) > _MAX_ANOTACIONES:
        raise ValueError(f"El paquete admite hasta {_MAX_ANOTACIONES} anotaciones.")

    normalizadas = []
    for indice, anotacion in enumerate(anotaciones, start=1):
        if not isinstance(anotacion, dict):
            raise ValueError(f"La anotación {indice} no tiene un formato válido.")
        tipo = anotacion.get("kind")
        if not isinstance(tipo, str) or tipo not in _TIPOS_ANOTACION:
            raise ValueError(f"La anotación {indice} tiene un tipo desconocido.")
        puntos = anotacion.get("points")
        if not isinstance(puntos, list) or not 1 <= len(puntos) <= _MAX_PUNTOS_POR_ANOTACION:
            raise ValueError(f"La anotación {indice} tiene una cantidad de puntos no válida.")
        if tipo in {"line", "arrow", "rectangle", "ellipse"} and len(puntos) != 2:
            raise ValueError(f"La anotación {indice} debe tener dos extremos.")
        if tipo == "text" and len(puntos) != 1:
            raise ValueError(f"La anotación {indice} debe tener un punto de anclaje.")

        puntos_normalizados = []
        for punto in puntos:
            if not isinstance(punto, dict):
                raise ValueError(f"La anotación {indice} contiene un punto no válido.")
            x, y = punto.get("x"), punto.get("y")
            if (isinstance(x, bool) or isinstance(y, bool)
                    or not isinstance(x, (int, float)) or not isinstance(y, (int, float))):
                raise ValueError(f"La anotación {indice} se sale de la rejilla de imagen.")
            try:
                x, y = float(x), float(y)
            except (OverflowError, ValueError) as exc:
                raise ValueError(f"La anotación {indice} se sale de la rejilla de imagen.") from exc
            if (not math.isfinite(x) or not math.isfinite(y)
                    or not 0 <= x <= ancho - 1 or not 0 <= y <= alto - 1):
                raise ValueError(f"La anotación {indice} se sale de la rejilla de imagen.")
            puntos_normalizados.append({"x": round(x, 3), "y": round(y, 3)})

        color = anotacion.get("color", "#ff4fa3")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError(f"El color de la anotación {indice} no es válido.")
        grosor = anotacion.get("width", 4)
        if isinstance(grosor, bool) or not isinstance(grosor, (int, float)):
            raise ValueError(f"El grosor de la anotación {indice} no es válido.")
        try:
            grosor = float(grosor)
        except (OverflowError, ValueError) as exc:
            raise ValueError(f"El grosor de la anotación {indice} no es válido.") from exc
        if not math.isfinite(grosor) or not 1 <= grosor <= 24:
            raise ValueError(f"El grosor de la anotación {indice} no es válido.")

        entrada = {
            "id": str(anotacion.get("id", indice))[:80],
            "kind": tipo,
            "points": puntos_normalizados,
            "color": color.lower(),
            "width": grosor,
        }
        if tipo == "text":
            texto = anotacion.get("text")
            if not isinstance(texto, str) or not texto.strip() or len(texto) > 500:
                raise ValueError(f"El texto de la anotación {indice} debe tener entre 1 y 500 caracteres.")
            entrada["text"] = texto.strip()
        normalizadas.append(entrada)
    return normalizadas


def _cargar_mascara(capas: dict[str, bytes], nombre: str, forma: tuple[int, int]) -> np.ndarray | None:
    contenido = capas.get(nombre)
    if contenido is None:
        return None
    with Image.open(BytesIO(contenido)) as imagen:
        mascara = np.asarray(imagen.convert("L")) >= 128
    if mascara.shape != forma:
        raise ValueError(f"La capa {nombre!r} no coincide con la rejilla declarada.")
    return mascara


def _borde(mascara: np.ndarray) -> np.ndarray:
    arriba = np.ones_like(mascara)
    abajo = np.ones_like(mascara)
    izquierda = np.ones_like(mascara)
    derecha = np.ones_like(mascara)
    arriba[1:, :] = ~mascara[:-1, :]
    abajo[:-1, :] = ~mascara[1:, :]
    izquierda[:, 1:] = ~mascara[:, :-1]
    derecha[:, :-1] = ~mascara[:, 1:]
    return mascara & (arriba | abajo | izquierda | derecha)


def _mezclar(
    pixeles: np.ndarray, seleccion: np.ndarray, color: tuple[int, int, int], alpha: float
) -> None:
    if not np.any(seleccion):
        return
    pixeles[seleccion] = np.clip(
        pixeles[seleccion].astype(np.float32) * (1.0 - alpha)
        + np.asarray(color, dtype=np.float32) * alpha,
        0,
        255,
    ).astype(np.uint8)


def _color_rgb(color: str) -> tuple[int, int, int]:
    return tuple(bytes.fromhex(color[1:]))  # type: ignore[return-value]


def _dibujar_anotaciones(imagen: Image.Image, anotaciones: list[dict[str, Any]]) -> None:
    dibujante = ImageDraw.Draw(imagen)
    for anotacion in anotaciones:
        puntos = [(round(p["x"]), round(p["y"])) for p in anotacion["points"]]
        color = _color_rgb(anotacion["color"])
        ancho = max(1, round(anotacion["width"]))
        tipo = anotacion["kind"]
        if tipo == "freehand":
            if len(puntos) == 1:
                x, y = puntos[0]
                radio = max(1, ancho // 2)
                dibujante.ellipse((x - radio, y - radio, x + radio, y + radio), fill=color)
            else:
                dibujante.line(puntos, fill=color, width=ancho, joint="curve")
        elif tipo in {"line", "arrow"}:
            inicio, fin = puntos
            dibujante.line((inicio, fin), fill=color, width=ancho)
            if tipo == "arrow":
                angulo = math.atan2(fin[1] - inicio[1], fin[0] - inicio[0])
                largo = max(12, ancho * 4)
                lateral = math.pi / 7
                ala1 = (round(fin[0] - largo * math.cos(angulo - lateral)),
                        round(fin[1] - largo * math.sin(angulo - lateral)))
                ala2 = (round(fin[0] - largo * math.cos(angulo + lateral)),
                        round(fin[1] - largo * math.sin(angulo + lateral)))
                dibujante.polygon((fin, ala1, ala2), fill=color)
        elif tipo == "rectangle":
            dibujante.rectangle((*puntos[0], *puntos[1]), outline=color, width=ancho)
        elif tipo == "ellipse":
            dibujante.ellipse((*puntos[0], *puntos[1]), outline=color, width=ancho)
        elif tipo == "text":
            x, y = puntos[0]
            try:
                fuente = ImageFont.truetype("DejaVuSans.ttf", size=24)
            except OSError:
                fuente = ImageFont.load_default()
            dibujante.text((x, y), anotacion["text"], fill=color, font=fuente,
                           stroke_width=max(1, ancho), stroke_fill=(8, 14, 22))


def _mapa_anotado(
    trabajo: dict[str, Any], anotaciones: list[dict[str, Any]], vista: dict[str, Any]
) -> bytes:
    capas: dict[str, bytes] = trabajo["outputs"]
    nombre_vista = vista.get("layer", "true-color")
    if nombre_vista not in _CAPAS_VISTA:
        raise ValueError("La capa visible indicada no es válida.")
    contenido = capas.get(nombre_vista)
    if contenido is None:
        raise ValueError(f"La capa visible {nombre_vista!r} no está disponible para exportar.")
    alto = int(trabajo["grid"]["alto_px"])
    ancho = int(trabajo["grid"]["ancho_px"])
    with Image.open(BytesIO(contenido)) as entrada:
        imagen = entrada.convert("RGB")
    if imagen.size != (ancho, alto):
        raise ValueError("La capa visible no coincide con la rejilla declarada.")

    if "estimated-surface" in capas and nombre_vista in ("true-color", "swir", "candidates"):
        # La pestaña Clases usa True Color como base del mismo visor compuesto.
        if nombre_vista == "candidates":
            with Image.open(BytesIO(capas["true-color"])) as entrada:
                imagen = entrada.convert("RGB")
        pixeles = np.asarray(imagen).copy()
        forma = (alto, ancho)
        union = _cargar_mascara(capas, "estimated-surface", forma)
        humo = _cargar_mascara(capas, "smoke", forma)
        if vista.get("show_visible_surface", True) and union is not None:
            _mezclar(pixeles, union, (230, 38, 30), .50)
        if vista.get("show_smoke", True) and humo is not None:
            _mezclar(pixeles, humo, (35, 145, 235), .27)
        if vista.get("show_segmentation", True) and vista.get("show_visible_surface", True) and union is not None:
            _mezclar(pixeles, _borde(union), (255, 230, 30), 1.0)
        imagen = Image.fromarray(pixeles)
    elif nombre_vista in ("true-color", "swir"):
        pixeles = np.asarray(imagen).copy()
        forma = (alto, ancho)
        humo = _cargar_mascara(capas, "smoke", forma)
        visible = _cargar_mascara(capas, "visible-surface", forma)
        bajo_humo = _cargar_mascara(capas, "smoke-candidates", forma)
        if vista.get("show_smoke", True) and humo is not None:
            _mezclar(pixeles, humo, (35, 145, 235), 0.27)
        if vista.get("show_visible_surface", True) and visible is not None:
            _mezclar(pixeles, visible, (230, 38, 30), 0.50)
        if vista.get("show_under_smoke", True) and bajo_humo is not None:
            yy = np.arange(alto, dtype=np.uint8)[:, None] % 40
            xx = np.arange(ancho, dtype=np.uint8)[None, :] % 40
            alpha = np.where((xx + yy) % 10 < 2, 0.62, 0.34)
            pixeles[bajo_humo] = np.clip(
                pixeles[bajo_humo].astype(np.float32) * (1 - alpha[bajo_humo, None])
                + np.asarray((220, 30, 195), dtype=np.float32) * alpha[bajo_humo, None],
                0,
                255,
            ).astype(np.uint8)
        if vista.get("show_segmentation", True):
            borde_visible = (
                _borde(visible)
                if vista.get("show_visible_surface", True) and visible is not None
                else np.zeros(forma, dtype=bool)
            )
            if np.any(borde_visible):
                _mezclar(pixeles, borde_visible, (255, 230, 30), 1.0)
            if vista.get("show_under_smoke", True) and bajo_humo is not None:
                yy = np.arange(alto, dtype=np.uint8)[:, None] % 40
                xx = np.arange(ancho, dtype=np.uint8)[None, :] % 40
                borde_oculto = _borde(bajo_humo) & ~borde_visible & ((xx + yy) % 8 < 4)
                _mezclar(pixeles, borde_oculto, (255, 45, 220), 1.0)
        imagen = Image.fromarray(pixeles)

    _dibujar_anotaciones(imagen, anotaciones)
    salida = BytesIO()
    imagen.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


def _anotaciones_svg(anotaciones: list[dict[str, Any]], ancho: int, alto: int) -> bytes:
    elementos = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}">',
        '<g fill="none" stroke-linecap="round" stroke-linejoin="round">',
    ]
    for anotacion in anotaciones:
        puntos = anotacion["points"]
        color = anotacion["color"]
        grosor = anotacion["width"]
        coords = [(punto["x"], punto["y"]) for punto in puntos]
        if anotacion["kind"] == "freehand":
            path = " ".join(("M" if i == 0 else "L") + f"{x:.3f},{y:.3f}" for i, (x, y) in enumerate(coords))
            if len(coords) == 1:
                x, y = coords[0]
                elementos.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{grosor / 2:g}" fill="{color}"/>')
            else:
                elementos.append(f'<path d="{path}" stroke="{color}" stroke-width="{grosor:g}"/>')
        elif anotacion["kind"] in {"line", "arrow"}:
            (x1, y1), (x2, y2) = coords
            elementos.append(f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" stroke="{color}" stroke-width="{grosor:g}"/>')
            if anotacion["kind"] == "arrow":
                angulo = math.atan2(y2 - y1, x2 - x1)
                largo = max(12, grosor * 4)
                lateral = math.pi / 7
                ala1 = (x2 - largo * math.cos(angulo - lateral), y2 - largo * math.sin(angulo - lateral))
                ala2 = (x2 - largo * math.cos(angulo + lateral), y2 - largo * math.sin(angulo + lateral))
                elementos.append(f'<path d="M{x2:.3f},{y2:.3f} L{ala1[0]:.3f},{ala1[1]:.3f} L{ala2[0]:.3f},{ala2[1]:.3f} Z" fill="{color}" stroke="{color}"/>')
        elif anotacion["kind"] in {"rectangle", "ellipse"}:
            (x1, y1), (x2, y2) = coords
            left, top = min(x1, x2), min(y1, y2)
            width, height = abs(x2 - x1), abs(y2 - y1)
            if anotacion["kind"] == "rectangle":
                elementos.append(f'<rect x="{left:.3f}" y="{top:.3f}" width="{width:.3f}" height="{height:.3f}" stroke="{color}" stroke-width="{grosor:g}"/>')
            else:
                elementos.append(f'<ellipse cx="{(left + width / 2):.3f}" cy="{(top + height / 2):.3f}" rx="{width / 2:.3f}" ry="{height / 2:.3f}" stroke="{color}" stroke-width="{grosor:g}"/>')
        elif anotacion["kind"] == "text":
            x, y = coords[0]
            texto = escape(anotacion["text"])
            elementos.append(
                f'<text x="{x:.3f}" y="{y:.3f}" dominant-baseline="hanging" fill="{color}" font-family="sans-serif" '
                f'font-size="24" stroke="#08111b" stroke-width="{max(2, grosor):g}" paint-order="stroke">{texto}</text>'
            )
    elementos.append("</g></svg>")
    return "\n".join(elementos).encode("utf-8")


def crear_paquete_resultado(
    trabajo: dict[str, Any], anotaciones_entrada: Any, vista_entrada: Any = None
) -> bytes:
    """Devuelve un ZIP con entradas alineadas, todas las capas y revisión humana."""
    grid = trabajo.get("grid")
    outputs = trabajo.get("outputs")
    if not isinstance(grid, dict) or not isinstance(outputs, dict):
        raise ValueError("El análisis todavía no tiene rejilla o capas exportables.")
    ancho, alto = int(grid.get("ancho_px", 0)), int(grid.get("alto_px", 0))
    if ancho < 1 or alto < 1:
        raise ValueError("La rejilla del análisis no es válida.")
    anotaciones = validar_anotaciones(anotaciones_entrada, ancho, alto)
    if vista_entrada is None:
        vista_entrada = {}
    elif isinstance(vista_entrada, dict):
        pass
    else:
        raise ValueError("La configuración de la vista no es válida.")
    vista = {"layer": vista_entrada.get("layer", "true-color")}
    if not isinstance(vista["layer"], str):
        raise ValueError("La capa visible indicada no es válida.")
    for clave in ("show_segmentation", "show_smoke", "show_visible_surface", "show_under_smoke"):
        valor = vista_entrada.get(clave, True)
        if not isinstance(valor, bool):
            raise ValueError(f"La opción de vista {clave!r} debe ser booleana.")
        vista[clave] = valor

    requeridas = ("true-color", "swir")
    if any(nombre not in outputs for nombre in requeridas):
        raise ValueError("El análisis no conserva la pareja de imágenes preparada.")
    for nombre in requeridas:
        with Image.open(BytesIO(outputs[nombre])) as imagen:
            if imagen.size != (ancho, alto):
                raise ValueError(f"La entrada {nombre!r} no coincide con la rejilla del análisis.")

    capas_manifest = []
    capas_zip = []
    for nombre, contenido in sorted(outputs.items()):
        if not isinstance(nombre, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", nombre):
            raise ValueError("El análisis contiene un nombre de capa no válido.")
        if not isinstance(contenido, bytes):
            raise ValueError(f"La capa {nombre!r} no está codificada como archivo.")
        archivo = f"capas/{nombre}.png"
        capas_zip.append((archivo, contenido))
        capas_manifest.append({
            "name": nombre,
            "file": archivo,
            "description": _DESCRIPCIONES_CAPA.get(nombre, "Diagnóstico visual adicional del análisis."),
            "format": "PNG",
            "width": ancho,
            "height": alto,
        })

    vista_nombre = vista.get("layer", "true-color")
    if vista_nombre not in _CAPAS_VISTA:
        raise ValueError("La capa visible indicada no es válida.")
    mapa = _mapa_anotado(trabajo, anotaciones, vista)
    anotaciones_json = {
        "coordinate_system": {
            "units": "pixel",
            "origin": "top_left",
            "x_axis": "column_to_right",
            "y_axis": "row_down",
            "width": ancho,
            "height": alto,
            "grid": grid,
        },
        "features": anotaciones,
        "note": "Human review marks; they are not model output or ground truth.",
    }
    manifiesto = {
        "schema_version": "lumbre-ai-review-package/1.0",
        "application": "Lumbre",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "job_id": trabajo.get("id"),
        "input": {
            "source": trabajo.get("input_source", "unknown"),
            "scene_id": trabajo.get("scene_id"),
            "filenames": trabajo.get("input_filenames", {}),
            "analysis_grid_pair": ["entradas/true_color_rejilla_analisis.png", "entradas/swir_rejilla_analisis.png"],
            "pixel_grid_note": "Estas matrices exactas usadas por el análisis comparten dimensiones e índices de píxel.",
            "geospatial_alignment": "not_verified_by_lumbre; no reprojection is performed",
        },
        "grid": grid,
        "processing": trabajo.get("settings", {}),
        "metrics": trabajo.get("metrics", {}),
        "layers": capas_manifest,
        "semantic_class_values": {
            "0": "indeterminado",
            "1": "vegetacion",
            "2": "agua_posible",
            "3": "humo_probable",
            "4": "superficie_afectada_candidata",
            "5": "fuego_activo_posible",
            "6": "nube_bruma",
            "7": "suelo_desnudo_urbano",
        },
        "annotated_view": {
            "file": "revision/mapa_anotado.png",
            "base_layer": vista_nombre,
            "base_layer_label": _CAPAS_VISTA[vista_nombre],
            "display_options": {
                "show_segmentation": vista["show_segmentation"],
                "show_smoke": vista["show_smoke"],
                "show_visible_surface": vista["show_visible_surface"],
                "show_under_smoke": vista["show_under_smoke"],
            },
            "annotation_file": "anotaciones/anotaciones.svg",
        },
        "annotations": {
            "file": "anotaciones/anotaciones.json",
            "count": len(anotaciones),
            "human_review_only": True,
        },
        "limitations": [
            "Las capas representan observaciones, clases estimadas e hipótesis según su nombre; no son verdad terreno.",
            "El GSD aporta escala local cuando está disponible, pero no sustituye CRS ni georreferenciación.",
            "La pareja de entrada no se ha reproyectado. Si sus fuentes no estaban alineadas, este paquete no corrige esa georreferencia.",
        ],
    }
    instrucciones = """# Paquete de revisión de Lumbre

Este paquete reúne las dos entradas preparadas para el análisis, todas las capas PNG disponibles, los parámetros y métricas, y las anotaciones añadidas por una persona.

## Alineación y coordenadas

`entradas/true_color_rejilla_analisis.png` y `entradas/swir_rejilla_analisis.png` son las matrices exactas que recibió el motor. Tienen la misma anchura, altura e índices de píxel que las capas. Las anotaciones usan esa rejilla: x es columna hacia la derecha, y es fila hacia abajo y el origen está en la esquina superior izquierda. La rejilla y el GSD, cuando se conoce, están en `manifest.json`.

El programa requiere imágenes de entrada con dimensiones coincidentes y no reproyecta imágenes. Un tamaño igual no demuestra por sí solo que las fuentes originales tengan la misma georreferenciación; no se declara CRS salvo que exista realmente.

## Contenido

- `capas/`: todas las capas PNG generadas por esta ejecución. Los nombres conservan el identificador de capa; `manifest.json` describe su contenido.
- `capas/semantic-classes.png`: identificador semántico por píxel; los valores y nombres están en `semantic_class_values` del manifiesto. `capas/class-*.png` contiene la máscara binaria independiente de cada clase.
- Las máscaras binarias usan 0 para fondo y 255 para la clase marcada. Las capas `*-border.png` son contornos interiores en píxeles, no perímetros geográficos.
- `revision/mapa_anotado.png`: vista seleccionada con las anotaciones renderizadas.
- `anotaciones/anotaciones.json`: anotaciones editables con coordenadas de píxel.
- `anotaciones/anotaciones.svg`: capa vectorial transparente en la misma rejilla.
- `manifest.json`: procedencia, rejilla, parámetros, métricas y limitaciones.

Las anotaciones son observaciones humanas para revisar errores; no son etiquetas validadas ni verdad terreno.
"""

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED, compresslevel=1) as paquete:
        paquete.writestr("README.md", instrucciones)
        paquete.writestr("manifest.json", json.dumps(manifiesto, ensure_ascii=False, indent=2, allow_nan=False))
        paquete.writestr("entradas/true_color_rejilla_analisis.png", outputs["true-color"])
        paquete.writestr("entradas/swir_rejilla_analisis.png", outputs["swir"])
        if "reference-wildfires" in outputs:
            paquete.writestr("entradas/wildfires_referencia.png", outputs["reference-wildfires"])
        for ruta, contenido in capas_zip:
            paquete.writestr(ruta, contenido)
        paquete.writestr("revision/mapa_anotado.png", mapa)
        paquete.writestr("anotaciones/anotaciones.json", json.dumps(anotaciones_json, ensure_ascii=False, indent=2))
        paquete.writestr("anotaciones/anotaciones.svg", _anotaciones_svg(anotaciones, ancho, alto))
    return buffer.getvalue()
