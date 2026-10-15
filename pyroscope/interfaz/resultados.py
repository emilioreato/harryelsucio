"""Telemetría, exportación y explicación del resultado del análisis."""

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
                '<div class="pyro-section-heading"><strong>Telemetría</strong>'
                f'<span>{nombre_detector.upper()}</span></div>',
                unsafe_allow_html=True,
            )
            st.metric("Zona candidata", f"{resultado.proporcion * 100:.1f}%")
            st.progress(
                float(resultado.proporcion),
                text="Cobertura candidata de la imagen",
            )
            st.metric("Área calculada", formato_area(area_calculada, unidad_area))
            st.metric("Perímetro estimado", formato_distancia(perimetro, unidad_perimetro))
            st.metric("Humo probable", f"{resultado.mascara_humo.mean() * 100:.1f}%")
            st.metric("Píxeles excluidos como posible agua", f"{resultado.pixeles_agua_excluidos:,}")
            st.metric(
                "Componentes remotos descartados",
                str(resultado.componentes_remotos_descartados),
                help=f"Radio máximo desde la zona principal: {resultado.distancia_maxima_px} px.",
            )
            st.caption(
                f"Rejilla analizada: {tc.shape[1]} × {tc.shape[0]} px. "
                "La cobertura es una hipótesis de superficie afectada, no una probabilidad ni fuego activo."
            )
            if resultado.sistema_coordenadas.gsd_x_m is not None:
                st.caption(
                    "GSD efectivo: "
                    f"{resultado.sistema_coordenadas.gsd_x_m:.3f} × "
                    f"{resultado.sistema_coordenadas.gsd_y_m:.3f} m/píxel."
                )
            st.markdown('<div class="pyro-divider"></div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="pyro-section-heading"><strong>Acciones</strong>'
                '<span>EXPORTAR RESULTADOS</span></div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "Descargar mapa anotado PNG",
                data=descarga_overlay,
                file_name="pyroscope_perimetro_estimado.png",
                mime="image/png",
                width="stretch",
            )
            st.download_button(
                "Descargar máscara PNG",
                data=descarga_mascara,
                file_name="pyroscope_mascara_area_candidata.png",
                mime="image/png",
                width="stretch",
            )

        with st.container(border=True):
            st.markdown(
                '<div class="pyro-section-heading"><strong>Notas de campo</strong>'
                '<span>SOLO ESTA SESIÓN</span></div>',
                unsafe_allow_html=True,
            )
            with st.form("pyroscope_nota_form", clear_on_submit=True):
                nota_campo = st.text_input(
                    "Nueva nota",
                    max_chars=240,
                    label_visibility="collapsed",
                    placeholder="Añadir una nota de revisión…",
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
                    st.caption(f"[{nota['hora']}]")
                    st.write(nota["texto"])
            else:
                st.caption("No hay notas registradas.")

    st.markdown(
        '<div class="pyro-footnote">Las composiciones JPEG son imágenes renderizadas, no reflectancias calibradas. '
        'El contorno requiere revisión humana y no representa una delimitación oficial.</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Comparar clasificación por píxel y segmentación de regiones"):
        st.markdown(
            "**A · Evidencia semántica:** candidatos a superficie afectada usando SWIR + True Color; "
            "la capa cian marca humo probable y sus píxeles no se interpretan como terreno despejado. "
            "**B · Región final:** candidatos tras limpiar ruido, agruparlos y filtrar regiones lejanas."
        )
        st.image(
            vista_semantica,
            caption="Etapa A: superficie candidata en naranja; humo probable / oclusión en cian",
            width="stretch",
        )
        st.markdown(
            "**Política bajo humo:** se conserva una capa de oclusión separada, pero el suelo que tapa "
            "queda indeterminado y no recibe la misma regla SWIR que los píxeles despejados. La pareja "
            "JPEG no permite recuperar con rigor la cobertura oculta."
        )

    with st.expander("Cómo interpretar este resultado"):
        st.markdown(
            f"""
            - El relleno y la línea amarilla muestran la **hipótesis automática** del algoritmo.
            - El cian señala una **máscara probable de humo**, calculada con las dos composiciones. En esa zona el terreno subyacente queda indeterminado.
            - Detector activo: **{nombre_detector}**. K-Means agrupa las señales conjuntas; V2 usa umbrales SWIR con histéresis y contexto True Color para reducir confusiones con agua y vegetación.
            - Si la escena contiene incendios independientes, activa **Conservar regiones desconectadas**; de otro modo el filtro prioriza el componente principal y puede descartar focos separados.
            - Las escenas de ejemplo se procesan solo con True Color y SWIR; la imagen **Wildfires** no se usa como entrada ni como etiqueta.
            - Ajusta sensibilidad y tamaño mínimo, compara ambas composiciones y revisa los falsos positivos.
            - El resultado separa superficie candidata de fondo; todavía no separa con certeza suelo quemado, suelo desnudo oscuro u otras cubiertas parecidas.
            """
        )
