"""Velo en True Color conectado a humo ya corroborado por ambas vistas."""
import cv2
import numpy as np
from scipy import ndimage as ndi

from .imagenes import validar_par_alineado


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
