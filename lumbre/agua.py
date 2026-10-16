"""Heurística conjunta para proponer píxeles de agua en las composiciones."""

from __future__ import annotations

import cv2
import numpy as np


UMBRALES_AGUA_POR_DEFECTO = {
    "true_color_darkness": 0.20,
    "swir_darkness": 0.10,
    "swir_red_max": 0.55,
    # El agua azul puede tener rojo/verde mayor que la vegetación verde. Un
    # percentil 0.55 la vetaba en escenas donde domina el verdor.
    "swir_red_green_max": 0.85,
}


def detectar_agua_probable(
    caracteristicas: np.ndarray,
    mascara_humo: np.ndarray,
    *,
    umbrales_percentil: dict[str, float] | None = None,
) -> np.ndarray:
    """Estima agua oscura con señales de True Color y SWIR.

    Los cuantiles se calculan sobre píxeles despejados. Es una máscara auxiliar
    conservadora, no un mapa de agua.
    """
    return _detectar_agua_probable_impl(
        caracteristicas,
        mascara_humo,
        umbrales_percentil=umbrales_percentil,
        experimental=False,
    )


def _detectar_agua_probable_experimental(
    caracteristicas: np.ndarray,
    mascara_humo: np.ndarray,
    *,
    umbrales_percentil: dict[str, float] | None = None,
) -> np.ndarray:
    """Propuesta cromática conservadora; no está conectada a los detectores.

    Se mantiene experimental porque, al retirar falsos píxeles de agua,
    SWIR + histéresis admite parte de ellos como superficie afectada.
    """
    return _detectar_agua_probable_impl(
        caracteristicas,
        mascara_humo,
        umbrales_percentil=umbrales_percentil,
        experimental=True,
    )


def _detectar_agua_probable_impl(
    caracteristicas: np.ndarray,
    mascara_humo: np.ndarray,
    *,
    umbrales_percentil: dict[str, float] | None,
    experimental: bool,
) -> np.ndarray:
    """Valida entradas y calcula la variante vigente o la experimental."""
    caracteristicas = np.asarray(caracteristicas, dtype=np.float32)
    if caracteristicas.ndim != 3 or caracteristicas.shape[2] < 8:
        raise ValueError("Se requieren al menos ocho características por píxel.")
    if not np.isfinite(caracteristicas).all():
        raise ValueError("Las características deben ser finitas.")
    mascara_humo = np.asarray(mascara_humo)
    if mascara_humo.shape != caracteristicas.shape[:2]:
        raise ValueError("La máscara de humo debe coincidir con la rejilla de características.")
    if not np.isfinite(mascara_humo).all() or not np.all(
        (mascara_humo == 0) | (mascara_humo == 1)
    ):
        raise ValueError("La máscara de humo debe contener únicamente valores 0/1.")
    mascara_humo = mascara_humo.astype(bool)
    percentiles = dict(
        UMBRALES_AGUA_POR_DEFECTO
        if umbrales_percentil is None
        else umbrales_percentil
    )
    if set(percentiles) != set(UMBRALES_AGUA_POR_DEFECTO):
        raise ValueError("Los percentiles de agua deben incluir las cuatro señales reconocidas.")
    valores = np.asarray([percentiles[k] for k in UMBRALES_AGUA_POR_DEFECTO], dtype=float)
    if not np.all(np.isfinite(valores)) or np.any(valores < 0.01) or np.any(valores > 0.99):
        raise ValueError("Los percentiles de agua deben estar entre 0,01 y 0,99.")

    despejado = ~mascara_humo
    if np.count_nonzero(despejado) < 16:
        return np.zeros(mascara_humo.shape, dtype=bool)

    luma_true_color = caracteristicas[:, :, 3]
    luma_swir = caracteristicas[:, :, 4]
    predominio_rojo_swir = caracteristicas[:, :, 0]
    cromaticidad_swir = caracteristicas[:, :, 1]
    predominio_verde_true_color = caracteristicas[:, :, 2]
    rojo_sobre_verde_swir = caracteristicas[:, :, 6]
    predominio_azul_true_color = caracteristicas[:, :, 7]

    # Un percentil calculado sobre una imagen uniforme coincide con todos los
    # píxeles. Usar <= en ese caso convertía una escena plana entera en agua.
    # Tampoco conviene interpretar unas pocas unidades de ruido como una clase.
    rango_tc = float(np.ptp(luma_true_color[despejado]))
    rango_swir = float(np.ptp(luma_swir[despejado]))
    if rango_tc < 0.02 or rango_swir < 0.02:
        return np.zeros(mascara_humo.shape, dtype=bool)

    # El antiguo veto usaba una disyunción de pistas débiles y terminaba
    # etiquetando como agua grandes partes oscuras de terreno y cicatriz.
    # Exigimos que ambas composiciones sean oscuras y que SWIR no muestre la
    # señal rojiza que caracteriza a los candidatos actuales.
    def limite_oscuridad(valores: np.ndarray, percentil: float) -> float:
        muestra = valores[despejado]
        cuantil = float(np.quantile(muestra, percentil))
        mediana = float(np.quantile(muestra, 0.50))
        margen = max(2 / 255, float(np.quantile(muestra, 0.95)
                                     - np.quantile(muestra, 0.05)) * 0.02)
        # Si el percentil cae justo sobre el tono común, bajar ligeramente el
        # corte separa agua oscura del fondo sin perder agua que forme una
        # fracción mayor de la escena.
        return min(cuantil, mediana - margen)

    limite_luma_tc = limite_oscuridad(
        luma_true_color, percentiles["true_color_darkness"]
    )
    limite_luma_swir = limite_oscuridad(luma_swir, percentiles["swir_darkness"])
    cuantil_predominio_rojo = float(
        np.quantile(predominio_rojo_swir[despejado], percentiles["swir_red_max"])
    )
    cuantil_rojo_verde = float(
        np.quantile(
            rojo_sobre_verde_swir[despejado],
            percentiles["swir_red_green_max"],
        )
    )
    if not experimental:
        return (
            despejado
            & (luma_true_color <= limite_luma_tc)
            & (luma_swir <= limite_luma_swir)
            & (predominio_rojo_swir <= cuantil_predominio_rojo)
            & (rojo_sobre_verde_swir <= cuantil_rojo_verde)
        )

    # Si un cuantil negativo se usa como máximo, se exige que el píxel sea más
    # verde que el percentil de la escena: el agua neutra (valor cercano a 0)
    # queda fuera. Cero representa ausencia de predominio, no una señal de agua.
    limite_predominio_rojo = max(0.0, cuantil_predominio_rojo)
    limite_rojo_verde = max(0.0, cuantil_rojo_verde)

    # Una única señal no basta para etiquetar agua. Rechazar verdor fuerte solo
    # cuando coinciden predominio verde visible, verde SWIR y cromaticidad alta.
    limite_verde_visible = float(
        np.quantile(predominio_verde_true_color[despejado], 0.65)
    )
    limite_verde_swir = float(
        np.quantile(rojo_sobre_verde_swir[despejado], 0.25)
    )
    limite_cromaticidad_vegetacion = float(
        np.quantile(cromaticidad_swir[despejado], 0.65)
    )
    vegetacion_clara = (
        (predominio_verde_true_color >= limite_verde_visible)
        & (rojo_sobre_verde_swir <= limite_verde_swir)
        & (cromaticidad_swir >= limite_cromaticidad_vegetacion)
    )

    # Se conserva el agua oscura y poco cromática. Un agua más azul y saturada
    # también puede pasar si True Color aporta predominio azul sin verdor fuerte.
    limite_cromaticidad_agua = limite_cromaticidad_vegetacion
    limite_azul_visible = float(
        np.quantile(predominio_azul_true_color[despejado], 0.85)
    )
    limite_verde_visible_azul = float(
        np.quantile(predominio_verde_true_color[despejado], 0.75)
    )
    apoyo_azul = (
        (predominio_azul_true_color >= limite_azul_visible)
        & (predominio_azul_true_color > 0.0)
        & (predominio_verde_true_color < limite_verde_visible_azul)
    )
    candidato_cromatico = (
        despejado
        & (luma_true_color <= limite_luma_tc)
        & (luma_swir <= limite_luma_swir)
        & (predominio_rojo_swir <= limite_predominio_rojo)
        & (rojo_sobre_verde_swir <= limite_rojo_verde)
        & ~vegetacion_clara
        & ((cromaticidad_swir <= limite_cromaticidad_agua) | apoyo_azul)
    )

    # La vecindad inmediata retira motas sin respaldo local; no se usa un área
    # mínima, por lo que los cuerpos pequeños y coherentes siguen siendo válidos.
    cantidad_vecinos = cv2.boxFilter(
        candidato_cromatico.astype(np.float32),
        cv2.CV_32F,
        (3, 3),
        normalize=False,
        borderType=cv2.BORDER_CONSTANT,
    ) - candidato_cromatico.astype(np.float32)
    return candidato_cromatico & (cantidad_vecinos > 0)
