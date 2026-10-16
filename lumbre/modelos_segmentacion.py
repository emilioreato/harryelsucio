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
    caracteristicas_comunes: np.ndarray | None = None
    # La ruta contextual conserva la propuesta V2 y las fuentes nuevas por
    # separado; los detectores previos pueden dejar estos campos vacíos.
    mascara_candidata_v2: np.ndarray | None = None
    diagnosticos_evidencia: dict[str, np.ndarray] | None = None


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
    # Ampliaciones opcionales: los detectores existentes no cambian su contrato.
    mascara_indeterminada: np.ndarray | None = None
    mascara_bajo_humo_espectral: np.ndarray | None = None
    mascara_bajo_humo_continuidad: np.ndarray | None = None
    diagnosticos_contextuales: dict[str, np.ndarray] | None = None
    # Avisos no bloqueantes, por ejemplo un detector opcional que no pudo
    # cargarse y cuya ausencia no debe impedir obtener el resultado base.
    avisos: tuple[str, ...] = ()
    # Pequeños puentes/huecos con respaldo SWIR: continuidad inferida aparte.
    mascara_continuidad_superficie: np.ndarray | None = None

    @property
    def mascara_superficie_visible(self) -> np.ndarray:
        return self.mascara

    @property
    def mascara_superficie_estimada(self) -> np.ndarray:
        """Unión visual final; conserva aparte la procedencia y el área visible."""
        union = self.mascara | self.mascara_candidata_bajo_humo
        if self.mascara_continuidad_superficie is not None:
            union = union | self.mascara_continuidad_superficie
        return union
