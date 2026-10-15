"""Segmentación heurística de superficies con evidencia de incendio.

Las entradas son composiciones RGB renderizadas, no reflectancias Sentinel-2.
Por tanto, el resultado es una clasificación exploratoria, no una medición física.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from sklearn.cluster import MiniBatchKMeans

from .caracteristicas import extraer_caracteristicas_pareja
from .coordenadas import SistemaCoordenadasImagen
from .imagenes import validar_par_alineado


@dataclass(frozen=True)
class ResultadoAreaAfectada:
    sistema_coordenadas: SistemaCoordenadasImagen
    mascara: np.ndarray
    contornos: tuple[np.ndarray, ...]
    proporcion: float
    centros: np.ndarray
    clases_seleccionadas: tuple[int, ...]
    puntuaciones_clase: np.ndarray
    pixeles_agua_excluidos: int
    distancia_maxima_px: int
    componentes_remotos_descartados: int


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
) -> ResultadoAreaAfectada:
    """Propone una máscara de superficie afectada fusionando True Color y SWIR.

    Los grupos se ajustan por escena. La señal principal es el predominio de rojo
    sobre verde en SWIR; True Color aporta verdor, color azul y oscuridad para
    moderar falsos candidatos de agua. El agrupamiento recibe características de
    ambas composiciones en el mismo vector.
    """
    validar_par_alineado(true_color, swir)
    if not 2 <= numero_clases <= 12:
        raise ValueError("El número de clases debe estar entre 2 y 12.")
    if not 1 <= sensibilidad <= 10:
        raise ValueError("La sensibilidad debe estar entre 1 y 10.")
    if not 0 <= area_minima_pct <= 10:
        raise ValueError("El área mínima debe estar entre 0 y 10 por ciento.")
    if not 0 <= distancia_maxima_pct <= 50:
        raise ValueError("La distancia máxima debe estar entre 0 y 50 por ciento.")

    features = extraer_caracteristicas_pareja(true_color, swir)
    alto, ancho, numero_caracteristicas = features.shape
    if sistema_coordenadas is None:
        sistema_coordenadas = SistemaCoordenadasImagen(ancho_px=ancho, alto_px=alto)
    elif (sistema_coordenadas.ancho_px, sistema_coordenadas.alto_px) != (ancho, alto):
        raise ValueError("La rejilla de coordenadas debe coincidir con la imagen analizada.")
    plano = features.reshape(-1, numero_caracteristicas)

    rng = np.random.default_rng(semilla)
    muestra_n = min(120_000, plano.shape[0])
    indices = rng.choice(plano.shape[0], size=muestra_n, replace=False)
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
    # Mantiene el agrupamiento base conjunto probado en las seis señales previas;
    # las dos señales nuevas influyen en la puntuación de cada grupo y en los
    # vetos, sin cambiar el espacio geométrico del KMeans.
    modelo.fit(muestra_z[:, :6])
    centros = np.zeros((modelo.n_clusters, numero_caracteristicas), dtype=np.float32)
    centros[:, :6] = modelo.cluster_centers_.astype(np.float32)
    etiquetas_muestra = modelo.predict(muestra_z[:, :6])
    for clase in range(modelo.n_clusters):
        pixeles_clase = muestra_z[etiquetas_muestra == clase, 6:]
        if pixeles_clase.size:
            centros[clase, 6:] = pixeles_clase.mean(axis=0)

    # Se conserva la puntuación base y se añaden SWIR rojo/verde y True Color azul.
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

    # El agua y las sombras profundas suelen ser oscuras en SWIR, pero la cicatriz
    # puede serlo también. Una clase oscura solo se conserva si además tiene señal
    # rojiza y cromaticidad marcadas en la composición.
    elegibles = (centros[:, 4] > -2.0) | (
        (centros[:, 0] > 1.5) & (centros[:, 1] > 0.0)
    )
    if np.any(elegibles):
        puntuaciones_elegibles = np.where(elegibles, puntuaciones, -np.inf)
    else:
        puntuaciones_elegibles = puntuaciones
    mejor = int(np.argmax(puntuaciones_elegibles))

    # La sensibilidad abre la selección a clases cercanas al grupo mejor puntado.
    margen = 0.12 + (sensibilidad - 1) * 0.105
    seleccionadas = np.flatnonzero(
        elegibles & (puntuaciones >= puntuaciones[mejor] - margen)
    )
    if seleccionadas.size == 0:
        seleccionadas = np.asarray([mejor], dtype=np.int32)

    normalizado = np.clip((plano - medianas) / escalas, -6.0, 6.0).astype(np.float32)
    normalizado_3d = normalizado.reshape(alto, ancho, numero_caracteristicas)
    etiquetas = modelo.predict(normalizado[:, :6]).reshape(alto, ancho)
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

    # Refuerza directamente la diferencia SWIR rojo/verde y descarta píxeles que
    # sean muy verdes en esa composición. La guarda se adapta a cada escena.
    rojizo_minimo = max(-0.55, float(np.quantile(muestra_z[:, 0], 0.40)))
    mascara &= normalizado_3d[:, :, 0] >= rojizo_minimo
    rojo_verde_minimo = max(-0.75, float(np.quantile(muestra_z[:, 6], 0.35)))
    mascara &= normalizado_3d[:, :, 6] >= rojo_verde_minimo

    # Evidencia de agua en True Color: oscuridad relativa junto a dominancia azul,
    # baja cromaticidad (agua oscura/neutra) o señal SWIR claramente verde. Así,
    # un píxel oscuro con SWIR ambiguo no entra por sí solo como cicatriz.
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
    mascara_agua = agua_azulada | agua_oscura_ambigua
    mascara &= ~mascara_agua

    mascara_u8 = mascara.astype(np.uint8) * 255
    mascara_u8 = cv2.morphologyEx(
        mascara_u8, cv2.MORPH_CLOSE, np.ones((5, 5), dtype=np.uint8)
    )
    mascara_u8 = cv2.morphologyEx(
        mascara_u8, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8)
    )
    pixeles_agua_excluidos = int(np.count_nonzero(mascara_u8[mascara_agua]))
    # La clausura morfológica puede tender puentes estrechos; restituye el veto de
    # agua después de limpiarla para no unir la máscara a través de un lago.
    mascara_u8[mascara_agua] = 0

    cantidad, etiquetas_cc, stats, _ = cv2.connectedComponentsWithStats(
        mascara_u8, connectivity=8
    )
    minimo_pixeles = max(16, round(alto * ancho * area_minima_pct / 100.0))
    # La región candidata principal sirve de ancla. Se conservan manchas
    # secundarias cercanas (p. ej., separadas por humo) y se quitan candidatos
    # cromáticos aislados lejos del incendio principal.
    distancia_maxima_px = round(max(alto, ancho) * distancia_maxima_pct / 100.0)
    n_componentes = cantidad
    componentes_remotos_descartados = 0
    if n_componentes > 1:
        ancla = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mascara_ancla = etiquetas_cc == ancla
        distancia_al_ancla = cv2.distanceTransform(
            (~mascara_ancla).astype(np.uint8),
            cv2.DIST_L2,
            cv2.DIST_MASK_5,
        )
        limpia = np.zeros((alto, ancho), dtype=np.uint8)
        for etiqueta in range(1, n_componentes):
            area = stats[etiqueta, cv2.CC_STAT_AREA]
            if area < minimo_pixeles:
                continue
            componente = etiquetas_cc == etiqueta
            separacion = float(distancia_al_ancla[componente].min())
            if separacion > distancia_maxima_px:
                componentes_remotos_descartados += 1
                continue
            # Recorta también las colas muy lejanas de componentes conectados por
            # un puente estrecho, sin desechar la parte cercana al incendio.
            dentro_del_radio = componente & (distancia_al_ancla <= distancia_maxima_px)
            limpia[dentro_del_radio] = 255
    else:
        limpia = np.zeros((alto, ancho), dtype=np.uint8)

    contornos, _ = cv2.findContours(
        limpia, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contornos_ordenados = tuple(
        sorted(contornos, key=cv2.contourArea, reverse=True)
    )
    resultado = limpia > 0
    return ResultadoAreaAfectada(
        sistema_coordenadas=sistema_coordenadas,
        mascara=resultado,
        contornos=contornos_ordenados,
        proporcion=float(resultado.mean()),
        centros=centros,
        clases_seleccionadas=tuple(int(i) for i in seleccionadas),
        puntuaciones_clase=puntuaciones,
        pixeles_agua_excluidos=pixeles_agua_excluidos,
        distancia_maxima_px=distancia_maxima_px,
        componentes_remotos_descartados=componentes_remotos_descartados,
    )
