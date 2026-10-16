"""Representación visual de la máscara y el perímetro de área afectada."""

import cv2
import numpy as np

from .segmentacion import ResultadoAreaAfectada
from .ontologia import ClaseSemantica


_COLOR_HUMO = (30, 120, 221)
_COLOR_BORDE_HUMO = (19, 93, 168)


def crear_superposicion(
    imagen_base: np.ndarray,
    resultado: ResultadoAreaAfectada,
    *, unir_superficie: bool = False,
) -> np.ndarray:
    """Dibuja capas independientes; el humo no apaga la superficie inferida."""
    if imagen_base.shape[:2] != resultado.mascara.shape:
        raise ValueError("La imagen y la máscara deben tener las mismas dimensiones.")
    if unir_superficie:
        union = resultado.mascara_superficie_estimada
        salida = superponer_mascara(imagen_base, union, color=(225, 45, 35), opacidad=.56)
        salida = _superponer_humo(salida, resultado.mascara_humo)
        contornos, _ = cv2.findContours(union.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(salida, contornos, -1, (255, 238, 60), max(1, round(max(union.shape) / 1200)))
        return salida

    # El orden de pintado mantiene legibles ambas evidencias. Las tres máscaras
    # también se exportan por separado: este PNG combinado es solo una vista.
    salida = _superponer_humo(imagen_base, resultado.mascara_humo)
    salida = superponer_mascara(
        salida, resultado.mascara,
        color=(225, 45, 35), opacidad=0.56,
    )
    salida = superponer_mascara(
        salida, resultado.mascara_candidata_bajo_humo,
        color=(220, 35, 190), opacidad=0.48,
    )
    salida = _superponer_clases_adicionales(
        salida,
        resultado,
        opacidad_agua=0.5,
        opacidad_fuego=0.78,
        opacidad_nube=0.28,
    )
    if resultado.contornos:
        grosor = max(2, round(max(salida.shape[:2]) / 900))
        cv2.drawContours(salida, list(resultado.contornos), -1, (255, 238, 60), grosor)
    _superponer_borde_inferido(salida, resultado.mascara_candidata_bajo_humo)
    return salida


def crear_vista_clasificacion(
    true_color: np.ndarray,
    resultado: ResultadoAreaAfectada,
    *, unir_superficie: bool = False,
) -> np.ndarray:
    """Muestra por separado candidatos de superficie y humo probable."""
    if true_color.shape[:2] != resultado.mascara_clasificada.shape:
        raise ValueError("La imagen y las máscaras deben tener las mismas dimensiones.")
    if unir_superficie:
        return crear_superposicion(true_color, resultado, unir_superficie=True)

    salida = _superponer_humo(true_color, resultado.mascara_humo)
    salida = superponer_mascara(
        salida, resultado.mascara_clasificada,
        color=(225, 45, 35), opacidad=0.46,
    )
    salida = superponer_mascara(
        salida, resultado.mascara_candidata_bajo_humo,
        color=(220, 35, 190), opacidad=0.48,
    )
    salida = _superponer_clases_adicionales(
        salida,
        resultado,
        opacidad_agua=0.58,
        opacidad_fuego=0.82,
        opacidad_nube=0.3,
    )
    _superponer_borde_inferido(salida, resultado.mascara_candidata_bajo_humo)
    return salida


def _superponer_clases_adicionales(
    imagen: np.ndarray,
    resultado: ResultadoAreaAfectada,
    *,
    opacidad_agua: float,
    opacidad_fuego: float,
    opacidad_nube: float,
) -> np.ndarray:
    """Pinta clases semánticas cuando el resultado incluye esa capa opcional."""
    clases = getattr(resultado, "clase_por_pixel", None)
    if clases is None:
        return imagen
    if clases.shape != imagen.shape[:2]:
        raise ValueError("La imagen y las clases semánticas deben tener las mismas dimensiones.")

    salida = superponer_mascara(
        imagen,
        clases == ClaseSemantica.AGUA_POSIBLE,
        color=(25, 105, 255),
        opacidad=opacidad_agua,
    )
    salida = superponer_mascara(
        salida,
        clases == ClaseSemantica.FUEGO_ACTIVO_POSIBLE,
        color=(255, 245, 0),
        opacidad=opacidad_fuego,
    )
    return superponer_mascara(
        salida,
        clases == ClaseSemantica.NUBE_BRUMA,
        color=(170, 175, 185),
        opacidad=opacidad_nube,
    )


def colorear_diagnostico(datos: np.ndarray) -> np.ndarray:
    """Colores deterministas para etiquetas; máscaras binarias sin colorear."""
    datos = np.asarray(datos)
    if datos.ndim != 2:
        raise ValueError("El diagnóstico debe ser una máscara o etiquetas bidimensionales.")
    if datos.dtype == np.bool_ or (datos.size and datos.min() >= 0 and datos.max() <= 1):
        return datos.astype(bool)
    if np.issubdtype(datos.dtype, np.floating):
        return (np.clip(np.nan_to_num(datos), 0, 1) * 255).astype(np.uint8)
    etiquetas = np.maximum(datos, 0).astype(np.uint64)
    rgb = np.stack(((etiquetas * 73 + 37) % 256, (etiquetas * 151 + 71) % 256,
                    (etiquetas * 199 + 113) % 256), axis=-1).astype(np.uint8)
    rgb[etiquetas == 0] = 0
    return rgb


def superponer_mascara(
    imagen_rgb: np.ndarray,
    mascara: np.ndarray,
    *,
    color: tuple[int, int, int] = (245, 65, 35),
    opacidad: float = 0.32,
) -> np.ndarray:
    """Pinta una máscara binaria en la rejilla de una composición RGB."""
    if imagen_rgb.ndim != 3 or imagen_rgb.shape[2] != 3:
        raise ValueError("La imagen debe tener tres canales RGB.")
    if mascara.shape != imagen_rgb.shape[:2]:
        raise ValueError("La imagen y la máscara deben tener las mismas dimensiones.")
    if not 0.0 <= opacidad <= 1.0:
        raise ValueError("La opacidad debe estar entre cero y uno.")
    salida = imagen_rgb.copy()
    dentro = mascara.astype(bool)
    salida[dentro] = (
        (1.0 - opacidad) * salida[dentro]
        + opacidad * np.asarray(color, dtype=np.float32)
    ).astype(np.uint8)
    return salida


def _superponer_humo(imagen_rgb: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    """Dibuja el humo probable con el mismo azul y borde que el visor."""
    salida = superponer_mascara(imagen_rgb, mascara, color=_COLOR_HUMO, opacidad=.25)
    binaria = np.asarray(mascara, dtype=bool)
    interior = binaria.copy()
    interior[1:, :] &= binaria[:-1, :]
    interior[:-1, :] &= binaria[1:, :]
    interior[:, 1:] &= binaria[:, :-1]
    interior[:, :-1] &= binaria[:, 1:]
    borde = binaria & ~interior
    borde[0, :] |= binaria[0, :]
    borde[-1, :] |= binaria[-1, :]
    borde[:, 0] |= binaria[:, 0]
    borde[:, -1] |= binaria[:, -1]
    return superponer_mascara(salida, borde, color=_COLOR_BORDE_HUMO, opacidad=.42)


def _superponer_borde_inferido(imagen_rgb: np.ndarray, mascara: np.ndarray) -> None:
    """Traza una frontera discontinua para que la hipótesis no parezca observada."""
    if mascara.shape != imagen_rgb.shape[:2] or not np.any(mascara):
        return
    binaria = mascara.astype(np.uint8)
    borde = cv2.morphologyEx(binaria, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)).astype(bool)
    yy, xx = np.indices(mascara.shape)
    discontinuo = borde & ((xx + yy) % 8 < 4)
    imagen_rgb[discontinuo] = (255, 45, 220)
