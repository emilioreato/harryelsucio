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

    # El trazado principal representa observación despejada. La hipótesis bajo
    # humo se exporta y visualiza en su propia capa, nunca como fuego observado.
    superficie = resultado.mascara
    salida = superponer_mascara(imagen_base, superficie)
    contornos, _ = cv2.findContours(superficie.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if contornos:
        grosor = max(2, round(max(salida.shape[:2]) / 900))
        cv2.drawContours(salida, list(contornos), -1, (255, 238, 60), grosor)
    return _superponer_oclusiones(salida, resultado)


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
        color=(245, 65, 35),
        opacidad=0.36,
    )
    return _superponer_oclusiones(salida, resultado)


def crear_vista_capa(
    imagen_base: np.ndarray,
    mascara: np.ndarray,
    *,
    color: tuple[int, int, int],
    opacidad: float = 0.42,
) -> np.ndarray:
    """Superpone una máscara diagnóstica en su propia vista RGB."""
    return superponer_mascara(imagen_base, mascara, color=color, opacidad=opacidad)


def _superponer_oclusiones(imagen: np.ndarray, resultado: ResultadoAreaAfectada) -> np.ndarray:
    """Capa atmosférica superior; superficie e incertidumbre se exportan aparte."""
    return superponer_mascara(
        imagen,
        resultado.mascara_humo,
        color=(0, 165, 255),
        opacidad=0.28,
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
