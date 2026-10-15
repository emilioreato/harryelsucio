"""Punto de entrada de la web PyroScope y su backend Python."""

import argparse

from pyroscope.servidor_web import ejecutar_servidor


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inicia la aplicación local PyroScope.")
    parser.add_argument("--port", type=int, default=8501, help="Puerto HTTP local (por defecto: 8501).")
    parser.add_argument("--no-browser", action="store_true", help="No abrir automáticamente una pestaña.")
    arguments = parser.parse_args()
    if not 1 <= arguments.port <= 65535:
        parser.error("--port debe estar entre 1 y 65535.")
    if not ejecutar_servidor(puerto=arguments.port, abrir_navegador=not arguments.no_browser):
        raise SystemExit(2)
