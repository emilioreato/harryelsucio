"""Rutas y límites de entrada compartidos por la interfaz web."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
CARPETA_IMAGENES = RAIZ_REPOSITORIO / "imagenes"
EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MAX_LADO_ANALISIS = 1800
MAX_LADO_CONTEXTUAL = 2500


@dataclass(frozen=True)
class EscenaDisponible:
    """Pareja fuente válida encontrada en una subcarpeta de ``imagenes``."""

    nombre: str
    true_color: Path
    swir: Path
    fecha: str | None
    referencia_wildfires: Path | None = None
    gsd_m_por_pixel: float | None = None

    @property
    def etiqueta(self) -> str:
        nombre_corto = self.nombre.split(" (", maxsplit=1)[0]
        if self.fecha:
            dia, mes, anio = self.fecha.split("/")
            return f"{nombre_corto} · {dia}/{mes}/{anio[-2:]}"
        return nombre_corto


def listar_escenas_disponibles() -> tuple[EscenaDisponible, ...]:
    """Descubre carpetas con exactamente un True Color y un SWIR compatibles."""
    if not CARPETA_IMAGENES.is_dir():
        return ()

    escenas: list[EscenaDisponible] = []
    for carpeta in sorted(CARPETA_IMAGENES.iterdir(), key=lambda ruta: ruta.name.casefold()):
        if not carpeta.is_dir():
            continue

        archivos = tuple(
            ruta
            for ruta in carpeta.iterdir()
            if ruta.is_file() and ruta.suffix.casefold() in EXTENSIONES_IMAGEN
        )
        true_color = tuple(ruta for ruta in archivos if "truecolor" in _nombre_normalizado(ruta))
        swir = tuple(ruta for ruta in archivos if "swir" in _nombre_normalizado(ruta))
        if len(archivos) != 2 or len(true_color) != 1 or len(swir) != 1:
            continue

        fechas_true = _fechas_archivo(true_color[0])
        fechas_swir = _fechas_archivo(swir[0])
        if fechas_true and fechas_swir and fechas_true != fechas_swir:
            continue

        fecha = (fechas_true or fechas_swir or (None,))[0]
        if fecha:
            fecha = f"{fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}"
        carpeta_referencias = carpeta / "referencias"
        referencias_wildfires = (
            tuple(
                ruta
                for ruta in carpeta_referencias.iterdir()
                if ruta.is_file()
                and "wildfires" in _nombre_normalizado(ruta)
                and ruta.suffix.casefold() in EXTENSIONES_IMAGEN
            )
            if carpeta_referencias.is_dir()
            else ()
        )
        referencia_wildfires = referencias_wildfires[0] if len(referencias_wildfires) == 1 else None
        gsd = _gsd_de_metadatos(carpeta / "metadatos.json")
        escenas.append(
            EscenaDisponible(
                nombre=carpeta.name,
                true_color=true_color[0],
                swir=swir[0],
                fecha=fecha,
                referencia_wildfires=referencia_wildfires,
                gsd_m_por_pixel=gsd,
            )
        )
    return tuple(escenas)


def _nombre_normalizado(ruta: Path) -> str:
    return re.sub(r"[^a-z0-9]", "", ruta.stem.casefold())


def _fechas_archivo(ruta: Path) -> tuple[str, ...]:
    return tuple(re.findall(r"\d{4}-\d{2}-\d{2}", ruta.name))


def _gsd_de_metadatos(ruta: Path) -> float | None:
    """Devuelve el GSD declarado si hay metadatos legibles y plausibles."""
    try:
        valor = json.loads(ruta.read_text(encoding="utf-8")).get("gsd_m")
        gsd = float(valor)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return gsd if math.isfinite(gsd) and gsd > 0 else None
