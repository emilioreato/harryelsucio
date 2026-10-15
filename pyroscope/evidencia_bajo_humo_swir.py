"""Evidencia independiente de superficie posible bajo humo usando solo SWIR RGB.

La entrada SWIR es una composición RGB renderizada, no reflectancia ni una
medición térmica. El mapa ordinal se calibra con la firma SWIR de la superficie
visible del mismo análisis; no usa True Color, Wildfires ni una máscara final.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi


@dataclass(frozen=True)
class ResultadoEvidenciaBajoHumoSWIR:
    evidencia: np.ndarray
    candidatos_fuertes: np.ndarray
    candidatos_moderados: np.ndarray
    compatibilidad: np.ndarray
    umbrales: dict[str, float]


def _mascara(valor: np.ndarray, nombre: str, forma: tuple[int, int]) -> np.ndarray:
    matriz = np.asarray(valor)
    if matriz.shape != forma or not np.isfinite(matriz).all():
        raise ValueError(f"{nombre} debe coincidir con la rejilla y ser finita.")
    if not np.all((matriz == 0) | (matriz == 1)):
        raise ValueError(f"{nombre} debe contener únicamente valores booleanos o 0/1.")
    return matriz.astype(bool)


def _filtrar_componentes(mascara: np.ndarray, minimo: int) -> np.ndarray:
    etiquetas, cantidad = ndi.label(mascara, structure=np.ones((3, 3), dtype=np.uint8))
    if cantidad == 0:
        return np.zeros_like(mascara, dtype=bool)
    tamanos = np.bincount(etiquetas.ravel())
    conservar = tamanos >= minimo
    conservar[0] = False
    return conservar[etiquetas]


def evaluar_evidencia_bajo_humo_swir(
    swir: np.ndarray,
    humo: np.ndarray,
    superficie_visible: np.ndarray,
    *,
    minimo_semillas: int = 16,
    minimo_componente: int = 4,
) -> ResultadoEvidenciaBajoHumoSWIR:
    """Compara cada píxel bajo humo con firmas SWIR observadas sin leer True Color.

    Los dos índices cromáticos son relativos a la suma de canales y toleran
    cambios de brillo. Los umbrales moderados admiten una atenuación de la firma
    respecto a las semillas visibles; el nivel fuerte conserva un margen más
    estricto. Solo se generan candidatos donde ambos índices apoyan rojo SWIR.

    Este módulo no decide por sí solo la máscara final. La conexión y distancia
    a anclas o semillas SWIR fuertes se resuelven después, manteniendo separada
    la superficie observada de la hipótesis ocluida.
    """
    imagen = np.asarray(swir)
    if imagen.ndim != 3 or imagen.shape[2] != 3 or not np.issubdtype(imagen.dtype, np.number):
        raise ValueError("SWIR debe ser una imagen RGB de tres canales.")
    if imagen.size == 0 or not np.isfinite(imagen).all():
        raise ValueError("SWIR no puede estar vacía y debe ser finita.")
    if isinstance(minimo_semillas, bool) or not isinstance(minimo_semillas, (int, np.integer)) or minimo_semillas < 1:
        raise ValueError("El mínimo de semillas debe ser un entero positivo.")
    if isinstance(minimo_componente, bool) or not isinstance(minimo_componente, (int, np.integer)) or minimo_componente < 1:
        raise ValueError("El tamaño mínimo de componente debe ser un entero positivo.")

    forma = imagen.shape[:2]
    humo = _mascara(humo, "humo", forma)
    visible = _mascara(superficie_visible, "superficie_visible", forma)
    anclas = visible & ~humo
    vacia = np.zeros(forma, dtype=bool)
    evidencia_vacia = np.zeros(forma, dtype=np.float32)
    umbrales_vacios = {
        "rojo_fuerte": 1.0,
        "rojo_moderado": 1.0,
        "rojo_verde_fuerte": 1.0,
        "rojo_verde_moderado": 1.0,
    }
    if int(anclas.sum()) < minimo_semillas:
        return ResultadoEvidenciaBajoHumoSWIR(
            evidencia_vacia, vacia.copy(), vacia.copy(), evidencia_vacia.copy(),
            umbrales_vacios,
        )

    rgb = imagen.astype(np.float32)
    escala = float(np.iinfo(imagen.dtype).max) if np.issubdtype(imagen.dtype, np.integer) else 1.0
    if escala <= 0 or (not np.issubdtype(imagen.dtype, np.integer) and float(rgb.max()) > 1.0):
        escala = 255.0
    rgb = np.clip(rgb / escala, 0, 1)
    rojo, verde, azul = np.moveaxis(rgb, -1, 0)
    suma = rojo + verde + azul + 1e-3
    predominio_rojo = (2 * rojo - verde - azul) / suma
    rojo_verde = (rojo - verde) / (rojo + verde + 1e-3)

    terreno_despejado = ~humo
    fondo = terreno_despejado & ~anclas
    if int(fondo.sum()) < 32:
        fondo = terreno_despejado
    firma_roja = predominio_rojo[anclas]
    firma_rg = rojo_verde[anclas]
    fondo_rojo = predominio_rojo[fondo]
    fondo_rg = rojo_verde[fondo]
    if fondo_rojo.size == 0:
        fondo_rojo = predominio_rojo[terreno_despejado]
        fondo_rg = rojo_verde[terreno_despejado]

    # Si las anclas no tienen una firma rojiza separable del terreno despejado,
    # el método se abstiene: no inventa clases a partir de percentiles planos.
    separacion_roja = float(np.median(firma_roja) - np.median(fondo_rojo))
    separacion_rg = float(np.median(firma_rg) - np.median(fondo_rg))
    if separacion_roja < 0.025 or separacion_rg < 0.015:
        return ResultadoEvidenciaBajoHumoSWIR(
            evidencia_vacia, vacia.copy(), vacia.copy(), evidencia_vacia.copy(),
            umbrales_vacios,
        )

    rojo_semilla_bajo = float(np.quantile(firma_roja, 0.10))
    rg_semilla_bajo = float(np.quantile(firma_rg, 0.10))
    rojo_fuerte = max(
        float(np.quantile(fondo_rojo, 0.75)), rojo_semilla_bajo - 0.12, 0.04
    )
    rg_fuerte = max(
        float(np.quantile(fondo_rg, 0.65)), rg_semilla_bajo - 0.12, -0.08
    )
    rojo_moderado = max(
        float(np.quantile(fondo_rojo, 0.55)), rojo_semilla_bajo - 0.60, -0.04
    )
    rg_moderado = max(
        float(np.quantile(fondo_rg, 0.40)), rg_semilla_bajo - 0.40, -0.20
    )

    oculta = humo & ~visible
    fuerte = oculta & (predominio_rojo >= rojo_fuerte) & (rojo_verde >= rg_fuerte)
    moderada = oculta & (predominio_rojo >= rojo_moderado) & (rojo_verde >= rg_moderado)
    fuerte = _filtrar_componentes(fuerte, minimo_componente)
    moderada = _filtrar_componentes(moderada | fuerte, minimo_componente)

    margen_rojo = np.clip(
        (predominio_rojo - rojo_moderado) / max(rojo_fuerte - rojo_moderado, 1e-3), 0, 1
    )
    margen_rg = np.clip(
        (rojo_verde - rg_moderado) / max(rg_fuerte - rg_moderado, 1e-3), 0, 1
    )
    compatibilidad = (0.65 * margen_rojo + 0.35 * margen_rg).astype(np.float32)
    evidencia = np.zeros(forma, dtype=np.float32)
    evidencia[moderada] = 0.38 + 0.08 * compatibilidad[moderada]
    evidencia[fuerte] = 0.82 + 0.17 * compatibilidad[fuerte]
    return ResultadoEvidenciaBajoHumoSWIR(
        evidencia=evidencia,
        candidatos_fuertes=fuerte,
        candidatos_moderados=moderada & ~fuerte,
        compatibilidad=compatibilidad,
        umbrales={
            "rojo_fuerte": rojo_fuerte,
            "rojo_moderado": rojo_moderado,
            "rojo_verde_fuerte": rg_fuerte,
            "rojo_verde_moderado": rg_moderado,
        },
    )
