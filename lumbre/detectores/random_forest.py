"""Clasificador supervisado por píxel con contexto local."""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from ..imagenes import validar_par_alineado
from ..modelos_segmentacion import ResultadoClasificacionSemantica
from ..ontologia import ClaseSemantica
from ..progreso import ProgresoSegmentacion, informar_progreso


VERSION_CARACTERISTICAS = 1
NOMBRES_CARACTERISTICAS = (
    "true_red", "true_green", "true_blue",
    "swir_red", "swir_green", "swir_blue",
    "true_hue", "true_saturation", "swir_hue", "swir_saturation",
    "true_local_luminance_mean", "true_local_luminance_std",
    "swir_local_luminance_mean", "swir_local_luminance_std",
    "true_green_minus_red", "swir_green_minus_red",
)
RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
MODELO_RANDOM_FOREST = Path(
    os.environ.get(
        "LUMBRE_RF_MODEL",
        str(RAIZ_REPOSITORIO / "training" / "random_forest" / "random_forest.joblib"),
    )
).expanduser()
PIXELES_POR_LOTE = 120_000


def extraer_caracteristicas_random_forest(
    true_color: np.ndarray,
    swir: np.ndarray,
) -> np.ndarray:
    """Devuelve canales RGB, cromaticidad y textura local; no son bandas físicas."""
    validar_par_alineado(true_color, swir)
    true = true_color.astype(np.float32) / 255.0
    infrarrojo_renderizado = swir.astype(np.float32) / 255.0

    true_hsv = cv2.cvtColor(true_color, cv2.COLOR_RGB2HSV).astype(np.float32)
    swir_hsv = cv2.cvtColor(swir, cv2.COLOR_RGB2HSV).astype(np.float32)
    true_hue = true_hsv[:, :, 0] / 179.0
    true_saturation = true_hsv[:, :, 1] / 255.0
    swir_hue = swir_hsv[:, :, 0] / 179.0
    swir_saturation = swir_hsv[:, :, 1] / 255.0

    def luminancia_local(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        luminancia = (
            0.2126 * rgb[:, :, 0]
            + 0.7152 * rgb[:, :, 1]
            + 0.0722 * rgb[:, :, 2]
        ).astype(np.float32)
        media = cv2.boxFilter(
            luminancia, cv2.CV_32F, (9, 9), normalize=True,
            borderType=cv2.BORDER_REFLECT,
        )
        media_cuadratica = cv2.boxFilter(
            luminancia * luminancia, cv2.CV_32F, (9, 9), normalize=True,
            borderType=cv2.BORDER_REFLECT,
        )
        desviacion = np.sqrt(np.maximum(media_cuadratica - media * media, 0.0))
        return media, desviacion

    true_media, true_textura = luminancia_local(true)
    swir_media, swir_textura = luminancia_local(infrarrojo_renderizado)
    return np.stack(
        (
            true[:, :, 0], true[:, :, 1], true[:, :, 2],
            infrarrojo_renderizado[:, :, 0],
            infrarrojo_renderizado[:, :, 1],
            infrarrojo_renderizado[:, :, 2],
            true_hue, true_saturation, swir_hue, swir_saturation,
            true_media, true_textura, swir_media, swir_textura,
            true[:, :, 1] - true[:, :, 0],
            infrarrojo_renderizado[:, :, 1] - infrarrojo_renderizado[:, :, 0],
        ),
        axis=-1,
    ).astype(np.float32, copy=False)


def cargar_modelo_random_forest() -> dict[str, object]:
    """Carga y valida el modelo entrenado localmente para Lumbre."""
    if not MODELO_RANDOM_FOREST.is_file():
        raise ValueError(
            "No hay un modelo Random Forest entrenado. Sigue las instrucciones de "
            "'training/random_forest/README.md' para crear máscaras etiquetadas y entrenarlo."
        )
    paquete = joblib.load(MODELO_RANDOM_FOREST)
    if not isinstance(paquete, dict) or paquete.get("feature_version") != VERSION_CARACTERISTICAS:
        raise ValueError(
            "El modelo Random Forest no es compatible con esta versión de características; vuelve a entrenarlo."
        )
    modelo = paquete.get("model")
    if not isinstance(modelo, RandomForestClassifier):
        raise ValueError("El archivo Random Forest no contiene un clasificador compatible.")
    if tuple(paquete.get("feature_names", ())) != NOMBRES_CARACTERISTICAS:
        raise ValueError("El orden de características del modelo no coincide; vuelve a entrenarlo.")
    if int(getattr(modelo, "n_features_in_", -1)) != len(NOMBRES_CARACTERISTICAS):
        raise ValueError("El número de características del modelo no coincide; vuelve a entrenarlo.")
    clases = {int(clase) for clase in modelo.classes_}
    if not clases or 0 in clases or not clases <= set(range(1, 8)):
        raise ValueError("El modelo contiene IDs de clase incompatibles; vuelve a entrenarlo.")
    return paquete


def clasificar_random_forest(
    true_color: np.ndarray,
    swir: np.ndarray,
    *,
    on_progress: ProgresoSegmentacion | None = None,
) -> ResultadoClasificacionSemantica:
    """Predice clases supervisadas; solo el área quemada entra en su máscara."""
    validar_par_alineado(true_color, swir)
    informar_progreso(on_progress, "Cargando el modelo Random Forest", 10)
    paquete = cargar_modelo_random_forest()
    modelo = paquete["model"]

    informar_progreso(on_progress, "Calculando color y contexto local", 25)
    caracteristicas = extraer_caracteristicas_random_forest(true_color, swir)
    alto, ancho, cantidad_caracteristicas = caracteristicas.shape
    plano = caracteristicas.reshape(-1, cantidad_caracteristicas)
    clases_modelo = np.asarray(modelo.classes_, dtype=np.uint8)
    predicciones = np.empty(plano.shape[0], dtype=np.uint8)
    confianza_humo = np.zeros(plano.shape[0], dtype=np.float32)
    columna_humo = (
        int(np.flatnonzero(clases_modelo == ClaseSemantica.HUMO_PROBABLE)[0])
        if np.any(clases_modelo == ClaseSemantica.HUMO_PROBABLE)
        else None
    )

    total_lotes = max(1, (plano.shape[0] + PIXELES_POR_LOTE - 1) // PIXELES_POR_LOTE)
    for lote, inicio in enumerate(range(0, plano.shape[0], PIXELES_POR_LOTE), start=1):
        fin = min(inicio + PIXELES_POR_LOTE, plano.shape[0])
        probabilidades = modelo.predict_proba(plano[inicio:fin])
        indices = np.argmax(probabilidades, axis=1)
        predicciones[inicio:fin] = clases_modelo[indices]
        if columna_humo is not None:
            confianza_humo[inicio:fin] = probabilidades[:, columna_humo]
        informar_progreso(
            on_progress,
            "Clasificando celdas con Random Forest",
            25 + round(55 * lote / total_lotes),
        )

    clase_por_pixel = predicciones.reshape(alto, ancho)
    mascara_agua = clase_por_pixel == ClaseSemantica.AGUA_POSIBLE
    mascara_humo = clase_por_pixel == ClaseSemantica.HUMO_PROBABLE
    mascara_candidata = clase_por_pixel == ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
    return ResultadoClasificacionSemantica(
        mascara_candidata=mascara_candidata,
        mascara_candidata_bajo_humo=np.zeros((alto, ancho), dtype=bool),
        mascara_agua=mascara_agua,
        mascara_humo=mascara_humo,
        confianza_humo=confianza_humo.reshape(alto, ancho),
        clase_por_pixel=clase_por_pixel,
        centros=np.empty((0, cantidad_caracteristicas), dtype=np.float32),
        clases_seleccionadas=tuple(int(clase) for clase in clases_modelo),
        puntuaciones_clase=np.asarray(modelo.feature_importances_, dtype=np.float32),
    )
