"""Hipótesis conservadoras de suelo afectado ocluido, independientes del detector.

Las puntuaciones son evidencias normalizadas, nunca probabilidades calibradas.
Ninguna salida de este módulo debe sumarse al área observada. Las distancias
se expresan en píxeles de la rejilla de trabajo, no en unidades geográficas.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi


@dataclass(frozen=True)
class ResultadoEstimacionBajoHumo:
    mascara_espectral: np.ndarray
    mascara_continuidad: np.ndarray
    mascara_indeterminada: np.ndarray

    @property
    def mascara_candidata(self) -> np.ndarray:
        return self.mascara_espectral | self.mascara_continuidad


def _mascara(valor: np.ndarray, nombre: str, forma=None) -> np.ndarray:
    matriz = np.asarray(valor)
    if matriz.ndim != 2 or (forma is not None and matriz.shape != forma):
        raise ValueError(f"{nombre} debe ser una máscara 2D de la misma rejilla.")
    if not np.all(np.isfinite(matriz)) or not np.all((matriz == 0) | (matriz == 1)):
        raise ValueError(f"{nombre} debe contener únicamente valores booleanos o 0/1.")
    return matriz.astype(bool)


def _evidencia(valor: np.ndarray, nombre: str, forma) -> np.ndarray:
    matriz = np.asarray(valor, dtype=np.float32)
    if matriz.shape != forma or not np.all(np.isfinite(matriz)):
        raise ValueError(f"{nombre} debe ser finita y coincidir con la rejilla.")
    if np.any((matriz < 0) | (matriz > 1)):
        raise ValueError(f"{nombre} debe estar normalizada entre 0 y 1.")
    return matriz


def _puentes_linea(permitida, anclas, maximo):
    """Rellena solo recorridos ocluidos completos con dos extremos observados."""
    cambios = np.diff(np.r_[False, permitida, False].astype(np.int8))
    inicios = np.flatnonzero(cambios == 1)
    finales = np.flatnonzero(cambios == -1)
    validos = (inicios > 0) & (finales < permitida.size) & ((finales - inicios) <= maximo)
    inicios, finales = inicios[validos], finales[validos]
    validos = anclas[inicios - 1] & anclas[finales]
    # Diferencias acumuladas evitan un bucle Python por cada tramo de humo.
    marcas = np.zeros(permitida.size + 1, dtype=np.int32)
    marcas[inicios[validos]] += 1
    marcas[finales[validos]] -= 1
    return np.cumsum(marcas[:-1]) > 0


def estimar_bajo_humo(
    visible: np.ndarray,
    humo: np.ndarray,
    agua: np.ndarray,
    evidencia_espectral: np.ndarray | None = None,
    *,
    compatibilidad_swir: np.ndarray | None = None,
    contradiccion: np.ndarray | None = None,
    distancia_maxima_px: int = 24,
    umbral_espectral: float = 0.65,
    umbral_compatibilidad: float = 0.35,
    umbral_semilla_bajo_humo: float | None = None,
    distancia_espectral_px: int | None = None,
) -> ResultadoEstimacionBajoHumo:
    """Separa evidencia bajo humo, puentes geométricos cortos e incertidumbre.

    ``visible`` contiene observaciones fiables. Para continuidad solo sirven
    como anclas las que están fuera del humo. Se buscan interrupciones rectas
    horizontales, verticales y diagonales con ambos extremos observados; una
    hipótesis nunca se reutiliza como semilla. No se rellenan nubes completas.

    La ruta espectral requiere puntuación suficiente y crecimiento limitado
    desde observaciones visibles o señales ocultas fuertes. La evidencia
    moderada puede crecer de forma geodésica desde esas semillas originales,
    sin reutilizar hipótesis intermedias como nuevas observaciones.
    ``compatibilidad_swir``, cuando se suministra, veta también los puentes
    geométricos incompatibles. Un valor bajo debe indicar contradicción fiable,
    no simplemente ausencia de información.
    """
    visible = _mascara(visible, "visible")
    humo = _mascara(humo, "humo", visible.shape)
    agua = _mascara(agua, "agua", visible.shape)
    if visible.size == 0:
        raise ValueError("La rejilla no puede estar vacía.")
    if isinstance(distancia_maxima_px, bool) or not isinstance(distancia_maxima_px, (int, np.integer)) or distancia_maxima_px < 1:
        raise ValueError("La distancia máxima debe ser un entero positivo en píxeles.")
    for nombre, umbral in (
        ("espectral", umbral_espectral),
        ("compatibilidad", umbral_compatibilidad),
    ):
        if not np.isfinite(umbral) or not 0 <= umbral <= 1:
            raise ValueError(f"El umbral {nombre} debe estar entre 0 y 1.")
    if (umbral_semilla_bajo_humo is not None
            and (not np.isfinite(umbral_semilla_bajo_humo)
                 or not 0 <= umbral_semilla_bajo_humo <= 1)):
        raise ValueError("El umbral semilla bajo humo debe estar entre 0 y 1.")
    obstaculos = agua.copy()
    if distancia_espectral_px is None:
        distancia_espectral_px = distancia_maxima_px
    if (isinstance(distancia_espectral_px, bool)
            or not isinstance(distancia_espectral_px, (int, np.integer))
            or distancia_espectral_px < 1):
        raise ValueError("La distancia espectral debe ser un entero positivo.")
    if contradiccion is not None:
        obstaculos |= _mascara(contradiccion, "contradiccion", visible.shape)
    compatible = ~obstaculos
    if compatibilidad_swir is not None:
        compatible &= _evidencia(compatibilidad_swir, "compatibilidad_swir", visible.shape) >= umbral_compatibilidad
    anclas = visible & ~humo & compatible
    oculta = humo & ~visible & compatible
    espectral = np.zeros_like(visible)
    continuidad_geodesica = np.zeros_like(visible)
    if evidencia_espectral is not None:
        evidencia = _evidencia(evidencia_espectral, "evidencia_espectral", visible.shape)
        # Solo una fuente que identifique explícitamente evidencia fuerte, o un
        # umbral optativo, puede aportar semillas ocultas. Un score genérico no
        # cambia el comportamiento de otros detectores.
        diagnosticos = getattr(evidencia_espectral, "diagnosticos", {}) or {}
        frente_fuerte = diagnosticos.get("frente_candidato_fuerte")
        if frente_fuerte is not None:
            frente_fuerte = _mascara(frente_fuerte, "frente_fuerte", visible.shape)
            semillas_ocultas = oculta & frente_fuerte
        elif umbral_semilla_bajo_humo is not None:
            semillas_ocultas = oculta & (evidencia >= umbral_semilla_bajo_humo)
        else:
            semillas_ocultas = np.zeros_like(visible)
        semillas = anclas | semillas_ocultas
        if np.any(semillas):
            distancia_ancla = ndi.distance_transform_edt(~semillas)
            admisible = oculta & (evidencia >= umbral_compatibilidad)
            dentro_radio = admisible & (distancia_ancla <= distancia_espectral_px)
            alcanzable = ndi.binary_propagation(semillas, mask=semillas | dentro_radio)
            conectada = dentro_radio & alcanzable
            espectral = semillas_ocultas | (conectada & (evidencia >= umbral_espectral))
            continuidad_geodesica = conectada & (evidencia < umbral_espectral)

    continuidad = continuidad_geodesica.copy()
    if np.any(anclas):
        alto, ancho = visible.shape
        for fila in range(alto):
            continuidad[fila] |= _puentes_linea(oculta[fila], anclas[fila], distancia_maxima_px)
        for columna in range(ancho):
            continuidad[:, columna] |= _puentes_linea(oculta[:, columna], anclas[:, columna], distancia_maxima_px)
        maximo_diagonal = int(distancia_maxima_px / np.sqrt(2))
        for invertida in (False, True):
            permitida = oculta[:, ::-1] if invertida else oculta
            semillas = anclas[:, ::-1] if invertida else anclas
            destino = continuidad[:, ::-1] if invertida else continuidad
            for desplazamiento in range(1 - alto, ancho):
                inicio_fila = max(0, -desplazamiento)
                inicio_columna = max(0, desplazamiento)
                longitud = min(alto - inicio_fila, ancho - inicio_columna)
                indices = np.arange(longitud)
                filas, columnas = inicio_fila + indices, inicio_columna + indices
                destino[filas, columnas] |= _puentes_linea(
                    permitida[filas, columnas], semillas[filas, columnas], maximo_diagonal,
                )
    continuidad &= ~espectral
    indeterminada = humo & ~visible & ~obstaculos & ~(espectral | continuidad)
    return ResultadoEstimacionBajoHumo(espectral, continuidad, indeterminada)
