"""Compara la estabilidad del perfil en las escenas disponibles, sin ground truth.

Ejemplo:
    python scripts/evaluar_estabilidad_escenas.py --max-lado 900 --sensibilidades 4,5,6

Los píxeles, componentes y tiempos son diagnósticos de salida. No son métricas
de precisión ni superficie terrestre: las escenas actuales no tienen máscaras
de referencia independientes alineadas.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pyroscope.imagenes import abrir_rgb, validar_par_alineado
from pyroscope.interfaz.configuracion import listar_escenas_disponibles
from pyroscope.segmentacion import segmentar_superficie_afectada


def _sensibilidades(texto: str) -> tuple[int, ...]:
    try:
        valores = tuple(int(item.strip()) for item in texto.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Usa una lista como 4,5,6.") from exc
    if not valores or any(not 1 <= valor <= 10 for valor in valores):
        raise argparse.ArgumentTypeError("Cada sensibilidad debe estar entre 1 y 10.")
    if len(set(valores)) != len(valores):
        raise argparse.ArgumentTypeError("No repitas sensibilidades.")
    return valores


def evaluar(escena, max_lado: int, sensibilidades: tuple[int, ...]) -> dict:
    true_color, tamano_tc = abrir_rgb(escena.true_color.read_bytes(), max_lado)
    swir, tamano_swir = abrir_rgb(escena.swir.read_bytes(), max_lado)
    validar_par_alineado(true_color, swir)
    if tamano_tc != tamano_swir:
        raise ValueError(f"La pareja de {escena.nombre} no tiene dimensiones originales iguales.")

    ejecuciones = []
    for sensibilidad in sensibilidades:
        inicio = time.perf_counter()
        resultado = segmentar_superficie_afectada(
            true_color,
            swir,
            metodo="contextual_hibrida",
            sensibilidad=sensibilidad,
            area_minima_pct=0.15,
            distancia_maxima_pct=10,
        )
        segundos = time.perf_counter() - inicio
        if resultado.mascara.dtype != np.bool_:
            raise TypeError("El motor debe devolver una máscara booleana.")
        if np.any(resultado.mascara & resultado.mascara_humo):
            raise ValueError("La máscara visible se solapa con la capa de humo.")
        componentes = cv2.connectedComponentsWithStats(
            resultado.mascara.astype(np.uint8), connectivity=8
        )[0] - 1
        ejecuciones.append(
            {
                "sensibilidad": sensibilidad,
                "pixeles_candidatos": int(resultado.mascara.sum()),
                "fraccion_imagen_pct": round(float(resultado.mascara.mean() * 100), 4),
                "componentes_finales": int(componentes),
                "componentes_remotos_descartados": int(
                    resultado.componentes_remotos_descartados
                ),
                "segundos": round(segundos, 3),
            }
        )

    return {
        "escena": escena.nombre,
        "fecha": escena.fecha,
        "tamano_original_px": list(tamano_tc),
        "rejilla_trabajo_px": [int(true_color.shape[1]), int(true_color.shape[0])],
        "ejecuciones": ejecuciones,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-lado", type=int, default=900)
    parser.add_argument("--sensibilidades", type=_sensibilidades, default=(4, 5, 6))
    parser.add_argument("--escena", help="Filtra por parte del nombre de escena.")
    args = parser.parse_args()
    if args.max_lado < 64 or args.max_lado > 2500:
        parser.error("--max-lado debe estar entre 64 y 2500.")

    escenas = tuple(
        escena
        for escena in listar_escenas_disponibles()
        if not args.escena or args.escena.casefold() in escena.nombre.casefold()
    )
    if not escenas:
        parser.error("No se encontró ninguna escena que coincida con el filtro.")

    informe = {
        "metodo": "contextual_hibrida",
        "max_lado": args.max_lado,
        "area_minima_pct": 0.15,
        "distancia_maxima_pct": 10,
        "conservar_focos_separados": False,
        "sensibilidades": args.sensibilidades,
        "limitacion": (
            "No hay máscaras de referencia independientes; los píxeles y componentes "
            "describen estabilidad de salida, no precisión ni área real."
        ),
        "escenas": [evaluar(escena, args.max_lado, args.sensibilidades) for escena in escenas],
    }
    print(json.dumps(informe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
