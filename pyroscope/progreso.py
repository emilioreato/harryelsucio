"""Contrato de progreso para informar hitos sin acoplar el motor a Streamlit."""

from __future__ import annotations

from typing import Callable


ProgresoSegmentacion = Callable[[str, int], None]


def informar_progreso(
    callback: ProgresoSegmentacion | None,
    etapa: str,
    porcentaje: int,
) -> None:
    """Envía un hito del proceso si la capa llamadora lo solicitó."""
    if callback is not None:
        callback(etapa, porcentaje)
