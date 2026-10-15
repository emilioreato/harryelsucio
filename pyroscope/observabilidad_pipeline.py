"""Contrato opcional de observabilidad para capturas reales del pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
import unicodedata

import numpy as np


logger = logging.getLogger(__name__)
RenderizarCaptura = Callable[[], np.ndarray]
CallbackCheckpoint = Callable[["CheckpointPipeline"], None]


@dataclass(frozen=True)
class CheckpointPipeline:
    """Captura de presentación asociada a un estado real del análisis."""

    id: str
    order: int
    label: str
    description: str
    kind: str
    progress: int
    image: np.ndarray
    created_at: str
    comparison_to: str | None = None
    applied: bool | None = None
    final: bool = False

    def metadata(self, image_url: str) -> dict[str, object]:
        """Devuelve solo datos ligeros; la imagen se sirve en una ruta aparte."""
        salida: dict[str, object] = {
            "id": self.id,
            "order": self.order,
            "label": self.label,
            "description": self.description,
            "kind": self.kind,
            "progress": self.progress,
            "comparison_to": self.comparison_to,
            "image": image_url,
            "created_at": self.created_at,
            "final": self.final,
        }
        if self.applied is not None:
            salida["applied"] = self.applied
        return salida


class PublicadorCheckpoint:
    """Asigna orden e IDs y mantiene best-effort el callback fuera del motor."""

    def __init__(
        self,
        callback: CallbackCheckpoint | None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._callback = callback
        self._on_error = on_error
        self._order = 0
        self._ultimo_id: str | None = None

    @property
    def activo(self) -> bool:
        return self._callback is not None

    def publicar(
        self,
        slug: str,
        label: str,
        description: str,
        *,
        kind: str,
        progress: int,
        image: np.ndarray | RenderizarCaptura,
        comparison_to: str | None = None,
        applied: bool | None = None,
        final: bool = False,
    ) -> CheckpointPipeline | None:
        """Publica una miniatura; con callback nulo no invoca su renderizador."""
        if self._callback is None:
            return None
        try:
            if kind not in {"image", "mask", "regions", "diagnostic"}:
                raise ValueError("Tipo de checkpoint no reconocido.")
            progreso = int(progress)
            if not 0 <= progreso <= 100:
                raise ValueError("El progreso del checkpoint debe estar entre 0 y 100.")
            imagen = image() if callable(image) else image
            if not isinstance(imagen, np.ndarray) or imagen.ndim != 3 or imagen.shape[2] != 3:
                raise ValueError("La previsualización del checkpoint debe ser una imagen RGB.")
            if imagen.dtype != np.uint8 or not imagen.size:
                raise ValueError("La previsualización debe ser RGB uint8 y no estar vacía.")

            orden = self._order + 1
            identificador = f"{_slug(slug)}-{orden}"
            captura = CheckpointPipeline(
                id=identificador,
                order=orden,
                label=str(label)[:80],
                description=str(description)[:300],
                kind=kind,
                progress=progreso,
                image=imagen,
                created_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                comparison_to=comparison_to or self._ultimo_id,
                applied=applied,
                final=bool(final),
            )
            self._callback(captura)
            self._order = orden
            self._ultimo_id = identificador
            return captura
        except Exception as exc:  # La telemetría nunca debe cambiar el resultado científico.
            logger.warning("Se omitió una captura del pipeline: %s", exc, exc_info=True)
            if self._on_error is not None:
                try:
                    self._on_error(exc)
                except Exception:
                    logger.debug("También falló el registro del error de observabilidad.", exc_info=True)
            return None


def _slug(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", str(valor).casefold())
    ascii_texto = normalizado.encode("ascii", "ignore").decode("ascii")
    seguro = re.sub(r"[^a-z0-9]+", "-", ascii_texto).strip("-")
    return (seguro or "checkpoint")[:48]
