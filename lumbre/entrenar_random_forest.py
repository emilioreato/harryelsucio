"""Entrena y evalúa un clasificador de píxeles a partir de máscaras revisadas."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from PIL import Image
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import GroupShuffleSplit

from .detectores.random_forest import (
    MODELO_RANDOM_FOREST,
    NOMBRES_CARACTERISTICAS,
    VERSION_CARACTERISTICAS,
    extraer_caracteristicas_random_forest,
)
from .imagenes import abrir_rgb
from .ontologia import ETIQUETAS_CLASE, ClaseSemantica


CLASES_ENTRENABLES = tuple(int(clase) for clase in ETIQUETAS_CLASE if int(clase) != 0)
MAX_LADO_ENTRENAMIENTO = 1800
NOMBRES_ARCHIVO = {
    "true_color": ("true_color.png", "true_color.jpg", "true_color.jpeg", "true_color.tif", "true_color.tiff"),
    "swir": ("swir.png", "swir.jpg", "swir.jpeg", "swir.tif", "swir.tiff"),
    "labels": ("labels.png", "labels.tif", "labels.tiff"),
}


def _buscar_archivo(carpeta: Path, nombres: tuple[str, ...]) -> Path:
    encontrados = [
        carpeta / nombre
        for nombre in nombres
        if (carpeta / nombre).is_file()
    ]
    if len(encontrados) != 1:
        legibles = ", ".join(nombres)
        raise ValueError(
            f"Cada escena debe tener exactamente un archivo de estos nombres: {legibles}. "
            f"Problema en {carpeta}."
        )
    return encontrados[0]


def _grupo_incendio(carpeta: Path) -> str:
    archivo = carpeta / "group.txt"
    if not archivo.is_file():
        return carpeta.name
    grupo = archivo.read_text(encoding="utf-8").strip()
    if not grupo:
        raise ValueError(f"group.txt está vacío en {carpeta}.")
    return grupo


def _leer_escena(carpeta: Path, limite_muestras: int, rng: np.random.Generator):
    ruta_true = _buscar_archivo(carpeta, NOMBRES_ARCHIVO["true_color"])
    ruta_swir = _buscar_archivo(carpeta, NOMBRES_ARCHIVO["swir"])
    ruta_labels = _buscar_archivo(carpeta, NOMBRES_ARCHIVO["labels"])

    true_color, tamano_true = abrir_rgb(ruta_true.read_bytes(), MAX_LADO_ENTRENAMIENTO)
    swir, tamano_swir = abrir_rgb(ruta_swir.read_bytes(), MAX_LADO_ENTRENAMIENTO)
    if tamano_true != tamano_swir or true_color.shape != swir.shape:
        raise ValueError(
            f"True Color y SWIR deben tener la misma rejilla y fecha: {carpeta.name}."
        )

    with Image.open(ruta_labels) as imagen_labels:
        if imagen_labels.mode not in ("L", "P", "I", "I;16"):
            raise ValueError(
                f"{ruta_labels.name} debe ser una máscara de un canal con IDs de clase, no una imagen coloreada."
            )
        labels = np.asarray(imagen_labels, dtype=np.uint16)
    ancho_original, alto_original = tamano_true
    if labels.shape != (alto_original, ancho_original):
        raise ValueError(
            f"La máscara de {carpeta.name} no tiene el mismo tamaño que las imágenes originales."
        )
    if labels.max(initial=0) > max(CLASES_ENTRENABLES):
        raise ValueError(
            f"La máscara de {carpeta.name} contiene un ID de clase no reconocido. "
            f"Usa 0–{max(CLASES_ENTRENABLES)}."
        )
    if labels.shape != true_color.shape[:2]:
        labels = np.asarray(
            Image.fromarray(labels.astype(np.uint8)).resize(
                (true_color.shape[1], true_color.shape[0]),
                resample=Image.Resampling.NEAREST,
            ),
            dtype=np.uint8,
        )
    if not np.any(labels):
        raise ValueError(
            f"La máscara de {carpeta.name} solo contiene 0 (sin etiqueta); no aporta muestras de entrenamiento."
        )

    caracteristicas = extraer_caracteristicas_random_forest(true_color, swir).reshape(
        -1, len(NOMBRES_CARACTERISTICAS)
    )
    etiquetas_planas = labels.reshape(-1)
    muestras: list[np.ndarray] = []
    destinos: list[np.ndarray] = []
    for clase in CLASES_ENTRENABLES:
        indices = np.flatnonzero(etiquetas_planas == clase)
        if indices.size == 0:
            continue
        cantidad = min(limite_muestras, indices.size)
        seleccion = rng.choice(indices, size=cantidad, replace=False)
        muestras.append(caracteristicas[seleccion])
        destinos.append(np.full(cantidad, clase, dtype=np.uint8))
    if not muestras:
        raise ValueError(f"La máscara de {carpeta.name} no contiene clases reconocidas.")
    return np.concatenate(muestras), np.concatenate(destinos)


def entrenar(
    carpeta_dataset: Path,
    ruta_modelo: Path,
    *,
    muestras_por_clase: int = 25_000,
    semilla: int = 42,
) -> dict[str, object]:
    """Evalúa dejando escenas fuera y guarda el modelo final entrenado en todas."""
    if muestras_por_clase < 1:
        raise ValueError("El máximo de muestras por clase debe ser positivo.")
    escenas = tuple(
        carpeta
        for carpeta in sorted(carpeta_dataset.iterdir(), key=lambda p: p.name.casefold())
        if carpeta.is_dir()
    ) if carpeta_dataset.is_dir() else ()
    if len(escenas) < 2:
        raise ValueError(
            "Se necesitan al menos dos carpetas de escena etiquetadas para evaluar "
            "sin mezclar píxeles vecinos entre entrenamiento y prueba."
        )
    grupos_escenas = {escena.name: _grupo_incendio(escena) for escena in escenas}
    if len(set(grupos_escenas.values())) < 2:
        raise ValueError(
            "Se necesitan al menos dos incendios/grupos independientes. Si dos escenas "
            "son del mismo incendio, pon el mismo ID en su archivo group.txt."
        )

    rng = np.random.default_rng(semilla)
    caracteristicas: list[np.ndarray] = []
    etiquetas: list[np.ndarray] = []
    grupos: list[np.ndarray] = []
    for escena in escenas:
        print(f"Leyendo etiquetas revisadas: {escena.name}")
        x_escena, y_escena = _leer_escena(escena, muestras_por_clase, rng)
        caracteristicas.append(x_escena)
        etiquetas.append(y_escena)
        grupos.append(np.full(y_escena.size, grupos_escenas[escena.name], dtype=object))

    x = np.concatenate(caracteristicas)
    y = np.concatenate(etiquetas)
    group_ids = np.concatenate(grupos)
    if np.unique(y).size < 2:
        raise ValueError("El conjunto debe contener al menos dos clases etiquetadas.")

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=semilla)
    indices_train, indices_test = next(splitter.split(x, y, groups=group_ids))
    modelo = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced_subsample",
        min_samples_leaf=2,
        max_features="sqrt",
        random_state=semilla,
        n_jobs=-1,
    )
    modelo.fit(x[indices_train], y[indices_train])
    predicciones = modelo.predict(x[indices_test])
    etiquetas_evaluacion = sorted(int(clase) for clase in np.unique(y))
    nombres_evaluacion = [
        ETIQUETAS_CLASE[ClaseSemantica(clase)]
        for clase in etiquetas_evaluacion
    ]
    print("\nEvaluación en escenas reservadas (métricas por clase):")
    print(
        classification_report(
            y[indices_test],
            predicciones,
            labels=etiquetas_evaluacion,
            target_names=nombres_evaluacion,
            zero_division=0,
        )
    )
    print("Matriz de confusión (filas = referencia, columnas = predicción):")
    print(confusion_matrix(y[indices_test], predicciones, labels=etiquetas_evaluacion))
    print(f"Escenas de prueba: {', '.join(sorted(set(group_ids[indices_test])))}")

    # Solo después de imprimir la evaluación se ajusta el artefacto final con
    # todas las escenas disponibles. El informe previo sigue siendo hold-out.
    modelo_final = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced_subsample",
        min_samples_leaf=2,
        max_features="sqrt",
        random_state=semilla,
        n_jobs=-1,
    )
    modelo_final.fit(x, y)
    paquete = {
        "feature_version": VERSION_CARACTERISTICAS,
        "feature_names": NOMBRES_CARACTERISTICAS,
        "model": modelo_final,
        "classes": tuple(int(clase) for clase in modelo_final.classes_),
        "class_names": {
            int(clase): ETIQUETAS_CLASE[ClaseSemantica(int(clase))]
            for clase in modelo_final.classes_
        },
        "training_scenes": tuple(escena.name for escena in escenas),
        "validation_groups": tuple(sorted(set(group_ids[indices_test]))),
        "validation_report": classification_report(
            y[indices_test],
            predicciones,
            labels=etiquetas_evaluacion,
            target_names=nombres_evaluacion,
            output_dict=True,
            zero_division=0,
        ),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "rendered_rgb_only": True,
    }
    ruta_modelo.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(paquete, ruta_modelo)
    print(f"\nModelo guardado en: {ruta_modelo}")
    print("Entrenamiento experimental con composiciones RGB renderizadas; no son reflectancias.")
    return paquete


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Entrena Random Forest desde parejas RGB alineadas y máscaras PNG revisadas."
    )
    raiz = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--dataset",
        type=Path,
        default=raiz / "training" / "random_forest" / "dataset",
        help="Carpeta con una subcarpeta etiquetada por escena.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=MODELO_RANDOM_FOREST,
        help="Ruta del artefacto para usar después en el detector de Lumbre.",
    )
    parser.add_argument(
        "--samples-per-class",
        type=int,
        default=25_000,
        help="Límite reproducible de muestras por clase y escena.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    entrenar(
        args.dataset,
        args.model,
        muestras_por_clase=args.samples_per_class,
        semilla=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
