"""Detector conjunto K-Means para señales SWIR y True Color."""

from __future__ import annotations

import cv2
import numpy as np
from sklearn.cluster import MiniBatchKMeans

from ..caracteristicas import extraer_caracteristicas_pareja
from ..humo import detectar_humo_probable
from ..imagenes import validar_par_alineado
from ..modelos_segmentacion import ResultadoClasificacionSemantica
from ..ontologia import ClaseSemantica
from ..progreso import ProgresoSegmentacion, informar_progreso as _informar_progreso


def clasificar_pixeles_area_afectada(
    true_color: np.ndarray,
    swir: np.ndarray,
    *,
    numero_clases: int = 7,
    sensibilidad: int = 5,
    semilla: int = 42,
    on_progress: ProgresoSegmentacion | None = None,
) -> ResultadoClasificacionSemantica:
    """Clasifica evidencias de área afectada usando ambas imágenes por píxel.

    Esta es la etapa semántica: combina señales SWIR y True Color para proponer
    píxeles candidatos y vetar posibles píxeles de agua. No forma todavía
    regiones, no elimina manchas lejanas y no declara clases de fuego activo.
    """
    validar_par_alineado(true_color, swir)
    if not 2 <= numero_clases <= 12:
        raise ValueError("El número de clases debe estar entre 2 y 12.")
    if not 1 <= sensibilidad <= 10:
        raise ValueError("La sensibilidad debe estar entre 1 y 10.")

    # La oclusión atmosférica se modela primero. Los píxeles cubiertos por humo
    # no enseñan al agrupador cómo se ve una superficie despejada.
    _informar_progreso(on_progress, "Buscando zonas con posible humo", 12)
    humo = detectar_humo_probable(true_color, swir)
    mascara_humo = humo.mascara_probable
    _informar_progreso(on_progress, "Extrayendo señales de color", 25)
    features = extraer_caracteristicas_pareja(true_color, swir)
    alto, ancho, numero_caracteristicas = features.shape
    plano = features.reshape(-1, numero_caracteristicas)

    rng = np.random.default_rng(semilla)
    indices_despejados = np.flatnonzero(~mascara_humo.reshape(-1))
    if indices_despejados.size < 2:
        clases = np.zeros((alto, ancho), dtype=np.uint8)
        clases[mascara_humo] = ClaseSemantica.HUMO_PROBABLE
        return ResultadoClasificacionSemantica(
            mascara_candidata=np.zeros((alto, ancho), dtype=bool),
            mascara_agua=np.zeros((alto, ancho), dtype=bool),
            mascara_humo=mascara_humo,
            confianza_humo=humo.confianza,
            clase_por_pixel=clases,
            centros=np.empty((0, numero_caracteristicas), dtype=np.float32),
            clases_seleccionadas=(),
            puntuaciones_clase=np.empty((0,), dtype=np.float32),
        )

    muestra_n = min(120_000, indices_despejados.size)
    indices = rng.choice(indices_despejados, size=muestra_n, replace=False)
    muestra = plano[indices]

    medianas = np.median(muestra, axis=0).astype(np.float32)
    q25, q75 = np.quantile(muestra, [0.25, 0.75], axis=0)
    escalas = np.maximum((q75 - q25) / 1.349, 0.025).astype(np.float32)
    muestra_z = np.clip((muestra - medianas) / escalas, -6.0, 6.0).astype(np.float32)

    modelo = MiniBatchKMeans(
        n_clusters=min(numero_clases, muestra_n),
        random_state=semilla,
        n_init=3,
        max_iter=80,
        batch_size=4096,
        reassignment_ratio=0.01,
    )
    # El espacio conjunto base conserva las seis señales originales. Las dos
    # señales adicionales ajustan la decisión semántica y el veto de agua.
    modelo.fit(muestra_z[:, :6])
    _informar_progreso(on_progress, "Agrupando patrones de color", 55)
    centros = np.zeros((modelo.n_clusters, numero_caracteristicas), dtype=np.float32)
    centros[:, :6] = modelo.cluster_centers_.astype(np.float32)
    etiquetas_muestra = modelo.predict(muestra_z[:, :6])
    for clase in range(modelo.n_clusters):
        pixeles_clase = muestra_z[etiquetas_muestra == clase, 6:]
        if pixeles_clase.size:
            centros[clase, 6:] = pixeles_clase.mean(axis=0)

    # La puntuación fusiona evidencias de ambas composiciones en cada clase.
    puntuaciones = (
        1.25 * centros[:, 0]
        + 0.18 * centros[:, 1]
        - 0.62 * centros[:, 2]
        - 0.22 * centros[:, 3]
        - 0.12 * centros[:, 4]
        + 0.10 * centros[:, 5]
        + 0.22 * centros[:, 6]
        - 0.30 * centros[:, 7]
    )

    elegibles = (centros[:, 4] > -2.0) | (
        (centros[:, 0] > 1.5) & (centros[:, 1] > 0.0)
    )
    puntuaciones_elegibles = (
        np.where(elegibles, puntuaciones, -np.inf) if np.any(elegibles) else puntuaciones
    )
    mejor = int(np.argmax(puntuaciones_elegibles))

    margen = 0.12 + (sensibilidad - 1) * 0.105
    seleccionadas = np.flatnonzero(
        elegibles & (puntuaciones >= puntuaciones[mejor] - margen)
    )
    if seleccionadas.size == 0:
        seleccionadas = np.asarray([mejor], dtype=np.int32)

    normalizado = np.clip((plano - medianas) / escalas, -6.0, 6.0).astype(np.float32)
    normalizado_3d = normalizado.reshape(alto, ancho, numero_caracteristicas)
    etiquetas = modelo.predict(normalizado[:, :6]).reshape(alto, ancho)
    _informar_progreso(on_progress, "Clasificando píxeles", 72)
    puntuacion_pixel = (
        1.25 * normalizado_3d[:, :, 0]
        + 0.18 * normalizado_3d[:, :, 1]
        - 0.62 * normalizado_3d[:, :, 2]
        - 0.22 * normalizado_3d[:, :, 3]
        - 0.12 * normalizado_3d[:, :, 4]
        + 0.10 * normalizado_3d[:, :, 5]
        + 0.22 * normalizado_3d[:, :, 6]
        - 0.30 * normalizado_3d[:, :, 7]
    )
    margen_pixel = 0.35 + (sensibilidad - 1) * 0.16
    mascara = np.isin(etiquetas, seleccionadas) & (
        puntuacion_pixel >= puntuaciones[mejor] - margen_pixel
    )

    rojizo_minimo = max(-0.55, float(np.quantile(muestra_z[:, 0], 0.40)))
    mascara &= normalizado_3d[:, :, 0] >= rojizo_minimo
    rojo_verde_minimo = max(-0.75, float(np.quantile(muestra_z[:, 6], 0.35)))
    mascara &= normalizado_3d[:, :, 6] >= rojo_verde_minimo

    # True Color aporta el contexto para reducir confusiones con agua oscura.
    muestra_cruda = plano[indices]
    luma_tc_oscura = float(np.quantile(muestra_cruda[:, 3], 0.18))
    tc_azul_umbral = max(0.04, float(np.quantile(muestra_cruda[:, 7], 0.85)))
    tc_croma_baja = float(np.quantile(muestra_cruda[:, 5], 0.20))
    swir_rg_no_rojo = float(np.quantile(muestra_cruda[:, 6], 0.70))
    visible_oscura = features[:, :, 3] <= luma_tc_oscura
    agua_azulada = visible_oscura & (features[:, :, 7] >= tc_azul_umbral)
    agua_oscura_ambigua = visible_oscura & (
        (features[:, :, 5] <= tc_croma_baja)
        | (features[:, :, 6] <= swir_rg_no_rojo)
    )
    mascara_agua = (agua_azulada | agua_oscura_ambigua) & ~mascara_humo
    mascara &= ~mascara_agua
    # Bajo humo no se aplica la regla cromática de terreno despejado. El fondo
    # queda indeterminado hasta disponer de bandas/calidad para otra política.
    mascara &= ~mascara_humo

    clases = np.full((alto, ancho), ClaseSemantica.INDETERMINADO, dtype=np.uint8)
    clases[mascara_agua] = ClaseSemantica.AGUA_POSIBLE
    clases[mascara] = ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
    clases[mascara_humo] = ClaseSemantica.HUMO_PROBABLE

    return ResultadoClasificacionSemantica(
        mascara_candidata=mascara,
        mascara_agua=mascara_agua,
        mascara_humo=mascara_humo,
        confianza_humo=humo.confianza,
        clase_por_pixel=clases,
        centros=centros,
        clases_seleccionadas=tuple(int(i) for i in seleccionadas),
        puntuaciones_clase=puntuaciones,
    )
