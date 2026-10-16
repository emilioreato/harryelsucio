from types import SimpleNamespace

import numpy as np

import lumbre.regiones_contextuales as regiones_contextuales
import lumbre.segmentacion as segmentacion
from lumbre.modelos_segmentacion import (
    ResultadoClasificacionSemantica,
    ResultadoRegionesEspaciales,
)
from lumbre.ontologia import ClaseSemantica


def test_humo_ampliado_no_borra_superficie_visible_ni_funde_hipotesis_oculta(monkeypatch):
    forma = (64, 96)
    true_color = np.full((*forma, 3), (120, 112, 105), np.uint8)
    swir = true_color.copy()
    superficie = np.zeros(forma, bool)
    superficie[28:33, 42:49] = True
    humo_referencia = np.zeros(forma, bool)
    humo_referencia[5:10, 5:10] = True
    humo_ampliado = humo_referencia.copy()
    humo_ampliado[24:38, 36:56] = True
    agua = np.zeros(forma, bool)
    clases = np.zeros(forma, np.uint8)
    clases[humo_ampliado] = ClaseSemantica.HUMO_PROBABLE
    confianza = humo_ampliado.astype(np.float32) * .8
    evidencia_oculta = np.zeros(forma, np.float32)
    pixel_oculto = (30, 52)
    evidencia_oculta[pixel_oculto] = .95
    caracteristicas = np.zeros((*forma, 8), np.float32)

    clasificacion = ResultadoClasificacionSemantica(
        mascara_candidata=superficie.copy(),
        mascara_candidata_bajo_humo=np.zeros(forma, bool),
        mascara_agua=agua,
        mascara_humo=humo_ampliado,
        confianza_humo=confianza,
        clase_por_pixel=clases,
        centros=np.empty((0, 2), np.float32),
        clases_seleccionadas=(),
        puntuaciones_clase=np.asarray((.8, .4), np.float32),
        caracteristicas_comunes=caracteristicas,
        mascara_candidata_v2=superficie.copy(),
        diagnosticos_evidencia={
            "humo_referencia": humo_referencia,
            "evidencia_bajo_humo_swir": evidencia_oculta,
        },
    )
    detector = SimpleNamespace(
        id="contextual_hibrida",
        usa_sensibilidad=False,
        usa_numero_clases=False,
        clasificar=lambda *args, **kwargs: clasificacion,
    )
    monkeypatch.setattr(segmentacion, "obtener_detector_superficie", lambda _id: detector)

    capturado = {}

    def segmentar_visible(_tc, _swir, candidata, _agua, humo, *, evidencia, **_kwargs):
        capturado["humo_contextual"] = humo.copy()
        capturado["evidencia_visible"] = np.asarray(evidencia).copy()
        return SimpleNamespace(mascara=candidata.copy(), diagnosticos={})

    def filtrar_geometria(clasificacion_espacial, **_kwargs):
        capturado["clasificacion_geometria"] = clasificacion_espacial
        mascara = clasificacion_espacial.mascara_candidata.copy()
        return ResultadoRegionesEspaciales(
            mascara=mascara,
            contornos=(),
            proporcion=float(mascara.mean()),
            pixeles_agua_excluidos=0,
            pixeles_humo_excluidos=0,
            distancia_maxima_px=0,
            componentes_remotos_descartados=0,
        )

    monkeypatch.setattr(regiones_contextuales, "segmentar_contextual", segmentar_visible)
    monkeypatch.setattr(segmentacion, "segmentar_regiones_espaciales", filtrar_geometria)

    resultado = segmentacion.segmentar_superficie_afectada(
        true_color, swir, metodo="contextual_hibrida"
    )

    assert np.array_equal(capturado["humo_contextual"], humo_referencia)
    assert capturado["evidencia_visible"][28, 44] == 1
    assert capturado["evidencia_visible"][pixel_oculto] == 0
    geometria = capturado["clasificacion_geometria"]
    assert np.array_equal(geometria.mascara_humo, humo_referencia)
    assert np.all(
        geometria.clase_por_pixel[superficie]
        == ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
    )
    assert np.all(resultado.mascara[superficie])
    assert np.all(resultado.mascara_humo[superficie])
    assert not resultado.mascara_candidata_bajo_humo[pixel_oculto]
