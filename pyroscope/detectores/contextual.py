"""Adaptador experimental: V2 aporta semántica, el motor regional la organiza."""
from .swir_histeresis import clasificar_pixeles_area_afectada_swir
from dataclasses import replace
import numpy as np
from ..ontologia import ClaseSemantica


def clasificar_base_contextual(true_color, swir, **opciones):
    resultado = clasificar_pixeles_area_afectada_swir(true_color, swir, **opciones)
    f = resultado.caracteristicas_comunes
    # Percentiles iguales en una escena plana no constituyen semillas de fuego.
    # Corrección exclusiva del adaptador; los detectores anteriores se conservan.
    if f is not None and np.ptp(f[..., 0]) < 1e-5 and np.max(f[..., 0]) <= .05:
        vacia = np.zeros(true_color.shape[:2], bool)
        clases = resultado.clase_por_pixel.copy()
        clases[resultado.mascara_candidata] = ClaseSemantica.INDETERMINADO
        resultado = replace(resultado, mascara_candidata=vacia,
                            mascara_candidata_bajo_humo=vacia.copy(), clase_por_pixel=clases)
    return resultado
