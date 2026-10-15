"""Punto de entrada de la web PyroScope y su backend Python."""

from pyroscope.servidor_web import ejecutar_servidor


if __name__ == "__main__":
    if not ejecutar_servidor():
        raise SystemExit(2)
