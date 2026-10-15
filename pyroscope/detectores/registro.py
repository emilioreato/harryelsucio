"""Registro único de detectores de superficie expuestos al motor y a la web."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..modelos_segmentacion import ResultadoClasificacionSemantica
from .fusion import clasificar_fusion_ponderada
from .kmeans import clasificar_pixeles_area_afectada
from .swir_histeresis import clasificar_pixeles_area_afectada_swir


Clasificador = Callable[..., ResultadoClasificacionSemantica]


@dataclass(frozen=True)
class DetectorSuperficie:
    """Metadatos y función de clasificación de un método intercambiable."""

    id: str
    nombre: str
    descripcion: str
    usa_numero_clases: bool
    clasificar: Clasificador


DETECTORES_SUPERFICIE: tuple[DetectorSuperficie, ...] = (
    DetectorSuperficie(
        id="kmeans",
        nombre="K-Means conjunto",
        descripcion=(
            "Agrupa señales de True Color y SWIR; la puntuación posterior propone "
            "píxeles candidatos a superficie afectada."
        ),
        usa_numero_clases=True,
        clasificar=clasificar_pixeles_area_afectada,
    ),
    DetectorSuperficie(
        id="swir_histeresis",
        nombre="Contraste SWIR + histéresis (V2)",
        descripcion=(
            "Busca semillas de contraste SWIR alto y las expande por regiones "
            "contiguas; True Color aporta el verdor y ambas vistas confirman "
            "oscuridad compatible con agua."
        ),
        usa_numero_clases=False,
        clasificar=clasificar_pixeles_area_afectada_swir,
    ),
    DetectorSuperficie(
        id="fusion_ponderada",
        nombre="Fusión ponderada (K-Means + SWIR)",
        descripcion=(
            "Combina las máscaras de ambos detectores. En Herramientas de desarrollo "
            "puedes ponderar sus votos y ajustar sus scores y umbrales."
        ),
        usa_numero_clases=True,
        clasificar=clasificar_fusion_ponderada,
    ),
)

_DETECTORES_POR_ID = {detector.id: detector for detector in DETECTORES_SUPERFICIE}


def listar_detectores_superficie() -> tuple[DetectorSuperficie, ...]:
    """Devuelve los métodos en el orden de presentación de la interfaz."""
    return DETECTORES_SUPERFICIE


def obtener_detector_superficie(metodo: str) -> DetectorSuperficie:
    """Busca un detector por ID y explica los IDs válidos si no existe."""
    try:
        return _DETECTORES_POR_ID[metodo]
    except KeyError as exc:
        opciones = ", ".join(_DETECTORES_POR_ID)
        raise ValueError(
            f"Método de segmentación no reconocido: {metodo!r}. Opciones: {opciones}."
        ) from exc
