"""Clasificación semántica por píxel y segmentación espacial de regiones.

Las entradas son composiciones RGB renderizadas, no reflectancias Sentinel-2.
La clasificación expresa evidencias compatibles con superficie afectada; no
confirma por sí sola que un píxel esté quemado ni detecta fuego activo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np
from sklearn.cluster import MiniBatchKMeans

from .caracteristicas import extraer_caracteristicas_pareja
from .coordenadas import SistemaCoordenadasImagen
from .humo import detectar_humo_probable
from .imagenes import validar_par_alineado
from .ontologia import ClaseSemantica


ProgresoSegmentacion = Callable[[str, int], None]


def _informar_progreso(
    callback: ProgresoSegmentacion | None,
    etapa: str,
    porcentaje: int,
) -> None:
    """Notifica hitos reales del análisis sin acoplar el motor a la interfaz."""
    if callback is not None:
        callback(etapa, porcentaje)


@dataclass(frozen=True)
class ResultadoClasificacionSemantica:
    """Evidencia por píxel antes de aplicar reglas de forma y proximidad."""

    mascara_candidata: np.ndarray
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
    sistema_coordenadas: SistemaCoordenadasImagen
    mascara: np.ndarray
    mascara_clasificada: np.ndarray
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


def segmentar_regiones_espaciales(
    clasificacion: ResultadoClasificacionSemantica,
    *,
    area_minima_pct: float = 0.04,
    distancia_maxima_pct: float = 10.0,
    on_progress: ProgresoSegmentacion | None = None,
    conservar_regiones_separadas: bool = False,
) -> ResultadoRegionesEspaciales:
    """Convierte candidatos semánticos en regiones espaciales depuradas.

    Esta etapa aplica morfología, tamaño mínimo y proximidad al componente
    principal. El veto de agua se repone después de la clausura para impedir que
    esta conecte regiones a través de lagos o píxeles protegidos.
    """
    mascara = clasificacion.mascara_candidata
    mascara_agua = clasificacion.mascara_agua
    mascara_humo = clasificacion.mascara_humo
    if (
        mascara.ndim != 2
        or mascara_agua.shape != mascara.shape
        or mascara_humo.shape != mascara.shape
    ):
        raise ValueError("Las máscaras semánticas deben ser rejillas 2D del mismo tamaño.")
    if not 0 <= area_minima_pct <= 10:
        raise ValueError("El área mínima debe estar entre 0 y 10 por ciento.")
    if not 0 <= distancia_maxima_pct <= 50:
        raise ValueError("La distancia máxima debe estar entre 0 y 50 por ciento.")

    alto, ancho = mascara.shape
    _informar_progreso(on_progress, "Limpiando ruido y agrupando regiones", 82)
    mascara_u8 = mascara.astype(np.uint8) * 255
    mascara_u8 = cv2.morphologyEx(
        mascara_u8, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8)
    )
    mascara_u8 = cv2.morphologyEx(
        mascara_u8, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8)
    )
    pixeles_agua_excluidos = int(np.count_nonzero(mascara_u8[mascara_agua]))
    pixeles_humo_excluidos = int(np.count_nonzero(mascara_u8[mascara_humo]))
    mascara_u8[mascara_agua] = 0
    mascara_u8[mascara_humo] = 0

    cantidad, etiquetas_cc, stats, _ = cv2.connectedComponentsWithStats(
        mascara_u8, connectivity=8
    )
    _informar_progreso(on_progress, "Filtrando componentes alejados", 92)
    minimo_pixeles = max(16, round(alto * ancho * area_minima_pct / 100.0))
    distancia_maxima_px = round(max(alto, ancho) * distancia_maxima_pct / 100.0)
    componentes_remotos_descartados = 0

    if conservar_regiones_separadas and cantidad > 1:
        limpia = np.zeros((alto, ancho), dtype=np.uint8)
        for etiqueta in range(1, cantidad):
            if stats[etiqueta, cv2.CC_STAT_AREA] >= minimo_pixeles:
                limpia[etiquetas_cc == etiqueta] = 255
    elif cantidad > 1:
        ancla = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mascara_ancla = etiquetas_cc == ancla
        distancia_al_ancla = cv2.distanceTransform(
            (~mascara_ancla).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_5
        )
        limpia = np.zeros((alto, ancho), dtype=np.uint8)
        for etiqueta in range(1, cantidad):
            if stats[etiqueta, cv2.CC_STAT_AREA] < minimo_pixeles:
                continue
            componente = etiquetas_cc == etiqueta
            separacion = float(distancia_al_ancla[componente].min())
            if separacion > distancia_maxima_px:
                componentes_remotos_descartados += 1
                continue
            dentro_del_radio = componente & (distancia_al_ancla <= distancia_maxima_px)
            limpia[dentro_del_radio] = 255
    else:
        limpia = np.zeros((alto, ancho), dtype=np.uint8)

    contornos, _ = cv2.findContours(
        limpia, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contornos_ordenados = tuple(sorted(contornos, key=cv2.contourArea, reverse=True))
    _informar_progreso(on_progress, "Preparando el resultado visual", 98)
    resultado = limpia > 0
    return ResultadoRegionesEspaciales(
        mascara=resultado,
        contornos=contornos_ordenados,
        proporcion=float(resultado.mean()),
        pixeles_agua_excluidos=pixeles_agua_excluidos,
        pixeles_humo_excluidos=pixeles_humo_excluidos,
        distancia_maxima_px=distancia_maxima_px,
        componentes_remotos_descartados=componentes_remotos_descartados,
    )


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
    metodo: str = "kmeans",
    conservar_regiones_separadas: bool = False,
) -> ResultadoAreaAfectada:
    """Ejecuta el clasificador elegido y, después, depura las regiones."""
    validar_par_alineado(true_color, swir)
    alto, ancho = true_color.shape[:2]
    if sistema_coordenadas is None:
        sistema_coordenadas = SistemaCoordenadasImagen(ancho_px=ancho, alto_px=alto)
    elif (sistema_coordenadas.ancho_px, sistema_coordenadas.alto_px) != (ancho, alto):
        raise ValueError("La rejilla de coordenadas debe coincidir con la imagen analizada.")

    _informar_progreso(on_progress, "Pareja alineada; iniciando clasificación", 5)
    if metodo == "kmeans":
        clasificacion = clasificar_pixeles_area_afectada(
            true_color,
            swir,
            numero_clases=numero_clases,
            sensibilidad=sensibilidad,
            semilla=semilla,
            on_progress=on_progress,
        )
    elif metodo == "swir_histeresis":
        # Importación local: ambos clasificadores siguen siendo módulos
        # independientes y el segundo puede compartir su contrato de salida.
        from .segmentacion_swir import clasificar_pixeles_area_afectada_swir

        _informar_progreso(on_progress, "Detectando candidatos por contraste SWIR", 40)
        clasificacion = clasificar_pixeles_area_afectada_swir(
            true_color,
            swir,
            sensibilidad=sensibilidad,
        )
    else:
        raise ValueError("Método no reconocido. Usa 'kmeans' o 'swir_histeresis'.")
    regiones = segmentar_regiones_espaciales(
        clasificacion,
        area_minima_pct=area_minima_pct,
        distancia_maxima_pct=distancia_maxima_pct,
        on_progress=on_progress,
        conservar_regiones_separadas=conservar_regiones_separadas,
    )
    return ResultadoAreaAfectada(
        sistema_coordenadas=sistema_coordenadas,
        mascara=regiones.mascara,
        mascara_clasificada=clasificacion.mascara_candidata,
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
    )
