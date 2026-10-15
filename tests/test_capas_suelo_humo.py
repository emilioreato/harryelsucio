from types import SimpleNamespace

import numpy as np

from pyroscope.visualizacion import crear_superposicion, superponer_mascara
from pyroscope.humo_visible import ampliar_humo_true_color
from pyroscope.estimacion_bajo_humo import estimar_bajo_humo


def test_superficie_visible_e_inferida_se_dibujan_en_capas_distintas():
    base = np.full((40, 60, 3), 100, np.uint8)
    visible = np.zeros((40, 60), bool)
    visible[8:32, 8:28] = True
    inferida = np.zeros_like(visible)
    inferida[8:32, 28:48] = True
    resultado = SimpleNamespace(mascara=visible, mascara_candidata_bajo_humo=inferida,
        mascara_humo=inferida, mascara_indeterminada=np.zeros_like(visible), contornos=())
    salida = crear_superposicion(base, resultado)
    humo_azul = superponer_mascara(base, inferida, color=(35, 145, 225), opacidad=.22)
    suelo_inferido = superponer_mascara(
        humo_azul, inferida, color=(220, 35, 190), opacidad=.48
    )
    superficie_roja = superponer_mascara(
        base, visible, color=(225, 45, 35), opacidad=.56
    )
    assert np.array_equal(salida[20, 38], suelo_inferido[20, 38])
    assert np.array_equal(salida[20, 18], superficie_roja[20, 18])
    assert salida[20, 38, 0] > salida[20, 38, 1]
    assert salida[20, 38, 2] > salida[20, 38, 1]
    # El borde inferido es discontinuo y no sustituye el contorno observado.
    assert tuple(salida[20, 28]) == (255, 45, 220)
    assert np.array_equal(salida[20, 27], superficie_roja[20, 27])
    assert visible.sum() == 480


def test_true_color_amplia_velo_sin_propagarse_por_vegetacion():
    tc = np.empty((80, 160, 3), np.uint8)
    tc[:] = (45, 110, 40)
    tc[20:60, 20:130] = (160, 165, 170)
    humo = np.zeros((80, 160), bool)
    humo[25:55, 40:60] = True
    ampliada, _ = ampliar_humo_true_color(tc, tc, humo, humo.astype(np.float32))
    assert ampliada[40, 63]
    assert not ampliada[5, 40]
    assert not ampliada[40, 140]
    assert np.all(ampliada[humo])


def test_sin_ancla_no_inventa_humo_en_suelo_claro():
    tc = np.full((50, 50, 3), 180, np.uint8)
    vacia = np.zeros((50, 50), bool)
    ampliada, _ = ampliar_humo_true_color(tc, tc, vacia, vacia.astype(float))
    assert not ampliada.any()


def test_swir_moderado_permite_mas_recorrido_sin_alargar_puentes_geometricos():
    visible = np.zeros((30, 70), bool)
    visible[10:20, 5:20] = True
    humo = np.zeros_like(visible)
    humo[10:20, 20:60] = True
    evidencia = humo.astype(float) * .5
    resultado = estimar_bajo_humo(visible, humo, np.zeros_like(humo), evidencia,
        umbral_espectral=.4, distancia_maxima_px=4, distancia_espectral_px=12)
    assert resultado.mascara_espectral[15, 30]
    assert not resultado.mascara_candidata[15, 40]
    assert not resultado.mascara_continuidad.any()
