"""Características conjuntas para combinar True Color y SWIR por píxel."""

from __future__ import annotations

import numpy as np

from .imagenes import validar_par_alineado


NOMBRES_CARACTERISTICAS = (
    "predominio_rojo_swir",
    "cromaticidad_swir",
    "predominio_verde_true_color",
    "luminancia_true_color",
    "luminancia_swir",
    "cromaticidad_true_color",
    "predominio_rojo_sobre_verde_swir",
    "predominio_azul_true_color",
)


def extraer_caracteristicas_pareja(
    true_color: np.ndarray,
    swir: np.ndarray,
) -> np.ndarray:
    """Devuelve un vector de evidencias de las dos imágenes para cada píxel.

    Las medidas se calculan sobre los canales RGB renderizados disponibles; no
    representan reflectancias físicas ni bandas Sentinel-2 recuperadas.
    """
    validar_par_alineado(true_color, swir)
    tc = true_color.astype(np.float32) / 255.0
    sw = swir.astype(np.float32) / 255.0
    epsilon = 1e-3

    r, g, b = np.moveaxis(sw, -1, 0)
    suma_swir = r + g + b + epsilon
    swir_rojo = (2.0 * r - g - b) / suma_swir
    swir_rojo_verde = (r - g) / (r + g + epsilon)
    max_swir = np.maximum.reduce((r, g, b))
    min_swir = np.minimum.reduce((r, g, b))
    swir_croma = (max_swir - min_swir) / (max_swir + 0.025)
    swir_luma = 0.2126 * r + 0.7152 * g + 0.0722 * b

    tr, tg, tb = np.moveaxis(tc, -1, 0)
    suma_tc = tr + tg + tb + epsilon
    verde_visible = (2.0 * tg - tr - tb) / suma_tc
    luma_visible = 0.2126 * tr + 0.7152 * tg + 0.0722 * tb
    azul_visible = (2.0 * tb - tr - tg) / suma_tc
    max_tc = np.maximum.reduce((tr, tg, tb))
    min_tc = np.minimum.reduce((tr, tg, tb))
    croma_visible = (max_tc - min_tc) / (max_tc + 0.025)

    return np.stack(
        (
            swir_rojo,
            swir_croma,
            verde_visible,
            luma_visible,
            swir_luma,
            croma_visible,
            swir_rojo_verde,
            azul_visible,
        ),
        axis=-1,
    ).astype(np.float32)
