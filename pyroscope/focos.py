"""Candidatos visuales a focos calientes en composiciones RGB/SWIR renderizadas.

No mide temperatura ni confirma fuego activo: trabaja con colores de pantalla,
que dependen de la composición y el estiramiento de cada imagen.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .imagenes import validar_par_alineado
from .ontologia import ClaseSemantica
from .segmentacion import ResultadoAreaAfectada
from .visualizacion import superponer_mascara


@dataclass(frozen=True)
class ResultadoFocos:
    """Máscara y evidencia visual relativa, separadas de la superficie afectada."""

    mascara: np.ndarray
    contraste_local: np.ndarray
    puntuacion_visual: np.ndarray
    componentes: int


def detectar_focos_visuales(
    true_color: np.ndarray,
    swir: np.ndarray,
    resultado: ResultadoAreaAfectada,
    *,
    contraste_minimo: float = 14.0,
    area_minima_px: int = 3,
) -> ResultadoFocos:
    """Marca píxeles cálidos de alto contraste coincidentes en RGB y SWIR.

    El color cálido en ambas vistas sigue la lógica conservadora documentada
    en `algoritmos_segmentacion_fuego_humo_agua.md`. El contraste se mide
    respecto a un fondo suavizado local. Agua posible y humo probable se vetan.
    Los umbrales son valores iniciales para revisar, no magnitudes físicas.
    """
    validar_par_alineado(true_color, swir)
    if resultado.mascara.shape != true_color.shape[:2]:
        raise ValueError("Las imágenes y el resultado deben compartir la misma rejilla.")
    if contraste_minimo < 0 or area_minima_px < 1:
        raise ValueError("El contraste mínimo no puede ser negativo y el área debe ser positiva.")

    alto, ancho = true_color.shape[:2]
    lado = max(9, min(41, (min(alto, ancho) // 24) | 1))

    def calidez(imagen: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        hsv = cv2.cvtColor(imagen, cv2.COLOR_RGB2HSV)
        rojo, verde, azul = [imagen[:, :, indice].astype(np.int16) for indice in range(3)]
        hue, saturacion, valor = cv2.split(hsv)
        color_calido = (
            ((hue <= 24) | (hue >= 170))
            & (saturacion >= 65)
            & (valor >= 80)
            & (rojo >= verde * 1.10)
            & (rojo >= azul * 1.15)
        )
        luminancia = cv2.cvtColor(imagen, cv2.COLOR_RGB2GRAY).astype(np.float32)
        fondo = cv2.GaussianBlur(luminancia, (lado, lado), 0)
        contraste = np.maximum(luminancia - fondo, 0.0)
        return color_calido, contraste

    calido_rgb, contraste_rgb = calidez(true_color)
    calido_swir, contraste_swir = calidez(swir)
    contraste = np.maximum(contraste_rgb, contraste_swir)

    agua = resultado.clase_por_pixel == ClaseSemantica.AGUA_POSIBLE
    mascara = calido_rgb & calido_swir & (contraste >= contraste_minimo)
    mascara &= ~agua & ~resultado.mascara_humo

    binaria = mascara.astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)
    cantidad, etiquetas, estadisticas, _ = cv2.connectedComponentsWithStats(binaria, 8)
    limpia = np.zeros_like(binaria, dtype=bool)
    componentes = 0
    for etiqueta in range(1, cantidad):
        if estadisticas[etiqueta, cv2.CC_STAT_AREA] >= area_minima_px:
            limpia[etiquetas == etiqueta] = True
            componentes += 1

    puntuacion = np.clip(contraste / 64.0, 0.0, 1.0).astype(np.float32)
    puntuacion[~limpia] = 0.0
    return ResultadoFocos(limpia, contraste.astype(np.float32), puntuacion, componentes)


def crear_superposicion_focos(imagen_rgb: np.ndarray, focos: ResultadoFocos) -> np.ndarray:
    """Resalta candidatos en amarillo eléctrico con un halo magenta fino."""
    mascara = focos.mascara.astype(np.uint8)
    if imagen_rgb.shape[:2] != mascara.shape:
        raise ValueError("La imagen y los focos deben tener las mismas dimensiones.")
    salida = imagen_rgb.copy()
    if not np.any(mascara):
        return salida

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    halo = cv2.dilate(mascara, kernel, iterations=1).astype(bool) & ~focos.mascara
    salida = superponer_mascara(salida, halo, color=(255, 30, 220), opacidad=0.7)
    salida = superponer_mascara(salida, focos.mascara, color=(255, 244, 0), opacidad=0.92)
    contornos, _ = cv2.findContours(mascara * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(salida, contornos, -1, (255, 255, 255), 1)
    return salida
