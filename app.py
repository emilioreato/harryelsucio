"""Interfaz inicial PyroScope: delineación heurística de superficie afectada."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
import cv2
import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

from pyroscope import (
    SistemaCoordenadasImagen,
    abrir_rgb,
    crear_superposicion,
    crear_vista_clasificacion,
    reducir_par_alineado,
    segmentar_superficie_afectada,
)


ROOT = Path(__file__).resolve().parent
CARPETA_EJEMPLOS = ROOT / "DOCUMENTACION" / "Presentacion reto"
ESCENAS = {
    "Niebla (Huelva)": "Niebla (Huelva)",
    "La Mierla (Guadalajara)": "La Mierla (Guadalajara)",
    "Madrid-Ávila": "Madrid-Avila",
}
MAX_LADO_ANALISIS = 1800
ANCHO_MEDICION = 1000


def _dibujar_marcas(
    imagen: np.ndarray,
    puntos: list[tuple[float, float]],
    *,
    poligono_cerrado: bool,
    conectar_por_pares: bool = False,
) -> np.ndarray:
    """Pinta sobre la vista las marcas manuales sin alterar sus coordenadas."""
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


def _formato_distancia(valor: float, unidad: str) -> str:
    if unidad == "m":
        return f"{valor / 1000:.3f} km" if valor >= 1000 else f"{valor:.1f} m"
    return f"{valor:.1f} {unidad}"


def _formato_area(valor: float, unidad: str) -> str:
    if unidad == "m²":
        return f"{valor:,.0f} m² ({valor / 10_000:.2f} ha)"
    return f"{valor:,.1f} {unidad}"

st.set_page_config(page_title="PyroScope · Área afectada", layout="wide")
st.markdown(
    f"<style>{(ROOT / 'assets' / 'pyroscope.css').read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)
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

with st.sidebar:
    st.markdown(
        '<div class="pyro-eyebrow">PyroScope · estación de análisis</div>',
        unsafe_allow_html=True,
    )
    st.header("Entrada de imágenes")
    origen = st.radio("Imágenes", ("Ejemplo del reto", "Subir una pareja"))

    if origen == "Ejemplo del reto":
        escena = st.selectbox("Escena", tuple(ESCENAS))
        carpeta = CARPETA_EJEMPLOS / ESCENAS[escena]
        true_path = next(carpeta.glob("*_True_color.jpg"), None)
        swir_path = next(carpeta.glob("*_SWIR.jpg"), None)
        if true_path is None or swir_path is None:
            st.error(f"No se encontraron las dos imágenes de {escena}.")
            st.stop()
        true_bytes = true_path.read_bytes()
        swir_bytes = swir_path.read_bytes()
    else:
        escena = "Imágenes cargadas"
        true_file = st.file_uploader(
            "True Color", type=("jpg", "jpeg", "png", "tif", "tiff"), key="true"
        )
        swir_file = st.file_uploader(
            "SWIR", type=("jpg", "jpeg", "png", "tif", "tiff"), key="swir"
        )
        if true_file is None or swir_file is None:
            st.caption("Sube las dos composiciones de la misma escena y adquisición.")
            true_bytes = b""
            swir_bytes = b""
            pareja_disponible = False
        else:
            true_bytes = true_file.getvalue()
            swir_bytes = swir_file.getvalue()
            pareja_disponible = True

    if origen == "Ejemplo del reto":
        pareja_disponible = True

    st.header("Ajustes del análisis")
    nombre_detector = st.selectbox(
        "Detector de superficie",
        ("K-Means conjunto", "Contraste SWIR + histéresis (V2)"),
        help=(
            "K-Means agrupa señales de ambas composiciones. V2 busca semillas con contraste "
            "rojizo SWIR y crece por zonas contiguas; True Color ayuda a vetar agua y "
            "vegetación muy verde. Ambos apartan antes las zonas con posible humo."
        ),
    )
    metodo = "kmeans" if nombre_detector == "K-Means conjunto" else "swir_histeresis"
    sensibilidad = st.slider(
        "Sensibilidad", min_value=1, max_value=10, value=5,
        help=(
            "K-Means amplía la tolerancia del candidato cromático; V2 baja los umbrales "
            "de semilla y crecimiento SWIR. En ambos casos puede aumentar el área candidata."
        ),
    )
    numero_clases = st.slider(
        "Grupos de color por escena", min_value=4, max_value=10, value=7,
        help="El agrupamiento se ajusta a los colores de cada pareja, no a una máscara etiquetada.",
        disabled=metodo != "kmeans",
    )
    area_minima_pct = st.slider(
        "Descartar objetos menores (% de imagen)",
        min_value=0.01,
        max_value=1.0,
        value=0.15,
        step=0.01,
    )
    conservar_regiones_separadas = st.checkbox(
        "Conservar regiones desconectadas",
        value=False,
        help=(
            "Por defecto se prioriza la región principal y se filtran candidatos remotos. "
            "Activa esta opción si la escena puede contener varios focos independientes."
        ),
    )
    distancia_maxima_pct = st.slider(
        "Distancia máxima del foco principal (% del lado mayor)",
        min_value=3,
        max_value=20,
        value=10,
        help=(
            "En el modo de foco principal se descartan regiones que excedan esta distancia. "
            "Se desactiva al conservar regiones desconectadas."
        ),
        disabled=conservar_regiones_separadas,
    )
    st.header("Escala de medición")
    gsd_texto = st.text_input(
        "GSD de la imagen (metros por píxel)",
        value="",
        placeholder="Déjalo vacío hasta conocerlo",
        help=(
            "Introduce el GSD real de la pareja exportada. No se deduce del JPEG: "
            "las bandas Sentinel-2 pueden tener resoluciones distintas y el visor puede reescalar la imagen."
        ),
    )

gsd_m_por_px = None
if gsd_texto.strip():
    try:
        gsd_m_por_px = float(gsd_texto.strip().replace(",", "."))
        if gsd_m_por_px <= 0:
            raise ValueError
    except ValueError:
        st.error("El GSD debe ser un número positivo en metros por píxel.")
        st.stop()

if not pareja_disponible:
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
    st.stop()


@st.cache_data(show_spinner=False, max_entries=8)
def _procesar(
    true_color: np.ndarray,
    swir: np.ndarray,
    sensibilidad_actual: int,
    clases: int,
    area_minima: float,
    distancia_maxima: int,
    gsd_x_m: float | None,
    gsd_y_m: float | None,
    metodo_actual: str,
    conservar_separadas: bool,
    _on_progress=None,
):
    tc, sw = reducir_par_alineado(true_color, swir, MAX_LADO_ANALISIS)
    factor_x = true_color.shape[1] / tc.shape[1]
    factor_y = true_color.shape[0] / tc.shape[0]
    gsd_x_actual = gsd_x_m * factor_x if gsd_x_m is not None else None
    gsd_y_actual = gsd_y_m * factor_y if gsd_y_m is not None else None
    sistema = SistemaCoordenadasImagen(
        ancho_px=tc.shape[1],
        alto_px=tc.shape[0],
        gsd_x_m=gsd_x_actual,
        gsd_y_m=gsd_y_actual,
    )
    resultado = segmentar_superficie_afectada(
        tc,
        sw,
        numero_clases=clases,
        sensibilidad=sensibilidad_actual,
        area_minima_pct=area_minima,
        distancia_maxima_pct=distancia_maxima,
        sistema_coordenadas=sistema,
        on_progress=_on_progress,
        metodo=metodo_actual,
        conservar_regiones_separadas=conservar_separadas,
    )
    return tc, sw, resultado


st.markdown(
    f'<div class="pyro-section-heading"><strong>{escena}</strong>'
    '<span>ENTRADA · TRUE COLOR + SWIR</span></div>',
    unsafe_allow_html=True,
)
with st.container(border=True):
    st.markdown(
        '<div class="pyro-section-heading"><strong>Progreso del análisis</strong>'
        '<span>AVANCE POR ETAPAS DEL MOTOR</span></div>',
        unsafe_allow_html=True,
    )
    progress_label = st.empty()
    progress_bar = st.progress(0, text="Esperando validación de las imágenes")


def actualizar_progreso(etapa: str, porcentaje: int) -> None:
    """Presenta hitos notificados por el algoritmo del backend Python."""
    porcentaje = max(0, min(100, int(porcentaje)))
    progress_label.markdown(
        f'<div class="pyro-mono">{etapa}</div>',
        unsafe_allow_html=True,
    )
    progress_bar.progress(porcentaje, text=f"{porcentaje}%")


actualizar_progreso("Leyendo y alineando las composiciones", 3)
try:
    tc_original, tamano_tc = abrir_rgb(true_bytes, MAX_LADO_ANALISIS)
    swir_original, tamano_swir = abrir_rgb(swir_bytes, MAX_LADO_ANALISIS)
except Exception as exc:
    st.error(f"No se pudieron leer las imágenes: {exc}")
    st.stop()

if tamano_tc != tamano_swir or tc_original.shape != swir_original.shape:
    st.error(
        "Las imágenes no tienen las mismas dimensiones después de leerlas. "
        "Este MVP requiere la pareja ya alineada; no la ajustará con resize."
    )
    st.stop()

try:
    gsd_x_reducido = (
        gsd_m_por_px * tamano_tc[0] / tc_original.shape[1]
        if gsd_m_por_px is not None
        else None
    )
    gsd_y_reducido = (
        gsd_m_por_px * tamano_tc[1] / tc_original.shape[0]
        if gsd_m_por_px is not None
        else None
    )
    tc, swir, resultado = _procesar(
        tc_original,
        swir_original,
        sensibilidad,
        numero_clases,
        area_minima_pct,
        distancia_maxima_pct,
        gsd_x_reducido,
        gsd_y_reducido,
        metodo,
        conservar_regiones_separadas,
        actualizar_progreso,
    )
    actualizar_progreso("Análisis completado; resultados listos", 100)
except Exception as exc:
    progress_label.markdown(
        '<div class="pyro-mono">No se pudo completar el análisis</div>',
        unsafe_allow_html=True,
    )
    st.error(f"No se pudo segmentar esta pareja: {exc}")
    st.stop()

superposicion = crear_superposicion(tc, resultado)
area_px = int(resultado.mascara.sum())
area_calculada, unidad_area = resultado.sistema_coordenadas.area_de_pixeles(area_px)
perimetro = 0.0
unidad_perimetro = "m" if resultado.sistema_coordenadas.gsd_x_m is not None else "px"
for contorno in resultado.contornos:
    vertices = [tuple(map(float, punto[0])) for punto in contorno]
    longitud, unidad_perimetro = resultado.sistema_coordenadas.longitud_de_linea(
        vertices, cerrar=True
    )
    perimetro += longitud

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

vista_col, telemetria_col = st.columns([3.2, 1.05], gap="large")
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

            vista_medicion = _dibujar_marcas(
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
                        f"Tramo {indice // 2 + 1}: **{_formato_distancia(distancia, unidad)}**"
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
                    medida1.metric("Área manual", _formato_area(area_manual, unidad_manual))
                    medida2.metric(
                        "Perímetro del polígono",
                        _formato_distancia(perimetro_manual, unidad_perimetro_manual),
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
        st.metric("Área calculada", _formato_area(area_calculada, unidad_area))
        st.metric("Perímetro estimado", _formato_distancia(perimetro, unidad_perimetro))
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
            data=descarga_overlay.getvalue(),
            file_name="pyroscope_perimetro_estimado.png",
            mime="image/png",
            width="stretch",
        )
        st.download_button(
            "Descargar máscara PNG",
            data=descarga_mascara.getvalue(),
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
