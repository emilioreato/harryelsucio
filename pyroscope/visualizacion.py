"""Representación visual de la máscara y el perímetro de área afectada."""

import cv2
import numpy as np

from .segmentacion import ResultadoAreaAfectada


def crear_superposicion(
    true_color: np.ndarray,
    resultado: ResultadoAreaAfectada,
) -> np.ndarray:
    """Dibuja relleno translúcido y perímetro sobre True Color."""
    if true_color.shape[:2] != resultado.mascara.shape:
        raise ValueError("La imagen y la máscara deben tener las mismas dimensiones.")

    salida = true_color.copy()
    relleno = np.zeros_like(salida)
    relleno[:] = (245, 65, 35)
    dentro = resultado.mascara
    salida[dentro] = (
        0.68 * salida[dentro] + 0.32 * relleno[dentro]
    ).astype(np.uint8)

    if resultado.contornos:
        grosor = max(2, round(max(salida.shape[:2]) / 900))
        cv2.drawContours(salida, list(resultado.contornos), -1, (255, 238, 60), grosor)
    return salida
