"""Controles de entrada y configuración del análisis en la barra lateral."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ..detectores import DetectorSuperficie, listar_detectores_superficie
from .configuracion import CARPETA_EJEMPLOS, ESCENAS


@dataclass(frozen=True)
class EntradaImagenes:
    escena: str
    true_color: bytes
    swir: bytes


@dataclass(frozen=True)
class AjustesAnalisis:
    detector: DetectorSuperficie
    sensibilidad: int
    numero_clases: int
    area_minima_pct: float
    distancia_maxima_pct: float
    conservar_regiones_separadas: bool
    gsd_m_por_px: float | None


def renderizar_barra_lateral() -> tuple[EntradaImagenes | None, AjustesAnalisis]:
    """Muestra la selección de pareja y ajustes; devuelve valores sin analizar."""
    with st.sidebar:
        st.markdown(
            '<div class="pyro-eyebrow">PyroScope · estación de análisis</div>',
            unsafe_allow_html=True,
        )
        st.header("Entrada de imágenes")
        origen = st.radio("Imágenes", ("Ejemplo del reto", "Subir una pareja"))
        entrada = _leer_entrada(origen)

        st.header("Ajustes del análisis")
        detectores = {d.id: d for d in listar_detectores_superficie()}
        metodo = st.selectbox(
            "Detector de superficie",
            tuple(detectores),
            format_func=lambda detector_id: detectores[detector_id].nombre,
            help=" ".join(d.descripcion for d in detectores.values()),
        )
        detector = detectores[metodo]
        sensibilidad = st.slider(
            "Sensibilidad",
            min_value=1,
            max_value=10,
            value=5,
            help=(
                "K-Means amplía la tolerancia del candidato cromático; V2 baja los umbrales "
                "de semilla y crecimiento SWIR. En ambos casos puede aumentar el área candidata."
            ),
        )
        numero_clases = st.slider(
            "Grupos de color por escena",
            min_value=4,
            max_value=10,
            value=7,
            help="El agrupamiento se ajusta a los colores de cada pareja, no a una máscara etiquetada.",
            disabled=not detector.usa_numero_clases,
        )
        area_minima_pct = st.slider(
            "Descartar objetos menores (% de imagen)",
            min_value=0.01,
            max_value=1.0,
            value=0.15,
            step=0.01,
        )
        conservar_regiones = st.checkbox(
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
            disabled=conservar_regiones,
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

    return entrada, AjustesAnalisis(
        detector=detector,
        sensibilidad=sensibilidad,
        numero_clases=numero_clases,
        area_minima_pct=area_minima_pct,
        distancia_maxima_pct=distancia_maxima_pct,
        conservar_regiones_separadas=conservar_regiones,
        gsd_m_por_px=_validar_gsd(gsd_texto),
    )


def _leer_entrada(origen: str) -> EntradaImagenes | None:
    if origen == "Ejemplo del reto":
        escena = st.selectbox("Escena", tuple(ESCENAS))
        carpeta = CARPETA_EJEMPLOS / ESCENAS[escena]
        true_path = next(carpeta.glob("*_True_color.jpg"), None)
        swir_path = next(carpeta.glob("*_SWIR.jpg"), None)
        if true_path is None or swir_path is None:
            st.error(f"No se encontraron las dos imágenes de {escena}.")
            st.stop()
        return EntradaImagenes(escena, true_path.read_bytes(), swir_path.read_bytes())

    true_file = st.file_uploader(
        "True Color", type=("jpg", "jpeg", "png", "tif", "tiff"), key="true"
    )
    swir_file = st.file_uploader(
        "SWIR", type=("jpg", "jpeg", "png", "tif", "tiff"), key="swir"
    )
    if true_file is None or swir_file is None:
        st.caption("Sube las dos composiciones de la misma escena y adquisición.")
        return None
    return EntradaImagenes(
        "Imágenes cargadas",
        true_file.getvalue(),
        swir_file.getvalue(),
    )


def _validar_gsd(texto: str) -> float | None:
    if not texto.strip():
        return None
    try:
        gsd = float(texto.strip().replace(",", "."))
        if gsd <= 0:
            raise ValueError
        return gsd
    except ValueError:
        st.error("El GSD debe ser un número positivo en metros por píxel.")
        st.stop()
        return None
