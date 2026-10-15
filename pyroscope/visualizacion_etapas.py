"""Renderizado ligero y fiel de estados intermedios sobre la rejilla del análisis."""

from __future__ import annotations

import cv2
import numpy as np

from .ontologia import ClaseSemantica


MAX_LADO_PREVISUALIZACION = 900


def previsualizar_imagen(imagen: np.ndarray) -> np.ndarray:
    """Reduce RGB conservando aspecto y rejilla, sin ampliar imágenes pequeñas."""
    _validar_rgb(imagen)
    alto, ancho = imagen.shape[:2]
    escala = min(1.0, MAX_LADO_PREVISUALIZACION / max(alto, ancho))
    if escala == 1.0:
        return imagen
    destino = (max(1, round(ancho * escala)), max(1, round(alto * escala)))
    return cv2.resize(imagen, destino, interpolation=cv2.INTER_AREA)


def previsualizar_clasificacion(
    imagen: np.ndarray,
    candidata: np.ndarray,
    humo: np.ndarray,
    agua: np.ndarray,
    bajo_humo: np.ndarray,
) -> np.ndarray:
    salida, mascaras = _preparar(imagen, candidata, humo, agua, bajo_humo)
    _pintar(salida, mascaras[0], (245, 65, 35), 0.45)
    _pintar(salida, mascaras[3], (220, 55, 175), 0.58)
    _pintar(salida, mascaras[1], (0, 165, 255), 0.35)
    _pintar(salida, mascaras[2], (25, 105, 255), 0.52)
    return salida


def previsualizar_slic(imagen: np.ndarray, etiquetas: np.ndarray) -> np.ndarray:
    salida = previsualizar_imagen(imagen).copy()
    ids = _reducir_etiquetas(etiquetas, salida.shape[:2])
    bordes = np.zeros(ids.shape, dtype=bool)
    bordes[:, 1:] |= ids[:, 1:] != ids[:, :-1]
    bordes[1:, :] |= ids[1:, :] != ids[:-1, :]
    bordes = cv2.dilate(bordes.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    salida[bordes] = (70, 235, 215)
    return salida


def previsualizar_clases_regionales(
    imagen: np.ndarray, clases: np.ndarray, etiquetas: np.ndarray
) -> np.ndarray:
    salida = previsualizar_imagen(imagen).copy()
    ids = _reducir_etiquetas(etiquetas, salida.shape[:2])
    clases_reducidas = clases[ids]
    _pintar(salida, clases_reducidas == 1, (244, 82, 47), 0.55)
    _pintar(salida, clases_reducidas == 2, (246, 202, 65), 0.60)
    _pintar(salida, clases_reducidas == 3, (166, 145, 190), 0.58)
    return salida


def previsualizar_rag(
    imagen: np.ndarray, etiquetas: np.ndarray, grupos: np.ndarray
) -> np.ndarray:
    salida = previsualizar_imagen(imagen).copy()
    ids = grupos[_reducir_etiquetas(etiquetas, salida.shape[:2])].astype(np.uint64)
    colores = np.stack(
        ((ids * 73 + 37) % 256, (ids * 151 + 71) % 256, (ids * 199 + 113) % 256),
        axis=-1,
    ).astype(np.uint8)
    dentro = ids != 0
    salida[dentro] = (
        salida[dentro].astype(np.float32) * 0.48 + colores[dentro].astype(np.float32) * 0.52
    ).astype(np.uint8)
    return salida


def previsualizar_crecimiento(
    imagen: np.ndarray,
    evidencia_original: np.ndarray,
    crecimiento: np.ndarray,
) -> np.ndarray:
    salida, mascaras = _preparar(imagen, evidencia_original, crecimiento)
    _pintar(salida, mascaras[0], (245, 65, 35), 0.55)
    _pintar(salida, mascaras[1], (50, 210, 235), 0.72)
    return salida


def previsualizar_watershed(
    imagen: np.ndarray,
    mascara_previa: np.ndarray,
    mascara_refinada: np.ndarray,
) -> np.ndarray:
    salida, mascaras = _preparar(imagen, mascara_previa, mascara_refinada)
    _pintar(salida, mascaras[0], (245, 65, 35), 0.48)
    cambios = mascaras[0] ^ mascaras[1]
    _pintar(salida, mascaras[1], (245, 65, 35), 0.48)
    _pintar(salida, cambios, (255, 224, 65), 0.92)
    return salida


def previsualizar_mascara(imagen: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    salida, mascaras = _preparar(imagen, mascara)
    _pintar(salida, mascaras[0], (245, 65, 35), 0.58)
    return salida


def previsualizar_bajo_humo(
    imagen: np.ndarray,
    humo: np.ndarray,
    hipotesis: np.ndarray,
    indeterminada: np.ndarray,
) -> np.ndarray:
    salida, mascaras = _preparar(imagen, humo, hipotesis, indeterminada)
    _pintar(salida, mascaras[0], (0, 165, 255), 0.32)
    _pintar(salida, mascaras[1], (220, 55, 175), 0.68)
    _pintar(salida, mascaras[2], (168, 175, 185), 0.4)
    return salida


def previsualizar_resultado(
    imagen: np.ndarray,
    mascara: np.ndarray,
    bajo_humo: np.ndarray,
    humo: np.ndarray,
    clases: np.ndarray,
    contornos: tuple[np.ndarray, ...],
) -> np.ndarray:
    salida, mascaras = _preparar(imagen, mascara, bajo_humo, humo)
    _pintar(salida, mascaras[0] | mascaras[1], (245, 65, 35), 0.32)
    clases_reducidas = _reducir_etiquetas(clases, salida.shape[:2])
    _pintar(salida, clases_reducidas == ClaseSemantica.AGUA_POSIBLE, (25, 105, 255), 0.5)
    _pintar(salida, clases_reducidas == ClaseSemantica.FUEGO_ACTIVO_POSIBLE, (255, 245, 0), 0.78)
    _pintar(salida, clases_reducidas == ClaseSemantica.NUBE_BRUMA, (170, 175, 185), 0.28)
    _pintar(salida, mascaras[2], (0, 165, 255), 0.28)
    if contornos:
        alto, ancho = imagen.shape[:2]
        escala = np.asarray([salida.shape[1] / ancho, salida.shape[0] / alto], dtype=np.float32)
        contornos_reducidos = tuple(
            np.rint(np.asarray(contorno, dtype=np.float32) * escala).astype(np.int32)
            for contorno in contornos
        )
        grosor = max(1, round(max(salida.shape[:2]) / 900))
        cv2.drawContours(salida, list(contornos_reducidos), -1, (255, 238, 60), grosor)
    return salida


def _preparar(imagen: np.ndarray, *mascaras: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
    _validar_rgb(imagen)
    salida = previsualizar_imagen(imagen).copy()
    reducidas = []
    for mascara in mascaras:
        matriz = np.asarray(mascara)
        if matriz.ndim != 2 or matriz.shape != imagen.shape[:2]:
            raise ValueError("Las máscaras deben compartir la rejilla de la imagen.")
        reducidas.append(_reducir_mascara(matriz, salida.shape[:2]))
    return salida, reducidas


def _validar_rgb(imagen: np.ndarray) -> None:
    if not isinstance(imagen, np.ndarray) or imagen.ndim != 3 or imagen.shape[2] != 3:
        raise ValueError("La imagen base debe estar en formato RGB.")
    if imagen.dtype != np.uint8 or not imagen.size:
        raise ValueError("La imagen base debe ser RGB uint8 y no estar vacía.")


def _reducir_etiquetas(etiquetas: np.ndarray, destino: tuple[int, int]) -> np.ndarray:
    matriz = np.asarray(etiquetas, dtype=np.int32)
    if matriz.ndim != 2 or not matriz.size:
        raise ValueError("Las etiquetas deben formar una matriz 2D no vacía.")
    if matriz.shape == destino:
        return matriz
    return cv2.resize(matriz, (destino[1], destino[0]), interpolation=cv2.INTER_NEAREST)


def _reducir_mascara(mascara: np.ndarray, destino: tuple[int, int]) -> np.ndarray:
    if mascara.shape == destino:
        return mascara.astype(bool)
    reducida = cv2.resize(
        mascara.astype(np.uint8), (destino[1], destino[0]), interpolation=cv2.INTER_NEAREST
    )
    return reducida > 0


def _pintar(imagen: np.ndarray, mascara: np.ndarray, color: tuple[int, int, int], opacidad: float) -> None:
    if np.any(mascara):
        imagen[mascara] = (
            imagen[mascara].astype(np.float32) * (1.0 - opacidad)
            + np.asarray(color, dtype=np.float32) * opacidad
        ).astype(np.uint8)
