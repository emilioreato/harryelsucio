"""Carga, validación y ejecución del motor de análisis."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..coordenadas import SistemaCoordenadasImagen
from ..imagenes import abrir_rgb, reducir_par_alineado
from ..segmentacion import ResultadoAreaAfectada, segmentar_superficie_afectada
from ..progreso import ProgresoSegmentacion
from .configuracion import MAX_LADO_ANALISIS, MAX_LADO_CONTEXTUAL


@dataclass(frozen=True)
class ParejaPreparada:
    true_color: np.ndarray
    swir: np.ndarray
    gsd_x_m: float | None
    gsd_y_m: float | None


def preparar_pareja(
    true_bytes: bytes,
    swir_bytes: bytes,
    gsd_m_por_px: float | None,
    max_lado: int = MAX_LADO_ANALISIS,
) -> ParejaPreparada:
    """Lee ambas composiciones y exige dimensiones originales coincidentes."""
    true_color, tamano_true = abrir_rgb(true_bytes, max_lado)
    swir, tamano_swir = abrir_rgb(swir_bytes, max_lado)
    if tamano_true != tamano_swir or true_color.shape != swir.shape:
        raise ValueError(
            "Las imágenes no tienen las mismas dimensiones después de leerlas. "
            "Este MVP requiere la pareja ya alineada; no la ajustará con resize."
        )
    gsd_x = (
        gsd_m_por_px * tamano_true[0] / true_color.shape[1]
        if gsd_m_por_px is not None
        else None
    )
    gsd_y = (
        gsd_m_por_px * tamano_true[1] / true_color.shape[0]
        if gsd_m_por_px is not None
        else None
    )
    return ParejaPreparada(true_color, swir, gsd_x, gsd_y)


def procesar_pareja(
    true_color: np.ndarray,
    swir: np.ndarray,
    sensibilidad: int,
    numero_clases: int,
    area_minima_pct: float,
    distancia_maxima_pct: int,
    gsd_x_m: float | None,
    gsd_y_m: float | None,
    metodo: str,
    conservar_regiones_separadas: bool,
    on_progress: ProgresoSegmentacion | None = None,
    ajustes_avanzados: dict[str, object] | None = None,
) -> tuple[np.ndarray, np.ndarray, ResultadoAreaAfectada]:
    """Reduce en pareja y llama al servicio de segmentación compartido."""
    true_reducido, swir_reducida = reducir_par_alineado(
        true_color, swir, MAX_LADO_CONTEXTUAL if metodo == "contextual_hibrida" else MAX_LADO_ANALISIS
    )
    factor_x = true_color.shape[1] / true_reducido.shape[1]
    factor_y = true_color.shape[0] / true_reducido.shape[0]
    sistema = SistemaCoordenadasImagen(
        ancho_px=true_reducido.shape[1],
        alto_px=true_reducido.shape[0],
        gsd_x_m=gsd_x_m * factor_x if gsd_x_m is not None else None,
        gsd_y_m=gsd_y_m * factor_y if gsd_y_m is not None else None,
    )
    resultado = segmentar_superficie_afectada(
        true_reducido,
        swir_reducida,
        numero_clases=numero_clases,
        sensibilidad=sensibilidad,
        area_minima_pct=area_minima_pct,
        distancia_maxima_pct=distancia_maxima_pct,
        sistema_coordenadas=sistema,
        on_progress=on_progress,
        metodo=metodo,
        conservar_regiones_separadas=conservar_regiones_separadas,
        ajustes_avanzados=ajustes_avanzados,
    )
    return true_reducido, swir_reducida, resultado
