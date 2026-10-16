"""Comparación reproducible de escenas; métricas geométricas, no precisión.

python scripts/comparar_contextual.py --fase baseline --salida .tmp/pruebas/comparacion
python scripts/comparar_contextual.py --fase contextual_roi --salida .tmp/pruebas/comparacion --baseline .tmp/pruebas/comparacion/baseline
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw
from _salidas import directorio_salida, resolver_ruta_repositorio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lumbre.imagenes import abrir_rgb
from lumbre.segmentacion import segmentar_superficie_afectada
from lumbre.visualizacion import crear_superposicion


def geometria(mask):
    mask = np.asarray(mask, dtype=np.uint8)
    cantidad, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    contornos, jerarquia = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    return {
        "pixeles": int(mask.sum()), "fraccion": float(mask.mean()),
        "componentes": cantidad - 1,
        "componente_mayor_px": int(stats[1:, cv2.CC_STAT_AREA].max()) if cantidad > 1 else 0,
        "perimetro_todos_bordes_px": float(sum(cv2.arcLength(c, True) for c in contornos)),
        "contornos_internos": int(np.count_nonzero(jerarquia[0, :, 3] >= 0)) if jerarquia is not None else 0,
    }


def panel(path, panels):
    width, height = 600, 500
    columns = min(3, len(panels))
    canvas = Image.new("RGB", (columns * width, ((len(panels) + columns - 1) // columns) * height), "#17212b")
    draw = ImageDraw.Draw(canvas)
    for index, (label, pixels) in enumerate(panels):
        x, y = index % columns * width, index // columns * height
        im = Image.fromarray(np.asarray(pixels, dtype=np.uint8))
        im.thumbnail((width, height - 30))
        canvas.paste(im, (x + (width - im.width) // 2, y + 30))
        draw.text((x + 8, y + 8), label, fill="white")
    canvas.save(path)


def colorear(etiquetas):
    rng = np.random.default_rng(42)
    colores = rng.integers(25, 240, (int(etiquetas.max()) + 1, 3), dtype=np.uint8)
    return colores[etiquetas]


def tinte(base, mascara, color):
    result = base.copy()
    result[mascara] = (.45 * result[mascara] + .55 * np.array(color)).astype(np.uint8)
    return result


def perimetro(base, mascara, color=(255, 230, 30)):
    result = base.copy()
    contours, _ = cv2.findContours(mascara.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(result, contours, -1, color, 2)
    return result


def render_cached(tc, destination):
    for nombre in ("slic", "rag", "watershed"):
        with np.load(destination / f"{nombre}.npz") as data:
            mask = data["visible"]
            Image.fromarray(perimetro(tinte(tc, mask, (255,80,20)), mask)).save(destination / f"{nombre}.png")
    with np.load(destination / "watershed.npz") as data:
        panel(destination / "bordes_marcadores.png", [
            ("Antes Watershed y filtro tamano", perimetro(tc,data["before-watershed"])),
            ("Perimetro final (incluye agujeros)", perimetro(tc,data["visible"])),
            ("Cambios locales Watershed", tinte(tc,data["watershed-changes"],(255,20,180))),
            ("Marcadores positivos", tinte(tc,data["positive-markers"],(255,50,20))),
            ("Marcadores negativos", tinte(tc,data["negative-markers"],(20,180,255)))])


def comparar_hibrido(tc, swir, destination, baseline, representaciones=False):
    from lumbre.caracteristicas import extraer_caracteristicas_pareja
    from lumbre.detectores.swir_histeresis import clasificar_pixeles_area_afectada_swir
    from lumbre.regiones_contextuales import segmentar_contextual
    from lumbre.evidencia_contextual import evidencia_desde_v2
    from lumbre.estimacion_bajo_humo import estimar_bajo_humo
    from lumbre.geometria_segmentacion import segmentar_regiones_espaciales
    from dataclasses import replace

    inicio = time.perf_counter()
    clasificacion = clasificar_pixeles_area_afectada_swir(tc, swir)
    features = extraer_caracteristicas_pareja(tc, swir)
    score = evidencia_desde_v2(clasificacion, features)
    tiempo_semantica = time.perf_counter() - inicio
    resultados = {}
    paneles = [("True Color", tc), ("SWIR", swir)]
    anterior = np.load(baseline / "swir_histeresis.npz")
    paneles.append(("Actual SWIR baseline", tinte(tc, anterior["visible"], (255, 80, 20))))
    variantes = [("slic", False, False), ("rag", True, False), ("watershed", True, True)]
    for nombre, rag, refinar in variantes:
        inicio = time.perf_counter()
        result = segmentar_contextual(tc, swir, clasificacion.mascara_candidata,
            clasificacion.mascara_agua, clasificacion.mascara_humo,
            evidencia=score, caracteristicas=features, usar_rag=rag, refinar=refinar)
        final = segmentar_regiones_espaciales(replace(clasificacion, mascara_candidata=result.mascara),
            area_minima_pct=.15, preservar_geometria=True, conservar_regiones_separadas=True)
        mascara = final.mascara
        segundos = time.perf_counter() - inicio
        np.savez_compressed(destination / f"{nombre}.npz", visible=mascara,
                            **result.diagnosticos)
        resultados[nombre] = {"segundos_espacial": round(segundos, 3),
            "segundos_semantica_compartida": round(tiempo_semantica, 3),
            "uniones": int(result.uniones), "watershed_aplicado": bool(result.watershed_aplicado),
            "visible": geometria(mascara),
            "antes_filtro_tamano": geometria(result.mascara),
            "agregados_vs_baseline": int(np.count_nonzero(mascara & ~anterior["visible"])),
            "retirados_vs_baseline": int(np.count_nonzero(~mascara & anterior["visible"])),
            "crecimiento_px": int(result.diagnosticos["growth"].sum()),
            "incorporados_motor_vs_candidata_px": int(np.count_nonzero(result.mascara & ~clasificacion.mascara_candidata)),
            "cambios_watershed_px": int(result.diagnosticos["watershed-changes"].sum())}
        paneles.append((nombre, tinte(tc, mascara, (255, 80, 20))))
        Image.fromarray(perimetro(tinte(tc, mascara, (255,80,20)), mascara)).save(destination / f"{nombre}.png")
        print(destination.name, nombre, round(segundos, 2), "s", int(mascara.sum()), "px", flush=True)
    diagnosticos = [
        ("SLIC regiones", colorear(result.etiquetas)),
        ("Clases: exterior/interior/ambiguo/humo", np.array([[40, 60, 65], [235, 90, 20], [245, 200, 50], [70, 175, 230]], np.uint8)[result.diagnosticos["region-classes"]]),
        ("Grupos RAG", colorear(result.diagnosticos["rag"])),
        ("Semillas fiables", tinte(tc, result.diagnosticos["seeds"], (255, 230, 20))),
        ("Crecimiento RAG", tinte(tc, result.diagnosticos["growth"], (0, 255, 150))),
        ("Cambios Watershed", tinte(tc, result.diagnosticos["watershed-changes"], (255, 0, 255))),
    ]
    panel(destination / "diagnosticos.png", diagnosticos)
    panel(destination / "bordes_marcadores.png", [
        ("Borde antes de Watershed", perimetro(tc,result.diagnosticos["before-watershed"])),
        ("Borde tras Watershed (antes filtro area)", perimetro(tc,result.mascara)),
        ("Perimetro final (todos los agujeros)", perimetro(tc,mascara)),
        ("Marcadores positivos", tinte(tc,result.diagnosticos["positive-markers"],(255,50,20))),
        ("Marcadores negativos", tinte(tc,result.diagnosticos["negative-markers"],(20,180,255)))])
    humo = estimar_bajo_humo(mascara, clasificacion.mascara_humo, clasificacion.mascara_agua, score,
        contradiccion=(features[...,2]>.25)&(features[...,0]<-.05)&(clasificacion.confianza_humo<.7),
        distancia_maxima_px=max(3,min(24,round(min(mascara.shape)*.015))))
    np.savez_compressed(destination / "humo.npz", humo=clasificacion.mascara_humo,
        espectral=humo.mascara_espectral, continuidad=humo.mascara_continuidad,
        indeterminada=humo.mascara_indeterminada, candidata=humo.mascara_candidata)
    resultados["humo"] = {"antes": geometria(anterior["bajo_humo"]),
        "despues": geometria(humo.mascara_candidata), "espectral": geometria(humo.mascara_espectral),
        "continuidad": geometria(humo.mascara_continuidad), "indeterminada": geometria(humo.mascara_indeterminada)}
    humo_base = tinte(tc, clasificacion.mascara_humo, (0,170,255))
    humo_antes = tinte(humo_base, anterior["bajo_humo"], (235,20,180))
    humo_despues = tinte(humo_base, humo.mascara_candidata, (235,20,180))
    panel(destination / "humo_comparacion.png", [("Humo probable", humo_base),
        ("Hipotesis anterior", humo_antes), ("Hipotesis nueva", humo_despues),
        ("Evidencia espectral", tinte(tc,humo.mascara_espectral,(235,20,180))),
        ("Continuidad espacial", tinte(tc,humo.mascara_continuidad,(255,220,40))),
        ("Terreno indeterminado", tinte(tc,humo.mascara_indeterminada,(150,150,150)))])
    panel(destination / "comparacion.png", paneles)
    if representaciones:
        comparativa = []
        for representacion in ("true_color", "swir", "conjunta"):
            inicio = time.perf_counter()
            region = segmentar_contextual(tc, swir, clasificacion.mascara_candidata,
                clasificacion.mascara_agua, clasificacion.mascara_humo,
                evidencia=score, caracteristicas=features, representacion=representacion,
                usar_rag=True, refinar=False)
            resultados[f"representacion_{representacion}"] = {
                "segundos": round(time.perf_counter()-inicio, 3), "visible": geometria(region.mascara),
                "uniones": int(region.uniones), "superpixeles": int(region.etiquetas.max()) + 1}
            comparativa.append((representacion, colorear(region.etiquetas)))
        panel(destination / "representaciones_slic.png", comparativa)
    return resultados


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fase", default="baseline")
    parser.add_argument(
        "--salida", type=Path,
        help="Carpeta base para conservar artefactos; si se omite, se borran al terminar.",
    )
    parser.add_argument(
        "--baseline", type=Path,
        help="Carpeta baseline guardada previamente; obligatoria para fases comparativas.",
    )
    parser.add_argument("--max-lado", type=int, default=1800)
    parser.add_argument("--escena", help="Substring del nombre de escena")
    parser.add_argument("--representaciones", action="store_true", help="Compara 3 representaciones SLIC")
    parser.add_argument("--render-only", action="store_true", help="Dibuja perimetros desde NPZ guardados")
    args = parser.parse_args()

    if not args.render_only and args.fase != "baseline" and args.baseline is None:
        parser.error("Para una fase comparativa indica --baseline con la carpeta guardada de la fase baseline.")
    if args.render_only:
        if args.salida is None:
            parser.error("--render-only requiere --salida con la carpeta de artefactos existente.")
        ejecutar(resolver_ruta_repositorio(args.salida), args)
        return
    with directorio_salida(args.salida, "lumbre-comparacion-") as raiz_salida:
        ejecutar(raiz_salida, args)


def ejecutar(raiz_salida: Path, args: argparse.Namespace) -> None:
    output = raiz_salida / args.fase
    if args.render_only:
        if not output.is_dir():
            raise FileNotFoundError(f"No existe la carpeta con artefactos para renderizar: {output}")
    else:
        output.mkdir(parents=True, exist_ok=True)
    report = {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "codigo_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "lumbre").glob("*.py")},
        "advertencia": "JPEG renderizados sin verdad terreno: métricas geométricas, no accuracy; no áreas métricas sin GSD.",
        "parametros": {"max_lado": args.max_lado, "numero_clases": 7, "sensibilidad": 5,
                       "area_minima_pct": 0.15, "distancia_maxima_pct": 10, "conservar_regiones_separadas": False},
        "escenas": {},
    }
    if args.fase != "baseline":
        report["parametros"].update(conservar_regiones_separadas=True, preservar_geometria=True,
            area_superpixel=144, representacion="conjunta", distancia_crecimiento_px=8, limitar_contexto=True,
            nota="Cada variante reutiliza la semantica V2; tiempos espaciales incluyen filtro de area minima.")
    for scene in sorted((ROOT / "imagenes_muestra").iterdir()):
        if not scene.is_dir() or (args.escena and args.escena.lower() not in scene.name.lower()):
            continue
        true_path = next(scene.glob("*True_color*"))
        swir_path = next(scene.glob("*SWIR*"))
        tc, size_tc = abrir_rgb(true_path.read_bytes(), args.max_lado)
        swir, size_sw = abrir_rgb(swir_path.read_bytes(), args.max_lado)
        if size_tc != size_sw:
            raise ValueError(f"Pareja con dimensiones distintas: {scene.name}")
        destination = output / scene.name
        destination.mkdir(exist_ok=True)
        if args.render_only:
            render_cached(tc, destination)
            continue
        images = [("True Color", tc), ("SWIR", swir)]
        scene_report = {"original_wh": size_tc, "trabajo_hw": tc.shape[:2], "metodos": {},
                        "fuentes_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (true_path, swir_path)}}
        if args.fase != "baseline":
            scene_report["metodos"] = comparar_hibrido(tc, swir, destination,
                resolver_ruta_repositorio(args.baseline) / scene.name, args.representaciones)
            report["escenas"][scene.name] = scene_report
            (output / "metricas.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            continue
        for method in ("kmeans", "swir_histeresis", "fusion_ponderada"):
            started = time.perf_counter()
            result = segmentar_superficie_afectada(tc, swir, metodo=method, area_minima_pct=.15)
            elapsed = time.perf_counter() - started
            masks = {"visible": result.mascara, "candidata": result.mascara_clasificada,
                     "humo": result.mascara_humo, "bajo_humo": result.mascara_candidata_bajo_humo}
            np.savez_compressed(destination / f"{method}.npz", **masks)
            overlay = crear_superposicion(tc, result)
            Image.fromarray(overlay).save(destination / f"{method}.png")
            images.append((method, overlay))
            scene_report["metodos"][method] = {
                "segundos": round(elapsed, 3), **{name: geometria(mask) for name, mask in masks.items()},
                "componentes_remotos_descartados": result.componentes_remotos_descartados,
            }
            print(scene.name, method, round(elapsed, 2), "s", int(result.mascara.sum()), "px", flush=True)
        panel(destination / "comparacion.png", images)
        report["escenas"][scene.name] = scene_report
        (output / "metricas.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
