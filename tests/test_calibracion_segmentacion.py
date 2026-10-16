"""Matriz pequeña y reproducible para casos difíciles de la segmentación.

Las máscaras aquí son verdad sintética conocida; estas pruebas comprueban
robustez y regresiones, no estiman precisión en las escenas JPEG del reto.
"""

import numpy as np
import pytest

from lumbre.detectores.swir_histeresis import (
    clasificar_pixeles_area_afectada_swir,
)
from lumbre.detectores.kmeans import clasificar_pixeles_area_afectada
from lumbre.detectores.fusion import clasificar_fusion_ponderada
from lumbre.caracteristicas import extraer_caracteristicas_pareja
from lumbre.agua import detectar_agua_probable
from lumbre.segmentacion import segmentar_superficie_afectada
from lumbre.servidor_web import _validar_ajustes


def _escena(tipo: str, *, ruido: int = 2, semilla: int = 19):
    rng = np.random.default_rng(semilla)
    forma = (128, 128)
    tc = np.full((*forma, 3), (48, 112, 42), dtype=np.uint8)
    swir = np.full_like(tc, (52, 120, 48))
    quemado = np.zeros(forma, dtype=bool)
    artefacto = np.zeros(forma, dtype=bool)

    if tipo != "sin_incendio":
        quemado[28:78, 25:75] = True
        tc[quemado] = (128, 94, 62)
        swir[quemado] = (210, 76, 52)
    if tipo == "agua":
        tc[14:54, 82:120] = (20, 44, 88)
        swir[14:54, 82:120] = (16, 32, 82)
    elif tipo == "humo":
        tc[38:70, 48:90] = (165, 170, 174)
        swir[38:70, 48:90] = (82, 125, 132)
    elif tipo == "artefacto_remoto":
        artefacto[92:115, 88:118] = True
        tc[artefacto] = (204, 82, 36)
        swir[artefacto] = (218, 62, 36)

    if ruido:
        for imagen in (tc, swir):
            imagen[:] = np.clip(
                imagen.astype(np.int16)
                + rng.integers(-ruido, ruido + 1, imagen.shape),
                0,
                255,
            ).astype(np.uint8)
    return tc, swir, quemado, artefacto


def _precision_recall(predicha, referencia):
    tp = int(np.count_nonzero(predicha & referencia))
    fp = int(np.count_nonzero(predicha & ~referencia))
    fn = int(np.count_nonzero(~predicha & referencia))
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return precision, recall, tp, fp, fn


@pytest.mark.parametrize("ruido", [0, 1, 2])
@pytest.mark.parametrize("sensibilidad", [1, 5, 10])
def test_ruido_sin_incendio_no_se_convierte_en_superficie(ruido, sensibilidad):
    tc, swir, _, _ = _escena("sin_incendio", ruido=ruido)
    resultado = clasificar_pixeles_area_afectada_swir(
        tc, swir, sensibilidad=sensibilidad
    )
    assert not resultado.mascara_candidata.any()
    assert not resultado.mascara_candidata_bajo_humo.any()


@pytest.mark.parametrize("sensibilidad", [4, 5, 6])
def test_sensibilidad_moderada_conserva_la_cicatriz_sintetica(sensibilidad):
    tc, swir, quemado, _ = _escena("incendio")
    resultado = clasificar_pixeles_area_afectada_swir(
        tc, swir, sensibilidad=sensibilidad
    )
    precision, recall, _, falsos_positivos, _ = _precision_recall(
        resultado.mascara_candidata, quemado
    )
    assert precision >= 0.98
    assert recall >= 0.98
    assert falsos_positivos <= 50


@pytest.mark.parametrize("sensibilidad", [5, 6])
def test_perfil_filtra_artefacto_naranja_remoto_y_conserva_cicatriz(sensibilidad):
    tc, swir, quemado, artefacto = _escena("artefacto_remoto")
    resultado = segmentar_superficie_afectada(
        tc,
        swir,
        metodo="contextual_hibrida",
        sensibilidad=sensibilidad,
        area_minima_pct=0.15,
        distancia_maxima_pct=10,
    )
    precision, recall, _, _, _ = _precision_recall(resultado.mascara, quemado)
    assert precision >= 0.98
    assert recall >= 0.90
    assert not resultado.mascara[artefacto].any()
    assert resultado.componentes_remotos_descartados >= 1


def test_lago_oscuro_no_se_incluye_en_superficie_candidata():
    tc, swir, _, _ = _escena("agua")
    agua_real = np.zeros(tc.shape[:2], dtype=bool)
    agua_real[14:54, 82:120] = True
    resultado = clasificar_pixeles_area_afectada_swir(tc, swir, sensibilidad=5)
    mascara_agua = detectar_agua_probable(
        extraer_caracteristicas_pareja(tc, swir), resultado.mascara_humo
    )
    assert mascara_agua[agua_real].mean() >= 0.95
    assert not resultado.mascara_candidata[agua_real].any()


def test_ajuste_conservar_focos_separados_puede_retener_el_componente_remoto():
    tc, swir, _, artefacto = _escena("artefacto_remoto")
    resultado = segmentar_superficie_afectada(
        tc,
        swir,
        metodo="contextual_hibrida",
        sensibilidad=5,
        area_minima_pct=0.15,
        distancia_maxima_pct=10,
        conservar_regiones_separadas=True,
    )
    assert resultado.mascara[artefacto].any()


@pytest.mark.parametrize("sensibilidad", [4, 5, 6])
def test_una_sensibilidad_mayor_no_reduce_la_candidata_en_caso_controlado(sensibilidad):
    tc, swir, _, _ = _escena("incendio")
    menor = clasificar_pixeles_area_afectada_swir(
        tc, swir, sensibilidad=sensibilidad
    ).mascara_candidata
    mayor = clasificar_pixeles_area_afectada_swir(
        tc, swir, sensibilidad=sensibilidad + 1
    ).mascara_candidata
    assert np.all(menor <= mayor)


def test_perfil_inicial_del_servidor_usa_valores_recomendados():
    perfil = _validar_ajustes({})
    assert perfil["detector"].id == "contextual_hibrida"
    assert perfil["sensitivity"] == 6
    assert perfil["minimum_area_pct"] == 0.15
    assert perfil["max_distance_pct"] == 10
    assert perfil["keep_separate"] is False
    assert perfil["advanced"]["use_random_forest"] is False
    assert perfil["advanced"]["water_thresholds"]["swir_red_green_max"] == 0.85


@pytest.mark.parametrize("color", [(120, 120, 120), (52, 120, 48)])
@pytest.mark.parametrize("sensibilidad", [1, 6, 10])
def test_kmeans_no_fuerza_superficie_sin_senal_swir(color, sensibilidad):
    imagen = np.full((48, 48, 3), color, np.uint8)
    resultado = clasificar_pixeles_area_afectada(imagen, imagen, sensibilidad=sensibilidad)
    assert not resultado.mascara_candidata.any()
    assert not resultado.mascara_candidata_bajo_humo.any()


def test_kmeans_conserva_cicatriz_con_senal_swir():
    tc, swir, quemado, _ = _escena("incendio")
    resultado = clasificar_pixeles_area_afectada(tc, swir, sensibilidad=6)
    precision, recall, *_ = _precision_recall(resultado.mascara_candidata, quemado)
    assert precision >= 0.98
    assert recall >= 0.98


def test_fusion_umbral_cero_no_inventa_votos():
    tc, swir, _, _ = _escena("sin_incendio", ruido=0)
    resultado = clasificar_fusion_ponderada(tc, swir, umbral_voto=0)
    assert not resultado.mascara_candidata.any()
    assert not resultado.mascara_candidata_bajo_humo.any()

