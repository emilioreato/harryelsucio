"""Destinos opt-in para artefactos pesados de evaluación y depuración."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

_RAIZ = Path(__file__).resolve().parents[1]


def resolver_ruta_repositorio(ruta: str | Path) -> Path:
    """Resuelve rutas relativas desde la raíz, aunque el comando se lance desde otro cwd."""
    candidata = Path(ruta).expanduser()
    if not candidata.is_absolute():
        candidata = _RAIZ / candidata
    return candidata.resolve()


@contextmanager
def directorio_salida(salida: str | Path | None, prefijo: str) -> Iterator[Path]:
    """Usa una carpeta temporal autolimpiable o una ruta explícita del operador."""
    if salida is not None:
        destino = resolver_ruta_repositorio(salida)
        destino.mkdir(parents=True, exist_ok=True)
        print(f"Artefactos conservados por solicitud en: {destino}", flush=True)
        yield destino
        return

    temporal_root = _RAIZ / ".tmp" / "salidas"
    temporal_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=prefijo, dir=temporal_root) as temporal:
        destino = Path(temporal)
        print(f"Artefactos temporales (se borran al terminar): {destino}", flush=True)
        yield destino
    for carpeta in (temporal_root, temporal_root.parent):
        try:
            carpeta.rmdir()
        except OSError:
            break
