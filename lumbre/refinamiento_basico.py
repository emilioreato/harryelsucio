"""Refinamientos locales posteriores a la detección, sin realimentar semillas."""

import cv2
import numpy as np
from scipy import ndimage as ndi

from .imagenes import validar_par_alineado


def _mascara(valor, forma):
    matriz = np.asarray(valor)
    if matriz.shape != forma or not np.all((matriz == 0) | (matriz == 1)):
        raise ValueError("Las máscaras deben ser binarias y compartir la rejilla RGB.")
    return matriz.astype(bool)


def refinar_superficie_local(swir, superficie, agua):
    """Cierra discontinuidades cortas compatibles con SWIR; no rellena islas grandes.

    Devuelve la unión estimada refinada. Los píxeles añadidos son continuidad
    inferida, no observación visible ni nuevas semillas espectrales.
    """
    validar_par_alineado(swir, swir)
    superficie = _mascara(superficie, swir.shape[:2])
    agua = _mascara(agua, superficie.shape)
    if not superficie.any():
        return superficie.copy()
    r, g, b = np.moveaxis(swir.astype(np.float32) / 255, -1, 0)
    rojo = (2 * r - g - b) / (r + g + b + .001)
    rg = (r - g) / (r + g + .001)
    compatible = (
        (rojo >= max(.02, float(np.quantile(rojo[superficie], .10)) - .16))
        & (rg >= max(-.06, float(np.quantile(rg[superficie], .10)) - .10))
        & (r >= .10) & ~agua
    )
    radio = max(1, min(3, round(min(superficie.shape) * .002)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radio + 1,) * 2)
    cerrada = cv2.morphologyEx(superficie.astype(np.uint8), cv2.MORPH_CLOSE,
                             kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
    huecos = ndi.binary_fill_holes(superficie) & ~superficie
    etiquetas, _ = ndi.label(huecos)
    tamanos = np.bincount(etiquetas.ravel())
    pequenas = tamanos <= max(16, round(np.pi * (2 * radio) ** 2))
    pequenas[0] = False
    # Un cierre no puede tapar un hueco grande ni parcialmente una isla de agua
    # o vegetación: el tamaño se decide antes de aplicar el veto espectral.
    huecos_permitidos = pequenas[etiquetas]
    propuestas = (cerrada | huecos_permitidos) & ~superficie
    propuestas &= ~huecos | huecos_permitidos
    return superficie | (propuestas & compatible)


def refinar_velo_contextual(true_color, swir, humo, agua):
    """Velo conectado sobre cualquier terreno, antes de evaluar suelo ocluido.

    No usa una máscara de quemado y no fabrica semillas en zonas aisladas.
    Exige neutralidad visible y apoyo azul SWIR; la distancia se mide desde
    el humo de entrada, sin iteraciones que lo reutilicen como nuevas semillas.
    """
    validar_par_alineado(true_color, swir)
    forma = true_color.shape[:2]
    humo, agua = (_mascara(m, forma) for m in (humo, agua))
    if not humo.any():
        return humo.copy()
    tc = true_color.astype(np.float32) / 255
    r, g, b = np.moveaxis(tc, -1, 0)
    luma = .2126 * r + .7152 * g + .0722 * b
    croma = np.ptp(tc, axis=2) / (tc.max(axis=2) + .025)
    textura = np.sqrt(np.maximum(0, ndi.uniform_filter(luma * luma, 7)
                                 - ndi.uniform_filter(luma, 7) ** 2))
    sr, sg, sb = np.moveaxis(swir.astype(np.float32) / 255, -1, 0)
    verde_swir = (sg - sb) / (sg + sb + .001)
    velo = ((croma <= .16) & (b >= .88 * r) & (b >= .88 * g)
            & (luma >= .40) & (textura <= .10))
    apoyo_swir = (verde_swir <= .42) & (sr <= 1.15 * sg) & (sb >= .10)
    distancia = ndi.distance_transform_edt(~humo)
    radio = max(8, min(128, round(min(forma) * .08)))
    permitida = velo & apoyo_swir & ~agua & (distancia <= radio)
    return ndi.binary_propagation(humo, mask=humo | permitida,
                                  structure=np.ones((3, 3), bool))


def refinar_humo_sobre_superficie(true_color, swir, humo, superficie, agua):
    """Recupera velo en el borde del penacho sobre suelo estimado quemado.

    La superficie solo delimita dónde mirar. Se exige señal atmosférica visible,
    contraste con suelo despejado y conexión al humo previo. No se reutiliza
    este refinamiento para volver a clasificar el suelo.
    """
    validar_par_alineado(true_color, swir)
    forma = true_color.shape[:2]
    humo, superficie, agua = (_mascara(m, forma) for m in (humo, superficie, agua))
    if not humo.any() or not superficie.any():
        return humo.copy()
    tc = true_color.astype(np.float32) / 255
    r, g, b = np.moveaxis(tc, -1, 0)
    luma = .2126 * r + .7152 * g + .0722 * b
    croma = np.ptp(tc, axis=2) / (tc.max(axis=2) + .025)
    suelo_despejado = superficie & ~humo & ~agua & (b < .90 * r) & (croma >= .18)
    if suelo_despejado.sum() < 16:
        return humo.copy()
    brillo_suelo = float(np.quantile(luma[suelo_despejado], .40))
    sigma = max(3, round(min(forma) * .008))
    peso_suelo = ndi.gaussian_filter(suelo_despejado.astype(np.float32), sigma)
    brillo_local = ndi.gaussian_filter(luma * suelo_despejado, sigma) / np.maximum(peso_suelo, 1e-5)
    brillo_local = np.where(peso_suelo >= .05, brillo_local, brillo_suelo)
    contraste = ndi.gaussian_filter(luma, 1) >= np.maximum(.18, brillo_local + .015)
    # La tierra amarilla puede ser clara, pero no tiene este equilibrio azulado.
    velo = (croma <= .28) & (b >= .92 * r) & (b >= .92 * g)
    textura = np.sqrt(np.maximum(0, ndi.uniform_filter(luma * luma, 7)
                                 - ndi.uniform_filter(luma, 7) ** 2))
    margen = max(2, min(6, round(min(forma) * .003)))
    entorno = ndi.binary_dilation(superficie, iterations=margen)
    # La oclusión puede interrumpir precisamente la firma SWIR del suelo.
    # Esa ausencia no es un veto de humo. Construir un contexto que atraviese
    # interrupciones interiores; no modifica la clasificación de superficie.
    radio_contexto = max(2, min(24, round(min(forma) * .015)))
    kernel_contexto = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * radio_contexto + 1,) * 2,
    )
    envolvente = cv2.morphologyEx(superficie.astype(np.uint8), cv2.MORPH_CLOSE,
                                kernel_contexto) > 0
    entorno |= ndi.binary_fill_holes(envolvente | superficie)
    distancia = ndi.distance_transform_edt(~humo)
    radio = max(8, min(128, round(min(forma) * .08)))
    permitida = entorno & contraste & velo & (textura <= .10) & ~agua & (distancia <= radio)
    return ndi.binary_propagation(humo, mask=humo | permitida,
                                  structure=np.ones((3, 3), bool))
