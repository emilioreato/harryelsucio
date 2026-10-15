import numpy as np
import pytest

from pyroscope.agua import UMBRALES_AGUA_POR_DEFECTO, detectar_agua_probable
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
    resultado = detectar_agua_probable(
        extraer_caracteristicas_pareja(tc, swir), np.zeros(tc.shape[:2], dtype=bool)
    )
    assert not resultado.any()


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

