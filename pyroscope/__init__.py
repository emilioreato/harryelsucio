"""API inicial de PyroScope para analizar superficie afectada por incendios."""

from .imagenes import abrir_rgb, reducir_par_alineado, validar_par_alineado
from .coordenadas import CapaImagen, SistemaCoordenadasImagen
from .segmentacion import (
    ResultadoAreaAfectada,
    ResultadoClasificacionSemantica,
    ResultadoRegionesEspaciales,
    clasificar_pixeles_area_afectada,
    segmentar_regiones_espaciales,
    segmentar_superficie_afectada,
)
from .humo import ResultadoHumo, detectar_humo_probable
from .ontologia import ClaseSemantica, ETIQUETAS_CLASE
from .segmentacion_swir import clasificar_pixeles_area_afectada_swir
from .visualizacion import crear_superposicion, crear_vista_clasificacion, superponer_mascara

__all__ = [
    "ResultadoAreaAfectada",
    "ResultadoClasificacionSemantica",
    "ResultadoRegionesEspaciales",
    "ResultadoHumo",
    "ClaseSemantica",
    "ETIQUETAS_CLASE",
    "CapaImagen",
    "SistemaCoordenadasImagen",
    "abrir_rgb",
    "clasificar_pixeles_area_afectada",
    "clasificar_pixeles_area_afectada_swir",
    "crear_superposicion",
    "crear_vista_clasificacion",
    "detectar_humo_probable",
    "reducir_par_alineado",
    "segmentar_regiones_espaciales",
    "segmentar_superficie_afectada",
    "superponer_mascara",
    "validar_par_alineado",
]
