"""Filtrado morfológico y agrupación espacial de candidatos semánticos."""

from __future__ import annotations

import cv2
import numpy as np

from .modelos_segmentacion import ResultadoClasificacionSemantica, ResultadoRegionesEspaciales
from .progreso import ProgresoSegmentacion, informar_progreso as _informar_progreso


def segmentar_regiones_espaciales(
    clasificacion: ResultadoClasificacionSemantica,
    *,
    area_minima_pct: float = 0.04,
    distancia_maxima_pct: float = 10.0,
    on_progress: ProgresoSegmentacion | None = None,
    conservar_regiones_separadas: bool = False,
    preservar_geometria: bool = False,
) -> ResultadoRegionesEspaciales:
    """Convierte candidatos semánticos en regiones espaciales depuradas.

    Esta etapa aplica morfología, tamaño mínimo y proximidad al componente
    principal. El veto de agua se repone después de la clausura para impedir que
    esta conecte regiones a través de lagos o píxeles protegidos.
    """
    mascara = clasificacion.mascara_candidata
    mascara_agua = clasificacion.mascara_agua
    mascara_humo = clasificacion.mascara_humo
    if (
        mascara.ndim != 2
        or mascara_agua.shape != mascara.shape
        or mascara_humo.shape != mascara.shape
    ):
        raise ValueError("Las máscaras semánticas deben ser rejillas 2D del mismo tamaño.")
    if not 0 <= area_minima_pct <= 10:
        raise ValueError("El área mínima debe estar entre 0 y 10 por ciento.")
    if not 0 <= distancia_maxima_pct <= 50:
        raise ValueError("La distancia máxima debe estar entre 0 y 50 por ciento.")

    alto, ancho = mascara.shape
    _informar_progreso(on_progress, "Limpiando ruido y agrupando regiones", 82)
    mascara_u8 = mascara.astype(np.uint8) * 255
    if not preservar_geometria:
        mascara_u8 = cv2.morphologyEx(
            mascara_u8, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8)
        )
        mascara_u8 = cv2.morphologyEx(
            mascara_u8, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8)
        )
    pixeles_agua_excluidos = int(np.count_nonzero(mascara_u8[mascara_agua]))
    pixeles_humo_excluidos = int(np.count_nonzero(mascara_u8[mascara_humo]))
    mascara_u8[mascara_agua] = 0
    mascara_u8[mascara_humo] = 0

    cantidad, etiquetas_cc, stats, _ = cv2.connectedComponentsWithStats(
        mascara_u8, connectivity=8
    )
    _informar_progreso(on_progress, "Filtrando componentes alejados", 92)
    minimo_pixeles = max(16, round(alto * ancho * area_minima_pct / 100.0))
    distancia_maxima_px = round(max(alto, ancho) * distancia_maxima_pct / 100.0)
    componentes_remotos_descartados = 0

    if conservar_regiones_separadas and cantidad > 1:
        limpia = np.zeros((alto, ancho), dtype=np.uint8)
        for etiqueta in range(1, cantidad):
            if stats[etiqueta, cv2.CC_STAT_AREA] >= minimo_pixeles:
                limpia[etiquetas_cc == etiqueta] = 255
    elif cantidad > 1:
        ancla = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mascara_ancla = etiquetas_cc == ancla
        distancia_al_ancla = cv2.distanceTransform(
            (~mascara_ancla).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_5
        )
        limpia = np.zeros((alto, ancho), dtype=np.uint8)
        for etiqueta in range(1, cantidad):
            if stats[etiqueta, cv2.CC_STAT_AREA] < minimo_pixeles:
                continue
            componente = etiquetas_cc == etiqueta
            separacion = float(distancia_al_ancla[componente].min())
            if separacion > distancia_maxima_px:
                componentes_remotos_descartados += 1
                continue
            # La proximidad decide sobre el componente entero; no es un recorte.
            limpia[componente] = 255
    else:
        limpia = np.zeros((alto, ancho), dtype=np.uint8)

    contornos, _ = cv2.findContours(
        limpia, cv2.RETR_LIST if preservar_geometria else cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )
    contornos_ordenados = tuple(sorted(contornos, key=cv2.contourArea, reverse=True))
    _informar_progreso(on_progress, "Preparando el resultado visual", 98)
    resultado = limpia > 0
    return ResultadoRegionesEspaciales(
        mascara=resultado,
        contornos=contornos_ordenados,
        proporcion=float(resultado.mean()),
        pixeles_agua_excluidos=pixeles_agua_excluidos,
        pixeles_humo_excluidos=pixeles_humo_excluidos,
        distancia_maxima_px=distancia_maxima_px,
        componentes_remotos_descartados=componentes_remotos_descartados,
    )
