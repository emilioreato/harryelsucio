"""Detector alternativo por contraste SWIR, umbral doble e histéresis."""

from __future__ import annotations

import cv2
import numpy as np

from ..agua import detectar_agua_probable
from ..caracteristicas import extraer_caracteristicas_pareja
from ..humo import detectar_humo_probable
from ..imagenes import validar_par_alineado
from ..modelos_segmentacion import ResultadoClasificacionSemantica
from ..ontologia import ClaseSemantica
from ..progreso import ProgresoSegmentacion, informar_progreso as _informar_progreso


def clasificar_pixeles_area_afectada_swir(
    true_color: np.ndarray,
    swir: np.ndarray,
    *,
    sensibilidad: int = 5,
    umbrales_percentil: dict[str, float | None] | None = None,
    pesos_humo: dict[str, float] | None = None,
    umbral_humo: float = 0.55,
    umbrales_agua: dict[str, float] | None = None,
    on_progress: ProgresoSegmentacion | None = None,
) -> ResultadoClasificacionSemantica:
    """Propone superficie afectada con contraste cromático SWIR e histéresis.

    El umbral alto localiza semillas con una señal rojiza SWIR marcada; el
    umbral bajo permite crecer desde esas semillas por píxeles contiguos que
    conservan evidencia cromática moderada. True Color aporta el verdor y la
    oscuridad visible; ambas vistas se combinan para vetar agua. La máscara
    principal aparta el humo y en paralelo conserva hipótesis bajo esa capa.
    """
    validar_par_alineado(true_color, swir)
    if not 1 <= sensibilidad <= 10:
        raise ValueError("La sensibilidad debe estar entre 1 y 10.")
    ajustes_umbral = umbrales_percentil or {}
    nombres_umbral = {
        "seed_red",
        "grow_red",
        "seed_red_green",
        "grow_red_green",
        "vegetation_max",
    }
    if set(ajustes_umbral) - nombres_umbral:
        raise ValueError("Se recibió un percentil SWIR no reconocido.")
    rangos_percentiles = {
        "seed_red": (0.80, 0.9999),
        "grow_red": (0.50, 0.98),
        "seed_red_green": (0.40, 0.99),
        "grow_red_green": (0.30, 0.98),
        "vegetation_max": (0.50, 1.0),
    }
    for nombre, valor in ajustes_umbral.items():
        if valor is None:
            continue
        minimo, maximo = rangos_percentiles[nombre]
        if not np.isfinite(valor) or not minimo <= valor <= maximo:
            raise ValueError(
                f"El percentil SWIR '{nombre}' debe estar entre {minimo} y {maximo}."
            )

    _informar_progreso(on_progress, "Buscando zonas con posible humo", 12)
    humo = detectar_humo_probable(
        true_color,
        swir,
        pesos_confianza=pesos_humo,
        umbral_confianza=umbral_humo,
    )
    mascara_humo = humo.mascara_probable
    alto, ancho = true_color.shape[:2]
    _informar_progreso(on_progress, "Midiendo contraste SWIR y contexto visible", 35)
    caracteristicas = extraer_caracteristicas_pareja(true_color, swir)
    rojo_swir = caracteristicas[:, :, 0]
    rojo_verde_swir = caracteristicas[:, :, 6]
    verde_visible = caracteristicas[:, :, 2]
    despejado = ~mascara_humo

    if not np.any(despejado):
        clases = np.zeros((alto, ancho), dtype=np.uint8)
        clases[mascara_humo] = ClaseSemantica.HUMO_PROBABLE
        return ResultadoClasificacionSemantica(
            mascara_candidata=np.zeros((alto, ancho), dtype=bool),
            mascara_candidata_bajo_humo=np.zeros((alto, ancho), dtype=bool),
            mascara_agua=np.zeros((alto, ancho), dtype=bool),
            mascara_humo=mascara_humo,
            confianza_humo=humo.confianza,
            clase_por_pixel=clases,
            centros=np.empty((0, caracteristicas.shape[2]), dtype=np.float32),
            clases_seleccionadas=(),
            puntuaciones_clase=np.empty((0,), dtype=np.float32),
        )

    # Los percentiles por escena toleran estiramientos distintos de la
    # composición. La sensibilidad baja los dos umbrales sin alterar la firma.
    cuantiles = rojo_swir[despejado]
    percentiles = {
        "seed_red": 0.994 - (sensibilidad - 1) * 0.006,
        "grow_red": 0.94 - (sensibilidad - 1) * 0.010,
        "seed_red_green": 0.82 - (sensibilidad - 1) * 0.005,
        "grow_red_green": 0.68 - (sensibilidad - 1) * 0.012,
        "vegetation_max": 0.90,
    }
    percentiles.update({k: v for k, v in ajustes_umbral.items() if v is not None})
    if percentiles["grow_red"] > percentiles["seed_red"]:
        raise ValueError("El percentil de crecimiento SWIR debe ser menor o igual al de semilla.")
    if percentiles["grow_red_green"] > percentiles["seed_red_green"]:
        raise ValueError("El percentil rojo/verde de crecimiento debe ser menor o igual al de semilla.")
    umbral_semilla = float(np.quantile(cuantiles, percentiles["seed_red"]))
    umbral_crecimiento = float(np.quantile(cuantiles, percentiles["grow_red"]))
    umbral_rg_semilla = float(
        np.quantile(rojo_verde_swir[despejado], percentiles["seed_red_green"])
    )
    umbral_rg_crecimiento = float(
        np.quantile(rojo_verde_swir[despejado], percentiles["grow_red_green"])
    )
    limite_vegetacion = float(
        np.quantile(verde_visible[despejado], percentiles["vegetation_max"])
    )

    # Evita que los umbrales degeneren si la escena tiene un histograma plano.
    umbral_crecimiento = min(umbral_crecimiento, umbral_semilla)
    evidencia_semilla = (
        (rojo_swir >= umbral_semilla)
        & (rojo_verde_swir >= umbral_rg_semilla)
        & (verde_visible <= limite_vegetacion)
    )
    evidencia_crecimiento = (
        (rojo_swir >= umbral_crecimiento)
        & (rojo_verde_swir >= umbral_rg_crecimiento)
        & (verde_visible <= limite_vegetacion)
    )
    mascara_semillas = evidencia_semilla & despejado
    mascara_crecimiento = evidencia_crecimiento & despejado

    agua = detectar_agua_probable(
        caracteristicas, mascara_humo, umbrales_percentil=umbrales_agua
    )
    mascara_semillas &= ~agua
    mascara_crecimiento &= ~agua

    cantidad, etiquetas = cv2.connectedComponents(
        mascara_crecimiento.astype(np.uint8), connectivity=8
    )
    _informar_progreso(on_progress, "Creciendo candidatos SWIR desde semillas", 68)
    clases_con_semilla = np.unique(etiquetas[mascara_semillas])
    clases_con_semilla = clases_con_semilla[clases_con_semilla != 0]
    candidata = np.isin(etiquetas, clases_con_semilla) if cantidad > 1 else np.zeros_like(despejado)
    candidata &= ~mascara_humo & ~agua
    candidata_u8 = cv2.morphologyEx(
        candidata.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8)
    )
    candidata_u8[mascara_humo | agua] = 0
    candidata = candidata_u8 > 0

    # Evaluar en paralelo la misma firma SWIR dentro del humo. Los cuantiles
    # siguen aprendidos del terreno despejado; el resultado es solo una
    # hipótesis subyacente y nunca se suma al área visible.
    semillas_subyacentes = evidencia_semilla & ~agua
    crecimiento_subyacente = evidencia_crecimiento & ~agua
    cantidad_subyacente, etiquetas_subyacentes = cv2.connectedComponents(
        crecimiento_subyacente.astype(np.uint8), connectivity=8
    )
    clases_con_semilla_subyacente = np.unique(
        etiquetas_subyacentes[semillas_subyacentes]
    )
    clases_con_semilla_subyacente = clases_con_semilla_subyacente[
        clases_con_semilla_subyacente != 0
    ]
    if cantidad_subyacente > 1 and clases_con_semilla_subyacente.size:
        candidata_subyacente = np.isin(
            etiquetas_subyacentes, clases_con_semilla_subyacente
        )
        candidata_subyacente = cv2.morphologyEx(
            candidata_subyacente.astype(np.uint8),
            cv2.MORPH_CLOSE,
            np.ones((5, 5), dtype=np.uint8),
        ) > 0
        candidata_bajo_humo = candidata_subyacente & mascara_humo
    else:
        candidata_bajo_humo = np.zeros((alto, ancho), dtype=bool)

    clases = np.full((alto, ancho), ClaseSemantica.INDETERMINADO, dtype=np.uint8)
    clases[agua] = ClaseSemantica.AGUA_POSIBLE
    clases[candidata] = ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
    clases[mascara_humo] = ClaseSemantica.HUMO_PROBABLE

    return ResultadoClasificacionSemantica(
        mascara_candidata=candidata,
        mascara_candidata_bajo_humo=candidata_bajo_humo,
        mascara_agua=agua,
        mascara_humo=mascara_humo,
        confianza_humo=humo.confianza,
        clase_por_pixel=clases,
        centros=np.empty((0, caracteristicas.shape[2]), dtype=np.float32),
        # V2 no usa IDs de clúster; los umbrales se guardan en puntuaciones.
        clases_seleccionadas=(),
        puntuaciones_clase=np.asarray(
            [umbral_semilla, umbral_crecimiento], dtype=np.float32
        ),
    )
