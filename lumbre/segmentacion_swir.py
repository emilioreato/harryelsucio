"""Compatibilidad con la ruta previa del detector SWIR.

La implementación vigente forma parte del paquete de detectores de superficie.
"""

from .detectores.swir_histeresis import clasificar_pixeles_area_afectada_swir

__all__ = ["clasificar_pixeles_area_afectada_swir"]
