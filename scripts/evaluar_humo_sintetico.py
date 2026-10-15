"""Oclusiones conocidas: verifica lógica; no valida reconstrucción de humo real."""
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pyroscope.estimacion_bajo_humo import estimar_bajo_humo


def main():
    destino = Path(__file__).resolve().parents[1] / "resultados_contextual" / "sintetico"
    destino.mkdir(parents=True, exist_ok=True)
    informe = {"limite": "Geometría sintética conocida; no valida humo real.", "casos": {}}
    panel = Image.new("RGB", (720, 6 * 145), (22, 30, 38))
    dibujo = ImageDraw.Draw(panel)
    for fila, (nombre, anchura) in enumerate((("estrecha", 8), ("extensa", 60),
            ("agua", 8), ("sin_incendio", 8), ("varias_cicatrices", 8), ("espectral", 8))):
        suelo = np.zeros((120, 220), bool)
        if nombre != "sin_incendio":
            suelo[30:90, 25:195] = True
        if nombre == "varias_cicatrices":
            suelo[55:65] = False
        humo = np.zeros_like(suelo)
        humo[:, 110 - anchura // 2:110 + anchura // 2] = True
        agua = np.zeros_like(suelo)
        if nombre == "agua":
            agua[:, 108:112] = True
            suelo &= ~agua
        visible = suelo & ~humo
        evidencia = (suelo & humo).astype(float) if nombre == "espectral" else None
        resultado = estimar_bajo_humo(visible, humo, agua, evidencia, distancia_maxima_px=12)
        verdad, candidata = suelo & humo, resultado.mascara_candidata
        tp = int((verdad & candidata).sum())
        fp = int((~verdad & candidata).sum())
        fn = int((verdad & ~candidata).sum())
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        bv = verdad ^ ndi.binary_erosion(verdad)
        bp = candidata ^ ndi.binary_erosion(candidata)
        pr_b = float((bp & ndi.binary_dilation(bv)).sum() / bp.sum()) if bp.any() else None
        re_b = float((bv & ndi.binary_dilation(bp)).sum() / bv.sum()) if bv.any() else None
        informe["casos"][nombre] = {"tp": tp, "fp": fp, "fn": fn,
            "iou": tp / (tp + fp + fn) if tp + fp + fn else None,
            "precision": precision, "recall": recall,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "frontera_precision_tolerancia_1px": pr_b, "frontera_recall_tolerancia_1px": re_b,
            "desconocidos_px": int(resultado.mascara_indeterminada.sum())}
        assert fp == 0
        if nombre == "extensa":
            assert not candidata.any()
        if nombre == "estrecha":
            assert np.array_equal(verdad, candidata)
        for columna, (titulo, mascara) in enumerate((("verdad oculta", verdad),
                ("observacion", visible), ("hipotesis", candidata))):
            rgb = np.full((*suelo.shape, 3), 45, np.uint8)
            rgb[humo] = (35, 90, 125)
            rgb[mascara] = (225, 65, 175) if columna == 2 else (235, 160, 40)
            panel.paste(Image.fromarray(rgb), (columna * 240, fila * 145 + 22))
            dibujo.text((columna * 240 + 4, fila * 145 + 4), nombre + " / " + titulo, fill="white")
    panel.save(destino / "oclusiones.png")
    (destino / "metricas.json").write_text(json.dumps(informe, indent=2), encoding="utf-8")
    print("6 escenarios sintéticos verificados; métricas y panel en", destino)


if __name__ == "__main__":
    main()
