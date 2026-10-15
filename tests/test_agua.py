import numpy as np
import pytest

from pyroscope.agua import (
    UMBRALES_AGUA_POR_DEFECTO,
    _detectar_agua_probable_experimental,
    detectar_agua_probable,
)
from pyroscope.caracteristicas import extraer_caracteristicas_pareja


def _caracteristicas_uniformes(color_tc, color_swir, *, ruido=0):
    rng = np.random.default_rng(13)
    tc = np.full((96, 112, 3), color_tc, dtype=np.uint8)
    swir = np.full_like(tc, color_swir)
    if ruido:
        for imagen in (tc, swir):
            imagen[:] = np.clip(
                imagen.astype(np.int16)
                + rng.integers(-ruido, ruido + 1, imagen.shape),
                0,
                255,
            ).astype(np.uint8)
    return tc, swir


def _escena_terreno_sintetica(*, incluir_agua=True):
    """Composición de prueba con verdes, suelo oscuro, humo y agua opcional."""
    alto, ancho = 192, 224
    rng = np.random.default_rng(31)
    ruido = rng.integers(-13, 14, (alto, ancho, 3), dtype=np.int16)
    true_color = np.clip(np.array((96, 112, 83)) + ruido, 0, 255).astype(np.uint8)
    swir = np.clip(np.array((83, 107, 75)) + ruido, 0, 255).astype(np.uint8)

    agua = np.zeros((alto, ancho), dtype=bool)
    if incluir_agua:
        agua[8:15, 10:21] = True
        true_color[agua] = (15, 16, 18)
        swir[agua] = (13, 14, 15)

    vegetacion_verde = np.zeros_like(agua)
    vegetacion_verde[32:68, 28:70] = True
    true_color[vegetacion_verde] = (11, 38, 9)
    swir[vegetacion_verde] = (9, 43, 7)

    vegetacion_oscura = np.zeros_like(agua)
    vegetacion_oscura[82:114, 25:64] = True
    true_color[vegetacion_oscura] = (16, 30, 12)
    swir[vegetacion_oscura] = (9, 31, 7)

    suelo_quemado = np.zeros_like(agua)
    suelo_quemado[125:158, 26:68] = True
    true_color[suelo_quemado] = (24, 11, 5)
    swir[suelo_quemado] = (35, 12, 4)

    humo = np.zeros_like(agua)
    humo[82:114, 130:162] = True
    true_color[humo] = (35, 43, 37)
    swir[humo] = (27, 34, 30)

    return true_color, swir, {
        "agua": agua,
        "vegetacion_verde": vegetacion_verde,
        "vegetacion_oscura": vegetacion_oscura,
        "suelo_quemado": suelo_quemado,
        "humo": humo,
    }


@pytest.mark.parametrize(
    "color_tc,color_swir,ruido",
    [
        ((48, 112, 42), (52, 120, 48), 0),
        ((48, 112, 42), (52, 120, 48), 2),
        ((12, 18, 24), (10, 14, 20), 0),
    ],
)
def test_escena_uniforme_no_se_convierte_entera_en_agua(color_tc, color_swir, ruido):
    tc, swir = _caracteristicas_uniformes(color_tc, color_swir, ruido=ruido)
    caracteristicas = extraer_caracteristicas_pareja(tc, swir)
    mascara_humo = np.zeros(tc.shape[:2], dtype=bool)
    assert not detectar_agua_probable(caracteristicas, mascara_humo).any()
    assert not _detectar_agua_probable_experimental(caracteristicas, mascara_humo).any()


def test_agua_oscura_azulada_se_detecta_con_apoyo_de_las_dos_vistas():
    forma = (128, 128)
    tc = np.full((*forma, 3), (48, 112, 42), dtype=np.uint8)
    swir = np.full_like(tc, (52, 120, 48))
    agua = np.zeros(forma, dtype=bool)
    agua[25:90, 82:120] = True
    tc[agua] = (20, 44, 88)
    swir[agua] = (16, 32, 82)

    resultado = detectar_agua_probable(
        extraer_caracteristicas_pareja(tc, swir), np.zeros(forma, dtype=bool)
    )

    assert resultado[agua].all()
    assert not resultado[~agua].any()
    assert UMBRALES_AGUA_POR_DEFECTO["swir_red_green_max"] == 0.85


def test_todo_bajo_humo_no_aporta_una_mascara_de_agua():
    tc, swir = _caracteristicas_uniformes((48, 112, 42), (52, 120, 48))
    humo = np.ones(tc.shape[:2], dtype=bool)
    resultado = detectar_agua_probable(extraer_caracteristicas_pareja(tc, swir), humo)
    assert not resultado.any()


def test_agua_neutra_pequena_se_detecta_con_predominio_verde_en_la_escena():
    tc, swir, regiones = _escena_terreno_sintetica()
    caracteristicas = extraer_caracteristicas_pareja(tc, swir)
    mascara_humo = regiones["humo"]

    # Reproduce el caso observado en La Mierla: el cuantil global es negativo,
    # por lo que el agua neutra no debe confundirse con ausencia de rojo.
    despejado = ~mascara_humo
    assert np.quantile(caracteristicas[..., 6][despejado], 0.85) < 0

    resultado = _detectar_agua_probable_experimental(caracteristicas, mascara_humo)

    assert resultado[regiones["agua"]].all()
    assert not resultado[regiones["humo"]].any()


def test_vegetacion_verde_intensa_y_oscura_no_se_convierte_en_agua():
    tc, swir, regiones = _escena_terreno_sintetica()
    resultado = _detectar_agua_probable_experimental(
        extraer_caracteristicas_pareja(tc, swir), regiones["humo"]
    )

    assert not resultado[regiones["vegetacion_verde"]].any()
    assert not resultado[regiones["vegetacion_oscura"]].any()


def test_suelo_quemado_oscuro_no_se_convierte_en_agua():
    tc, swir, regiones = _escena_terreno_sintetica(incluir_agua=False)
    resultado = _detectar_agua_probable_experimental(
        extraer_caracteristicas_pareja(tc, swir), regiones["humo"]
    )

    assert not resultado[regiones["suelo_quemado"]].any()


def test_escena_sin_agua_mantiene_candidatos_aislados_sin_clasificar():
    tc, swir, regiones = _escena_terreno_sintetica(incluir_agua=False)
    resultado = _detectar_agua_probable_experimental(
        extraer_caracteristicas_pareja(tc, swir), regiones["humo"]
    )

    assert not resultado.any()


def test_el_humo_marcado_no_aparece_en_la_mascara_de_agua():
    tc, swir, regiones = _escena_terreno_sintetica()
    resultado = _detectar_agua_probable_experimental(
        extraer_caracteristicas_pareja(tc, swir), regiones["humo"]
    )

    assert not resultado[regiones["humo"]].any()


@pytest.mark.parametrize(
    "caracteristicas,humo",
    [
        (np.full((8, 8, 8), np.nan, dtype=np.float32), np.zeros((8, 8), bool)),
        (np.zeros((8, 8, 8), dtype=np.float32), np.full((8, 8), 2, dtype=np.uint8)),
        (np.zeros((7, 8, 8), dtype=np.float32), np.zeros((8, 8), bool)),
    ],
)
def test_rechaza_caracteristicas_o_mascaras_malformadas(caracteristicas, humo):
    with pytest.raises(ValueError):
        detectar_agua_probable(caracteristicas, humo)

