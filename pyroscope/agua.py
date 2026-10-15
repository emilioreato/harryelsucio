"""Heurística conjunta para proponer píxeles de agua en las composiciones."""

from __future__ import annotations

import numpy as np


UMBRALES_AGUA_POR_DEFECTO = {
    "true_color_darkness": 0.20,
    "swir_darkness": 0.10,
    "swir_red_max": 0.55,
    "swir_red_green_max": 0.55,
}


def detectar_agua_probable(
    caracteristicas: np.ndarray,
    mascara_humo: np.ndarray,
    *,
    umbrales_percentil: dict[str, float] | None = None,
) -> np.ndarray:
    """Estima agua oscura con evidencia concordante de True Color y SWIR.

    Solo usa señales RGB renderizadas: oscuridad en ambas vistas y ausencia de
    predominio rojo en SWIR. Los cuantiles se calculan sobre píxeles despejados
    de la escena. Es una máscara auxiliar conservadora, no un mapa de agua.
    """
    if caracteristicas.ndim != 3 or caracteristicas.shape[2] < 8:
        raise ValueError("Se requieren al menos ocho características por píxel.")
    if mascara_humo.shape != caracteristicas.shape[:2]:
        raise ValueError("La máscara de humo debe coincidir con la rejilla de características.")
    percentiles = dict(
        UMBRALES_AGUA_POR_DEFECTO
        if umbrales_percentil is None
        else umbrales_percentil
    )
    if set(percentiles) != set(UMBRALES_AGUA_POR_DEFECTO):
        raise ValueError("Los percentiles de agua deben incluir las cuatro señales reconocidas.")
    valores = np.asarray([percentiles[k] for k in UMBRALES_AGUA_POR_DEFECTO], dtype=float)
    if not np.all(np.isfinite(valores)) or np.any(valores < 0.01) or np.any(valores > 0.99):
        raise ValueError("Los percentiles de agua deben estar entre 0,01 y 0,99.")

    despejado = ~mascara_humo
    if not np.any(despejado):
        return np.zeros(mascara_humo.shape, dtype=bool)

    luma_true_color = caracteristicas[:, :, 3]
    luma_swir = caracteristicas[:, :, 4]
    predominio_rojo_swir = caracteristicas[:, :, 0]
    rojo_sobre_verde_swir = caracteristicas[:, :, 6]

    # El antiguo veto usaba una disyunción de pistas débiles y terminaba
    # etiquetando como agua grandes partes oscuras de terreno y cicatriz.
    # Exigimos que ambas composiciones sean oscuras y que SWIR no muestre la
    # señal rojiza que caracteriza a los candidatos actuales.
    limite_luma_tc = float(
        np.quantile(luma_true_color[despejado], percentiles["true_color_darkness"])
    )
    limite_luma_swir = float(
        np.quantile(luma_swir[despejado], percentiles["swir_darkness"])
    )
    limite_predominio_rojo = float(
        np.quantile(predominio_rojo_swir[despejado], percentiles["swir_red_max"])
    )
    limite_rojo_verde = float(
        np.quantile(rojo_sobre_verde_swir[despejado], percentiles["swir_red_green_max"])
    )

    return (
        despejado
        & (luma_true_color <= limite_luma_tc)
        & (luma_swir <= limite_luma_swir)
        & (predominio_rojo_swir <= limite_predominio_rojo)
        & (rojo_sobre_verde_swir <= limite_rojo_verde)
    )
