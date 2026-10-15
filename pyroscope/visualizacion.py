"""Representación visual de la máscara y el perímetro de área afectada."""

import cv2
import numpy as np

from .segmentacion import ResultadoAreaAfectada


def crear_superposicion(
    imagen_base: np.ndarray,
    resultado: ResultadoAreaAfectada,
) -> np.ndarray:
    """Dibuja relleno translúcido y perímetro sobre una composición RGB."""
    if imagen_base.shape[:2] != resultado.mascara.shape:
        raise ValueError("La imagen y la máscara deben tener las mismas dimensiones.")

    salida = superponer_mascara(imagen_base, resultado.mascara)
    salida = _superponer_oclusiones(salida, resultado)

    if resultado.contornos:
        grosor = max(2, round(max(salida.shape[:2]) / 900))
        cv2.drawContours(salida, list(resultado.contornos), -1, (255, 238, 60), grosor)
    return salida


def crear_vista_clasificacion(
    true_color: np.ndarray,
    resultado: ResultadoAreaAfectada,
) -> np.ndarray:
    """Muestra por separado candidatos de superficie y humo probable."""
    if true_color.shape[:2] != resultado.mascara_clasificada.shape:
        raise ValueError("La imagen y las máscaras deben tener las mismas dimensiones.")

    salida = superponer_mascara(
        true_color,
        resultado.mascara_clasificada,
        color=(255, 115, 25),
        opacidad=0.36,
    )
    return _superponer_oclusiones(salida, resultado)


def _superponer_oclusiones(imagen: np.ndarray, resultado: ResultadoAreaAfectada) -> np.ndarray:
    """Humo atmosférico debajo de las hipótesis; desconocido con trama ligera."""
    salida = superponer_mascara(
        imagen,
        resultado.mascara_humo,
        color=(0, 165, 255),
        opacidad=0.42,
    )
    desconocida = getattr(resultado, "mascara_indeterminada", None)
    if desconocida is not None:
        filas, columnas = np.ogrid[:salida.shape[0], :salida.shape[1]]
        trama = desconocida.astype(bool) & ((filas + columnas) % 8 < 2)
        salida = superponer_mascara(salida, trama, color=(220, 220, 220), opacidad=0.55)
    return superponer_mascara(
        salida,
        resultado.mascara_candidata_bajo_humo,
        color=(220, 55, 175),
        opacidad=0.62,
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
