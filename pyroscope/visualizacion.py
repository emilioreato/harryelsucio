"""Representación visual de la máscara y el perímetro de área afectada."""

import cv2
import numpy as np

from .segmentacion import ResultadoAreaAfectada
from .ontologia import ClaseSemantica


def crear_superposicion(
    imagen_base: np.ndarray,
    resultado: ResultadoAreaAfectada,
) -> np.ndarray:
    """Dibuja relleno translúcido y perímetro sobre una composición RGB."""
    if imagen_base.shape[:2] != resultado.mascara.shape:
        raise ValueError("La imagen y la máscara deben tener las mismas dimensiones.")

    salida = superponer_mascara(imagen_base, resultado.mascara)
    salida = superponer_mascara(
        salida,
        resultado.mascara_candidata_bajo_humo,
        color=(220, 55, 175),
        opacidad=0.62,
    )
    salida = superponer_mascara(
        salida,
        resultado.mascara_humo,
        color=(0, 165, 255),
        opacidad=0.42,
    )
    salida = superponer_mascara(
        salida,
        resultado.clase_por_pixel == ClaseSemantica.AGUA_POSIBLE,
        color=(25, 105, 255),
        opacidad=0.5,
    )
    salida = superponer_mascara(
        salida,
        resultado.clase_por_pixel == ClaseSemantica.FUEGO_ACTIVO_POSIBLE,
        color=(255, 245, 0),
        opacidad=0.78,
    )
    salida = superponer_mascara(
        salida,
        resultado.clase_por_pixel == ClaseSemantica.NUBE_BRUMA,
        color=(170, 175, 185),
        opacidad=0.28,
    )

    if resultado.contornos:
        grosor = max(2, round(max(salida.shape[:2]) / 900))
        cv2.drawContours(salida, list(resultado.contornos), -1, (255, 238, 60), grosor)
    return salida


def crear_vista_clasificacion(
    true_color: np.ndarray,
    resultado: ResultadoAreaAfectada,
) -> np.ndarray:
    """Muestra por separado candidatos de superficie y humo probable."""
    if true_color.shape[:2] != resultado.mascara_clasificada.shape:
        raise ValueError("La imagen y las máscaras deben tener las mismas dimensiones.")

    salida = superponer_mascara(
        true_color,
        resultado.mascara_clasificada,
        color=(255, 115, 25),
        opacidad=0.36,
    )
    salida = superponer_mascara(
        salida,
        resultado.mascara_candidata_bajo_humo,
        color=(220, 55, 175),
        opacidad=0.62,
    )
    salida = superponer_mascara(
        salida,
        resultado.mascara_humo,
        color=(0, 165, 255),
        opacidad=0.48,
    )
    salida = superponer_mascara(
        salida,
        resultado.clase_por_pixel == ClaseSemantica.AGUA_POSIBLE,
        color=(25, 105, 255),
        opacidad=0.58,
    )
    salida = superponer_mascara(
        salida,
        resultado.clase_por_pixel == ClaseSemantica.FUEGO_ACTIVO_POSIBLE,
        color=(255, 245, 0),
        opacidad=0.82,
    )
    return superponer_mascara(
        salida,
        resultado.clase_por_pixel == ClaseSemantica.NUBE_BRUMA,
        color=(170, 175, 185),
        opacidad=0.3,
    )


def superponer_mascara(
    imagen_rgb: np.ndarray,
    mascara: np.ndarray,
    *,
    color: tuple[int, int, int] = (245, 65, 35),
    opacidad: float = 0.32,
) -> np.ndarray:
    """Pinta una máscara binaria en la rejilla de una composición RGB."""
    if imagen_rgb.ndim != 3 or imagen_rgb.shape[2] != 3:
        raise ValueError("La imagen debe tener tres canales RGB.")
    if mascara.shape != imagen_rgb.shape[:2]:
        raise ValueError("La imagen y la máscara deben tener las mismas dimensiones.")
    if not 0.0 <= opacidad <= 1.0:
        raise ValueError("La opacidad debe estar entre cero y uno.")
    salida = imagen_rgb.copy()
    dentro = mascara.astype(bool)
    salida[dentro] = (
        (1.0 - opacidad) * salida[dentro]
        + opacidad * np.asarray(color, dtype=np.float32)
    ).astype(np.uint8)
    return salida
