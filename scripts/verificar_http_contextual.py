"""Prueba real de HTTP: tres escenas, análisis, capas PNG y exportaciones.

Ejecutar con Lumbre ya iniciada: python scripts/verificar_http_contextual.py --url http://127.0.0.1:8501
"""
import argparse
import io
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
from _salidas import directorio_salida


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument(
        "--salida", type=Path,
        help="Conserva PNG y métricas en esta carpeta; si se omite, se borran al terminar.",
    )
    args = parser.parse_args()
    with directorio_salida(args.salida, "lumbre-http-") as carpeta:
        ejecutar(args.url, carpeta)


def ejecutar(url: str, carpeta: Path) -> None:
    base = url.rstrip("/")

    def leer(ruta, datos=None):
        request = Request(base + ruta, data=json.dumps(datos).encode() if datos else None,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=30) as respuesta:
            return respuesta.read()

    escenas = json.loads(leer("/api/scenes"))["scenes"]
    assert "contextual_hibrida" in [d["id"] for d in json.loads(leer("/api/detectors"))["detectors"]]
    carpeta.mkdir(parents=True, exist_ok=True)
    informe = {}
    for escena in escenas:
        inicio = time.perf_counter()
        job = json.loads(leer("/api/analyze", {"source": "preloaded", "scene": escena["id"],
            "settings": {"method": "contextual_hibrida"}}))["job_id"]
        limite = time.monotonic() + 180
        while True:
            resultado = json.loads(leer(f"/api/jobs/{job}"))
            if resultado["state"] in ("complete", "error"):
                break
            if time.monotonic() > limite:
                raise TimeoutError(escena["id"])
            time.sleep(.3)
        assert resultado["state"] == "complete", resultado
        metricas = resultado["metrics"]
        mascaras = {}
        destino = carpeta / escena["id"]
        destino.mkdir(exist_ok=True)
        for nombre in metricas["available_layers"]:
            datos = leer(f"/api/jobs/{job}/layers/{nombre}.png")
            imagen = np.asarray(Image.open(io.BytesIO(datos)))
            assert imagen.shape[:2] == (metricas["grid_height"], metricas["grid_width"])
            (destino / f"{nombre}.png").write_bytes(datos)
            if imagen.ndim == 2:
                mascaras[nombre] = imagen > 0
        assert not np.any(mascaras["mask"] & mascaras["smoke"])
        assert not np.any(mascaras["smoke-candidates"] & ~mascaras["smoke"])
        assert not np.any(mascaras["smoke-candidates"] & mascaras["smoke-unknown"])
        assert np.array_equal(mascaras["smoke-candidates"],
                              mascaras["smoke-spectral"] | mascaras["smoke-continuity"])
        assert metricas["pixel_count"] == int(mascaras["mask"].sum())
        assert metricas["area_unit"] == "px²", metricas["area_unit"]
        informe[escena["id"]] = {"segundos_http_y_exportacion": round(time.perf_counter() - inicio, 3),
                                  "metricas": metricas}
        (carpeta / "verificacion.json").write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding="utf-8")
        print(escena["id"], "OK", informe[escena["id"]]["segundos_http_y_exportacion"], "s", flush=True)


if __name__ == "__main__":
    main()
