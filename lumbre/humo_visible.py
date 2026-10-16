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
    candidatos_debiles: np.ndarray
    descartados_por_distancia: np.ndarray
    descartados_por_conectividad: np.ndarray
    candidatos_perdidos_por_swir: np.ndarray


def detectar_humo_por_niveles(
    true_color, swir, humo_inicial, confianza, *, mascara_nucleo=None,
    fraccion_distancia_nucleo: float = .08,
    umbral_expansion: float = .50,
):
    """Amplía el humo por histéresis sin convertir terreno claro en semilla.

    Conserva la máscara previa como referencia. Los píxeles añadidos exigen
    señales claras de velo en True Color y textura atenuada a dos escalas;
    además deben conectar con un núcleo fiable y quedar dentro de una
    distancia medida desde ese núcleo original. SWIR se conserva para
    diagnosticar contradicciones, pero no veta el humo: bajo el velo puede
    revelar la firma del terreno y no la del aerosol. La puntuación es ordinal,
    no una probabilidad calibrada.
    """
    validar_par_alineado(true_color, swir)
    humo_inicial = np.asarray(humo_inicial)
    confianza = np.asarray(confianza, dtype=np.float32)
    forma = true_color.shape[:2]
    if humo_inicial.shape != forma or confianza.shape != forma:
        raise ValueError("Humo y confianza deben compartir la rejilla de las imágenes.")
    if not np.isfinite(confianza).all() or np.any((confianza < 0) | (confianza > 1)):
        raise ValueError("La confianza del humo debe ser finita y estar entre 0 y 1.")
    if (not np.isfinite(fraccion_distancia_nucleo)
            or not 0 < fraccion_distancia_nucleo <= .5):
        raise ValueError("La fracción de distancia debe estar en el intervalo (0, 0.5].")
    if not np.isfinite(umbral_expansion) or not .5 <= umbral_expansion <= 1:
        raise ValueError("El umbral de expansión debe estar entre 0.5 y 1.")
    humo_inicial = humo_inicial.astype(bool)
    if mascara_nucleo is None:
        mascara_nucleo = humo_inicial
    else:
        mascara_nucleo = np.asarray(mascara_nucleo)
        if mascara_nucleo.shape != forma:
            raise ValueError("El núcleo y las imágenes deben compartir la rejilla.")
        mascara_nucleo = mascara_nucleo.astype(bool)
    if not humo_inicial.any():
        vacia = np.zeros(forma, dtype=bool)
        return ResultadoHumoPorNiveles(
            vacia, vacia.copy(), vacia.copy(), confianza.copy(),
            vacia.copy(), vacia.copy(), vacia.copy(), vacia.copy(),
        )

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
    # El SWIR ve la superficie que hay debajo del velo; exigir que también
    # parezca humo excluía precisamente penachos sobre suelo rojizo. En la
    # expansión moderada se puntúan solo rasgos atmosféricos observables en
    # True Color. El núcleo inicial conserva la corroboración SWIR existente.
    puntuacion = (
        .275 * evidencia_luminosa
        + .25 * evidencia_neutra
        + .30 * evidencia_textura_corta
        + .175 * evidencia_textura_media
    ).astype(np.float32)

    if not mascara_nucleo.any():
        moderada = humo_inicial.copy()
        return ResultadoHumoPorNiveles(
            np.zeros(forma, bool), moderada, humo_inicial.copy(), confianza.copy(),
            np.zeros(forma, bool), np.zeros(forma, bool), np.zeros(forma, bool),
            np.zeros(forma, bool),
        )
    confianza_semilla = max(.68, float(np.quantile(confianza[mascara_nucleo], .60)))
    cian_semilla = max(.10, float(np.quantile(cian[mascara_nucleo], .65)))
    mascara_fuerte = mascara_nucleo & (
        (confianza >= confianza_semilla)
        | ((cian >= cian_semilla) & (neutralidad >= .45))
    )
    # Sin una semilla atmosférica fiable no se expande desde píxeles claros.
    if not mascara_fuerte.any():
        moderada = humo_inicial.copy()
        return ResultadoHumoPorNiveles(
            mascara_fuerte, moderada, humo_inicial.copy(), confianza.copy(),
            np.zeros(forma, bool), np.zeros(forma, bool), np.zeros(forma, bool),
            np.zeros(forma, bool),
        )

    luminosa = luma_suave >= max(.22, float(lum_q[0]))
    neutra = neutralidad >= .54
    baja_textura = (
        (textura_corta <= max(.095, float(corta_q[1])))
        & (textura_media <= max(.16, float(media_q[1])))
        & (gradiente <= max(.055, float(np.quantile(gradiente, .92))))
    )
    candidatos_por_true_color = luminosa & neutra & baja_textura & (puntuacion >= umbral_expansion)
    candidatos_perdidos_por_swir = candidatos_por_true_color & ~compatible_swir
    candidatos_debiles = candidatos_por_true_color
    distancia = ndi.distance_transform_edt(~mascara_fuerte)
    radio_maximo = max(8, round(min(forma) * fraccion_distancia_nucleo))
    candidata_debil = candidatos_debiles & (distancia <= radio_maximo)
    permitida = humo_inicial | candidata_debil | mascara_fuerte
    conectada = ndi.binary_propagation(mascara_fuerte, mask=permitida)
    # La máscara de referencia se conserva. Los píxeles heredados que no son
    # núcleo y la nueva extensión débil quedan explícitamente en el nivel
    # moderado, sin convertirlos en nuevas semillas.
    mascara_moderada = (humo_inicial & ~mascara_fuerte) | (
        conectada & candidata_debil & ~humo_inicial
    )
    mascara_probable = humo_inicial | mascara_moderada | mascara_fuerte
    descartados_por_distancia = candidatos_debiles & (distancia > radio_maximo)
    descartados_por_conectividad = candidata_debil & ~conectada

    puntuacion[humo_inicial] = np.maximum(puntuacion[humo_inicial], .55)
    puntuacion[mascara_fuerte] = np.maximum(puntuacion[mascara_fuerte], .75)
    puntuacion[mascara_moderada] = np.clip(puntuacion[mascara_moderada], .50, .74)
    return ResultadoHumoPorNiveles(
        mascara_fuerte, mascara_moderada, mascara_probable, puntuacion,
        candidatos_debiles, descartados_por_distancia,
        descartados_por_conectividad, candidatos_perdidos_por_swir,
    )


def ampliar_humo_true_color(true_color, swir, humo, confianza, *, conservadora=False):
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
    neutra = croma <= (.32 if conservadora else .38)
    detalle_atenuado = textura <= (.06 if conservadora else .085)
    admisible = luminosa & neutra & detalle_atenuado
    admisible = cv2.morphologyEx(admisible.astype(np.uint8), cv2.MORPH_CLOSE,
                                np.ones((3, 3), np.uint8)).astype(bool)
    distancia = ndi.distance_transform_edt(~humo)
    admisible &= distancia <= max(4, round(min(humo.shape) * (.03 if conservadora else .06)))
    ampliada = ndi.binary_propagation(humo, mask=humo | admisible)
    nueva_confianza = confianza.copy()
    # Evidencia visible ordinal: no es probabilidad de humo.
    nueva_confianza[ampliada & ~humo] = .55
    return ampliada, nueva_confianza
