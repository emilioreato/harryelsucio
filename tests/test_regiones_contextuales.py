"""Invariantes del motor espacial; no evalúan precisión en imágenes reales."""

import numpy as np
import pytest
from scipy import ndimage as ndi

from lumbre.regiones_contextuales import refinar_frontera_local, segmentar_contextual


def escena():
    rng = np.random.default_rng(42)
    tc = rng.integers(40, 160, (48, 64, 3), dtype=np.uint8)
    swir = tc.copy()
    candidata = np.zeros(tc.shape[:2], bool)
    candidata[8:25, 6:23] = True
    candidata[30:43, 46:60] = True
    vacia = np.zeros_like(candidata)
    return tc, swir, candidata, vacia.copy(), vacia.copy()


def test_reproducibilidad_y_conservacion_de_cicatrices_independientes():
    entrada = escena()
    primero = segmentar_contextual(*entrada, refinar=False)
    segundo = segmentar_contextual(*entrada, refinar=False)
    assert np.array_equal(primero.etiquetas, segundo.etiquetas)
    assert np.array_equal(primero.mascara, segundo.mascara)
    assert primero.uniones == segundo.uniones
    assert np.array_equal(primero.mascara, entrada[2])
    assert ndi.label(primero.mascara)[1] == 2


@pytest.mark.parametrize("evidencia", [None, 0.6, 1.0])
def test_sin_candidatos_no_crece_aunque_haya_score(evidencia):
    tc, swir, candidata, agua, humo = escena()
    candidata[:] = False
    score = None if evidencia is None else np.full(candidata.shape, evidencia)
    resultado = segmentar_contextual(tc, swir, candidata, agua, humo, evidencia=score)
    assert not resultado.mascara.any()
    assert not resultado.diagnosticos["seeds"].any()
    assert not resultado.watershed_aplicado


def test_agua_y_humo_vetan_superficie_sin_destruir_capas_de_entrada():
    tc, swir, candidata, agua, humo = escena()
    agua[12:16, 10:14] = True
    humo[18:22, 10:18] = True
    agua_original, humo_original = agua.copy(), humo.copy()
    resultado = segmentar_contextual(tc, swir, candidata, agua, humo)
    assert not resultado.mascara[agua | humo].any()
    assert np.array_equal(agua, agua_original)
    assert np.array_equal(humo, humo_original)


def test_superpixel_mixto_conserva_detalles_individuales():
    tc = np.full((32, 32, 3), 100, np.uint8)
    candidata = np.zeros((32, 32), bool)
    candidata[5:27, 5:27] = True
    candidata[10:22, 10:22] = False
    candidata[15, 5:15] = False
    vacia = np.zeros_like(candidata)
    resultado = segmentar_contextual(
        tc, tc, candidata, vacia, vacia, area_superpixel=1024,
        refinar=False,
    )
    assert np.unique(resultado.etiquetas).size == 1
    assert np.array_equal(resultado.mascara, candidata)
    etiqueta = int(resultado.etiquetas[0, 0])
    assert resultado.estadisticas["clase"][etiqueta] == 2


@pytest.mark.parametrize("score", [np.nan, np.inf, -0.01, 1.01])
def test_rechaza_scores_no_normalizados(score):
    entrada = escena()
    with pytest.raises(ValueError, match="evidencia"):
        segmentar_contextual(*entrada, evidencia=np.full(entrada[2].shape, score))


def test_rechaza_evidencia_con_otra_rejilla():
    with pytest.raises(ValueError, match="evidencia"):
        segmentar_contextual(*escena(), evidencia=np.zeros((4, 4)))


def test_watershed_fallback_sin_marcadores_fiables():
    mascara = escena()[2]
    salida, aplicado, positivas, negativas = refinar_frontera_local(
        mascara, np.full(mascara.shape, .5), np.zeros(mascara.shape),
        np.zeros_like(mascara),
    )
    assert np.array_equal(salida, mascara)
    assert not aplicado
    assert not positivas.any()
    assert not negativas.any()


def test_watershed_sin_semillas_positivas_tampoco_modifica():
    mascara = escena()[2]
    salida, aplicado, positivas, negativas = refinar_frontera_local(
        mascara, np.full(mascara.shape, .1), np.zeros(mascara.shape),
        np.zeros_like(mascara),
    )
    assert np.array_equal(salida, mascara)
    assert not aplicado
    assert not positivas.any()
    assert negativas.any()


def test_contexto_excluye_terreno_remoto_y_conserva_cicatriz_lejana():
    tc = np.full((160, 240, 3), (45, 110, 45), np.uint8)
    candidata = np.zeros(tc.shape[:2], bool)
    candidata[12:30, 12:30] = True
    candidata[128:143, 206:223] = True
    tc[candidata] = (120, 55, 35)
    agua = np.zeros_like(candidata)
    resultado = segmentar_contextual(tc, tc, candidata, agua, agua, refinar=False)
    contexto = resultado.diagnosticos["context"]
    assert contexto[candidata].all()
    assert not contexto[70:90, 105:125].any()
    assert not resultado.etiquetas[~contexto].any()
    assert np.all(resultado.etiquetas[candidata] > 0)
    assert np.array_equal(resultado.mascara, candidata)
    assert ndi.label(resultado.mascara)[1] == 2
    assert np.all(resultado.mascara[128:143, 206:223])


def test_contexto_completo_sigue_disponible_como_comparacion():
    tc = np.full((96, 160, 3), 100, np.uint8)
    candidata = np.zeros(tc.shape[:2], bool)
    candidata[10:20, 10:20] = True
    vacia = np.zeros_like(candidata)
    resultado = segmentar_contextual(
        tc, tc, candidata, vacia, vacia, limitar_contexto=False, refinar=False,
    )
    assert resultado.diagnosticos["context"].all()
    assert np.all(resultado.etiquetas > 0)
    assert np.array_equal(resultado.mascara, candidata)


def test_sin_semillas_no_ejecuta_slic_y_devuelve_estadisticas_vacias():
    tc, swir, candidata, agua, humo = escena()
    candidata[:] = False
    resultado = segmentar_contextual(tc, swir, candidata, agua, humo)
    assert resultado.estadisticas == {}
    assert not resultado.diagnosticos["context"].any()
    assert not resultado.etiquetas.any()
    assert resultado.uniones == 0
    assert not resultado.mascara.any()


def test_exterior_roi_no_es_region_ambigua_aunque_otro_detector_de_scores():
    tc = np.full((96, 160, 3), 100, np.uint8)
    candidata = np.zeros(tc.shape[:2], bool)
    candidata[10:20, 10:20] = True
    vacia = np.zeros_like(candidata)
    resultado = segmentar_contextual(
        tc, tc, candidata, vacia, vacia, evidencia=np.ones(candidata.shape),
        refinar=False,
    )
    exterior = ~resultado.diagnosticos["context"]
    assert exterior.any()
    assert not resultado.diagnosticos["region-classes"][exterior].any()
    assert not resultado.diagnosticos["rag"][exterior].any()
    assert not resultado.mascara[exterior].any()


@pytest.mark.parametrize("nombre", ["area_superpixel", "distancia_crecimiento_px"])
@pytest.mark.parametrize("valor", [np.nan, np.inf, -np.inf])
def test_rechaza_parametros_espaciales_no_finitos(nombre, valor):
    with pytest.raises(ValueError):
        segmentar_contextual(*escena(), **{nombre: valor})
