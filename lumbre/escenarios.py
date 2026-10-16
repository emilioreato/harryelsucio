"""Escenarios exploratorios de avance anisótropo desde un foco elegido a mano."""

from __future__ import annotations

import math
from typing import Any


def _numero(datos: dict[str, Any], clave: str, minimo: float, maximo: float) -> float:
    valor = datos.get(clave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{clave} debe ser un número entre {minimo:g} y {maximo:g}.")
    numero = float(valor)
    if not math.isfinite(numero) or not minimo <= numero <= maximo:
        raise ValueError(f"{clave} debe estar entre {minimo:g} y {maximo:g}.")
    return numero


def generar_escenario_progresion(
    ancho_px: int,
    alto_px: int,
    datos: dict[str, Any],
) -> dict[str, Any]:
    """Devuelve frentes ilustrativos en coordenadas de píxel, sin tiempo físico.

    Esta ecuación de forma no implementa Rothermel ni estima una tasa real de
    propagación. Su término temperatura-humedad es solo un modulador visual;
    no estima la humedad del combustible.
    """
    if isinstance(ancho_px, bool) or not isinstance(ancho_px, int) or ancho_px < 1:
        raise ValueError("El ancho de la rejilla debe ser un entero positivo.")
    if isinstance(alto_px, bool) or not isinstance(alto_px, int) or alto_px < 1:
        raise ValueError("El alto de la rejilla debe ser un entero positivo.")
    if not isinstance(datos, dict):
        raise ValueError("Los datos del escenario deben ser un objeto.")

    origen = datos.get("origin")
    if not isinstance(origen, dict):
        raise ValueError("Selecciona en la imagen un único punto de inicio.")
    x0 = _numero(origen, "x", 0.0, float(ancho_px - 1))
    y0 = _numero(origen, "y", 0.0, float(alto_px - 1))
    temperatura = _numero(datos, "temperature_c", -20.0, 60.0)
    humedad = _numero(datos, "relative_humidity_pct", 0.0, 100.0)
    viento_desde = _numero(datos, "wind_from_deg", 0.0, 359.9)
    velocidad = _numero(datos, "wind_speed_kmh", 0.0, 160.0)
    avance = _numero(datos, "base_advance_px", 0.5, 16.0)
    hora_datos = datos.get("weather_time", "")
    fuente_datos = datos.get("weather_source", "")
    if not isinstance(hora_datos, str) or len(hora_datos) > 120:
        raise ValueError("weather_time debe ser texto de hasta 120 caracteres.")
    if not isinstance(fuente_datos, str) or len(fuente_datos) > 120:
        raise ValueError("weather_source debe ser texto de hasta 120 caracteres.")
    pasos = datos.get("steps", 16)
    if isinstance(pasos, bool) or not isinstance(pasos, int) or not 4 <= pasos <= 32:
        raise ValueError("steps debe ser un entero entre 4 y 32.")

    sequedad_ambiente = ((temperatura + 20.0) / 80.0) * (1.0 - humedad / 100.0)
    factor_ambiente = 0.75 + 0.5 * sequedad_ambiente
    sesgo_viento = 0.45 * velocidad / (velocidad + 20.0) if velocidad else 0.0

    viento_hacia = (viento_desde + 180.0) % 360.0
    theta_viento = math.radians(viento_hacia - 90.0)
    muestras = 72
    angulos = [2.0 * math.pi * indice / muestras for indice in range(muestras + 1)]
    frames = []
    for paso in range(1, pasos + 1):
        radio_base = paso * avance * factor_ambiente
        frente = []
        for theta in angulos:
            radio = radio_base * (1.0 + sesgo_viento * math.cos(theta - theta_viento))
            frente.append([
                round(x0 + radio * math.cos(theta), 2),
                round(y0 + radio * math.sin(theta), 2),
            ])
        frames.append({"step": paso, "front": frente})

    return {
        "kind": "escenario_visual_exploratorio",
        "model": "frente polar anisótropo, con sesgo direccional de viento",
        "origin": {"x": round(x0, 2), "y": round(y0, 2)},
        "weather": {
            "temperature_c": temperatura,
            "relative_humidity_pct": humedad,
            "wind_from_deg": viento_desde,
            "wind_toward_deg": round(viento_hacia, 1),
            "wind_speed_kmh": velocidad,
        },
        "weather_provenance": {
            "time_and_timezone": hora_datos.strip() or None,
            "source": fuente_datos.strip() or None,
        },
        "factors": {
            "ambient_proxy_0_1": round(sequedad_ambiente, 4),
            "ambient_growth_factor": round(factor_ambiente, 4),
            "wind_anisotropy_factor": round(sesgo_viento, 4),
        },
        "base_advance_px_per_step": avance,
        "steps_have_no_physical_duration": True,
        "caveats": [
            "Escenario matemático exploratorio; no es una predicción validada.",
            "El modulador de temperatura y humedad relativa es heurístico y no estima humedad del combustible.",
            "No se modelan tipo/carga de combustible, humedad del combustible, pendiente, barreras ni cambios meteorológicos.",
            "El avance se expresa en píxeles por paso visual; no equivale a metros, minutos ni hectáreas.",
        ],
        "frames": frames,
    }
