"""Telemetría, exportación y detalles del resultado del análisis."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from ..segmentacion import ResultadoAreaAfectada
from .presentacion import formato_area, formato_distancia


def renderizar_resultados(
    telemetria_col,
    resultado: ResultadoAreaAfectada,
    nombre_detector: str,
    area_calculada: float,
    unidad_area: str,
    perimetro: float,
    unidad_perimetro: str,
    descarga_overlay: bytes,
    descarga_mascara: bytes,
    vista_semantica,
) -> None:
    with telemetria_col:
        with st.container(border=True):
            st.markdown(
                '<div class="pyro-section-heading"><strong>Resultado</strong></div>',
                unsafe_allow_html=True,
            )
            filas = st.columns(2, gap="small")
            filas[0].metric("Superficie candidata", f"{resultado.proporcion * 100:.1f}%")
            filas[1].metric("Área", formato_area(area_calculada, unidad_area))
            filas2 = st.columns(2, gap="small")
            filas2[0].metric("Perímetro", formato_distancia(perimetro, unidad_perimetro))
            filas2[1].metric("Humo", f"{resultado.mascara_humo.mean() * 100:.1f}%")
            st.caption("Hipótesis automática; requiere revisión humana.")

            descargas = st.columns(2, gap="small")
            descargas[0].download_button(
                "Mapa PNG",
                data=descarga_overlay,
                file_name="pyroscope_perimetro_estimado.png",
                mime="image/png",
                width="stretch",
            )
            descargas[1].download_button(
                "Máscara PNG",
                data=descarga_mascara,
                file_name="pyroscope_mascara_area_candidata.png",
                mime="image/png",
                width="stretch",
            )

        with st.expander("Detalles y notas", expanded=False):
            rejilla = resultado.sistema_coordenadas
            st.caption(
                f"Detector: {nombre_detector}. Rejilla: {rejilla.ancho_px} × {rejilla.alto_px} px. "
                f"Píxeles excluidos como agua: {resultado.pixeles_agua_excluidos:,}. "
                f"Regiones remotas descartadas: {resultado.componentes_remotos_descartados} "
                f"(radio máximo {resultado.distancia_maxima_px} px)."
            )
            st.caption(
                "La cobertura es una hipótesis de superficie afectada; no confirma terreno quemado ni fuego activo."
            )
            if rejilla.gsd_x_m is not None:
                st.caption(
                    f"GSD efectivo: {rejilla.gsd_x_m:.3f} × {rejilla.gsd_y_m:.3f} m/píxel."
                )
            st.markdown("**Notas de campo**")
            with st.form("pyroscope_nota_form", clear_on_submit=True):
                nota_campo = st.text_input(
                    "Nueva nota",
                    max_chars=240,
                    label_visibility="collapsed",
                    placeholder="Añadir una nota…",
                )
                nota_enviada = st.form_submit_button("Registrar nota", use_container_width=True)
            notas_campo = st.session_state.setdefault("_pyroscope_notas_campo", [])
            if nota_enviada and nota_campo.strip():
                notas_campo.insert(
                    0,
                    {
                        "hora": datetime.now(timezone.utc).strftime("%H:%M UTC"),
                        "texto": nota_campo.strip(),
                    },
                )
                st.session_state["_pyroscope_notas_campo"] = notas_campo[:12]
                notas_campo = st.session_state["_pyroscope_notas_campo"]
            if notas_campo:
                for nota in notas_campo:
                    st.caption(f"[{nota['hora']}] · {nota['texto']}")
            else:
                st.caption("Sin notas")

        with st.expander("Interpretación", expanded=False):
            st.markdown(
                f"""
                - El relleno y el contorno representan la hipótesis automática. El cian marca humo probable; el suelo oculto queda indeterminado.
                - Detector: **{nombre_detector}**. Compara las capas y revisa los falsos positivos.
                - La pareja JPEG no permite distinguir con certeza suelo quemado, suelo desnudo oscuro u otras cubiertas parecidas.
                - Activa **Conservar regiones desconectadas** si la escena puede contener focos independientes.
                """
            )

        with st.expander("Comparar clasificación", expanded=False):
            st.markdown(
                "Candidatos en naranja; humo probable en cian. La máscara final filtra ruido y regiones remotas."
            )
            st.image(vista_semantica, width=1000)
