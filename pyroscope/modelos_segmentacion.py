"""Contratos de datos compartidos por detectores y etapas espaciales."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .coordenadas import SistemaCoordenadasImagen


@dataclass(frozen=True)
class ResultadoClasificacionSemantica:
    """Evidencia por píxel antes de aplicar reglas de forma y proximidad."""

    mascara_candidata: np.ndarray
    # Hipótesis de superficie afectada que coincide con la oclusión por humo.
    # Se mantiene separada y no contribuye al área/perímetro observados.
    mascara_candidata_bajo_humo: np.ndarray
    mascara_agua: np.ndarray
    mascara_humo: np.ndarray
    confianza_humo: np.ndarray
    clase_por_pixel: np.ndarray
    centros: np.ndarray
    clases_seleccionadas: tuple[int, ...]
    puntuaciones_clase: np.ndarray


@dataclass(frozen=True)
class ResultadoRegionesEspaciales:
    """Máscara final tras limpiar y agrupar los candidatos en regiones."""

    mascara: np.ndarray
    contornos: tuple[np.ndarray, ...]
    proporcion: float
    pixeles_agua_excluidos: int
    pixeles_humo_excluidos: int
    distancia_maxima_px: int
    componentes_remotos_descartados: int


@dataclass(frozen=True)
class ResultadoAreaAfectada:
    """Resultado completo de una ejecución, sobre una rejilla de imagen."""

    sistema_coordenadas: SistemaCoordenadasImagen
    mascara: np.ndarray
    mascara_clasificada: np.ndarray
    mascara_candidata_bajo_humo: np.ndarray
    mascara_humo: np.ndarray
    confianza_humo: np.ndarray
    clase_por_pixel: np.ndarray
    contornos: tuple[np.ndarray, ...]
    proporcion: float
    pixeles_humo_excluidos: int
    centros: np.ndarray
    clases_seleccionadas: tuple[int, ...]
    puntuaciones_clase: np.ndarray
    pixeles_agua_excluidos: int
    distancia_maxima_px: int
    componentes_remotos_descartados: int
