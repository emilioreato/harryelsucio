from types import SimpleNamespace

import numpy as np

from pyroscope.visualizacion import crear_superposicion, superponer_mascara
from pyroscope.humo_visible import ampliar_humo_true_color
from pyroscope.estimacion_bajo_humo import estimar_bajo_humo


def test_suelo_inferido_rojo_y_humo_encima_sin_cambiar_medicion():
    base = np.full((40, 60, 3), 100, np.uint8)
    visible = np.zeros((40, 60), bool)
    visible[8:32, 8:28] = True
    inferida = np.zeros_like(visible)
    inferida[8:32, 28:48] = True
    resultado = SimpleNamespace(mascara=visible, mascara_candidata_bajo_humo=inferida,
        mascara_humo=inferida, mascara_indeterminada=np.zeros_like(visible), contornos=())
    salida = crear_superposicion(base, resultado)
    roja = superponer_mascara(base, visible | inferida)
    esperado = superponer_mascara(roja, inferida, color=(0, 165, 255), opacidad=.28)
    assert np.array_equal(salida[20, 38], esperado[20, 38])
    assert np.array_equal(salida[20, 18], roja[20, 18])
    # Borde común de la superficie, sin frontera artificial en el humo.
    assert np.array_equal(salida[20, 27], roja[20, 27])
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
