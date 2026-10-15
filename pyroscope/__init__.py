"""API de análisis satelital de incendios y superficie afectada."""

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
from .focos import ResultadoFocos, crear_superposicion_focos, detectar_focos_visuales
from .ontologia import ClaseSemantica, ETIQUETAS_CLASE
from .segmentacion_swir import clasificar_pixeles_area_afectada_swir
from .visualizacion import crear_superposicion, crear_vista_clasificacion, superponer_mascara
from .detectores import (
    DETECTORES_SUPERFICIE,
    DetectorSuperficie,
    listar_detectores_superficie,
    obtener_detector_superficie,
)

__all__ = [
    "ResultadoAreaAfectada",
    "ResultadoClasificacionSemantica",
    "ResultadoRegionesEspaciales",
    "ResultadoHumo",
    "ResultadoFocos",
    "DetectorSuperficie",
    "DETECTORES_SUPERFICIE",
    "ClaseSemantica",
    "ETIQUETAS_CLASE",
    "CapaImagen",
    "SistemaCoordenadasImagen",
    "abrir_rgb",
    "clasificar_pixeles_area_afectada",
    "clasificar_pixeles_area_afectada_swir",
    "crear_superposicion",
    "crear_superposicion_focos",
    "crear_vista_clasificacion",
    "detectar_humo_probable",
    "detectar_focos_visuales",
    "listar_detectores_superficie",
    "obtener_detector_superficie",
    "reducir_par_alineado",
    "segmentar_regiones_espaciales",
    "segmentar_superficie_afectada",
    "superponer_mascara",
    "validar_par_alineado",
]
