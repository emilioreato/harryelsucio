"""Rutas y límites de entrada compartidos por la interfaz web."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
CARPETA_IMAGENES = RAIZ_REPOSITORIO / "imagenes_muestra"
CARPETA_REFERENCIAS_RETO = RAIZ_REPOSITORIO / "DOCUMENTACION" / "Presentacion reto"
EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
MAX_LADO_ANALISIS = 1800
MAX_LADO_CONTEXTUAL = 2500

# La composición precargada del reto está fijada sobre una rejilla común de
# 10 m/píxel. Las parejas de prueba generadas también declaran este GSD en sus
# metadatos. Mantener estos valores en el catálogo evita pedírselos al usuario.
GSD_FIJO_M_POR_PIXEL = {
    "La Mierla (Guadalajara)": 10.0,
    "Madrid-Avila": 10.0,
    "Niebla (Huelva)": 10.0,
}


@dataclass(frozen=True)
class EscenaDisponible:
    """Pareja fuente válida encontrada en una subcarpeta de ``imagenes_muestra``."""

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
        referencia_wildfires = _buscar_referencia_wildfires(
            carpeta,
            true_color[0],
            swir[0],
        )
        gsd = _gsd_de_metadatos(carpeta / "metadatos.json")
        if gsd is None:
            gsd = GSD_FIJO_M_POR_PIXEL.get(carpeta.name)
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


def _buscar_referencia_wildfires(
    carpeta_escena: Path,
    true_color: Path,
    swir: Path,
) -> Path | None:
    """Resuelve Wildfires en referencias locales o en el paquete canónico del reto.

    El nombre de la carpeta y la fecha de adquisición evitan asociar por error
    una referencia de otra escena o de otro día. Si queda más de una candidata,
    se omite en lugar de elegir una arbitrariamente.
    """
    fecha_pareja = set(_fechas_archivo(true_color)) | set(_fechas_archivo(swir))
    carpetas_referencia = (
        carpeta_escena / "referencias",
        CARPETA_REFERENCIAS_RETO / carpeta_escena.name,
    )
    for carpeta_referencia in carpetas_referencia:
        if not carpeta_referencia.is_dir():
            continue
        candidatas = tuple(
            ruta
            for ruta in carpeta_referencia.iterdir()
            if ruta.is_file()
            and "wildfires" in _nombre_normalizado(ruta)
            and ruta.suffix.casefold() in EXTENSIONES_IMAGEN
            and not (
                fecha_pareja
                and _fechas_archivo(ruta)
                and not (fecha_pareja & set(_fechas_archivo(ruta)))
            )
        )
        if len(candidatas) == 1:
            return candidatas[0]
        if candidatas:
            return None
    return None


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
