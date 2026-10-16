import numpy as np
import pytest

from lumbre.estimacion_bajo_humo import estimar_bajo_humo


def escena(anchura=3):
    visible = np.zeros((32, 48), dtype=bool)
    visible[8:24, 4:44] = True
    humo = np.zeros_like(visible)
    humo[:, 20:20 + anchura] = True
    visible &= ~humo
    return visible, humo, np.zeros_like(visible)


def test_hueco_estrecho_con_dos_lados_y_sin_rellenar_penacho():
    visible, humo, agua = escena()
    resultado = estimar_bajo_humo(visible, humo, agua, distancia_maxima_px=5)
    assert np.all(resultado.mascara_continuidad[8:24, 20:23])
    assert not np.any(resultado.mascara_candidata[:6])
    assert np.all(resultado.mascara_indeterminada[:6, 20:23])
    assert not np.any(resultado.mascara_candidata & visible)


def test_columna_extensa_permanece_desconocida():
    visible, humo, agua = escena(16)
    resultado = estimar_bajo_humo(visible, humo, agua, distancia_maxima_px=5)
    assert not np.any(resultado.mascara_candidata)
    assert np.array_equal(resultado.mascara_indeterminada, humo)


@pytest.mark.parametrize("obstaculo", ["agua", "contradiccion", "swir"])
def test_obstaculos_impiden_puentes(obstaculo):
    visible, humo, agua = escena()
    bloqueo = np.zeros_like(visible)
    bloqueo[:, 21] = True
    opciones = {}
    if obstaculo == "agua":
        agua |= bloqueo
    elif obstaculo == "contradiccion":
        opciones["contradiccion"] = bloqueo
    else:
        opciones["compatibilidad_swir"] = (~bloqueo).astype(float)
    resultado = estimar_bajo_humo(visible, humo, agua, distancia_maxima_px=5, **opciones)
    assert not np.any(resultado.mascara_candidata)


def test_un_solo_extremo_no_es_continuidad():
    visible, humo, agua = escena()
    visible[:, 23:] = False
    resultado = estimar_bajo_humo(visible, humo, agua, distancia_maxima_px=5)
    assert not np.any(resultado.mascara_candidata)


def test_espectral_limitado_y_separado_de_continuidad():
    visible, humo, agua = escena(16)
    evidencia = humo.astype(float)
    resultado = estimar_bajo_humo(visible, humo, agua, evidencia, distancia_maxima_px=3)
    assert np.all(resultado.mascara_espectral[8:24, 20:23])
    assert not np.any(resultado.mascara_espectral[:, 26:30])
    assert not np.any(resultado.mascara_continuidad)
    assert np.all(resultado.mascara_indeterminada[8:24, 26:30])


def test_sin_semillas_no_inventa_superficie():
    visible, humo, agua = escena()
    visible[:] = False
    resultado = estimar_bajo_humo(visible, humo, agua, np.ones_like(visible, dtype=float))
    assert not np.any(resultado.mascara_candidata)


def test_diagonal_y_cicatrices_independientes():
    visible = np.zeros((12, 12), bool)
    humo = np.zeros_like(visible)
    visible[1, 1] = visible[5, 5] = True
    visible[2, 10] = visible[6, 10] = True
    humo[3:6, 10] = True
    for i in (2, 3, 4):
        humo[i, i] = True
    resultado = estimar_bajo_humo(visible, humo, np.zeros_like(visible), distancia_maxima_px=5)
    assert np.array_equal(resultado.mascara_continuidad, humo)


@pytest.mark.parametrize("opciones", [{"distancia_maxima_px": 0}, {"umbral_espectral": 2}, {"evidencia_espectral": np.full((32, 48), np.nan)}])
def test_validacion(opciones):
    with pytest.raises(ValueError):
        estimar_bajo_humo(*escena(), **opciones)
