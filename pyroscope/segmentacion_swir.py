"""Compatibilidad con la ruta previa del detector SWIR.

El código actual vive en :mod:`pyroscope.detectores.swir_histeresis`.
"""

from .detectores.swir_histeresis import clasificar_pixeles_area_afectada_swir

__all__ = ["clasificar_pixeles_area_afectada_swir"]
