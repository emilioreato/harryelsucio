"""Vista del plano, capas y herramientas interactivas de medición."""

from __future__ import annotations

from io import BytesIO
import hashlib
import json

import cv2
import numpy as np
import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

from ..segmentacion import ResultadoAreaAfectada
from ..visualizacion import crear_superposicion, crear_vista_clasificacion
from .configuracion import ANCHO_MEDICION
from .presentacion import dibujar_marcas, formato_area, formato_distancia


def renderizar_plano(vista_col, tc, swir, resultado: ResultadoAreaAfectada, true_bytes: bytes, swir_bytes: bytes):
    superposicion = crear_superposicion(tc, resultado)

    descarga_overlay = BytesIO()

    Image.fromarray(superposicion).save(descarga_overlay, format="PNG")

    descarga_mascara = BytesIO()

    Image.fromarray(resultado.mascara.astype(np.uint8) * 255).save(descarga_mascara, format="PNG")

    vista_semantica = crear_vista_clasificacion(tc, resultado)

    capas = {
        "Superposición": superposicion,
        "True Color": tc,
        "SWIR": swir,
        "Candidatos + humo": vista_semantica,
    }

    with vista_col:
        with st.container(border=True):
            st.markdown(
                '<div class="pyro-section-heading"><strong>Plano de análisis</strong>'
                '<span>CAPAS SATELITALES · REJILLA DE MEDICIÓN</span></div>',
                unsafe_allow_html=True,
            )
            capa_activa = st.radio(
                "Capa visible",
                tuple(capas),
                horizontal=True,
                label_visibility="collapsed",
                key="pyroscope_capa_activa",
            )
            st.markdown('<div class="pyro-divider"></div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="pyro-section-heading"><strong>Herramientas del plano</strong>'
                '<span>MEDICIONES EN LA REJILLA ANALIZADA</span></div>',
                unsafe_allow_html=True,
            )
            modo_medicion = st.radio(
                "Herramienta",
                ("Vista", "Distancia entre puntos", "Área de polígono", "Inspección de píxel"),
                horizontal=True,
                label_visibility="collapsed",
                key="pyroscope_modo_medicion_ui",
            )
            st.caption(
                "Selecciona una herramienta y marca sobre la imagen. Las mediciones usan la escala indicada; "
                "sin GSD se expresan en píxeles."
            )

            firma_imagen = hashlib.sha256(true_bytes + swir_bytes).hexdigest()[:20]
            if st.session_state.get("_pyroscope_firma_imagen") != firma_imagen:
                st.session_state["_pyroscope_firma_imagen"] = firma_imagen
                st.session_state["_pyroscope_puntos"] = []
                st.session_state["_pyroscope_poligono_cerrado"] = False
                st.session_state["_pyroscope_ultimo_clic"] = None
                st.session_state["_pyroscope_pixel_inspeccionado"] = None
                st.session_state["_pyroscope_modo_medicion"] = None

            if st.session_state.get("_pyroscope_modo_medicion") != modo_medicion:
                st.session_state["_pyroscope_puntos"] = []
                st.session_state["_pyroscope_poligono_cerrado"] = False
                st.session_state["_pyroscope_pixel_inspeccionado"] = None
                st.session_state["_pyroscope_modo_medicion"] = modo_medicion

            puntos = st.session_state.setdefault("_pyroscope_puntos", [])
            poligono_cerrado = st.session_state.setdefault("_pyroscope_poligono_cerrado", False)
            grid = resultado.sistema_coordenadas
            if modo_medicion == "Vista":
                st.image(capas[capa_activa], caption=capa_activa, width="stretch")
            else:
                if modo_medicion == "Inspección de píxel":
                    punto_inspeccionado = st.session_state.get("_pyroscope_pixel_inspeccionado")
                    puntos_vista = [punto_inspeccionado] if punto_inspeccionado else []
                else:
                    puntos_vista = puntos

                vista_medicion = dibujar_marcas(
                    capas[capa_activa],
                    puntos_vista,
                    poligono_cerrado=poligono_cerrado and modo_medicion == "Área de polígono",
                    conectar_por_pares=modo_medicion == "Distancia entre puntos",
                )
                evento = streamlit_image_coordinates(
                    vista_medicion,
                    width=ANCHO_MEDICION,
                    key=f"pyroscope_coordinate_click_{firma_imagen}_{modo_medicion}_{capa_activa}",
                    cursor="crosshair",
                )
                if evento and evento.get("unix_time") != st.session_state.get("_pyroscope_ultimo_clic"):
                    ancho_mostrado = float(evento.get("width", ANCHO_MEDICION))
                    alto_mostrado = float(
                        evento.get("height", ANCHO_MEDICION * tc.shape[0] / tc.shape[1])
                    )
                    punto_pixel = grid.punto_de_vista_a_pixel(
                        float(evento["x"]),
                        float(evento["y"]),
                        ancho_mostrado,
                        alto_mostrado,
                    )
                    st.session_state["_pyroscope_ultimo_clic"] = evento.get("unix_time")
                    if modo_medicion == "Inspección de píxel":
                        st.session_state["_pyroscope_pixel_inspeccionado"] = punto_pixel
                    else:
                        puntos.append(punto_pixel)
                        st.session_state["_pyroscope_puntos"] = puntos
                        st.session_state["_pyroscope_poligono_cerrado"] = False
                    st.rerun()

                if modo_medicion == "Distancia entre puntos":
                    controles = st.columns(2)
                    if controles[0].button("Deshacer último punto", disabled=not puntos):
                        st.session_state["_pyroscope_puntos"] = puntos[:-1]
                        st.rerun()
                    if controles[1].button("Borrar marcas", disabled=not puntos):
                        st.session_state["_pyroscope_puntos"] = []
                        st.rerun()
                    for indice in range(0, len(puntos) - 1, 2):
                        distancia, unidad = grid.distancia_entre_puntos(
                            puntos[indice], puntos[indice + 1]
                        )
                        st.write(
                            f"Tramo {indice // 2 + 1}: **{formato_distancia(distancia, unidad)}**"
                        )
                    if len(puntos) % 2:
                        st.info(f"Punto {len(puntos)} marcado; añade otro para completar el tramo.")
                elif modo_medicion == "Área de polígono":
                    controles = st.columns(3)
                    if controles[0].button("Deshacer vértice", disabled=not puntos):
                        st.session_state["_pyroscope_puntos"] = puntos[:-1]
                        st.session_state["_pyroscope_poligono_cerrado"] = False
                        st.rerun()
                    cerrar_habilitado = len(puntos) >= 3
                    if controles[1].button("Cerrar polígono", disabled=not cerrar_habilitado):
                        st.session_state["_pyroscope_poligono_cerrado"] = True
                        st.rerun()
                    if controles[2].button("Borrar marcas", disabled=not puntos):
                        st.session_state["_pyroscope_puntos"] = []
                        st.session_state["_pyroscope_poligono_cerrado"] = False
                        st.rerun()
                    if poligono_cerrado and len(puntos) >= 3:
                        area_manual, unidad_manual = grid.area_de_poligono(puntos)
                        perimetro_manual, unidad_perimetro_manual = grid.longitud_de_linea(
                            puntos, cerrar=True
                        )
                        medida1, medida2 = st.columns(2)
                        medida1.metric("Área manual", formato_area(area_manual, unidad_manual))
                        medida2.metric(
                            "Perímetro del polígono",
                            formato_distancia(perimetro_manual, unidad_perimetro_manual),
                        )
                elif modo_medicion == "Inspección de píxel":
                    punto_inspeccionado = st.session_state.get("_pyroscope_pixel_inspeccionado")
                    if punto_inspeccionado:
                        x_px, y_px = punto_inspeccionado
                        x_coord, y_coord = grid.pixel_a_coordenadas(x_px, y_px)
                        st.write(f"Píxel inspeccionado: **({x_px:.0f}, {y_px:.0f})**")
                        if gsd_m_por_px is not None:
                            st.caption(f"Coordenadas métricas locales: {x_coord:.2f}, {y_coord:.2f} m")

            if modo_medicion in ("Distancia entre puntos", "Área de polígono"):
                elementos = []
                for indice, (x_px, y_px) in enumerate(puntos, start=1):
                    x_coord, y_coord = grid.pixel_a_coordenadas(x_px, y_px)
                    elementos.append(
                        {
                            "id": f"punto-{indice}",
                            "tipo": "punto",
                            "coordenadas_px": [x_px, y_px],
                            "coordenadas_rejilla": [x_coord, y_coord],
                        }
                    )
                if modo_medicion == "Distancia entre puntos":
                    for indice in range(0, len(puntos) - 1, 2):
                        valor, unidad = grid.distancia_entre_puntos(
                            puntos[indice], puntos[indice + 1]
                        )
                        elementos.append(
                            {
                                "id": f"distancia-{indice // 2 + 1}",
                                "tipo": "linea",
                                "vertices_px": [list(puntos[indice]), list(puntos[indice + 1])],
                                "distancia": {"valor": valor, "unidad": unidad},
                            }
                        )
                if modo_medicion == "Área de polígono" and poligono_cerrado and len(puntos) >= 3:
                    valor_area, unidad_poligono = grid.area_de_poligono(puntos)
                    elementos.append(
                        {
                            "id": "poligono-1",
                            "tipo": "poligono",
                            "vertices_px": [list(punto) for punto in puntos],
                            "area": {"valor": valor_area, "unidad": unidad_poligono},
                        }
                    )
                anotaciones = {
                    "esquema": "pyroscope-imagen-v1",
                    "imagen_id": firma_imagen,
                    "sistema_coordenadas": grid.a_dict(),
                    "elementos": elementos,
                }
                st.download_button(
                    "Descargar puntos y medidas JSON",
                    data=json.dumps(anotaciones, ensure_ascii=False, indent=2).encode("utf-8"),
                    file_name="pyroscope_mediciones.json",
                    mime="application/json",
                )
    return (
        superposicion,
        vista_semantica,
        descarga_overlay.getvalue(),
        descarga_mascara.getvalue(),
    )
