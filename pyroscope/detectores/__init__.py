"""Detectores semánticos de superficie disponibles para el pipeline."""

from .registro import (
    DETECTORES_SUPERFICIE,
    DetectorSuperficie,
    listar_detectores_superficie,
    obtener_detector_superficie,
)
from .kmeans import clasificar_pixeles_area_afectada
from .fusion import clasificar_fusion_ponderada
from .swir_histeresis import clasificar_pixeles_area_afectada_swir

__all__ = [
    "DETECTORES_SUPERFICIE",
    "DetectorSuperficie",
    "clasificar_pixeles_area_afectada",
    "clasificar_pixeles_area_afectada_swir",
    "clasificar_fusion_ponderada",
    "listar_detectores_superficie",
    "obtener_detector_superficie",
]
