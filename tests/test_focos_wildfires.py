import numpy as np

from pyroscope.focos import crear_superposicion_focos, detectar_focos_wildfires


def test_extrae_marcas_wildfires_sin_exigir_suelo_visible_ni_true_color():
    wildfires = np.full((64, 64, 3), (85, 75, 65), dtype=np.uint8)
    wildfires[8:20, 8:20] = (255, 100, 65)  # Marca roja.
    wildfires[30:50, 40:45] = (255, 240, 30)  # Frente amarillo >100 px.
    wildfires[8:20, 40:50] = (240, 165, 110)  # Parcela clara, sin marca.
    wildfires[30:40, 8:20] = (130, 80, 60)  # Superficie rojiza oscura.
    wildfires[52:60, 8:20] = (235, 235, 235)  # Humo claro.
    wildfires[60, 60] = (255, 100, 65)  # Ruido aislado.

    focos = detectar_focos_wildfires(wildfires)

    assert focos.componentes == 2
    assert focos.mascara[8:20, 8:20].all()
    assert focos.mascara[30:50, 40:45].all()
    assert int(focos.mascara.sum()) == 244
    assert not focos.mascara_rgb_swir.any()
    assert not focos.mascara_swir_contextual.any()
    # La marca se dibuja incluso sobre una base RGB gris, sin llama visible.
    base = np.full_like(wildfires, 125)
    overlay = crear_superposicion_focos(base, focos)
    assert not np.array_equal(overlay[12, 12], base[12, 12])
