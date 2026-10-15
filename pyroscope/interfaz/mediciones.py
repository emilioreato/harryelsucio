"""Vista del plano, capas y herramientas interactivas de medición."""

from __future__ import annotations

from io import BytesIO
import hashlib
import json

import numpy as np
import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

from ..segmentacion import ResultadoAreaAfectada
from ..visualizacion import crear_superposicion, crear_vista_clasificacion
from .configuracion import ALTO_MEDICION, ANCHO_MEDICION
from .presentacion import dibujar_marcas, formato_area, formato_distancia


def renderizar_plano(
    vista_col,
    tc,
    swir,
    resultado: ResultadoAreaAfectada,
    true_bytes: bytes,
    swir_bytes: bytes,
):
    superposicion = crear_superposicion(tc, resultado)

    descarga_overlay = BytesIO()

    Image.fromarray(superposicion).save(descarga_overlay, format="PNG")

    descarga_mascara = BytesIO()

    Image.fromarray(resultado.mascara.astype(np.uint8) * 255).save(descarga_mascara, format="PNG")

    vista_semantica = crear_vista_clasificacion(tc, resultado)
    alto_imagen, ancho_imagen = tc.shape[:2]
    escala_vista = min(
        ANCHO_MEDICION / ancho_imagen,
        ALTO_MEDICION / alto_imagen,
    )
    ancho_vista = max(1, round(ancho_imagen * escala_vista))

    capas = {
        "Superposición": tc,
        "True Color": tc,
        "SWIR": swir,
        "Candidatos + humo": vista_semantica,
    }

    with vista_col:
        with st.container(border=True):
            st.markdown(
                '<div class="pyro-section-heading"><strong>Plano de análisis</strong></div>',
                unsafe_allow_html=True,
            )
            controles_vista = st.columns([1.7, 1, 1], gap="small")
            capa_activa = controles_vista[0].selectbox(
                "Capa",
                tuple(capas),
                key="pyroscope_capa_activa",
            )
            mostrar_segmentacion = controles_vista[1].toggle(
                "Segmentación",
                value=True,
                key="pyroscope_ver_segmentacion",
            )
            mostrar_marcas = controles_vista[2].toggle(
                "Marcas",
                value=True,
                key="pyroscope_ver_marcas",
            )
            st.markdown('<div class="pyro-divider"></div>', unsafe_allow_html=True)
            modo_medicion = st.radio(
                "Herramienta de medición",
                ("Vista", "Distancia entre puntos", "Área de polígono", "Inspección de píxel"),
                horizontal=True,
                label_visibility="collapsed",
                key="pyroscope_modo_medicion_ui",
            )

            firma_imagen = hashlib.sha256(true_bytes + swir_bytes).hexdigest()[:20]
            if st.session_state.get("_pyroscope_firma_imagen") != firma_imagen:
                st.session_state["_pyroscope_firma_imagen"] = firma_imagen
                st.session_state["_pyroscope_puntos"] = []
                st.session_state["_pyroscope_poligono_cerrado"] = False
                st.session_state["_pyroscope_ultimo_clic"] = None
                st.session_state["_pyroscope_pixel_inspeccionado"] = None
                st.session_state["_pyroscope_ultima_herramienta"] = None

            ultima_herramienta = st.session_state.get("_pyroscope_ultima_herramienta")
            if modo_medicion != "Vista":
                if ultima_herramienta and ultima_herramienta != modo_medicion:
                    st.session_state["_pyroscope_puntos"] = []
                    st.session_state["_pyroscope_poligono_cerrado"] = False
                    st.session_state["_pyroscope_pixel_inspeccionado"] = None
                st.session_state["_pyroscope_ultima_herramienta"] = modo_medicion
            puntos = st.session_state.setdefault("_pyroscope_puntos", [])
            poligono_cerrado = st.session_state.setdefault("_pyroscope_poligono_cerrado", False)
            grid = resultado.sistema_coordenadas
            if capa_activa == "Candidatos + humo":
                imagen_base = vista_semantica if mostrar_segmentacion else tc
            else:
                imagen_base = capas[capa_activa]
                if mostrar_segmentacion:
                    imagen_base = crear_superposicion(imagen_base, resultado)
            if modo_medicion == "Vista":
                imagen_vista = imagen_base
                herramienta_anterior = st.session_state.get("_pyroscope_ultima_herramienta")
                punto_inspeccionado = st.session_state.get("_pyroscope_pixel_inspeccionado")
                if mostrar_marcas and herramienta_anterior == "Inspección de píxel" and punto_inspeccionado:
                    marcas_vista = [punto_inspeccionado]
                else:
                    marcas_vista = puntos if mostrar_marcas else []
                if marcas_vista:
                    imagen_vista = dibujar_marcas(
                        imagen_vista,
                        marcas_vista,
                        poligono_cerrado=(
                            poligono_cerrado and herramienta_anterior == "Área de polígono"
                        ),
                        conectar_por_pares=(herramienta_anterior == "Distancia entre puntos"),
                    )
                st.image(imagen_vista, width=ancho_vista)
            else:
                if modo_medicion == "Inspección de píxel":
                    punto_inspeccionado = st.session_state.get("_pyroscope_pixel_inspeccionado")
                    puntos_vista = [punto_inspeccionado] if punto_inspeccionado else []
                else:
                    puntos_vista = puntos

                vista_medicion = dibujar_marcas(
                    imagen_base,
                    puntos_vista if mostrar_marcas else [],
                    poligono_cerrado=(
                        mostrar_marcas
                        and poligono_cerrado
                        and modo_medicion == "Área de polígono"
                    ),
                    conectar_por_pares=(
                        mostrar_marcas and modo_medicion == "Distancia entre puntos"
                    ),
                )
                evento = streamlit_image_coordinates(
                    vista_medicion,
                    width=ancho_vista,
                    key=f"pyroscope_coordinate_click_{firma_imagen}_{modo_medicion}_{capa_activa}",
                    cursor="crosshair",
                )
                if evento and evento.get("unix_time") != st.session_state.get("_pyroscope_ultimo_clic"):
                    ancho_mostrado = float(evento.get("width", ancho_vista))
                    alto_mostrado = float(
                        evento.get("height", ancho_vista * tc.shape[0] / tc.shape[1])
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
                        if grid.gsd_x_m is not None:
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
        vista_semantica,
        descarga_overlay.getvalue(),
        descarga_mascara.getvalue(),
    )
