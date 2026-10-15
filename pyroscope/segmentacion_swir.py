"""Detector alternativo por contraste SWIR, umbral doble e histéresis."""

from __future__ import annotations

import cv2
import numpy as np

from .caracteristicas import extraer_caracteristicas_pareja
from .humo import detectar_humo_probable
from .imagenes import validar_par_alineado
from .ontologia import ClaseSemantica
from .segmentacion import ResultadoClasificacionSemantica


def clasificar_pixeles_area_afectada_swir(
    true_color: np.ndarray,
    swir: np.ndarray,
    *,
    sensibilidad: int = 5,
) -> ResultadoClasificacionSemantica:
    """Propone superficie afectada con contraste cromático SWIR e histéresis.

    El umbral alto localiza semillas con una señal rojiza SWIR marcada; el
    umbral bajo permite crecer desde esas semillas por píxeles contiguos que
    conservan evidencia cromática moderada. True Color veta posible agua y
    vegetación muy verde, y la máscara de humo se aplica antes del crecimiento.
    """
    validar_par_alineado(true_color, swir)
    if not 1 <= sensibilidad <= 10:
        raise ValueError("La sensibilidad debe estar entre 1 y 10.")

    humo = detectar_humo_probable(true_color, swir)
    mascara_humo = humo.mascara_probable
    alto, ancho = true_color.shape[:2]
    caracteristicas = extraer_caracteristicas_pareja(true_color, swir)
    rojo_swir = caracteristicas[:, :, 0]
    rojo_verde_swir = caracteristicas[:, :, 6]
    verde_visible = caracteristicas[:, :, 2]
    luma_visible = caracteristicas[:, :, 3]
    despejado = ~mascara_humo

    if not np.any(despejado):
        clases = np.zeros((alto, ancho), dtype=np.uint8)
        clases[mascara_humo] = ClaseSemantica.HUMO_PROBABLE
        return ResultadoClasificacionSemantica(
            mascara_candidata=np.zeros((alto, ancho), dtype=bool),
            mascara_agua=np.zeros((alto, ancho), dtype=bool),
            mascara_humo=mascara_humo,
            confianza_humo=humo.confianza,
            clase_por_pixel=clases,
            centros=np.empty((0, caracteristicas.shape[2]), dtype=np.float32),
            clases_seleccionadas=(),
            puntuaciones_clase=np.empty((0,), dtype=np.float32),
        )

    # Los percentiles por escena toleran estiramientos distintos de la
    # composición. La sensibilidad baja los dos umbrales sin alterar la firma.
    cuantiles = rojo_swir[despejado]
    fraccion_semilla = 0.994 - (sensibilidad - 1) * 0.006
    fraccion_crecimiento = 0.94 - (sensibilidad - 1) * 0.010
    umbral_semilla = float(np.quantile(cuantiles, fraccion_semilla))
    umbral_crecimiento = float(np.quantile(cuantiles, fraccion_crecimiento))
    umbral_rg_semilla = float(
        np.quantile(rojo_verde_swir[despejado], 0.82 - (sensibilidad - 1) * 0.005)
    )
    umbral_rg_crecimiento = float(
        np.quantile(rojo_verde_swir[despejado], 0.68 - (sensibilidad - 1) * 0.012)
    )
    limite_vegetacion = float(np.quantile(verde_visible[despejado], 0.90))

    # Evita que los umbrales degeneren si la escena tiene un histograma plano.
    umbral_crecimiento = min(umbral_crecimiento, umbral_semilla)
    mascara_semillas = (
        (rojo_swir >= umbral_semilla)
        & (rojo_verde_swir >= umbral_rg_semilla)
        & (verde_visible <= limite_vegetacion)
        & despejado
    )
    mascara_crecimiento = (
        (rojo_swir >= umbral_crecimiento)
        & (rojo_verde_swir >= umbral_rg_crecimiento)
        & (verde_visible <= limite_vegetacion)
        & despejado
    )

    # Agua probable: True Color oscuro/azulado más baja separación SWIR rojo-verde.
    luma_tc_oscura = float(np.quantile(luma_visible[despejado], 0.18))
    tc_azul_umbral = max(0.04, float(np.quantile(caracteristicas[:, :, 7][despejado], 0.85)))
    tc_croma_baja = float(np.quantile(caracteristicas[:, :, 5][despejado], 0.20))
    swir_rg_no_rojo = float(np.quantile(rojo_verde_swir[despejado], 0.70))
    visible_oscura = luma_visible <= luma_tc_oscura
    agua = (
        visible_oscura
        & (
            (caracteristicas[:, :, 7] >= tc_azul_umbral)
            | (caracteristicas[:, :, 5] <= tc_croma_baja)
            | (rojo_verde_swir <= swir_rg_no_rojo)
        )
        & ~mascara_humo
    )
    mascara_semillas &= ~agua
    mascara_crecimiento &= ~agua

    cantidad, etiquetas = cv2.connectedComponents(
        mascara_crecimiento.astype(np.uint8), connectivity=8
    )
    clases_con_semilla = np.unique(etiquetas[mascara_semillas])
    clases_con_semilla = clases_con_semilla[clases_con_semilla != 0]
    candidata = np.isin(etiquetas, clases_con_semilla) if cantidad > 1 else np.zeros_like(despejado)
    candidata &= ~mascara_humo & ~agua
    candidata_u8 = cv2.morphologyEx(
        candidata.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8)
    )
    candidata_u8[mascara_humo | agua] = 0
    candidata = candidata_u8 > 0

    clases = np.full((alto, ancho), ClaseSemantica.INDETERMINADO, dtype=np.uint8)
    clases[agua] = ClaseSemantica.AGUA_POSIBLE
    clases[candidata] = ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
    clases[mascara_humo] = ClaseSemantica.HUMO_PROBABLE

    return ResultadoClasificacionSemantica(
        mascara_candidata=candidata,
        mascara_agua=agua,
        mascara_humo=mascara_humo,
        confianza_humo=humo.confianza,
        clase_por_pixel=clases,
        centros=np.empty((0, caracteristicas.shape[2]), dtype=np.float32),
        # V2 no usa IDs de clúster; los umbrales se guardan en puntuaciones.
        clases_seleccionadas=(),
        puntuaciones_clase=np.asarray(
            [umbral_semilla, umbral_crecimiento], dtype=np.float32
        ),
    )
