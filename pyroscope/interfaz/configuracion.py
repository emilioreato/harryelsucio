"""Rutas y límites de presentación para la interfaz Streamlit."""

from pathlib import Path


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
CARPETA_EJEMPLOS = RAIZ_REPOSITORIO / "DOCUMENTACION" / "Presentacion reto"
ESCENAS = {
    "Niebla (Huelva)": "Niebla (Huelva)",
    "La Mierla (Guadalajara)": "La Mierla (Guadalajara)",
    "Madrid-Ávila": "Madrid-Avila",
}
MAX_LADO_ANALISIS = 1800
ANCHO_MEDICION = 1000
ALTO_MEDICION = 560
