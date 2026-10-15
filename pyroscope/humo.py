"""Detección conservadora de humo y zonas con visibilidad degradada.

Opera sobre los JPEG RGB renderizados del reto. Su salida es una probabilidad
visual, no una máscara atmosférica calibrada ni una recuperación del terreno.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .imagenes import validar_par_alineado


PESOS_CONFIANZA_HUMO_POR_DEFECTO = {
    "cyan": 0.65,
    "luminance": 0.20,
    "neutrality": 0.15,
}


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
    pesos_confianza: dict[str, float] | None = None,
    umbral_confianza: float = 0.55,
) -> ResultadoHumo:
    """Estima humo con SWIR y amplía la máscara por el velo visible contiguo.

    El núcleo se detecta con la firma cian SWIR y señales de True Color. En
    paralelo, componentes grises/neutros, luminosos y de bajo contraste local
    pueden formar una capa de velo posible aunque no toquen un núcleo SWIR.
    Estas zonas se apartan del clasificador de superficie y se muestran como
    oclusión probable, no como fuego observado.

    La máscara sigue siendo una hipótesis visual sobre JPEG renderizados: no
    afirma qué cobertura hay debajo ni distingue humo de nubes/veladuras con
    certeza.
    """
    validar_par_alineado(true_color, swir)
    if not 0 <= area_minima_componente_pct <= 5:
        raise ValueError("El área mínima de componente debe estar entre 0 y 5 por ciento.")
    pesos = dict(
        PESOS_CONFIANZA_HUMO_POR_DEFECTO if pesos_confianza is None else pesos_confianza
    )
    if set(pesos) != set(PESOS_CONFIANZA_HUMO_POR_DEFECTO):
        raise ValueError("Los pesos de humo deben incluir las tres señales reconocidas.")
    coeficientes = np.asarray(
        [pesos[nombre] for nombre in PESOS_CONFIANZA_HUMO_POR_DEFECTO], dtype=np.float32
    )
    if (
        not np.all(np.isfinite(coeficientes))
        or np.any(coeficientes < 0)
        or np.any(coeficientes > 1)
        or not np.any(coeficientes)
    ):
        raise ValueError("Los pesos de humo deben estar entre 0 y 1 y alguno debe ser positivo.")
    if not np.isfinite(umbral_confianza) or not 0 <= umbral_confianza <= 1:
        raise ValueError("El umbral de confianza del humo debe estar entre 0 y 1.")
    coeficientes /= coeficientes.sum()

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
    confianza_cromatica = (
        coeficientes[0] * evidencia_cian
        + coeficientes[1] * evidencia_luminosidad
        + coeficientes[2] * evidencia_neutralidad
    ).astype(np.float32)

    candidata_cian = (
        (firma_cian >= umbral_cian)
        & (luminosidad_tc >= umbral_luminosidad)
        & (neutralidad_tc >= umbral_neutralidad)
        & (confianza_cromatica >= umbral_confianza)
    )
    alto, ancho = candidata_cian.shape
    minimo_pixeles = max(32, round(alto * ancho * area_minima_componente_pct / 100.0))
    nucleo_u8 = cv2.morphologyEx(
        candidata_cian.astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((5, 5), dtype=np.uint8),
    )
    cantidad_nucleo, etiquetas_nucleo, stats_nucleo, _ = cv2.connectedComponentsWithStats(
        nucleo_u8, connectivity=8
    )
    nucleo = np.zeros((alto, ancho), dtype=bool)
    for etiqueta in range(1, cantidad_nucleo):
        if stats_nucleo[etiqueta, cv2.CC_STAT_AREA] >= minimo_pixeles:
            nucleo |= etiquetas_nucleo == etiqueta

    # Busca velos grises directamente en True Color. Antes esta vía solo se
    # ejecutaba cuando SWIR ya había encontrado un núcleo cian, por lo que un
    # penacho neutro o de baja visibilidad podía pasar al clasificador de suelo.
    gris = cv2.cvtColor(true_color, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    lado_ventana = max(9, round(min(alto, ancho) * 0.0225))
    if lado_ventana % 2 == 0:
        lado_ventana += 1
    media_local = cv2.boxFilter(
        gris, cv2.CV_32F, (lado_ventana, lado_ventana), normalize=True
    )
    media_cuadrado_local = cv2.boxFilter(
        gris * gris, cv2.CV_32F, (lado_ventana, lado_ventana), normalize=True
    )
    contraste_local = np.sqrt(
        np.maximum(0.0, media_cuadrado_local - media_local * media_local)
    )

    umbral_contraste_bajo, umbral_contraste_alto = np.quantile(
        contraste_local, [0.20, 0.70]
    )
    evidencia_suavidad = np.clip(
        (umbral_contraste_alto - contraste_local)
        / max(float(umbral_contraste_alto - umbral_contraste_bajo), 1e-3),
        0,
        1,
    )
    confianza_velo = (
        0.30 * evidencia_luminosidad
        + 0.35 * evidencia_neutralidad
        + 0.35 * evidencia_suavidad
    ).astype(np.float32)
    umbral_textura = float(np.quantile(contraste_local, 0.30))
    umbral_luminosidad_velo = max(0.18, float(np.quantile(luminosidad_tc, 0.35)))
    umbral_neutralidad_velo = max(0.72, float(np.quantile(neutralidad_tc, 0.70)))
    candidata_velo = (
        (luminosidad_tc >= umbral_luminosidad_velo)
        & (neutralidad_tc >= umbral_neutralidad_velo)
        & (contraste_local <= umbral_textura)
        & (confianza_velo >= umbral_confianza)
    )

    # Las zonas grises/suaves suficientemente grandes cuentan como oclusión
    # posible aunque no tengan firma cian SWIR. Conservarlas aparte impide que
    # el clasificador las contabilice como superficie observada.
    candidata_unida = cv2.morphologyEx(
        (nucleo | candidata_velo).astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((5, 5), dtype=np.uint8),
    )
    cantidad, etiquetas, stats, _ = cv2.connectedComponentsWithStats(
        candidata_unida, connectivity=8
    )
    mascara = np.zeros((alto, ancho), dtype=bool)
    for etiqueta in range(1, cantidad):
        if stats[etiqueta, cv2.CC_STAT_AREA] >= minimo_pixeles:
            mascara |= etiquetas == etiqueta

    # Si hay núcleo SWIR, limita su expansión gris para no arrastrar superficies
    # neutras lejanas conectadas por una cadena débil de píxeles.
    if np.any(nucleo):
        distancia_al_nucleo = cv2.distanceTransform(
            (~nucleo).astype(np.uint8), cv2.DIST_L2, 5
        )
        distancia_maxima = max(1, round(min(alto, ancho) * 0.20))
        mascara &= (nucleo | (distancia_al_nucleo <= distancia_maxima)
                    | (candidata_velo & ~nucleo))
    confianza = confianza_cromatica.copy()
    ampliar_confianza = mascara & ~nucleo
    confianza[ampliar_confianza] = np.maximum(
        confianza_cromatica[ampliar_confianza], confianza_velo[ampliar_confianza]
    )

    return ResultadoHumo(
        mascara_probable=mascara,
        confianza=confianza,
        firma_cian_swir=firma_cian.astype(np.float32),
    )
