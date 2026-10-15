"""Punto de entrada de Lumbre y su backend Python."""

import argparse

from pyroscope.servidor_web import cerrar_servidor_local, ejecutar_servidor


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inicia Lumbre, la aplicación local de análisis satelital.")
    parser.add_argument("--port", type=int, default=8501, help="Puerto HTTP local (por defecto: 8501).")
    parser.add_argument("--no-browser", action="store_true", help="No abrir automáticamente una pestaña.")
    parser.add_argument("--close", action="store_true", help="Cierra la instancia local que ya está abierta.")
    arguments = parser.parse_args()
    if arguments.close:
        if not cerrar_servidor_local():
            raise SystemExit(1)
        raise SystemExit(0)
    if not 1 <= arguments.port <= 65535:
        parser.error("--port debe estar entre 1 y 65535.")
    if not ejecutar_servidor(puerto=arguments.port, abrir_navegador=not arguments.no_browser):
        raise SystemExit(2)
