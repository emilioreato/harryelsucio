"""Interfaz inicial PyroScope: delineación heurística de superficie afectada."""

from __future__ import annotations

import hashlib
import json
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
st.title("PyroScope · Delimitación de superficie afectada")
st.write(
    "Carga una pareja alineada True Color + SWIR. El prototipo propone una máscara "
    "con la señal rojiza SWIR y el contexto True Color, y dibuja el perímetro estimado sobre True Color."
)
st.info(
    "Esta primera versión aborda el reto básico: área afectada. No detecta fuego activo. "
    "Filtra manchas separadas que estén lejos del foco principal. Las entradas JPEG son "
    "composiciones visuales, no bandas calibradas; el contorno requiere revisión humana."
)

with st.sidebar:
    st.header("Entrada")
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
            st.stop()
        true_bytes = true_file.getvalue()
        swir_bytes = swir_file.getvalue()

    st.header("Ajustes del segmentador")
    sensibilidad = st.slider(
        "Sensibilidad", min_value=1, max_value=10, value=5,
        help="Al aumentarla, se admite más variación dentro de la clase de color candidata.",
    )
    numero_clases = st.slider(
        "Grupos de color por escena", min_value=4, max_value=10, value=7,
        help="El agrupamiento se ajusta a los colores de cada pareja, no a una máscara etiquetada.",
    )
    area_minima_pct = st.slider(
        "Descartar objetos menores (% de imagen)",
        min_value=0.01,
        max_value=1.0,
        value=0.15,
        step=0.01,
    )
    distancia_maxima_pct = st.slider(
        "Distancia máxima del foco principal (% del lado mayor)",
        min_value=3,
        max_value=20,
        value=10,
        help=(
            "Las regiones desconectadas que superen esta distancia desde la zona "
            "candidata principal se descartan como falsos positivos remotos."
        ),
    )
    st.header("Coordenadas y medidas")
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
    )
    return tc, sw, resultado


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

with st.spinner("Analizando las composiciones..."):
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
        )
    except Exception as exc:
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

st.subheader(escena)
metrica1, metrica2, metrica3, metrica4, metrica5 = st.columns(5)
metrica1.metric("Zona candidata", f"{resultado.proporcion * 100:.1f} % de la imagen")
metrica2.metric("Área calculada", _formato_area(area_calculada, unidad_area))
metrica3.metric("Perímetro estimado", _formato_distancia(perimetro, unidad_perimetro))
metrica4.metric("Píxeles protegidos como posible agua", f"{resultado.pixeles_agua_excluidos:,}")
metrica5.metric(
    "Componentes remotos descartados",
    str(resultado.componentes_remotos_descartados),
    help=f"Radio máximo desde la zona principal: {resultado.distancia_maxima_px} px.",
)
if resultado.sistema_coordenadas.gsd_x_m is not None:
    st.caption(
        "GSD aplicado a la vista analizada: "
        f"{resultado.sistema_coordenadas.gsd_x_m:.3f} × "
        f"{resultado.sistema_coordenadas.gsd_y_m:.3f} m/píxel, "
        "ajustado automáticamente al reducir la imagen."
    )

col1, col2, col3 = st.columns(3)
with col1:
    st.image(tc, caption="True Color (vista reducida solo para procesar/mostrar)", use_container_width=True)
with col2:
    st.image(swir, caption="SWIR (composición renderizada)", use_container_width=True)
with col3:
    st.image(superposicion, caption="Área candidata y perímetro estimado", use_container_width=True)

st.subheader("Mediciones interactivas")
modo_medicion = st.radio(
    "Herramienta",
    ("Sin medir", "Distancia entre puntos", "Área de polígono"),
    horizontal=True,
)
st.caption(
    "Haz clic sobre la imagen para añadir puntos. En distancia, cada dos puntos forman "
    "un tramo; en área, marca vértices y cierra el polígono."
)

firma_imagen = hashlib.sha256(true_bytes + swir_bytes).hexdigest()[:20]
if st.session_state.get("_pyroscope_firma_imagen") != firma_imagen:
    st.session_state["_pyroscope_firma_imagen"] = firma_imagen
    st.session_state["_pyroscope_puntos"] = []
    st.session_state["_pyroscope_poligono_cerrado"] = False
    st.session_state["_pyroscope_ultimo_clic"] = None

puntos = st.session_state.setdefault("_pyroscope_puntos", [])
poligono_cerrado = st.session_state.setdefault("_pyroscope_poligono_cerrado", False)
if modo_medicion == "Sin medir":
    st.image(superposicion, caption="Vista de análisis", width=ANCHO_MEDICION)
else:
    vista_medicion = _dibujar_marcas(
        superposicion,
        puntos,
        poligono_cerrado=poligono_cerrado and modo_medicion == "Área de polígono",
        conectar_por_pares=modo_medicion == "Distancia entre puntos",
    )
    evento = streamlit_image_coordinates(
        vista_medicion,
        width=ANCHO_MEDICION,
        key=f"pyroscope_coordinate_click_{firma_imagen}",
        cursor="crosshair",
    )
    if evento and evento.get("unix_time") != st.session_state.get("_pyroscope_ultimo_clic"):
        ancho_mostrado = float(evento.get("width", ANCHO_MEDICION))
        alto_mostrado = float(
            evento.get("height", ANCHO_MEDICION * tc.shape[0] / tc.shape[1])
        )
        x_px = float(evento["x"]) * tc.shape[1] / ancho_mostrado
        y_px = float(evento["y"]) * tc.shape[0] / alto_mostrado
        x_px = min(max(x_px, 0.0), tc.shape[1] - 1.0)
        y_px = min(max(y_px, 0.0), tc.shape[0] - 1.0)
        puntos.append((x_px, y_px))
        st.session_state["_pyroscope_puntos"] = puntos
        st.session_state["_pyroscope_poligono_cerrado"] = False
        st.session_state["_pyroscope_ultimo_clic"] = evento.get("unix_time")
        st.rerun()

    controles = st.columns(3)
    if controles[0].button("Deshacer último punto", disabled=not puntos):
        st.session_state["_pyroscope_puntos"] = puntos[:-1]
        st.session_state["_pyroscope_poligono_cerrado"] = False
        st.rerun()
    cerrar_habilitado = modo_medicion == "Área de polígono" and len(puntos) >= 3
    if controles[1].button("Cerrar polígono", disabled=not cerrar_habilitado):
        st.session_state["_pyroscope_poligono_cerrado"] = True
        st.rerun()
    if controles[2].button("Borrar marcas", disabled=not puntos):
        st.session_state["_pyroscope_puntos"] = []
        st.session_state["_pyroscope_poligono_cerrado"] = False
        st.rerun()

    grid = resultado.sistema_coordenadas
    if modo_medicion == "Distancia entre puntos":
        for indice in range(0, len(puntos) - 1, 2):
            distancia, unidad = grid.distancia_entre_puntos(
                puntos[indice], puntos[indice + 1]
            )
            st.write(
                f"Puntos {indice + 1}–{indice + 2}: "
                f"**{_formato_distancia(distancia, unidad)}**"
            )
        if len(puntos) % 2:
            st.info(f"Punto {len(puntos)} marcado; añade otro para completar la distancia.")
    elif modo_medicion == "Área de polígono" and poligono_cerrado and len(puntos) >= 3:
        area_manual, unidad_manual = grid.area_de_poligono(puntos)
        perimetro_manual, unidad_perimetro_manual = grid.longitud_de_linea(
            puntos, cerrar=True
        )
        st.write(f"Área del polígono: **{_formato_area(area_manual, unidad_manual)}**")
        st.write(
            "Perímetro del polígono: "
            f"**{_formato_distancia(perimetro_manual, unidad_perimetro_manual)}**"
        )

    if gsd_m_por_px is None:
        st.info(
            "Sin GSD, las medidas se expresan en píxeles y píxeles cuadrados. "
            "El GSD convierte escala, pero para asociar datos con una ubicación real "
            "también harán falta el CRS y la transformación geográfica de la imagen."
        )

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
            valor, unidad = grid.distancia_entre_puntos(puntos[indice], puntos[indice + 1])
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

st.caption(
    f"Procesamiento a {tc.shape[1]} × {tc.shape[0]} px para respuesta rápida. "
    "Sin georreferenciación no se calculan hectáreas ni coordenadas. "
    "El contorno no es una probabilidad ni una delimitación oficial."
)

descarga_overlay = BytesIO()
Image.fromarray(superposicion).save(descarga_overlay, format="PNG")
descarga_mascara = BytesIO()
Image.fromarray(resultado.mascara.astype(np.uint8) * 255).save(descarga_mascara, format="PNG")

desc1, desc2 = st.columns(2)
with desc1:
    st.download_button(
        "Descargar superposición PNG",
        data=descarga_overlay.getvalue(),
        file_name="pyroscope_perimetro_estimado.png",
        mime="image/png",
    )
with desc2:
    st.download_button(
        "Descargar máscara PNG",
        data=descarga_mascara.getvalue(),
        file_name="pyroscope_mascara_area_candidata.png",
        mime="image/png",
    )

with st.expander("Cómo interpretar este resultado"):
    st.markdown(
        """
        - El relleno y la línea amarilla muestran la **hipótesis automática** del algoritmo.
        - Las escenas de ejemplo se procesan solo con True Color y SWIR; la imagen **Wildfires** no se usa como entrada ni como etiqueta.
        - Ajusta sensibilidad y tamaño mínimo, compara ambas composiciones y revisa los falsos positivos.
        - El resultado separa superficie candidata de fondo; todavía no separa con certeza suelo quemado, suelo desnudo oscuro u otras cubiertas parecidas.
        """
    )
