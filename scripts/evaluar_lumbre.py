"""Compara el contextual anterior y el experimental con las mismas escenas.

Ejemplo:
    py scripts/evaluar_lumbre.py --salida resultados_contextual/lumbre_revision

Genera máscaras, capas fuente, paneles y métricas geométricas. Sin anotaciones
independientes, los conteos no se presentan como precisión científica.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pyroscope.caracteristicas import extraer_caracteristicas_pareja
from pyroscope.detectores.contextual import clasificar_base_contextual
from pyroscope.detectores.swir_histeresis import clasificar_pixeles_area_afectada_swir
from pyroscope.evidencia_contextual import evidencia_desde_v2
from pyroscope.estimacion_bajo_humo import estimar_bajo_humo
from pyroscope.geometria_segmentacion import segmentar_regiones_espaciales
from pyroscope.humo_visible import ampliar_humo_true_color
from pyroscope.imagenes import abrir_rgb
from pyroscope.ontologia import ClaseSemantica
from pyroscope.regiones_contextuales import segmentar_contextual


ESCENAS = (
    ("00_PRUEBA 02 - La Vall d'Uixo Castellon", "2026-07-28"),
    ("La Mierla (Guadalajara)", "2026-07-21"),
    ("Madrid-Avila", "2026-07-26"),
    ("Niebla (Huelva)", "2026-08-08"),
)


def geometria(mascara: np.ndarray) -> dict[str, int | float]:
    mascara = np.asarray(mascara, dtype=np.uint8)
    cantidad, _, stats, _ = cv2.connectedComponentsWithStats(mascara, 8)
    return {
        "pixeles": int(mascara.sum()),
        "fraccion": float(mascara.mean()),
        "componentes": cantidad - 1,
        "componente_mayor_px": int(stats[1:, cv2.CC_STAT_AREA].max()) if cantidad > 1 else 0,
    }


def tinte(base: np.ndarray, mascara: np.ndarray, color: tuple[int, int, int], alpha=.62) -> np.ndarray:
    salida = base.copy()
    mascara = np.asarray(mascara, dtype=bool)
    salida[mascara] = np.clip(
        salida[mascara] * (1 - alpha) + np.asarray(color) * alpha, 0, 255
    ).astype(np.uint8)
    return salida


def calor(base: np.ndarray, evidencia: np.ndarray, color=(255, 80, 20)) -> np.ndarray:
    hi = max(float(np.quantile(evidencia, .995)), 1e-6)
    alpha = (np.clip(evidencia / hi, 0, 1) * .75)[..., None]
    return np.clip(base * (1 - alpha) + np.asarray(color) * alpha, 0, 255).astype(np.uint8)


def guardar_panel(ruta: Path, paneles: list[tuple[str, np.ndarray]]) -> None:
    ancho, alto, columnas = 520, 355, 3
    filas = (len(paneles) + columnas - 1) // columnas
    lienzo = Image.new("RGB", (ancho * columnas, alto * filas), "#17212b")
    dibujo = ImageDraw.Draw(lienzo)
    for indice, (etiqueta, matriz) in enumerate(paneles):
        x, y = indice % columnas * ancho, indice // columnas * alto
        imagen = Image.fromarray(np.asarray(matriz, dtype=np.uint8))
        imagen.thumbnail((ancho - 12, alto - 35))
        lienzo.paste(imagen, (x + (ancho - imagen.width) // 2, y + 28))
        dibujo.text((x + 8, y + 7), etiqueta, fill="white")
    lienzo.save(ruta)


def ejecutar(tc: np.ndarray, swir: np.ndarray, *, experimental: bool) -> dict:
    inicio = time.perf_counter()
    if experimental:
        clasificacion = clasificar_base_contextual(tc, swir, sensibilidad=5, umbral_humo=.55)
    else:
        original = clasificar_pixeles_area_afectada_swir(
            tc, swir, sensibilidad=5, umbral_humo=.55
        )
        humo, confianza = ampliar_humo_true_color(
            tc, swir, original.mascara_humo, original.confianza_humo
        )
        candidata_v2 = original.mascara_candidata & ~humo & ~original.mascara_agua
        subyacente = (
            original.mascara_candidata_bajo_humo
            | (original.mascara_candidata & humo)
        ) & ~original.mascara_agua
        clases = original.clase_por_pixel.copy()
        clases[humo] = ClaseSemantica.HUMO_PROBABLE
        caracteristicas = original.caracteristicas_comunes
        clasificacion = replace(
            original,
            mascara_humo=humo,
            confianza_humo=confianza,
            mascara_candidata=candidata_v2,
            mascara_candidata_bajo_humo=subyacente,
            clase_por_pixel=clases,
            mascara_candidata_v2=candidata_v2,
        )
        if caracteristicas is not None and np.ptp(caracteristicas[..., 0]) < 1e-5 \
                and np.max(caracteristicas[..., 0]) <= .05:
            vacia = np.zeros(tc.shape[:2], bool)
            clasificacion = replace(
                clasificacion, mascara_candidata=vacia,
                mascara_candidata_v2=vacia.copy(),
                mascara_candidata_bajo_humo=vacia.copy(),
            )

    caracteristicas = clasificacion.caracteristicas_comunes
    if caracteristicas is None:
        caracteristicas = extraer_caracteristicas_pareja(tc, swir)
    score = evidencia_desde_v2(clasificacion, caracteristicas)
    regiones = segmentar_contextual(
        tc, swir, clasificacion.mascara_candidata, clasificacion.mascara_agua,
        clasificacion.mascara_humo, evidencia=score, caracteristicas=caracteristicas,
    )
    regiones_espaciales = segmentar_regiones_espaciales(
        replace(clasificacion, mascara_candidata=regiones.mascara),
        area_minima_pct=.15, distancia_maxima_pct=10,
        conservar_regiones_separadas=True, preservar_geometria=True,
    )
    contradiccion = (
        (caracteristicas[..., 2] > .25)
        & (caracteristicas[..., 0] < -.05)
        & (clasificacion.confianza_humo < .7)
    )
    bajo_humo = estimar_bajo_humo(
        regiones_espaciales.mascara,
        clasificacion.mascara_humo,
        clasificacion.mascara_agua,
        score,
        contradiccion=contradiccion,
        distancia_maxima_px=max(3, min(24, round(min(tc.shape[:2]) * .015))),
        umbral_espectral=.4,
        distancia_espectral_px=max(4, round(min(tc.shape[:2]) * .04)),
    )
    diagnosticos_evidencia = dict(getattr(score, "diagnosticos", {}) or {})
    return {
        "clasificacion": clasificacion,
        "contexto": regiones,
        "final": regiones_espaciales.mascara,
        "score": score,
        "fuentes": diagnosticos_evidencia,
        "bajo_humo": bajo_humo,
        "segundos": time.perf_counter() - inicio,
    }


def hash_archivo(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def procesar_escena(nombre: str, fecha: str, destino: Path) -> dict:
    carpeta = ROOT / "imagenes" / nombre
    tc_path = next(carpeta.glob("*True_color*"))
    swir_path = next(carpeta.glob("*SWIR*"))
    tc, original_tc = abrir_rgb(tc_path.read_bytes(), 2500)
    swir, original_swir = abrir_rgb(swir_path.read_bytes(), 2500)
    if original_tc != original_swir or tc.shape != swir.shape:
        raise ValueError(f"La pareja {nombre} difiere en dimensión o rejilla.")

    control = ejecutar(tc, swir, experimental=False)
    experimental = ejecutar(tc, swir, experimental=True)
    escena_dir = destino / nombre
    escena_dir.mkdir(parents=True, exist_ok=False)
    cls = experimental["clasificacion"]
    fuentes = experimental["fuentes"]
    bajo = experimental["bajo_humo"]
    antes = control["final"]
    despues = experimental["final"]
    humo_antes = control["clasificacion"].mascara_humo
    humo_despues = cls.mascara_humo
    frente_fuerte = fuentes.get("frente_candidato_fuerte", np.zeros(tc.shape[:2], bool))
    frente_moderado = fuentes.get("frente_candidato_moderado", np.zeros(tc.shape[:2], bool))
    semillas_nuevas = fuentes.get("frente_semillas_nuevas", np.zeros(tc.shape[:2], bool))
    evidence_front = fuentes.get("evidencia_frente", np.zeros(tc.shape[:2], np.float32))
    evidence_v2 = fuentes.get("evidencia_swir_v2", np.zeros(tc.shape[:2], np.float32))
    added = despues & ~antes
    removed = antes & ~despues
    diagnosticos = experimental["contexto"].diagnosticos
    atribuible_frente = added & (
        frente_fuerte | (frente_moderado & diagnosticos.get("growth", np.zeros_like(added)))
    )
    arrays = {
        "visible_antes": antes,
        "visible_despues": despues,
        "visible_incorporada": added,
        "visible_retirada": removed,
        "candidata_semantica": cls.mascara_candidata,
        "candidata_v2": cls.mascara_candidata_v2,
        "humo_antes": humo_antes,
        "humo_despues": humo_despues,
        "humo_referencia": fuentes.get("humo_referencia", np.zeros_like(humo_despues)),
        "humo_nucleo": fuentes.get("humo_nucleo", np.zeros_like(humo_despues)),
        "humo_fuerte": fuentes.get("humo_fuerte", np.zeros_like(humo_despues)),
        "humo_moderado": fuentes.get("humo_moderado", np.zeros_like(humo_despues)),
        "evidencia_humo": fuentes.get("evidencia_humo", cls.confianza_humo),
        "humo_candidatos_debiles": fuentes.get("humo_candidatos_debiles", np.zeros_like(humo_despues)),
        "humo_descartado_distancia": fuentes.get("humo_descartado_distancia", np.zeros_like(humo_despues)),
        "humo_descartado_conectividad": fuentes.get("humo_descartado_conectividad", np.zeros_like(humo_despues)),
        "evidencia_swir_v2": evidence_v2,
        "evidencia_frente": evidence_front,
        "frente_candidato_fuerte": frente_fuerte,
        "frente_candidato_moderado": frente_moderado,
        "frente_semillas_nuevas": semillas_nuevas,
        "visible_nuevo_atribuible_frente": atribuible_frente,
        "agua": cls.mascara_agua,
        "frente_fuerte_bajo_humo": frente_fuerte & humo_despues,
        "frente_moderado_bajo_humo": frente_moderado & humo_despues,
        "frente_moderado_vecinal": fuentes.get(
            "frente_candidato_moderado_vecinal", np.zeros_like(humo_despues)
        ),
        "tras_slic_rag": experimental["contexto"].mascara,
        "growth": diagnosticos.get("growth", np.zeros_like(despues)),
        "descartado_por_motor": cls.mascara_candidata & ~experimental["contexto"].mascara,
        "descartado_por_geometria": experimental["contexto"].mascara & ~despues,
        "bajo_humo_espectral": bajo.mascara_espectral,
        "bajo_humo_continuidad": bajo.mascara_continuidad,
        "bajo_humo_indeterminado": bajo.mascara_indeterminada,
    }
    np.savez_compressed(escena_dir / "capas_comparacion.npz", **arrays)

    paneles = [("True Color", tc), ("SWIR", swir)]
    paneles += [
        ("Humo contextual anterior", tinte(tc, humo_antes, (0, 165, 255))),
        ("Humo referencia (ampliación anterior)", tinte(tc, arrays["humo_referencia"], (0, 165, 255))),
        ("Humo fuerte", tinte(tc, arrays["humo_fuerte"], (0, 115, 240))),
        ("Humo moderado (heredado o añadido)", tinte(tc, arrays["humo_moderado"], (40, 210, 255))),
        ("Candidatos débiles antes del radio", tinte(tc, arrays["humo_candidatos_debiles"], (255, 180, 0))),
        ("Descartados por distancia", tinte(tc, arrays["humo_descartado_distancia"], (255, 0, 220))),
        ("Descartados por conectividad", tinte(tc, arrays["humo_descartado_conectividad"], (180, 60, 220))),
        ("Candidatos semánticos antes de SLIC", tinte(tc, cls.mascara_candidata, (255, 80, 20))),
        ("Evidencia SWIR V2", calor(tc, evidence_v2)),
        ("Evidencia visual del frente", calor(tc, evidence_front, (235, 15, 190))),
        ("Frente fuerte bajo humo", tinte(tinte(tc, humo_despues, (0, 140, 255)), arrays["frente_fuerte_bajo_humo"], (245, 0, 210))),
        ("Apoyo rojizo vecinal bajo humo", tinte(tinte(tc, humo_despues, (0, 140, 255)), arrays["frente_moderado_vecinal"] & humo_despues, (255, 210, 0))),
        ("Máscara tras SLIC/RAG", tinte(tc, arrays["tras_slic_rag"], (255, 80, 20))),
        ("Superficie visible anterior", tinte(tc, antes, (255, 50, 20))),
        ("Superficie visible experimental", tinte(tc, despues, (255, 50, 20))),
        ("Píxeles nuevos atribuibles al frente", tinte(tc, atribuible_frente, (240, 10, 210))),
        ("Hipótesis espectral bajo humo", tinte(tinte(tc, humo_despues, (0, 140, 255)), bajo.mascara_espectral, (235, 20, 180))),
        ("Continuidad geodésica bajo humo", tinte(tinte(tc, humo_despues, (0, 140, 255)), bajo.mascara_continuidad, (255, 220, 40))),
        ("Terreno indeterminado", tinte(tinte(tc, humo_despues, (0, 140, 255)), bajo.mascara_indeterminada, (145, 145, 145))),
        ("Descartado por geometría", tinte(tc, arrays["descartado_por_geometria"], (255, 0, 220))),
    ]
    guardar_panel(escena_dir / "panel_comparacion.png", paneles)
    metricas = {
        "fecha": fecha,
        "original_wh": original_tc,
        "trabajo_wh": [tc.shape[1], tc.shape[0]],
        "true_color_sha256": hash_archivo(tc_path),
        "swir_sha256": hash_archivo(swir_path),
        "tiempo_control_s": round(control["segundos"], 3),
        "tiempo_experimental_s": round(experimental["segundos"], 3),
        "control": {name: geometria(mask) for name, mask in (
            ("humo", humo_antes), ("visible", antes),
            ("bajo_humo", control["bajo_humo"].mascara_candidata),
        )},
        "experimental": {name: geometria(mask) for name, mask in (
            ("humo", humo_despues), ("humo_fuerte", arrays["humo_fuerte"]),
            ("humo_moderado", arrays["humo_moderado"]), ("visible", despues),
            ("bajo_humo_espectral", bajo.mascara_espectral),
            ("bajo_humo_continuidad", bajo.mascara_continuidad),
            ("bajo_humo_indeterminado", bajo.mascara_indeterminada),
        )},
        "diferencias_px": {
            "humo_nuevo": int(np.count_nonzero(humo_despues & ~humo_antes)),
            "humo_candidatos_debiles_px": int(arrays["humo_candidatos_debiles"].sum()),
            "humo_descartado_distancia_px": int(arrays["humo_descartado_distancia"].sum()),
            "humo_descartado_conectividad_px": int(arrays["humo_descartado_conectividad"].sum()),
            "visible_anadido": int(added.sum()),
            "visible_retirado": int(removed.sum()),
            "semillas_fuertes_frente": int(semillas_nuevas.sum()),
            "frente_fuerte_bajo_humo": int(arrays["frente_fuerte_bajo_humo"].sum()),
            "frente_vecinal_bajo_humo": int((arrays["frente_moderado_vecinal"] & humo_despues).sum()),
            "nuevos_visibles_atribuibles_frente": int(atribuible_frente.sum()),
            "descartado_motor_px": int(arrays["descartado_por_motor"].sum()),
            "descartado_geometria_px": int(arrays["descartado_por_geometria"].sum()),
        },
    }
    return metricas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--salida", default="resultados_contextual/lumbre_20261015_p0/comparacion_actual",
        help="Carpeta nueva donde guardar máscaras y paneles; no se sobrescriben archivos.",
    )
    parser.add_argument("--escena", help="Filtra por parte del nombre de escena.")
    args = parser.parse_args()
    destino = (ROOT / args.salida).resolve()
    destino.mkdir(parents=True, exist_ok=False)
    escenas = [par for par in ESCENAS if not args.escena or args.escena.casefold() in par[0].casefold()]
    informe = {
        "head": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "parametros": {
            "max_lado": 2500, "sensibilidad": 5, "area_minima_pct": .15,
            "distancia_maxima_pct": 10, "area_superpixel_px": 144,
            "distancia_crecimiento_px": 8,
        },
        "advertencia": "Composiciones JPEG sin anotaciones: los conteos son geométricos, no métricas de exactitud.",
        "escenas": {},
    }
    for nombre, fecha in escenas:
        informe["escenas"][nombre] = procesar_escena(nombre, fecha, destino)
        (destino / "metricas.json").write_text(
            json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(nombre, informe["escenas"][nombre]["diferencias_px"], flush=True)
    print(f"Resultados guardados en {destino}")


if __name__ == "__main__":
    main()
