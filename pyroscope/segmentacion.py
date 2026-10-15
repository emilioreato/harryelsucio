"""Orquestación de clasificación semántica y formación de regiones."""

from __future__ import annotations

from dataclasses import replace
import cv2
import numpy as np

from .coordenadas import SistemaCoordenadasImagen
from .detectores.kmeans import clasificar_pixeles_area_afectada
from .detectores.registro import obtener_detector_superficie
from .detectores.swir_histeresis import clasificar_pixeles_area_afectada_swir
from .geometria_segmentacion import segmentar_regiones_espaciales
from .imagenes import validar_par_alineado
from .modelos_segmentacion import (
    ResultadoAreaAfectada,
    ResultadoClasificacionSemantica,
    ResultadoRegionesEspaciales,
)
from .ontologia import ClaseSemantica
from .progreso import ProgresoSegmentacion, informar_progreso


def _detectar_rojo_swir(swir: np.ndarray, area_minima_pct: float) -> np.ndarray:
    """Marca componentes rojos SWIR que superen el tamaño mínimo elegido."""
    if not np.isfinite(area_minima_pct) or not 0 <= area_minima_pct <= 10:
        raise ValueError("El área mínima debe estar entre 0 y 10 por ciento.")
    hsv = cv2.cvtColor(swir, cv2.COLOR_RGB2HSV)
    tono, saturacion, valor = cv2.split(hsv)
    roja = (
        ((tono <= 18) | (tono >= 171))
        & (saturacion >= 48)
        & (valor >= 24)
    )
    roja = cv2.morphologyEx(
        roja.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), dtype=np.uint8)
    )
    minimo_pixeles = max(16, round(roja.size * area_minima_pct / 100.0))
    cantidad, etiquetas, estadisticas, _ = cv2.connectedComponentsWithStats(
        roja, connectivity=8
    )
    aceptada = np.zeros(roja.shape, dtype=bool)
    for etiqueta in range(1, cantidad):
        if estadisticas[etiqueta, cv2.CC_STAT_AREA] >= minimo_pixeles:
            aceptada |= etiquetas == etiqueta
    return aceptada


def segmentar_superficie_afectada(
    true_color: np.ndarray,
    swir: np.ndarray,
    *,
    numero_clases: int = 7,
    sensibilidad: int = 5,
    area_minima_pct: float = 0.04,
    distancia_maxima_pct: float = 10.0,
    sistema_coordenadas: SistemaCoordenadasImagen | None = None,
    semilla: int = 42,
    on_progress: ProgresoSegmentacion | None = None,
    metodo: str = "swir_histeresis",
    conservar_regiones_separadas: bool = False,
    ajustes_avanzados: dict[str, object] | None = None,
) -> ResultadoAreaAfectada:
    """Ejecuta un detector registrado y la etapa espacial común.

    Los detectores solo clasifican evidencia por píxel. El filtrado espacial y
    la conversión al contrato de salida se mantienen iguales para todos.
    """
    validar_par_alineado(true_color, swir)
    alto, ancho = true_color.shape[:2]
    if sistema_coordenadas is None:
        sistema_coordenadas = SistemaCoordenadasImagen(ancho_px=ancho, alto_px=alto)
    elif (sistema_coordenadas.ancho_px, sistema_coordenadas.alto_px) != (ancho, alto):
        raise ValueError("La rejilla de coordenadas debe coincidir con la imagen analizada.")

    detector = obtener_detector_superficie(metodo)
    avanzado = ajustes_avanzados or {}
    informar_progreso(on_progress, "Pareja alineada; iniciando clasificación", 5)
    opciones_detector: dict[str, object] = {
        "sensibilidad": sensibilidad,
        "on_progress": on_progress,
        "pesos_humo": avanzado.get("smoke_weights"),
        "umbral_humo": avanzado.get("smoke_threshold", 0.55),
        "umbrales_agua": avanzado.get("water_thresholds"),
    }
    if detector.usa_numero_clases:
        opciones_detector.update(numero_clases=numero_clases, semilla=semilla)
    if detector.id in ("kmeans", "fusion_ponderada"):
        opciones_detector["pesos_kmeans"] = avanzado.get("kmeans_weights")
        if detector.id == "kmeans":
            opciones_detector["pesos_score"] = opciones_detector.pop("pesos_kmeans")
    if detector.id in ("swir_histeresis", "fusion_ponderada", "contextual_hibrida"):
        opciones_detector["umbrales_swir"] = avanzado.get("swir_thresholds")
        if detector.id in ("swir_histeresis", "contextual_hibrida"):
            opciones_detector["umbrales_percentil"] = opciones_detector.pop("umbrales_swir")
    if detector.id == "fusion_ponderada":
        opciones_detector.update(
            peso_kmeans=avanzado.get("fusion_kmeans_weight", 0.5),
            peso_swir=avanzado.get("fusion_swir_weight", 0.5),
            umbral_voto=avanzado.get("fusion_threshold", 0.55),
        )

    clasificacion = detector.clasificar(true_color, swir, **opciones_detector)
    diagnosticos = None
    estimacion = None
    es_contextual = detector.id == "contextual_hibrida"
    if es_contextual:
        from .caracteristicas import extraer_caracteristicas_pareja
        from .evidencia_contextual import evidencia_desde_v2
        from .regiones_contextuales import segmentar_contextual
        caracteristicas = clasificacion.caracteristicas_comunes
        if caracteristicas is None:
            caracteristicas = extraer_caracteristicas_pareja(true_color, swir)
        score = evidencia_desde_v2(clasificacion, caracteristicas)
        informar_progreso(on_progress, "Organizando evidencia con SLIC y RAG", 75)
        contexto = segmentar_contextual(
            true_color, swir, clasificacion.mascara_candidata,
            clasificacion.mascara_agua, clasificacion.mascara_humo,
            evidencia=score, caracteristicas=caracteristicas,
        )
        diagnosticos = contexto.diagnosticos
        clasificacion = replace(clasificacion, mascara_candidata=contexto.mascara)

    # Una señal roja SWIR no se elimina porque True Color detecte humo encima.
    # Se conserva en la máscara principal y se etiqueta además bajo el humo.
    mascara_roja_swir = _detectar_rojo_swir(swir, area_minima_pct)
    if np.any(mascara_roja_swir):
        mascara_agua = clasificacion.mascara_agua & ~mascara_roja_swir
        mascara_candidata = clasificacion.mascara_candidata | mascara_roja_swir
        mascara_bajo_humo = (
            clasificacion.mascara_candidata_bajo_humo
            | (mascara_roja_swir & clasificacion.mascara_humo)
        )
        clases = clasificacion.clase_por_pixel.copy()
        clases[mascara_agua] = ClaseSemantica.AGUA_POSIBLE
        clases[clasificacion.mascara_humo] = ClaseSemantica.HUMO_PROBABLE
        clases[mascara_roja_swir] = ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
        clasificacion = replace(
            clasificacion,
            mascara_candidata=mascara_candidata,
            mascara_candidata_bajo_humo=mascara_bajo_humo,
            mascara_agua=mascara_agua,
            clase_por_pixel=clases,
        )
    regiones = segmentar_regiones_espaciales(
        clasificacion,
        area_minima_pct=area_minima_pct,
        distancia_maxima_pct=distancia_maxima_pct,
        on_progress=on_progress,
        conservar_regiones_separadas=conservar_regiones_separadas or es_contextual,
        preservar_geometria=es_contextual,
        mascara_roja_swir=mascara_roja_swir,
    )
    if es_contextual:
        from .estimacion_bajo_humo import estimar_bajo_humo
        # Una firma roja superviviente permite hipótesis espectral; ausencia de
        # contraste deja solo continuidad corta o suelo desconocido.
        contradiccion = ((caracteristicas[..., 2] > .25)
                         & (caracteristicas[..., 0] < -.05)
                         & (clasificacion.confianza_humo < .7))
        estimacion = estimar_bajo_humo(
            regiones.mascara, clasificacion.mascara_humo, clasificacion.mascara_agua,
            score, contradiccion=contradiccion,
            distancia_maxima_px=max(3, min(24, round(min(alto, ancho) * .015))),
            # La firma SWIR moderada superviviente se distingue de puentes
            # puramente geométricos: puede sostener un recorrido algo mayor.
            umbral_espectral=.4,
            distancia_espectral_px=max(4, round(min(alto, ancho) * .04)),
        )
    informar_progreso(on_progress, "Análisis completado", 100)

    return ResultadoAreaAfectada(
        sistema_coordenadas=sistema_coordenadas,
        mascara=regiones.mascara,
        mascara_clasificada=clasificacion.mascara_candidata,
        mascara_candidata_bajo_humo=(
            (estimacion.mascara_candidata if estimacion is not None
             else np.zeros_like(clasificacion.mascara_candidata_bajo_humo))
            | clasificacion.mascara_candidata_bajo_humo
        ),
        mascara_humo=clasificacion.mascara_humo,
        confianza_humo=clasificacion.confianza_humo,
        clase_por_pixel=clasificacion.clase_por_pixel,
        contornos=regiones.contornos,
        proporcion=regiones.proporcion,
        pixeles_humo_excluidos=regiones.pixeles_humo_excluidos,
        centros=clasificacion.centros,
        clases_seleccionadas=clasificacion.clases_seleccionadas,
        puntuaciones_clase=clasificacion.puntuaciones_clase,
        pixeles_agua_excluidos=regiones.pixeles_agua_excluidos,
        distancia_maxima_px=regiones.distancia_maxima_px,
        componentes_remotos_descartados=regiones.componentes_remotos_descartados,
        mascara_indeterminada=(
            estimacion.mascara_indeterminada if estimacion is not None
            else clasificacion.mascara_humo & ~clasificacion.mascara_candidata_bajo_humo
        ),
        mascara_bajo_humo_espectral=(estimacion.mascara_espectral if estimacion is not None else None),
        mascara_bajo_humo_continuidad=(estimacion.mascara_continuidad if estimacion is not None else None),
        diagnosticos_contextuales=diagnosticos,
    )


__all__ = [
    "ResultadoAreaAfectada",
    "ResultadoClasificacionSemantica",
    "ResultadoRegionesEspaciales",
    "clasificar_pixeles_area_afectada",
    "clasificar_pixeles_area_afectada_swir",
    "segmentar_regiones_espaciales",
    "segmentar_superficie_afectada",
]
