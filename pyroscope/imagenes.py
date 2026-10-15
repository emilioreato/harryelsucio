"""Lectura y preparación de parejas de composiciones satelitales."""

from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps


def abrir_rgb(datos: bytes, max_lado: int = 1800) -> tuple[np.ndarray, tuple[int, int]]:
    """Lee una imagen como RGB y reduce su vista de trabajo sin cambiar proporción."""
    if max_lado < 1:
        raise ValueError("max_lado debe ser al menos 1 px.")
    with Image.open(BytesIO(datos)) as imagen:
        imagen = ImageOps.exif_transpose(imagen).convert("RGB")
        tamano_original = imagen.size
        imagen.thumbnail(
            (max_lado, max_lado),
            resample=Image.Resampling.LANCZOS,
        )
        return np.asarray(imagen, dtype=np.uint8), tamano_original


def validar_par_alineado(true_color: np.ndarray, swir: np.ndarray) -> None:
    """Comprueba que ambas entradas sean RGB uint8 y tengan la misma rejilla."""
    for nombre, imagen in (("True Color", true_color), ("SWIR", swir)):
        if not isinstance(imagen, np.ndarray):
            raise TypeError(f"{nombre} debe ser un array NumPy RGB.")
        if imagen.ndim != 3 or imagen.shape[2] != 3:
            raise ValueError(f"{nombre} debe tener tres canales RGB.")
        if imagen.dtype != np.uint8:
            raise ValueError(f"{nombre} debe usar valores uint8 de 0 a 255.")
    if true_color.shape != swir.shape:
        raise ValueError(
            "True Color y SWIR deben tener el mismo tamaño y estar alineadas. "
            "No se deforman automáticamente porque eso falsearía la correspondencia espacial."
        )


def reducir_par_alineado(
    true_color: np.ndarray,
    swir: np.ndarray,
    max_lado: int = 1800,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce ambas imágenes con la misma escala; nunca corrige desalineación."""
    validar_par_alineado(true_color, swir)
    if max_lado < 1:
        raise ValueError("max_lado debe ser al menos 1 px.")
    alto, ancho = true_color.shape[:2]
    escala = min(1.0, max_lado / max(alto, ancho))
    if escala == 1.0:
        return true_color, swir

    nuevo_tamano = (max(1, round(ancho * escala)), max(1, round(alto * escala)))
    tc_reducida = cv2.resize(true_color, nuevo_tamano, interpolation=cv2.INTER_AREA)
    swir_reducida = cv2.resize(swir, nuevo_tamano, interpolation=cv2.INTER_AREA)
    return tc_reducida, swir_reducida
