"""Comparación antes/después de capas de suelo y humo, misma rejilla 2500."""
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pyroscope.interfaz.configuracion import listar_escenas_disponibles
from pyroscope.interfaz.procesamiento import preparar_pareja, procesar_pareja
from pyroscope.visualizacion import crear_superposicion


def main():
    raiz = Path(__file__).resolve().parents[1]
    destino = raiz / "resultados_contextual" / "capas_humo"
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
        anterior = raiz / "resultados_contextual" / "http" / escena.nombre
        datos = {"segundos": round(time.perf_counter()-inicio, 2),
            "visible_px": int(resultado.mascara.sum()), "humo_px": int(resultado.mascara_humo.sum()),
            "inferida_px": int(resultado.mascara_candidata_bajo_humo.sum()),
            "espectral_px": int(resultado.mascara_bajo_humo_espectral.sum()),
            "continuidad_px": int(resultado.mascara_bajo_humo_continuidad.sum())}
        if anterior.exists():
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


if __name__ == "__main__":
    main()
