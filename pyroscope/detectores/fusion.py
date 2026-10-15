"""Combinación por voto ponderado de K-Means y contraste SWIR."""

from __future__ import annotations

import numpy as np

from ..modelos_segmentacion import ResultadoClasificacionSemantica
from ..ontologia import ClaseSemantica
from ..progreso import ProgresoSegmentacion
from .kmeans import clasificar_pixeles_area_afectada
from .swir_histeresis import clasificar_pixeles_area_afectada_swir


def clasificar_fusion_ponderada(
    true_color: np.ndarray,
    swir: np.ndarray,
    *,
    numero_clases: int = 7,
    sensibilidad: int = 5,
    semilla: int = 42,
    peso_kmeans: float = 0.5,
    peso_swir: float = 0.5,
    umbral_voto: float = 0.55,
    pesos_kmeans: dict[str, float] | None = None,
    umbrales_swir: dict[str, float | None] | None = None,
    pesos_humo: dict[str, float] | None = None,
    umbral_humo: float = 0.55,
    umbrales_agua: dict[str, float] | None = None,
    on_progress: ProgresoSegmentacion | None = None,
) -> ResultadoClasificacionSemantica:
    """Fusiona las máscaras de ambos métodos con pesos configurables.

    Cada detector aporta un voto binario por píxel. Los pesos se normalizan por
    su suma y `umbral_voto` define la fracción necesaria para aceptar el píxel.
    Esta salida es un score heurístico, no una probabilidad calibrada.
    """
    valores = np.asarray([peso_kmeans, peso_swir, umbral_voto], dtype=float)
    if not np.all(np.isfinite(valores)) or np.any(valores < 0) or np.any(valores > 1):
        raise ValueError("Los pesos y el umbral de fusión deben estar entre 0 y 1.")
    suma_pesos = peso_kmeans + peso_swir
    if suma_pesos <= 0:
        raise ValueError("Al menos uno de los pesos de algoritmo debe ser mayor que cero.")

    def adaptar_progreso(inicio: int, tramo: int):
        if on_progress is None:
            return None

        def notificar(etapa: str, porcentaje: int) -> None:
            global_pct = inicio + round(tramo * max(0, min(100, porcentaje)) / 100)
            on_progress(etapa, global_pct)

        return notificar

    clasificacion_kmeans = clasificar_pixeles_area_afectada(
        true_color,
        swir,
        numero_clases=numero_clases,
        sensibilidad=sensibilidad,
        semilla=semilla,
        pesos_score=pesos_kmeans,
        pesos_humo=pesos_humo,
        umbral_humo=umbral_humo,
        umbrales_agua=umbrales_agua,
        on_progress=adaptar_progreso(8, 36),
    )
    clasificacion_swir = clasificar_pixeles_area_afectada_swir(
        true_color,
        swir,
        sensibilidad=sensibilidad,
        umbrales_percentil=umbrales_swir,
        pesos_humo=pesos_humo,
        umbral_humo=umbral_humo,
        umbrales_agua=umbrales_agua,
        on_progress=adaptar_progreso(48, 32),
    )

    peso_k = peso_kmeans / suma_pesos
    peso_s = peso_swir / suma_pesos
    evidencia_superficie_kmeans = (
        clasificacion_kmeans.mascara_candidata
        | clasificacion_kmeans.mascara_candidata_bajo_humo
    )
    evidencia_superficie_swir = (
        clasificacion_swir.mascara_candidata
        | clasificacion_swir.mascara_candidata_bajo_humo
    )
    voto = (
        peso_k * evidencia_superficie_kmeans.astype(np.float32)
        + peso_s * evidencia_superficie_swir.astype(np.float32)
    )
    agua = clasificacion_kmeans.mascara_agua | clasificacion_swir.mascara_agua
    humo = clasificacion_kmeans.mascara_humo | clasificacion_swir.mascara_humo
    candidata = (voto >= umbral_voto) & ~agua & ~humo
    candidata_bajo_humo = (voto >= umbral_voto) & humo & ~agua

    clases = np.full(candidata.shape, ClaseSemantica.INDETERMINADO, dtype=np.uint8)
    clases[agua] = ClaseSemantica.AGUA_POSIBLE
    clases[candidata] = ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
    clases[humo] = ClaseSemantica.HUMO_PROBABLE
    if on_progress is not None:
        on_progress("Combinando votos de K-Means y SWIR", 82)

    return ResultadoClasificacionSemantica(
        mascara_candidata=candidata,
        mascara_candidata_bajo_humo=candidata_bajo_humo,
        mascara_agua=agua,
        mascara_humo=humo,
        confianza_humo=np.maximum(
            clasificacion_kmeans.confianza_humo,
            clasificacion_swir.confianza_humo,
        ),
        clase_por_pixel=clases,
        centros=clasificacion_kmeans.centros,
        clases_seleccionadas=clasificacion_kmeans.clases_seleccionadas,
        puntuaciones_clase=np.asarray(
            [peso_k, peso_s, umbral_voto], dtype=np.float32
        ),
    )
