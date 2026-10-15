"""Coordinación del recorrido web cargar → analizar → revisar → exportar."""

from __future__ import annotations

import hashlib

import streamlit as st

from .entrada import renderizar_barra_lateral
from .mediciones import renderizar_plano
from .presentacion import configurar_pagina, mostrar_estado_vacio
from .procesamiento import preparar_pareja, procesar_pareja
from .resultados import renderizar_resultados


def main() -> None:
    configurar_pagina()
    entrada, ajustes = renderizar_barra_lateral()
    if entrada is None:
        mostrar_estado_vacio()
        st.stop()

    st.markdown(
        f'<div class="pyro-context"><strong>{entrada.escena}</strong><span>Análisis</span></div>',
        unsafe_allow_html=True,
    )
    progress_label = st.empty()
    progress_bar = st.progress(0)

    def actualizar_progreso(etapa: str, porcentaje: int) -> None:
        porcentaje = max(0, min(100, int(porcentaje)))
        progress_label.markdown(
            f'<div class="pyro-stage"><span>{etapa}</span><strong>{porcentaje}%</strong></div>',
            unsafe_allow_html=True,
        )
        progress_bar.progress(porcentaje)

    digest = hashlib.sha256()
    digest.update(entrada.true_color)
    digest.update(entrada.swir)
    clave_procesamiento = (
        digest.hexdigest(),
        ajustes.gsd_m_por_px,
        ajustes.detector.id,
        ajustes.sensibilidad,
        ajustes.numero_clases,
        ajustes.area_minima_pct,
        ajustes.distancia_maxima_pct,
        ajustes.conservar_regiones_separadas,
    )
    cache_sesion = st.session_state.get("_pyroscope_resultado_cache")
    if cache_sesion and cache_sesion[0] == clave_procesamiento:
        tc, swir, resultado = cache_sesion[1]
        actualizar_progreso("Listo", 100)
    else:
        actualizar_progreso("Leyendo y alineando las imágenes", 3)
        try:
            pareja = preparar_pareja(
                entrada.true_color,
                entrada.swir,
                ajustes.gsd_m_por_px,
            )
        except Exception as exc:
            st.error(f"No se pudieron leer o alinear las imágenes: {exc}")
            st.stop()

        try:
            tc, swir, resultado = procesar_pareja(
                pareja.true_color,
                pareja.swir,
                ajustes.sensibilidad,
                ajustes.numero_clases,
                ajustes.area_minima_pct,
                ajustes.distancia_maxima_pct,
                pareja.gsd_x_m,
                pareja.gsd_y_m,
                ajustes.detector.id,
                ajustes.conservar_regiones_separadas,
                actualizar_progreso,
            )
            st.session_state["_pyroscope_resultado_cache"] = (
                clave_procesamiento,
                (tc, swir, resultado),
            )
            actualizar_progreso("Completado", 100)
        except Exception as exc:
            progress_label.markdown(
                '<div class="pyro-stage"><span>No se pudo completar el análisis</span></div>',
                unsafe_allow_html=True,
            )
            st.error(f"No se pudo segmentar esta pareja: {exc}")
            st.stop()

    vista_col, telemetria_col = st.columns([2.8, 1.2], gap="medium")
    vista_semantica, descarga_overlay, descarga_mascara = renderizar_plano(
        vista_col,
        tc,
        swir,
        resultado,
        entrada.true_color,
        entrada.swir,
    )
    area_px = int(resultado.mascara.sum())
    area_calculada, unidad_area = resultado.sistema_coordenadas.area_de_pixeles(area_px)
    perimetro = 0.0
    unidad_perimetro = "m" if resultado.sistema_coordenadas.gsd_x_m is not None else "px"
    for contorno in resultado.contornos:
        vertices = [tuple(map(float, punto[0])) for punto in contorno]
        longitud, unidad_perimetro = resultado.sistema_coordenadas.longitud_de_linea(
            vertices,
            cerrar=True,
        )
        perimetro += longitud

    renderizar_resultados(
        telemetria_col,
        resultado,
        ajustes.detector.nombre,
        area_calculada,
        unidad_area,
        perimetro,
        unidad_perimetro,
        descarga_overlay,
        descarga_mascara,
        vista_semantica,
    )


__all__ = ["main"]
