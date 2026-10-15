"""Elementos visuales compartidos por las vistas web de PyroScope."""

from __future__ import annotations

import cv2
import numpy as np
import streamlit as st

from .configuracion import RAIZ_REPOSITORIO


def configurar_pagina() -> None:
    """Aplica los estilos locales y el encabezado común de la aplicación."""
    st.set_page_config(page_title="PyroScope · Área afectada", layout="wide")
    css = (RAIZ_REPOSITORIO / "assets" / "pyroscope.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="pyro-header">
          <div class="pyro-brand">
            <div class="pyro-brand-mark">🔥</div>
            <div>
              <div class="pyro-eyebrow">PyroScope · análisis satelital</div>
              <h1 class="pyro-title">Área afectada</h1>
              <div class="pyro-subtitle">Clasificación y revisión de una pareja True Color + SWIR</div>
            </div>
          </div>
          <div class="pyro-live"><span class="pyro-live-dot"></span> MOTOR PYTHON · LISTO</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mostrar_estado_vacio() -> None:
    """Presenta el estado inicial mientras se carga una pareja de imágenes."""
    st.markdown(
        """
        <div class="pyro-empty">
          <div>
            <div class="pyro-empty-icon">🛰️</div>
            <strong>Carga las dos composiciones para comenzar</strong>
            <span>True Color y SWIR deben corresponder a la misma escena, fecha y rejilla. Puedes subirlas en el panel lateral o elegir un ejemplo del reto.</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def dibujar_marcas(
    imagen: np.ndarray,
    puntos: list[tuple[float, float]],
    *,
    poligono_cerrado: bool,
    conectar_por_pares: bool = False,
) -> np.ndarray:
    """Pinta marcas sobre una copia de la imagen sin alterar coordenadas."""
    salida = imagen.copy()
    puntos_cv = [(round(x), round(y)) for x, y in puntos]
    if conectar_por_pares:
        for indice in range(0, len(puntos_cv) - 1, 2):
            cv2.line(
                salida,
                puntos_cv[indice],
                puntos_cv[indice + 1],
                (30, 235, 255),
                2,
                cv2.LINE_AA,
            )
    else:
        for inicio, fin in zip(puntos_cv, puntos_cv[1:]):
            cv2.line(salida, inicio, fin, (30, 235, 255), 2, cv2.LINE_AA)
    if poligono_cerrado and len(puntos_cv) >= 3:
        cv2.line(salida, puntos_cv[-1], puntos_cv[0], (30, 235, 255), 2, cv2.LINE_AA)
    for indice, punto in enumerate(puntos_cv, start=1):
        cv2.circle(salida, punto, 6, (255, 40, 220), -1, cv2.LINE_AA)
        cv2.putText(
            salida,
            str(indice),
            (punto[0] + 8, punto[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return salida


def formato_distancia(valor: float, unidad: str) -> str:
    """Formatea distancias métricas o distancias expresadas en píxeles."""
    if unidad == "m":
        return f"{valor / 1000:.3f} km" if valor >= 1000 else f"{valor:.1f} m"
    return f"{valor:.1f} {unidad}"


def formato_area(valor: float, unidad: str) -> str:
    """Formatea áreas en píxeles o metros cuadrados/hectáreas."""
    if unidad == "m²":
        return f"{valor:,.0f} m² ({valor / 10_000:.2f} ha)"
    return f"{valor:,.1f} {unidad}"
