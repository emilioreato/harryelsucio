"""Comparación antes/después de capas de suelo y humo, misma rejilla 2500."""
import json
import argparse
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
from _salidas import directorio_salida, resolver_ruta_repositorio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lumbre.interfaz.configuracion import listar_escenas_disponibles
from lumbre.interfaz.procesamiento import preparar_pareja, procesar_pareja
from lumbre.visualizacion import crear_superposicion


def generar(destino: Path, baseline: Path | None) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    informe = {}
    for escena in listar_escenas_disponibles():
        inicio = time.perf_counter()
        pareja = preparar_pareja(escena.true_color.read_bytes(), escena.swir.read_bytes(), None, max_lado=2500)
        tc, sw, resultado = procesar_pareja(pareja.true_color, pareja.swir, 5, 7, .15, 10,
            None, None, "contextual_hibrida", True)
        carpeta = destino / escena.nombre
        carpeta.mkdir(exist_ok=True)
        imagen = crear_superposicion(tc, resultado)
        Image.fromarray(imagen).save(carpeta / "suelo_humo.png")
        np.savez_compressed(carpeta / "mascaras.npz", visible=resultado.mascara,
            humo=resultado.mascara_humo, inferida=resultado.mascara_candidata_bajo_humo,
            desconocido=resultado.mascara_indeterminada,
            espectral=resultado.mascara_bajo_humo_espectral,
            continuidad=resultado.mascara_bajo_humo_continuidad)
        assert not np.any(resultado.mascara & resultado.mascara_humo)
        assert not np.any(resultado.mascara_candidata_bajo_humo & ~resultado.mascara_humo)
        anterior = baseline / escena.nombre if baseline is not None else None
        datos = {"segundos": round(time.perf_counter()-inicio, 2),
            "visible_px": int(resultado.mascara.sum()), "humo_px": int(resultado.mascara_humo.sum()),
            "inferida_px": int(resultado.mascara_candidata_bajo_humo.sum()),
            "espectral_px": int(resultado.mascara_bajo_humo_espectral.sum()),
            "continuidad_px": int(resultado.mascara_bajo_humo_continuidad.sum())}
        if anterior is not None and anterior.exists():
            for nombre, archivo in (("humo", "smoke"), ("inferida", "smoke-candidates")):
                datos[nombre + "_antes_px"] = int((np.asarray(Image.open(anterior / (archivo + ".png"))) > 0).sum())
            panel = Image.new("RGB", (1500, 500), (20, 30, 40))
            panel.paste(Image.open(anterior / "overlay-true-color.png").resize((750, 464)), (0, 30))
            panel.paste(Image.fromarray(imagen).resize((750, 464)), (750, 30))
            dibujo = ImageDraw.Draw(panel)
            dibujo.text((10, 8), "Antes: hipotesis fucsia y humo", fill="white")
            dibujo.text((760, 8), "Ahora: suelo rojo/amarillo; humo azul por encima", fill="white")
            panel.save(carpeta / "comparacion.png")
        informe[escena.nombre] = datos
        (destino / "metricas.json").write_text(json.dumps(informe, indent=2), encoding="utf-8")
        print(escena.nombre, datos, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--salida", type=Path,
        help="Conserva los artefactos en esta carpeta; si se omite, se borran al terminar.",
    )
    parser.add_argument(
        "--baseline", type=Path,
        help="Carpeta opcional de una verificación HTTP guardada, para crear paneles antes/después.",
    )
    args = parser.parse_args()
    with directorio_salida(args.salida, "lumbre-capas-humo-") as destino:
        baseline = resolver_ruta_repositorio(args.baseline) if args.baseline else None
        generar(destino, baseline)


if __name__ == "__main__":
    main()
