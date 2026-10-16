"""Indicadores visuales de verdor relativo en composiciones RGB renderizadas."""

from __future__ import annotations

import cv2
import numpy as np

from .imagenes import validar_par_alineado
from .ontologia import ClaseSemantica
from .segmentacion import ResultadoAreaAfectada


def detectar_verdor_aparente(
    true_color: np.ndarray,
    swir: np.ndarray,
    resultado: ResultadoAreaAfectada,
    *,
    area_minima_px: int = 6,
) -> np.ndarray:
    """Marca verdor coherente entre vistas tras excluir oclusiones y cicatriz.

    Las entradas son composiciones renderizadas, no bandas originales. La
    salida es un indicador visual para explorar la escena, no una clase de
    cobertura del suelo validada.
    """
    validar_par_alineado(true_color, swir)
    forma = true_color.shape[:2]
    if resultado.mascara.shape != forma:
        raise ValueError("Las imágenes y el resultado deben compartir la misma rejilla.")
    if area_minima_px < 1:
        raise ValueError("El área mínima debe ser positiva.")

    def predomina_verde(imagen: np.ndarray) -> np.ndarray:
        rojo, verde, azul = [imagen[:, :, canal].astype(np.float32) for canal in range(3)]
        return (verde >= rojo * 1.03) & (verde >= azul * 1.03)

    hsv_swir = cv2.cvtColor(swir, cv2.COLOR_RGB2HSV)
    hue, saturacion, valor = cv2.split(hsv_swir)
    verdor_visible = predomina_verde(true_color) & predomina_verde(swir)
    color_swir = (hue >= 35) & (hue <= 100) & (saturacion >= 30) & (valor >= 50)
    mascara = verdor_visible & color_swir

    clases = np.asarray(resultado.clase_por_pixel)
    excluidas = np.isin(
        clases,
        [
            ClaseSemantica.AGUA_POSIBLE,
            ClaseSemantica.HUMO_PROBABLE,
            ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA,
            ClaseSemantica.FUEGO_ACTIVO_POSIBLE,
            ClaseSemantica.NUBE_BRUMA,
        ],
    )
    excluidas |= np.asarray(resultado.mascara_humo, dtype=bool)
    excluidas |= np.asarray(resultado.mascara_clasificada, dtype=bool)
    mascara &= ~excluidas

    binaria = cv2.morphologyEx(
        mascara.astype(np.uint8),
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
    )
    cantidad, etiquetas, estadisticas, _ = cv2.connectedComponentsWithStats(binaria, 8)
    limpia = np.zeros(forma, dtype=bool)
    for etiqueta in range(1, cantidad):
        if estadisticas[etiqueta, cv2.CC_STAT_AREA] >= area_minima_px:
            limpia[etiquetas == etiqueta] = True
    return limpia
