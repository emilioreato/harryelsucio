from types import SimpleNamespace

import numpy as np

from lumbre.cobertura import detectar_verdor_aparente
from lumbre.escenarios import generar_escenario_progresion
from lumbre.focos import detectar_focos_visuales
from lumbre.ontologia import ClaseSemantica


def _resultado(shape, *, burned=None, smoke=None, classified=None, classes=None):
    return SimpleNamespace(
        mascara=np.zeros(shape, dtype=bool) if burned is None else burned,
        mascara_clasificada=(
            np.zeros(shape, dtype=bool) if classified is None else classified
        ),
        mascara_humo=np.zeros(shape, dtype=bool) if smoke is None else smoke,
        clase_por_pixel=(
            np.zeros(shape, dtype=np.uint8) if classes is None else classes
        ),
    )


def test_foco_estricto_sigue_separado_de_anomalia_swir_contextual():
    shape = (64, 64)
    true_color = np.zeros((*shape, 3), dtype=np.uint8)
    swir = np.zeros_like(true_color)
    strict_block = np.array([245, 65, 20], dtype=np.uint8)
    true_color[8:13, 8:13] = strict_block
    swir[8:13, 8:13] = strict_block
    true_color[44:49, 44:49] = strict_block
    swir[44:49, 44:49] = strict_block

    contextual_block = np.array([245, 65, 20], dtype=np.uint8)
    swir[27:32, 27:32] = contextual_block
    smoke = np.zeros(shape, dtype=bool)
    smoke[37, 20:43] = True
    smoke[18, 44:56] = True
    classified = np.zeros(shape, dtype=bool)
    classified[25:34, 25:34] = True
    classified[6:15, 44:53] = True
    burned = np.zeros(shape, dtype=bool)
    burned[7:14, 7:14] = True
    burned[25:34, 25:34] = True
    swir[8:13, 45:50] = contextual_block

    result = detectar_focos_visuales(
        true_color,
        swir,
        _resultado(shape, burned=burned, smoke=smoke, classified=classified),
    )

    assert result.componentes_rgb_swir >= 1
    assert result.componentes_swir_contextual >= 1
    assert np.any(result.mascara_rgb_swir[8:13, 8:13])
    assert np.any(result.mascara_swir_contextual[27:32, 27:32])
    assert not np.any(result.mascara_rgb_swir[44:49, 44:49])
    assert not np.any(result.mascara_swir_contextual[8:13, 45:50])
    assert not np.any(result.mascara_rgb_swir[27:32, 27:32])


def test_verdor_aparente_necesita_coincidencia_y_excluye_agua():
    shape = (48, 48)
    true_color = np.zeros((*shape, 3), dtype=np.uint8)
    swir = np.zeros_like(true_color)
    verde = np.array([40, 125, 32], dtype=np.uint8)
    true_color[8:25, 8:25] = verde
    swir[8:25, 8:25] = verde
    classes = np.zeros(shape, dtype=np.uint8)
    classes[8:25, 8:25] = ClaseSemantica.INDETERMINADO
    classes[8:15, 8:15] = ClaseSemantica.AGUA_POSIBLE

    result = detectar_verdor_aparente(
        true_color,
        swir,
        _resultado(shape, classes=classes),
    )

    assert np.any(result[16:25, 16:25])
    assert not np.any(result[8:15, 8:15])


def test_escenario_avanzado_genera_frentes_en_pixel_desde_un_origen():
    result = generar_escenario_progresion(
        120,
        80,
        {
            "origin": {"x": 30, "y": 40},
            "temperature_c": 30,
            "relative_humidity_pct": 30,
            "wind_from_deg": 270,
            "wind_speed_kmh": 20,
            "base_advance_px": 3,
            "steps": 16,
        },
    )

    assert result["kind"] == "escenario_visual_exploratorio"
    assert len(result["frames"]) == 16
    assert len(result["frames"][0]["front"]) > 2
    assert result["origin"] == {"x": 30.0, "y": 40.0}
