"""Velo en True Color conectado a humo ya corroborado por ambas vistas."""
from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage as ndi

from .imagenes import validar_par_alineado


@dataclass(frozen=True)
class ResultadoHumoPorNiveles:
    """Semillas fiables, humo moderado conectado y puntuación ordinal."""

    mascara_fuerte: np.ndarray
    mascara_moderada: np.ndarray
    mascara_probable: np.ndarray
    puntuacion: np.ndarray


def detectar_humo_por_niveles(true_color, swir, humo_inicial, confianza):
    """Amplía el humo por histéresis sin convertir terreno claro en semilla.

    Conserva la máscara previa como referencia. Los píxeles añadidos exigen
    señales claras en True Color, textura a dos escalas y compatibilidad
    cromática o tonal con SWIR; además deben conectar con un núcleo fiable y
    quedar dentro de una distancia medida desde ese núcleo original. La
    puntuación es ordinal y no está calibrada como probabilidad.
    """
    validar_par_alineado(true_color, swir)
    humo_inicial = np.asarray(humo_inicial)
    confianza = np.asarray(confianza, dtype=np.float32)
    forma = true_color.shape[:2]
    if humo_inicial.shape != forma or confianza.shape != forma:
        raise ValueError("Humo y confianza deben compartir la rejilla de las imágenes.")
    if not np.isfinite(confianza).all() or np.any((confianza < 0) | (confianza > 1)):
        raise ValueError("La confianza del humo debe ser finita y estar entre 0 y 1.")
    humo_inicial = humo_inicial.astype(bool)
    if not humo_inicial.any():
        vacia = np.zeros(forma, dtype=bool)
        return ResultadoHumoPorNiveles(vacia, vacia.copy(), vacia.copy(), confianza.copy())

    tc = true_color.astype(np.float32) / 255
    sw = swir.astype(np.float32) / 255
    luma = .2126 * tc[..., 0] + .7152 * tc[..., 1] + .0722 * tc[..., 2]
    max_tc, min_tc = tc.max(axis=2), tc.min(axis=2)
    neutralidad = 1 - np.ptp(tc, axis=2) / (max_tc + .025)
    luma_suave = ndi.gaussian_filter(luma, 1.2)

    def textura_local(matriz, lado):
        media = ndi.uniform_filter(matriz, size=lado)
        media_cuadrado = ndi.uniform_filter(matriz * matriz, size=lado)
        return np.sqrt(np.maximum(0, media_cuadrado - media * media))

    textura_corta = textura_local(luma, 7)
    textura_media = textura_local(luma, 21)
    gradiente = ndi.gaussian_gradient_magnitude(luma, sigma=1.2)

    sr, sg, sb = np.moveaxis(sw, -1, 0)
    cian = np.maximum(0, np.minimum(sg, sb) - sr) / (np.maximum(sg, sb) + 1e-3)
    cian *= 1 - np.abs(sg - sb) / (sg + sb + 1e-3)
    neutralidad_swir = 1 - np.ptp(sw, axis=2) / (sw.max(axis=2) + .025)
    luma_swir = .2126 * sr + .7152 * sg + .0722 * sb
    textura_swir = textura_local(luma_swir, 9)

    def escala(valor, bajo, alto):
        if alto <= bajo + 1e-6:
            return np.zeros_like(valor, dtype=np.float32)
        return np.clip((valor - bajo) / (alto - bajo), 0, 1).astype(np.float32)

    plano = ~humo_inicial
    lum_q = np.quantile(luma, [.35, .88])
    neutral_q = np.quantile(neutralidad, [.25, .88])
    corta_q = np.quantile(textura_corta, [.15, .78])
    media_q = np.quantile(textura_media, [.20, .85])
    cian_q = np.quantile(cian, [.35, .95])
    gris_swir_q = np.quantile(neutralidad_swir, [.50, .90])
    brillo_swir_q = np.quantile(luma_swir, [.35, .88])
    textura_swir_q = np.quantile(textura_swir, [.15, .78])

    evidencia_luminosa = escala(luma_suave, max(.20, float(lum_q[0])), float(lum_q[1]))
    evidencia_neutra = escala(neutralidad, float(neutral_q[0]), float(neutral_q[1]))
    evidencia_textura_corta = 1 - escala(textura_corta, float(corta_q[0]), float(corta_q[1]))
    evidencia_textura_media = 1 - escala(textura_media, float(media_q[0]), float(media_q[1]))
    evidencia_cian = escala(cian, max(.025, float(cian_q[0])), max(.10, float(cian_q[1])))
    evidencia_swir_neutra = (
        escala(neutralidad_swir, float(gris_swir_q[0]), float(gris_swir_q[1]))
        * escala(luma_swir, max(.15, float(brillo_swir_q[0])), float(brillo_swir_q[1]))
    )
    compatible_swir = (cian >= max(.025, float(cian_q[0]))) | (
        (neutralidad_swir >= max(.62, float(gris_swir_q[0])))
        & (luma_swir >= max(.18, float(brillo_swir_q[0])))
        & (textura_swir <= max(.10, float(textura_swir_q[1])))
    )
    puntuacion = (
        .22 * evidencia_luminosa
        + .20 * evidencia_neutra
        + .24 * evidencia_textura_corta
        + .14 * evidencia_textura_media
        + .20 * np.maximum(evidencia_cian, evidencia_swir_neutra)
    ).astype(np.float32)

    confianza_semilla = max(.68, float(np.quantile(confianza[humo_inicial], .60)))
    cian_semilla = max(.10, float(np.quantile(cian[humo_inicial], .65)))
    mascara_fuerte = humo_inicial & (
        (confianza >= confianza_semilla)
        | ((cian >= cian_semilla) & (neutralidad >= .45))
    )
    # Sin una semilla atmosférica fiable no se expande desde píxeles claros.
    if not mascara_fuerte.any():
        return ResultadoHumoPorNiveles(
            mascara_fuerte, np.zeros(forma, bool), humo_inicial.copy(), confianza.copy()
        )

    luminosa = luma_suave >= max(.22, float(lum_q[0]))
    neutra = neutralidad >= .54
    baja_textura = (
        (textura_corta <= max(.095, float(corta_q[1])))
        & (textura_media <= max(.16, float(media_q[1])))
        & (gradiente <= max(.055, float(np.quantile(gradiente, .92))))
    )
    candidata_debil = (
        luminosa & neutra & baja_textura & compatible_swir & (puntuacion >= .58)
    )
    distancia = ndi.distance_transform_edt(~mascara_fuerte)
    radio_maximo = max(8, round(min(forma) * .08))
    candidata_debil &= distancia <= radio_maximo
    permitida = humo_inicial | candidata_debil | mascara_fuerte
    conectada = ndi.binary_propagation(mascara_fuerte, mask=permitida)
    mascara_moderada = conectada & candidata_debil & ~humo_inicial
    mascara_probable = humo_inicial | mascara_moderada

    puntuacion[humo_inicial] = np.maximum(puntuacion[humo_inicial], .55)
    puntuacion[mascara_fuerte] = np.maximum(puntuacion[mascara_fuerte], .75)
    puntuacion[mascara_moderada] = np.clip(puntuacion[mascara_moderada], .50, .74)
    return ResultadoHumoPorNiveles(
        mascara_fuerte, mascara_moderada, mascara_probable, puntuacion
    )


def ampliar_humo_true_color(true_color, swir, humo, confianza):
    """Extiende humo por evidencia visible, sin colorear toda nube/suelo claro.

    SWIR aporta el ancla existente; la expansión depende de luminosidad,
    neutralidad y textura de True Color. No utiliza superficie afectada como
    semilla atmosférica. La distancia se fija desde el humo original.
    """
    validar_par_alineado(true_color, swir)
    if humo.shape != true_color.shape[:2] or confianza.shape != humo.shape:
        raise ValueError("Humo y confianza deben compartir la rejilla de las imágenes.")
    if not humo.any():
        return humo.copy(), confianza.copy()
    tc = true_color.astype(np.float32) / 255
    luma = .2126 * tc[..., 0] + .7152 * tc[..., 1] + .0722 * tc[..., 2]
    croma = np.ptp(tc, axis=2) / (tc.max(axis=2) + .025)
    suave = ndi.gaussian_filter(luma, 1.2)
    textura = np.sqrt(np.maximum(0, ndi.uniform_filter(luma * luma, 9)
                                - ndi.uniform_filter(luma, 9) ** 2))
    # Contraste local permite humo con estructura: no exige el 15% más liso
    # de toda la escena como el crecimiento antiguo.
    luminosa = suave >= max(.22, float(np.quantile(luma, .50)))
    neutra = croma <= .38
    detalle_atenuado = textura <= .085
    admisible = luminosa & neutra & detalle_atenuado
    admisible = cv2.morphologyEx(admisible.astype(np.uint8), cv2.MORPH_CLOSE,
                                np.ones((3, 3), np.uint8)).astype(bool)
    distancia = ndi.distance_transform_edt(~humo)
    admisible &= distancia <= max(4, round(min(humo.shape) * .06))
    ampliada = ndi.binary_propagation(humo, mask=humo | admisible)
    nueva_confianza = confianza.copy()
    # Evidencia visible ordinal: no es probabilidad de humo.
    nueva_confianza[ampliada & ~humo] = .55
    return ampliada, nueva_confianza
