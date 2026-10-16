from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace

import numpy as np
from PIL import Image

from lumbre import segmentacion
from lumbre.caracteristicas import extraer_caracteristicas_pareja
from lumbre.evidencia_bajo_humo_swir import evaluar_evidencia_bajo_humo_swir
from lumbre.modelos_segmentacion import ResultadoClasificacionSemantica
from lumbre.paquete_exportacion import crear_paquete_resultado
from lumbre.visualizacion import crear_superposicion
from test_paquete_exportacion import _trabajo, _png
from zipfile import ZipFile


def test_swir_conservador_descarta_firma_debil_sin_perder_firma_roja():
    sw = np.full((80, 120, 3), (50, 130, 55), np.uint8)
    visible = np.zeros((80, 120), bool)
    visible[20:50, 10:30] = True
    sw[visible] = (186, 84, 55)
    humo = np.zeros_like(visible)
    humo[10:70, 35:110] = True
    sw[25:45, 40:60] = (174, 91, 60)
    sw[25:45, 65:85] = (130, 112, 95)
    anterior = evaluar_evidencia_bajo_humo_swir(sw, humo, visible)
    actual = evaluar_evidencia_bajo_humo_swir(sw, humo, visible, conservadora=True)
    assert anterior.candidatos_moderados[30, 70]
    assert not actual.candidatos_moderados[30, 70]
    assert actual.candidatos_fuertes[30, 50]


def test_basico_filtra_contexto_antes_de_slic_y_refina_swir_oculto(monkeypatch):
    forma = (96, 160)
    tc = np.full((*forma, 3), (50, 110, 45), np.uint8)
    sw = np.full_like(tc, (50, 130, 55))
    visible = np.zeros(forma, bool)
    visible[35:65, 30:60] = True
    visible[5:7, 145:147] = True  # Ruido remoto que no debe crear contexto.
    humo = np.zeros(forma, bool)
    humo[30:70, 60:90] = True
    oculta = np.zeros(forma, bool)
    oculta[40:60, 60:78] = True
    sw[visible | oculta] = (185, 84, 55)
    score = oculta.astype(np.float32) * .95
    clases = np.zeros(forma, np.uint8)
    clases[visible] = 4
    clases[humo] = 3
    clasificacion = ResultadoClasificacionSemantica(
        visible, oculta, np.zeros(forma, bool), humo, humo.astype(np.float32),
        clases, np.empty((0, 8)), (), np.array([.2, .1]),
        caracteristicas_comunes=extraer_caracteristicas_pareja(tc, sw),
        mascara_candidata_v2=visible,
        diagnosticos_evidencia={"humo_referencia": humo,
            "evidencia_bajo_humo_swir": score,
            "superficie_bajo_humo_swir_fuerte": oculta},
    )
    opciones = []
    def clasificar(*args, **kwargs):
        opciones.append(kwargs)
        return clasificacion
    detector = SimpleNamespace(id="contextual_hibrida", usa_sensibilidad=False,
        usa_numero_clases=False, clasificar=clasificar)
    monkeypatch.setattr(segmentacion, "obtener_detector_superficie", lambda _: detector)
    checkpoints = []
    r = segmentacion.segmentar_superficie_afectada(tc, sw, metodo="contextual_hibrida",
        area_minima_pct=.15, ajustes_avanzados={"basic_surface": True},
        on_checkpoint=checkpoints.append)
    assert opciones[0]["ajuste_basico"] is True
    assert not r.diagnosticos_contextuales["context"][5, 145]
    assert np.any(r.diagnosticos_contextuales["under-smoke-slic"][oculta] > 0)
    # La firma fuerte oculta conserva su conexión al borde, pero no se usa
    # para resembrar toda la región más allá del radio desde lo visible.
    assert r.mascara_candidata_bajo_humo[40:60, 60:64].all()
    assert not r.mascara_candidata_bajo_humo[40:60, 66:78].any()
    assert any(c.label == "SLIC bajo humo (SWIR)" for c in checkpoints)
    assert checkpoints[-1].final
    assert "unificada" in checkpoints[-1].description
    assert np.array_equal(r.mascara_superficie_estimada,
                          r.mascara | r.mascara_candidata_bajo_humo)
    # La visualización unificada no dibuja una frontera en la unión interna.
    sin_humo = replace(r, mascara_humo=np.zeros(forma, bool))
    mapa = crear_superposicion(sw, sin_humo, unir_superficie=True)
    assert np.array_equal(mapa[50, 59], mapa[50, 60])


def test_exportacion_compone_union_y_humo_independientes():
    trabajo = _trabajo()
    union = np.zeros((24, 32), np.uint8)
    union[5:15, 7:25] = 255
    trabajo["outputs"]["estimated-surface"] = _png(union, "L")
    vista = {"layer": "candidates", "show_smoke": False,
             "show_visible_surface": True, "show_segmentation": False}
    def exportar(v):
        with ZipFile(BytesIO(crear_paquete_resultado(trabajo, [], v))) as z:
            return np.array(Image.open(BytesIO(z.read("revision/mapa_anotado.png"))))
    mapa = exportar(vista)
    # Mismo rojo a ambos lados de la antigua separación visible/oculta.
    assert np.array_equal(mapa[8, 12], mapa[8, 23])
    apagada = exportar(dict(vista, show_visible_surface=False))
    assert tuple(apagada[8, 23]) == (45, 70, 90)
    con_humo = exportar(dict(vista, show_smoke=True))
    assert not np.array_equal(con_humo[8, 23], mapa[8, 23])
