"""Sistema común de coordenadas para imágenes, máscaras y capas auxiliares."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any

import numpy as np
from pyproj import CRS


@dataclass(frozen=True)
class SistemaCoordenadasImagen:
    """Define una rejilla de píxeles y, opcionalmente, su escala o georreferencia.

    ``x_px`` y ``y_px`` se miden desde la esquina superior izquierda de la imagen.
    Si se aporta GSD, las coordenadas locales se expresan en metros hacia la
    derecha y hacia abajo. ``transformacion_affine`` usa el orden GDAL/rasterio
    ``(a, b, c, d, e, f)`` y permite añadir una georreferencia real más adelante.
    """

    ancho_px: int
    alto_px: int
    gsd_x_m: float | None = None
    gsd_y_m: float | None = None
    transformacion_affine: tuple[float, float, float, float, float, float] | None = None
    crs: str | None = None

    def __post_init__(self) -> None:
        if self.ancho_px < 1 or self.alto_px < 1:
            raise ValueError("La rejilla debe tener anchura y altura positivas.")
        if (self.gsd_x_m is None) != (self.gsd_y_m is None):
            raise ValueError("Indica el GSD de ambos ejes o deja ambos sin definir.")
        if self.gsd_x_m is not None and (self.gsd_x_m <= 0 or self.gsd_y_m <= 0):
            raise ValueError("El GSD debe ser positivo y expresarse en metros por píxel.")
        if self.gsd_x_m is not None and self.transformacion_affine is not None:
            raise ValueError("Usa GSD local o una transformación geográfica, no ambas.")
        if self.transformacion_affine is not None and len(self.transformacion_affine) != 6:
            raise ValueError("La transformación affine debe tener seis coeficientes.")
        if self.crs is not None and self.transformacion_affine is None:
            raise ValueError("Un CRS requiere una transformación affine de la imagen.")
        if self.crs is not None:
            CRS.from_user_input(self.crs)

    @property
    def tipo(self) -> str:
        if self.transformacion_affine is not None:
            return "georreferenciado"
        if self.gsd_x_m is not None:
            return "local_metrico"
        return "pixel"

    @property
    def unidad_pixel(self) -> str:
        return "m²" if self.area_pixel_m2 is not None else "px²"

    @property
    def area_pixel_m2(self) -> float | None:
        if self.gsd_x_m is not None and self.gsd_y_m is not None:
            return self.gsd_x_m * self.gsd_y_m
        if self.transformacion_affine is None or self.crs is None:
            return None

        crs = CRS.from_user_input(self.crs)
        if not crs.is_projected or len(crs.axis_info) < 2:
            return None
        a, b, _, d, e, _ = self.transformacion_affine
        factor_x = crs.axis_info[0].unit_conversion_factor
        factor_y = crs.axis_info[1].unit_conversion_factor
        if factor_x is None or factor_y is None:
            return None
        return abs(a * e - b * d) * factor_x * factor_y

    def pixel_a_coordenadas(self, x_px: float, y_px: float) -> tuple[float, float]:
        """Convierte una posición continua de píxel (columna, fila) a la rejilla."""
        if self.transformacion_affine is not None:
            a, b, c, d, e, f = self.transformacion_affine
            return a * x_px + b * y_px + c, d * x_px + e * y_px + f
        if self.gsd_x_m is not None and self.gsd_y_m is not None:
            return x_px * self.gsd_x_m, y_px * self.gsd_y_m
        return x_px, y_px

    def distancia_entre_puntos(
        self, punto_a: tuple[float, float], punto_b: tuple[float, float]
    ) -> tuple[float, str]:
        """Devuelve la distancia entre dos puntos de imagen y su unidad."""
        xa, ya = self.pixel_a_coordenadas(*punto_a)
        xb, yb = self.pixel_a_coordenadas(*punto_b)
        if self.transformacion_affine is not None and self.crs is not None:
            crs = CRS.from_user_input(self.crs)
            if crs.is_geographic:
                geod = crs.get_geod()
                _, _, distancia_m = geod.inv(xa, ya, xb, yb)
                return abs(float(distancia_m)), "m"
            if crs.is_projected and len(crs.axis_info) >= 2:
                factor_x = crs.axis_info[0].unit_conversion_factor
                factor_y = crs.axis_info[1].unit_conversion_factor
                if factor_x is not None and factor_y is not None:
                    return hypot((xb - xa) * factor_x, (yb - ya) * factor_y), "m"
        if self.gsd_x_m is not None and self.gsd_y_m is not None:
            return hypot(xb - xa, yb - ya), "m"
        if self.transformacion_affine is not None:
            return hypot(xb - xa, yb - ya), "unidades del CRS"
        return hypot(xb - xa, yb - ya), "px"

    def area_de_pixeles(self, numero_pixeles: int | float) -> tuple[float, str]:
        """Calcula área de celdas de máscara; conserva px² si falta escala."""
        if numero_pixeles < 0:
            raise ValueError("El número de píxeles no puede ser negativo.")
        if self.area_pixel_m2 is not None:
            return float(numero_pixeles) * self.area_pixel_m2, "m²"
        return float(numero_pixeles), "px²"

    def longitud_de_linea(
        self,
        vertices_px: list[tuple[float, float]] | tuple[tuple[float, float], ...],
        *,
        cerrar: bool = False,
    ) -> tuple[float, str]:
        """Mide una línea dibujada en la imagen, opcionalmente cerrada."""
        if len(vertices_px) < 2:
            return 0.0, "m" if self.gsd_x_m is not None else "px"
        pares = list(zip(vertices_px, vertices_px[1:]))
        if cerrar:
            pares.append((vertices_px[-1], vertices_px[0]))
        medidas = [self.distancia_entre_puntos(a, b) for a, b in pares]
        unidades = {unidad for _, unidad in medidas}
        if len(unidades) != 1:
            raise ValueError("La línea contiene distancias con unidades incompatibles.")
        return sum(valor for valor, _ in medidas), medidas[0][1]

    def area_de_poligono(
        self, vertices_px: list[tuple[float, float]] | tuple[tuple[float, float], ...]
    ) -> tuple[float, str]:
        """Calcula el área de un polígono trazado en coordenadas de píxel."""
        if len(vertices_px) < 3:
            raise ValueError("Un polígono necesita al menos tres vértices.")

        coordenadas = [self.pixel_a_coordenadas(x, y) for x, y in vertices_px]
        if self.transformacion_affine is not None and self.crs is not None:
            crs = CRS.from_user_input(self.crs)
            xs, ys = zip(*coordenadas)
            if crs.is_geographic:
                area_m2, _ = crs.get_geod().polygon_area_perimeter(xs, ys)
                return abs(float(area_m2)), "m²"
            if crs.is_projected and len(crs.axis_info) >= 2:
                factor_x = crs.axis_info[0].unit_conversion_factor
                factor_y = crs.axis_info[1].unit_conversion_factor
                if factor_x is not None and factor_y is not None:
                    coordenadas = [(x * factor_x, y * factor_y) for x, y in coordenadas]
                    return _area_zapatero(coordenadas), "m²"
        unidad = (
            "unidades²"
            if self.transformacion_affine is not None
            else self.unidad_pixel
        )
        return _area_zapatero(coordenadas), unidad

    def a_dict(self) -> dict[str, Any]:
        """Serializa la referencia para adjuntarla a medidas/capas descargadas."""
        return {
            "ancho_px": self.ancho_px,
            "alto_px": self.alto_px,
            "tipo": self.tipo,
            "gsd_x_m": self.gsd_x_m,
            "gsd_y_m": self.gsd_y_m,
            "transformacion_affine": self.transformacion_affine,
            "crs": self.crs,
            "origen_pixel": "esquina_superior_izquierda",
            "ejes_pixel": {"x": "columna hacia la derecha", "y": "fila hacia abajo"},
        }


@dataclass(frozen=True)
class CapaImagen:
    """Capa ráster que declara explícitamente la rejilla en la que vive."""

    nombre: str
    datos: np.ndarray
    sistema_coordenadas: SistemaCoordenadasImagen
    unidades: str | None = None

    def __post_init__(self) -> None:
        if self.datos.shape[:2] != (
            self.sistema_coordenadas.alto_px,
            self.sistema_coordenadas.ancho_px,
        ):
            raise ValueError(
                f"La capa {self.nombre!r} no coincide con la rejilla de coordenadas."
            )


def _area_zapatero(vertices: list[tuple[float, float]]) -> float:
    xs = np.asarray([p[0] for p in vertices], dtype=np.float64)
    ys = np.asarray([p[1] for p in vertices], dtype=np.float64)
    return float(abs(np.dot(xs, np.roll(ys, -1)) - np.dot(ys, np.roll(xs, -1))) / 2.0)
