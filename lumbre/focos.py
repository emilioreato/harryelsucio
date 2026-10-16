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


DISTANCIA_MAXIMA_SUPERFICIE_FOCO_PX = 8


@dataclass(frozen=True)
class ResultadoFocos:
    """Máscara y evidencia visual relativa, separadas de la superficie afectada."""

    mascara: np.ndarray
    contraste_local: np.ndarray
    puntuacion_visual: np.ndarray
    componentes: int
    mascara_rgb_swir: np.ndarray | None = None
    mascara_swir_contextual: np.ndarray | None = None
    componentes_rgb_swir: int = 0
    componentes_swir_contextual: int = 0
    mascara_wildfires: np.ndarray | None = None


def detectar_focos_wildfires(wildfires: np.ndarray) -> ResultadoFocos:
    """Extrae las marcas cálidas brillantes de la composición Wildfires.

    No reclasifica el terreno ni veta humo: conserva la señal ya representada
    en Wildfires. Es una extracción de colores renderizados, no temperatura.
    """
    if wildfires.ndim != 3 or wildfires.shape[2] != 3 or wildfires.dtype != np.uint8:
        raise ValueError("Wildfires debe ser una imagen RGB de 8 bits.")
    hsv = cv2.cvtColor(wildfires, cv2.COLOR_RGB2HSV)
    hue, saturacion, valor = cv2.split(hsv)
    rojo = wildfires[:, :, 0].astype(np.int16)
    azul = wildfires[:, :, 2].astype(np.int16)
    marcas = (hue <= 35) & (saturacion >= 120) & (valor >= 230) & (rojo - azul >= 90)
    cantidad, etiquetas, estadisticas, _ = cv2.connectedComponentsWithStats(
        marcas.astype(np.uint8), 8
    )
    # Conservar el borde cálido conectado a una marca intensa; una parcela
    # beige clara sin ese núcleo no basta para generar un foco.
    nucleos = marcas & ((saturacion >= 170) | ((hue <= 10) & (saturacion >= 150)))
    apoyo = np.bincount(etiquetas[nucleos], minlength=cantidad)
    conservar = (estadisticas[:, cv2.CC_STAT_AREA] >= 3) & (apoyo >= 3)
    conservar[0] = False
    mascara = conservar[etiquetas]
    vacia = np.zeros_like(mascara)
    return ResultadoFocos(
        mascara=mascara,
        contraste_local=np.zeros(mascara.shape, dtype=np.float32),
        puntuacion_visual=mascara.astype(np.float32),
        componentes=int(np.count_nonzero(conservar)),
        mascara_rgb_swir=vacia,
        mascara_swir_contextual=vacia.copy(),
        mascara_wildfires=mascara,
    )


def detectar_focos_visuales(
    true_color: np.ndarray,
    swir: np.ndarray,
    resultado: ResultadoAreaAfectada,
    *,
    contraste_minimo: float = 14.0,
    area_minima_px: int = 3,
    contraste_swir_contextual_minimo: float = 40.0,
    area_maxima_swir_contextual_px: int = 100,
) -> ResultadoFocos:
    """Devuelve candidatos estrictos RGB+SWIR y una señal SWIR contextual.

    La coincidencia cálida en ambas composiciones sigue la lógica conservadora
    documentada en `algoritmos_segmentacion_fuego_humo_agua.md`. Por separado,
    se conservan anomalías cálidas SWIR pequeñas junto al borde del humo y
    próximas a la superficie afectada candidata. Ambas señales usan colores
    renderizados: sus umbrales son valores iniciales para revisar, no magnitudes
    físicas. Ningún candidato se conserva a más de ocho píxeles de esa máscara.
    """
    validar_par_alineado(true_color, swir)
    if resultado.mascara.shape != true_color.shape[:2]:
        raise ValueError("Las imágenes y el resultado deben compartir la misma rejilla.")
    if (
        contraste_minimo < 0
        or contraste_swir_contextual_minimo < 0
        or area_minima_px < 1
        or area_maxima_swir_contextual_px < area_minima_px
    ):
        raise ValueError("Los contrastes y el rango de área de los candidatos no son válidos.")

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
    superficie_final = np.asarray(resultado.mascara, dtype=bool)
    if np.any(superficie_final):
        distancia_superficie = cv2.distanceTransform(
            (~superficie_final).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE
        )
        cerca_de_superficie = distancia_superficie <= DISTANCIA_MAXIMA_SUPERFICIE_FOCO_PX
    else:
        distancia_superficie = None
        cerca_de_superficie = np.zeros_like(superficie_final)
    mascara_estricta = calido_rgb & calido_swir & (contraste >= contraste_minimo)
    mascara_estricta &= ~agua & ~resultado.mascara_humo

    binaria = mascara_estricta.astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel)
    binaria &= cerca_de_superficie.astype(np.uint8)
    cantidad, etiquetas, estadisticas, _ = cv2.connectedComponentsWithStats(binaria, 8)
    limpia_estricta = np.zeros_like(binaria, dtype=bool)
    componentes_estrictos = 0
    for etiqueta in range(1, cantidad):
        if estadisticas[etiqueta, cv2.CC_STAT_AREA] >= area_minima_px:
            limpia_estricta[etiquetas == etiqueta] = True
            componentes_estrictos += 1

    # La rama SWIR de contexto es evidencia de menor confianza. Solo busca
    # anomalías cálidas pequeñas junto al borde del humo, dentro de la superficie
    # clasificada y a ocho píxeles como máximo de la máscara final afectada; el
    # núcleo de humo, el agua y la coincidencia RGB+SWIR se excluyen. Se entrega
    # separada de la señal estricta.
    rojo_swir = swir[:, :, 0].astype(np.float32)
    fondo_rojo_swir = cv2.GaussianBlur(rojo_swir, (lado, lado), 0)
    contraste_rojo_swir = np.maximum(rojo_swir - fondo_rojo_swir, 0.0)
    superficie = np.asarray(
        getattr(resultado, "mascara_clasificada", resultado.mascara), dtype=bool
    )
    humo = np.asarray(resultado.mascara_humo, dtype=bool)
    kernel_borde_humo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    cerca_del_humo = cv2.dilate(humo.astype(np.uint8), kernel_borde_humo, iterations=1) > 0
    mascara_contextual = (
        calido_swir
        & (contraste_rojo_swir >= contraste_swir_contextual_minimo)
        & superficie
        & cerca_del_humo
        & cerca_de_superficie
        & ~humo
        & ~agua
        & ~limpia_estricta
    )
    cantidad_ctx, etiquetas_ctx, estadisticas_ctx, _ = cv2.connectedComponentsWithStats(
        mascara_contextual.astype(np.uint8), 8
    )
    limpia_contextual = np.zeros_like(mascara_contextual)
    componentes_contextuales = 0
    for etiqueta in range(1, cantidad_ctx):
        area = estadisticas_ctx[etiqueta, cv2.CC_STAT_AREA]
        if area_minima_px <= area <= area_maxima_swir_contextual_px:
            limpia_contextual[etiquetas_ctx == etiqueta] = True
            componentes_contextuales += 1

    limpia = limpia_estricta | limpia_contextual
    cantidad_total, _, _, _ = cv2.connectedComponentsWithStats(limpia.astype(np.uint8), 8)
    componentes = cantidad_total - 1

    puntuacion = np.clip(contraste / 64.0, 0.0, 1.0).astype(np.float32)
    puntuacion[~limpia] = 0.0
    return ResultadoFocos(
        limpia,
        contraste.astype(np.float32),
        puntuacion,
        componentes,
        limpia_estricta,
        limpia_contextual,
        componentes_estrictos,
        componentes_contextuales,
    )


def crear_superposicion_focos(imagen_rgb: np.ndarray, focos: ResultadoFocos) -> np.ndarray:
    """Resalta candidatos en amarillo eléctrico con un halo magenta fino."""
    mascara = focos.mascara.astype(np.uint8)
    if imagen_rgb.shape[:2] != mascara.shape:
        raise ValueError("La imagen y los focos deben tener las mismas dimensiones.")
    salida = imagen_rgb.copy()
    if not np.any(mascara):
        return salida

    mascara_estricta = (
        focos.mascara_rgb_swir.astype(bool)
        if focos.mascara_rgb_swir is not None
        else focos.mascara.astype(bool)
    )
    if focos.mascara_wildfires is not None:
        mascara_estricta = focos.mascara_wildfires
    mascara_contextual = (
        focos.mascara_swir_contextual.astype(bool)
        if focos.mascara_swir_contextual is not None
        else np.zeros_like(focos.mascara, dtype=bool)
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    halo = cv2.dilate(mascara, kernel, iterations=1).astype(bool) & ~focos.mascara
    salida = superponer_mascara(salida, halo, color=(255, 30, 220), opacidad=0.7)
    salida = superponer_mascara(salida, mascara_contextual, color=(255, 145, 35), opacidad=0.90)
    salida = superponer_mascara(salida, mascara_estricta, color=(255, 244, 0), opacidad=0.92)
    contornos, _ = cv2.findContours(mascara * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(salida, contornos, -1, (255, 255, 255), 1)
    return salida
