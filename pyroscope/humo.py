"""Detección conservadora de humo y zonas con visibilidad degradada.

Opera sobre los JPEG RGB renderizados del reto. Su salida es una probabilidad
visual, no una máscara atmosférica calibrada ni una recuperación del terreno.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .imagenes import validar_par_alineado


@dataclass(frozen=True)
class ResultadoHumo:
    """Capa de humo probable y su confianza por píxel."""

    mascara_probable: np.ndarray
    confianza: np.ndarray
    firma_cian_swir: np.ndarray


def detectar_humo_probable(
    true_color: np.ndarray,
    swir: np.ndarray,
    *,
    area_minima_componente_pct: float = 0.035,
) -> ResultadoHumo:
    """Estima humo usando la firma cian SWIR y el velo claro de True Color.

    La detección combina las dos composiciones alineadas. La señal cian se
    calcula como combinación de los canales G/B por encima de R, penalizada
    cuando G y B difieren mucho; True Color aporta luminosidad y baja
    cromaticidad. Los umbrales se adaptan a la escena para tolerar cambios de
    estiramiento entre JPEG.

    La máscara es deliberadamente conservadora: sirve para apartar píxeles de
    visibilidad dudosa del clasificador de superficie. No afirma qué cobertura
    hay debajo del humo y no distingue humo fino de otras veladuras con certeza.
    """
    validar_par_alineado(true_color, swir)
    if not 0 <= area_minima_componente_pct <= 5:
        raise ValueError("El área mínima de componente debe estar entre 0 y 5 por ciento.")

    tc = true_color.astype(np.float32) / 255.0
    sw = swir.astype(np.float32) / 255.0
    r, g, b = np.moveaxis(sw, -1, 0)

    # En estas composiciones, el humo visible se representa a menudo cian.
    # Se usa el patrón relativo del JPEG, no se le asigna una banda física.
    epsilon = 1e-3
    contraste_cian = np.maximum(0.0, np.minimum(g, b) - r) / (
        np.maximum(g, b) + epsilon
    )
    balance_cian = 1.0 - np.abs(g - b) / (g + b + epsilon)
    firma_cian = np.clip(contraste_cian * balance_cian, 0.0, 1.0)

    max_tc = np.max(tc, axis=2)
    min_tc = np.min(tc, axis=2)
    cromaticidad_tc = (max_tc - min_tc) / (max_tc + 0.025)
    neutralidad_tc = 1.0 - cromaticidad_tc
    luminosidad_tc = (
        0.2126 * tc[:, :, 0] + 0.7152 * tc[:, :, 1] + 0.0722 * tc[:, :, 2]
    )

    # Los cuantiles de escena compensan diferencias de exposición/estiramiento.
    umbral_cian = max(0.04, float(np.quantile(firma_cian, 0.95)))
    umbral_luminosidad = float(np.quantile(luminosidad_tc, 0.45))
    umbral_neutralidad = float(np.quantile(neutralidad_tc, 0.40))

    evidencia_cian = np.clip(firma_cian / max(umbral_cian * 2.2, 0.16), 0, 1)
    q_lum_baja, q_lum_alta = np.quantile(luminosidad_tc, [0.35, 0.90])
    evidencia_luminosidad = np.clip(
        (luminosidad_tc - q_lum_baja) / max(float(q_lum_alta - q_lum_baja), 0.08),
        0,
        1,
    )
    q_neutral_baja, q_neutral_alta = np.quantile(neutralidad_tc, [0.30, 0.90])
    evidencia_neutralidad = np.clip(
        (neutralidad_tc - q_neutral_baja)
        / max(float(q_neutral_alta - q_neutral_baja), 0.08),
        0,
        1,
    )
    confianza = (
        0.65 * evidencia_cian
        + 0.20 * evidencia_luminosidad
        + 0.15 * evidencia_neutralidad
    ).astype(np.float32)

    candidata = (
        (firma_cian >= umbral_cian)
        & (luminosidad_tc >= umbral_luminosidad)
        & (neutralidad_tc >= umbral_neutralidad)
        & (confianza >= 0.55)
    )
    mascara_u8 = candidata.astype(np.uint8)
    mascara_u8 = cv2.morphologyEx(
        mascara_u8, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8)
    )

    alto, ancho = mascara_u8.shape
    minimo_pixeles = max(32, round(alto * ancho * area_minima_componente_pct / 100.0))
    cantidad, etiquetas, stats, _ = cv2.connectedComponentsWithStats(
        mascara_u8, connectivity=8
    )
    mascara = np.zeros((alto, ancho), dtype=bool)
    for etiqueta in range(1, cantidad):
        if stats[etiqueta, cv2.CC_STAT_AREA] >= minimo_pixeles:
            mascara |= etiquetas == etiqueta

    return ResultadoHumo(
        mascara_probable=mascara,
        confianza=confianza,
        firma_cian_swir=firma_cian.astype(np.float32),
    )
