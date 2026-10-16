from dataclasses import replace

import numpy as np
import pytest
import joblib
from sklearn.ensemble import RandomForestClassifier

from lumbre.caracteristicas import extraer_caracteristicas_pareja
from lumbre.detectores import random_forest as random_forest_module
from lumbre.evidencia_contextual import EvidenciaContextual
from lumbre.modelos_segmentacion import ResultadoClasificacionSemantica
from lumbre.ontologia import ClaseSemantica
from lumbre.segmentacion import (
    _aplicar_random_forest_contextual,
    _fusionar_evidencia_random_forest,
    segmentar_superficie_afectada,
)
from lumbre.servidor_web import _validar_ajustes


def _clasificacion(candidata, agua=None, humo=None):
    forma = candidata.shape
    vacia = np.zeros(forma, dtype=bool)
    return ResultadoClasificacionSemantica(
        mascara_candidata=candidata.copy(),
        mascara_candidata_bajo_humo=vacia.copy(),
        mascara_agua=vacia.copy() if agua is None else agua.copy(),
        mascara_humo=vacia.copy() if humo is None else humo.copy(),
        confianza_humo=np.zeros(forma, dtype=np.float32),
        clase_por_pixel=np.zeros(forma, dtype=np.uint8),
        centros=np.empty((0, 8), dtype=np.float32),
        clases_seleccionadas=(),
        puntuaciones_clase=np.asarray((0.8, 0.4), dtype=np.float32),
    )


def test_random_forest_solo_aporta_con_respaldo_y_respeta_agua_humo():
    forma = (12, 12)
    base = np.zeros(forma, dtype=bool)
    base[1, 1] = True
    agua, humo = np.zeros(forma, bool), np.zeros(forma, bool)
    agua[3, 3], humo[4, 4] = True, True
    clasificacion_base = _clasificacion(base, agua, humo)

    propuesta_rf = np.zeros(forma, dtype=bool)
    propuesta_rf[1, 1] = True  # RF no puede borrar el resultado de base.
    propuesta_rf[2, 2] = True  # SWIR/contexto confirma este píxel.
    propuesta_rf[3, 3] = True  # Agua protegida.
    propuesta_rf[4, 4] = True  # Humo protegido.
    propuesta_rf[5, 5] = True  # Sin corroboración externa.
    clasificacion_rf = _clasificacion(propuesta_rf)

    evidencia = np.zeros(forma, dtype=np.float32)
    evidencia[2, 2] = 0.45
    evidencia[3, 3] = 0.7
    evidencia[4, 4] = 0.7
    evidencia[5, 5] = 0.2
    evidencia_base = EvidenciaContextual(evidencia, {"evidencia_swir_v2": evidencia.copy()})

    fusionada, evidencia_fusionada = _fusionar_evidencia_random_forest(
        clasificacion_base, clasificacion_rf, evidencia_base
    )

    assert fusionada.mascara_candidata[1, 1]
    assert fusionada.mascara_candidata[2, 2]
    assert fusionada.clase_por_pixel[2, 2] == ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
    assert not fusionada.mascara_candidata[3, 3]
    assert not fusionada.mascara_candidata[4, 4]
    assert not fusionada.mascara_candidata[5, 5]
    assert evidencia_fusionada[2, 2] >= 0.8
    assert evidencia_fusionada.diagnosticos["random_forest_unconfirmed"][5, 5]
    assert not clasificacion_base.mascara_candidata[2, 2]  # Entrada inmutable.


def test_fallo_del_modelo_opcional_devuelve_aviso_sin_detener_v2(monkeypatch):
    forma = (10, 10)
    base = _clasificacion(np.zeros(forma, dtype=bool))
    imagen = np.full((*forma, 3), 80, dtype=np.uint8)
    caracteristicas = np.zeros((*forma, 8), dtype=np.float32)

    def fallo(*_args, **_kwargs):
        raise ValueError("modelo de prueba incompatible")

    monkeypatch.setattr("lumbre.segmentacion.clasificar_random_forest", fallo)
    resultado, evidencia, aviso = _aplicar_random_forest_contextual(
        base, imagen, imagen, caracteristicas, None
    )

    assert resultado is base
    assert evidencia is None
    assert aviso and "modelo de prueba incompatible" in aviso
    assert "segmentación contextual habitual" in aviso


def test_fusion_rf_rechaza_mascaras_desalineadas():
    forma = (8, 8)
    base = _clasificacion(np.zeros(forma, dtype=bool))
    desalineada = _clasificacion(np.zeros((7, 8), dtype=bool))
    with pytest.raises(ValueError, match="coincidir con la rejilla"):
        _fusionar_evidencia_random_forest(base, desalineada, np.zeros(forma, np.float32))


def test_api_valida_el_interruptor_random_forest():
    ajustes = _validar_ajustes({
        "method": "contextual_hibrida",
        "advanced": {"use_random_forest": True},
    })
    assert ajustes["advanced"]["use_random_forest"] is True
    with pytest.raises(ValueError, match="debe ser booleana"):
        _validar_ajustes({
            "method": "contextual_hibrida",
            "advanced": {"use_random_forest": "true"},
        })


def test_fallo_rf_en_el_recorrido_completo_conserva_resultado_contextual(monkeypatch):
    forma = (48, 48)
    true_color = np.full((*forma, 3), (46, 116, 44), dtype=np.uint8)
    swir = np.full((*forma, 3), (52, 122, 50), dtype=np.uint8)

    def fallo(*_args, **_kwargs):
        raise RuntimeError("fallo simulado del modelo")

    monkeypatch.setattr("lumbre.segmentacion.clasificar_random_forest", fallo)
    resultado = segmentar_superficie_afectada(
        true_color,
        swir,
        metodo="contextual_hibrida",
        ajustes_avanzados={"use_random_forest": True},
    )

    assert resultado.mascara.shape == forma
    assert resultado.avisos and "fallo simulado del modelo" in resultado.avisos[0]
    assert "segmentación contextual habitual" in resultado.avisos[0]


def test_clasificador_rf_entrenado_en_temporal_se_integra_con_evidencia_swir(
    monkeypatch, tmp_path
):
    forma = (32, 32)
    true_color = np.full((*forma, 3), (42, 118, 40), dtype=np.uint8)
    swir = np.full((*forma, 3), (50, 116, 46), dtype=np.uint8)
    zona = np.zeros(forma, dtype=bool)
    zona[10:22, 10:22] = True
    true_color[zona] = (150, 96, 62)
    swir[zona] = (220, 68, 36)
    caracteristicas = extraer_caracteristicas_pareja(true_color, swir)
    filas_rf = random_forest_module.extraer_caracteristicas_random_forest(true_color, swir)
    etiquetas = np.where(zona, ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA,
                         ClaseSemantica.VEGETACION).astype(np.uint8)
    modelo = RandomForestClassifier(n_estimators=8, random_state=7, n_jobs=1)
    modelo.fit(filas_rf.reshape(-1, filas_rf.shape[-1]), etiquetas.ravel())
    ruta_modelo = tmp_path / "random_forest.joblib"
    joblib.dump({
        "feature_version": random_forest_module.VERSION_CARACTERISTICAS,
        "feature_names": random_forest_module.NOMBRES_CARACTERISTICAS,
        "model": modelo,
    }, ruta_modelo)
    monkeypatch.setattr(random_forest_module, "MODELO_RANDOM_FOREST", ruta_modelo)

    candidata_v2 = zona.copy()
    base = replace(
        _clasificacion(np.zeros(forma, dtype=bool)),
        mascara_candidata_v2=candidata_v2,
    )
    resultado, evidencia, aviso = _aplicar_random_forest_contextual(
        base, true_color, swir, caracteristicas, None
    )

    assert aviso is None
    assert evidencia is not None
    assert evidencia.diagnosticos["random_forest_candidates"][zona].all()
    assert evidencia.diagnosticos["random_forest_support"][zona].all()
    assert resultado.mascara_candidata[zona].all()


def test_recorrido_contextual_completo_con_rf_opcional(monkeypatch, tmp_path):
    forma = (48, 48)
    true_color = np.full((*forma, 3), (42, 118, 40), dtype=np.uint8)
    swir = np.full((*forma, 3), (50, 116, 46), dtype=np.uint8)
    zona = np.zeros(forma, dtype=bool)
    zona[14:34, 14:34] = True
    true_color[zona] = (150, 96, 62)
    swir[zona] = (220, 68, 36)
    filas_rf = random_forest_module.extraer_caracteristicas_random_forest(true_color, swir)
    etiquetas = np.where(zona, ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA,
                         ClaseSemantica.VEGETACION).astype(np.uint8)
    modelo = RandomForestClassifier(n_estimators=8, random_state=7, n_jobs=1)
    modelo.fit(filas_rf.reshape(-1, filas_rf.shape[-1]), etiquetas.ravel())
    ruta_modelo = tmp_path / "random_forest.joblib"
    joblib.dump({
        "feature_version": random_forest_module.VERSION_CARACTERISTICAS,
        "feature_names": random_forest_module.NOMBRES_CARACTERISTICAS,
        "model": modelo,
    }, ruta_modelo)
    monkeypatch.setattr(random_forest_module, "MODELO_RANDOM_FOREST", ruta_modelo)

    resultado = segmentar_superficie_afectada(
        true_color,
        swir,
        metodo="contextual_hibrida",
        area_minima_pct=0.01,
        ajustes_avanzados={"use_random_forest": True},
    )

    assert not resultado.avisos
    assert resultado.diagnosticos_contextuales is not None
    assert resultado.diagnosticos_contextuales["random_forest_candidates"].shape == forma
    assert resultado.diagnosticos_contextuales["random_forest_support"].any()
