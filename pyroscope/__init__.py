"""API inicial de PyroScope para analizar superficie afectada por incendios."""

from .imagenes import abrir_rgb, reducir_par_alineado, validar_par_alineado
from .coordenadas import CapaImagen, SistemaCoordenadasImagen
from .segmentacion import ResultadoAreaAfectada, segmentar_superficie_afectada
from .visualizacion import crear_superposicion

__all__ = [
    "ResultadoAreaAfectada",
    "CapaImagen",
    "SistemaCoordenadasImagen",
    "abrir_rgb",
    "crear_superposicion",
    "reducir_par_alineado",
    "segmentar_superficie_afectada",
    "validar_par_alineado",
]
