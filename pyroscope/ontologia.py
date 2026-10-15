"""Clases de salida separadas de las capas de observación y de oclusión."""

from __future__ import annotations

from enum import IntEnum


class ClaseSemantica(IntEnum):
    """Ontología compacta compartida por el motor y las interfaces."""

    INDETERMINADO = 0
    VEGETACION = 1
    AGUA_POSIBLE = 2
    HUMO_PROBABLE = 3
    SUPERFICIE_AFECTADA_CANDIDATA = 4
    FUEGO_ACTIVO_POSIBLE = 5


ETIQUETAS_CLASE = {
    ClaseSemantica.INDETERMINADO: "Sin clasificar / oculto",
    ClaseSemantica.VEGETACION: "Vegetación (verdor relativo)",
    ClaseSemantica.AGUA_POSIBLE: "Agua posible",
    ClaseSemantica.HUMO_PROBABLE: "Humo probable (oclusión)",
    ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA: "Superficie afectada candidata",
    ClaseSemantica.FUEGO_ACTIVO_POSIBLE: "Posible fuego activo",
}
