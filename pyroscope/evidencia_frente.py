"""Evidencia visual relativa para frentes rojizos, naranjas y amarillos.

Las entradas son composiciones RGB renderizadas. Las puntuaciones describen
compatibilidad visual relativa; no miden temperatura ni prueban fuego activo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi


@dataclass(frozen=True)
class ResultadoEvidenciaFrente:
    """Evidencia conservada por separado de la clasificación SWIR existente."""

    puntuacion: np.ndarray
    candidatos_fuertes: np.ndarray
    candidatos_moderados: np.ndarray


def _validar_mascara(valor: np.ndarray, nombre: str, forma: tuple[int, int]) -> np.ndarray:
    matriz = np.asarray(valor)
    if matriz.shape != forma:
        raise ValueError(f"{nombre} debe compartir la rejilla de características.")
    return matriz.astype(bool)


def _cuantil(valores: np.ndarray, q: float, defecto: float) -> float:
    valores = np.asarray(valores)
    if valores.size < 256:
        return defecto
    resultado = float(np.quantile(valores, q))
    return resultado if np.isfinite(resultado) else defecto


def _rango(valor: np.ndarray, bajo: float, alto: float) -> np.ndarray:
    if alto <= bajo + 1e-6:
        return np.zeros_like(valor, dtype=np.float32)
    return np.clip((valor - bajo) / (alto - bajo), 0, 1).astype(np.float32)


def evaluar_evidencia_frente(
    caracteristicas: np.ndarray,
    candidata_swir_v2: np.ndarray,
    humo: np.ndarray,
    agua: np.ndarray,
    *,
    distancia_contexto_px: int | None = None,
) -> ResultadoEvidenciaFrente:
    """Calcula señales de frente sin convertirlas directamente en la máscara final.

    Combina dominancia roja y rojo/verde SWIR, tonalidad cálida/amarilla en
    True Color, contraste respecto al vecindario y proximidad a superficie
    candidata o humo. La señal dentro del humo se conserva como evidencia
    subyacente; las superficies de agua y el exterior remoto quedan vetados.
    """
    f = np.asarray(caracteristicas, dtype=np.float32)
    if f.ndim != 3 or f.shape[2] != 8 or not np.isfinite(f).all():
        raise ValueError("Se requieren ocho características conjuntas finitas.")
    forma = f.shape[:2]
    candidata_swir_v2 = _validar_mascara(candidata_swir_v2, "candidata_swir_v2", forma)
    humo = _validar_mascara(humo, "humo", forma)
    agua = _validar_mascara(agua, "agua", forma)
    if isinstance(distancia_contexto_px, bool) or (
        distancia_contexto_px is not None
        and (not isinstance(distancia_contexto_px, (int, np.integer)) or distancia_contexto_px < 1)
    ):
        raise ValueError("La distancia de contexto debe ser un entero positivo.")

    rojo_swir = f[..., 0]
    rojo_verde_swir = f[..., 6]
    verde_tc = f[..., 2]
    luminancia_tc = f[..., 3]
    croma_tc = f[..., 5]
    azul_tc = f[..., 7]
    valida = ~agua
    despejada = valida & ~humo
    oculta = valida & humo
    referencia = despejada if np.count_nonzero(despejada) >= 256 else valida
    rojo_ref = rojo_swir[referencia]
    rg_ref = rojo_verde_swir[referencia]
    rojo_oculto = rojo_swir[oculta]
    rg_oculto = rojo_verde_swir[oculta]

    # El grupo oculto usa sus propios cuantiles: el velo reduce la amplitud
    # cromática y aplicar umbrales despejados a ciegas perdería esa señal.
    rojo_fuerte_despejado = max(_cuantil(rojo_ref, .985, .12), .10)
    rojo_moderado_despejado = max(_cuantil(rojo_ref, .92, .06), .045)
    rg_fuerte_despejado = max(_cuantil(rg_ref, .72, -.04), -.08)
    rg_moderado_despejado = max(_cuantil(rg_ref, .52, -.13), -.18)
    rojo_fuerte_oculto = max(_cuantil(rojo_oculto, .96, .16), .10)
    rojo_moderado_oculto = max(_cuantil(rojo_oculto, .84, .07), .035)
    rg_fuerte_oculto = max(_cuantil(rg_oculto, .68, -.06), -.12)
    rg_moderado_oculto = max(_cuantil(rg_oculto, .48, -.16), -.22)

    sigma = max(3.0, min(10.0, min(forma) * .006))
    contraste_rojo = rojo_swir - ndi.gaussian_filter(rojo_swir, sigma=sigma)
    calida_tc = np.maximum(
        _rango(-verde_tc, -.08, .30),
        _rango(-azul_tc, -.10, .35),
    ) * np.clip(croma_tc / .28, 0, 1)
    contraste_calido = calida_tc - ndi.gaussian_filter(calida_tc, sigma=sigma)
    evidencia_local = np.maximum(
        _rango(contraste_rojo, .005, .12),
        _rango(contraste_calido, .015, .28),
    )

    dist_surface = ndi.distance_transform_edt(~candidata_swir_v2)
    dist_smoke = ndi.distance_transform_edt(~humo)
    radio = distancia_contexto_px or max(12, round(min(forma) * .025))
    contexto_visible = dist_surface <= radio
    contexto_atmosferico = dist_smoke <= radio
    contexto = contexto_visible | contexto_atmosferico

    umbral_rojo_fuerte = np.where(humo, rojo_fuerte_oculto, rojo_fuerte_despejado)
    umbral_rojo_moderado = np.where(humo, rojo_moderado_oculto, rojo_moderado_despejado)
    umbral_rg_fuerte = np.where(humo, rg_fuerte_oculto, rg_fuerte_despejado)
    umbral_rg_moderado = np.where(humo, rg_moderado_oculto, rg_moderado_despejado)
    senal_swir_fuerte = (rojo_swir >= umbral_rojo_fuerte) & (rojo_verde_swir >= umbral_rg_fuerte)
    senal_swir_moderada = (rojo_swir >= umbral_rojo_moderado) & (rojo_verde_swir >= umbral_rg_moderado)

    # Vegetación muy verde contradice la señal cálida, salvo que el contraste
    # local SWIR sea marcado. El veto solo actúa ante una señal positiva clara.
    verdor_alto = verde_tc > _cuantil(verde_tc[referencia], .96, .48)
    apoyo_cromatico = (calida_tc >= .18) | (evidencia_local >= .24)
    contradiccion_verde = verdor_alto & (calida_tc < .12) & (evidencia_local < .58)
    base = valida & contexto & apoyo_cromatico & ~contradiccion_verde

    fuertes = base & senal_swir_fuerte
    moderados = base & senal_swir_moderada & ~fuertes
    # Señales ya seleccionadas por V2 se conservan como fuente V2; este mapa
    # solo registra dónde también existe evidencia de frente independiente.
    puntuacion = np.clip(
        .52 * _rango(rojo_swir, rojo_moderado_despejado, rojo_fuerte_despejado)
        + .20 * _rango(rojo_verde_swir, rg_moderado_despejado, rg_fuerte_despejado)
        + .16 * calida_tc
        + .12 * evidencia_local,
        0,
        1,
    ).astype(np.float32)
    puntuacion[~base] = 0
    puntuacion[moderados] = np.maximum(puntuacion[moderados], .45)
    puntuacion[fuertes] = np.maximum(puntuacion[fuertes], .80)
    return ResultadoEvidenciaFrente(puntuacion, fuertes, moderados)
