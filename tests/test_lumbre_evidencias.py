"""Casos sintéticos para humo por niveles, frente y suelo ocluido."""

import numpy as np

from pyroscope.caracteristicas import extraer_caracteristicas_pareja
from pyroscope.detectores import contextual
from pyroscope.evidencia_contextual import EvidenciaContextual
from pyroscope.evidencia_frente import evaluar_evidencia_frente
from pyroscope.estimacion_bajo_humo import estimar_bajo_humo
from pyroscope.humo_visible import detectar_humo_por_niveles
from pyroscope.modelos_segmentacion import ResultadoClasificacionSemantica


def test_humo_extenso_crece_desde_nucleo_y_respeta_superficie_clara_distinta():
    rng = np.random.default_rng(41)
    tc = np.full((80, 160, 3), (42, 105, 38), np.uint8)
    swir = np.full_like(tc, (48, 112, 46))
    tc[18:62, 20:72] = np.clip(
        np.array((162, 166, 171)) + rng.normal(0, 2, (44, 52, 3)), 0, 255
    ).astype(np.uint8)
    swir[18:62, 20:72] = (38, 154, 165)
    # Edificio blanco contiguo, con una firma SWIR distinta al velo.
    tc[30:50, 52:75] = (224, 226, 228)
    swir[30:50, 52:75] = (220, 92, 75)
    humo = np.zeros((80, 160), bool)
    humo[32:48, 34:46] = True
    confianza = humo.astype(np.float32)

    resultado = detectar_humo_por_niveles(tc, swir, humo, confianza)

    assert resultado.mascara_fuerte.any()
    assert resultado.mascara_moderada[40, 48]
    assert not resultado.mascara_probable[40, 65]
    assert resultado.mascara_probable[humo].all()
    assert np.all((resultado.puntuacion >= 0) & (resultado.puntuacion <= 1))


def test_radio_contextual_mayor_recupera_velo_conectado_sin_incluir_edificio():
    rng = np.random.default_rng(42)
    tc = np.full((80, 160, 3), (42, 105, 38), np.uint8)
    swir = np.full_like(tc, (48, 112, 46))
    tc[18:62, 20:72] = np.clip(
        np.array((162, 166, 171)) + rng.normal(0, 2, (44, 52, 3)), 0, 255
    ).astype(np.uint8)
    swir[18:62, 20:72] = (38, 154, 165)
    tc[30:50, 52:75] = (224, 226, 228)
    swir[30:50, 52:75] = (220, 92, 75)
    humo = np.zeros((80, 160), bool)
    humo[32:48, 34:46] = True
    confianza = humo.astype(np.float32)

    anterior = detectar_humo_por_niveles(tc, swir, humo, confianza)
    ampliado = detectar_humo_por_niveles(
        tc, swir, humo, confianza, fraccion_distancia_nucleo=.16
    )

    assert not anterior.mascara_probable[25, 55]
    assert ampliado.mascara_probable[25, 55]
    assert ampliado.descartados_por_distancia.any()
    assert not ampliado.mascara_probable[40, 65]


def test_suelo_blanco_sin_nucleo_no_se_declara_humo():
    tc = np.full((64, 96, 3), (184, 186, 188), np.uint8)
    swir = np.full_like(tc, (190, 190, 190))
    vacia = np.zeros((64, 96), bool)

    resultado = detectar_humo_por_niveles(tc, swir, vacia, vacia.astype(np.float32))

    assert not resultado.mascara_fuerte.any()
    assert not resultado.mascara_moderada.any()
    assert not resultado.mascara_probable.any()


def test_contextual_conserva_la_ampliacion_previa_de_humo(monkeypatch):
    forma = (64, 96)
    tc = np.full((*forma, 3), (58, 112, 54), np.uint8)
    swir = tc.copy()
    nucleo = np.zeros(forma, bool)
    nucleo[26:34, 30:38] = True
    confianza = np.zeros(forma, np.float32)
    confianza[nucleo] = .92
    vacia = np.zeros(forma, bool)
    caracteristicas = extraer_caracteristicas_pareja(tc, swir)
    clasificacion = ResultadoClasificacionSemantica(
        mascara_candidata=vacia.copy(), mascara_candidata_bajo_humo=vacia.copy(),
        mascara_agua=vacia.copy(), mascara_humo=nucleo,
        confianza_humo=confianza, clase_por_pixel=np.zeros(forma, np.uint8),
        centros=np.empty((0, 2), np.float32), clases_seleccionadas=(),
        puntuaciones_clase=np.asarray((.8, .4), np.float32),
        caracteristicas_comunes=caracteristicas,
    )
    referencia = np.zeros(forma, bool)
    referencia[22:38, 26:44] = True
    confianza_referencia = confianza.copy()
    confianza_referencia[referencia & ~nucleo] = .55
    monkeypatch.setattr(
        "pyroscope.detectores.contextual.clasificar_pixeles_area_afectada_swir",
        lambda *args, **kwargs: clasificacion,
    )
    monkeypatch.setattr(
        "pyroscope.humo_visible.ampliar_humo_true_color",
        lambda *args, **kwargs: (referencia.copy(), confianza_referencia.copy()),
    )

    resultado = contextual.clasificar_base_contextual(tc, swir)

    assert np.all(resultado.mascara_humo[referencia])
    assert resultado.diagnosticos_evidencia["humo_fuerte"][nucleo].any()
    assert resultado.diagnosticos_evidencia["humo_moderado"][referencia & ~nucleo].all()


def test_frente_calido_cercano_se_separa_de_rojo_aislado_y_agua():
    tc = np.full((120, 180, 3), (48, 118, 42), np.uint8)
    swir = np.full_like(tc, (50, 125, 48))
    candidata = np.zeros((120, 180), bool)
    candidata[64:86, 48:72] = True
    tc[candidata] = (130, 92, 64)
    swir[candidata] = (180, 82, 52)
    humo = np.zeros_like(candidata)
    humo[18:62, 40:104] = True
    tc[43:55, 72:96] = (226, 126, 48)
    swir[43:55, 72:96] = (226, 65, 34)
    # Rojo aislado lejos del humo y de las semillas; no basta por sí solo.
    tc[98:108, 145:157] = (230, 78, 32)
    swir[98:108, 145:157] = (232, 50, 24)
    agua = np.zeros_like(candidata)
    agua[42:55, 80:84] = True
    features = extraer_caracteristicas_pareja(tc, swir)

    resultado = evaluar_evidencia_frente(features, candidata, humo, agua)

    assert resultado.candidatos_fuertes[43:55, 72:96].any()
    assert not resultado.candidatos_fuertes[agua].any()
    assert not resultado.candidatos_fuertes[98:108, 145:157].any()
    assert not (resultado.candidatos_fuertes & resultado.candidatos_moderados).any()


def test_evidencia_moderada_bajo_humo_crece_con_limite_y_deja_opacidad_desconocida():
    visible = np.zeros((36, 100), bool)
    visible[12:24, 6:20] = True
    humo = np.zeros_like(visible)
    humo[12:24, 20:94] = True
    agua = np.zeros_like(visible)
    evidencia = np.zeros(visible.shape, np.float32)
    evidencia[12:24, 20:94] = .38
    # Agua corta el recorrido antes del resto del penacho.
    agua[:, 34] = True

    resultado = estimar_bajo_humo(
        visible, humo, agua, evidencia,
        distancia_maxima_px=8, distancia_espectral_px=28,
    )

    assert resultado.mascara_continuidad[18, 28]
    assert not resultado.mascara_candidata[:, 34].any()
    assert not resultado.mascara_candidata[18, 50]
    assert resultado.mascara_indeterminada[18, 70]


def test_senal_bajo_humo_fuerte_puede_ser_semilla_y_agua_detiene_crecimiento():
    visible = np.zeros((48, 100), bool)
    humo = np.zeros_like(visible)
    humo[8:40, 10:92] = True
    agua = np.zeros_like(visible)
    agua[:, 54] = True
    evidencia = np.zeros(visible.shape, np.float32)
    evidencia[16:32, 36:48] = .90
    evidencia[16:32, 48:54] = .38
    evidencia[16:32, 55:63] = .38
    fuerte = np.zeros_like(visible)
    fuerte[16:32, 36:48] = True
    evidencia_contextual = EvidenciaContextual(
        evidencia, {"frente_candidato_fuerte": fuerte}
    )

    resultado = estimar_bajo_humo(
        visible, humo, agua, evidencia_contextual,
        umbral_espectral=.4, distancia_maxima_px=4,
        distancia_espectral_px=12,
    )

    assert resultado.mascara_espectral[24, 42]
    assert resultado.mascara_continuidad[24, 51]
    assert not resultado.mascara_candidata[:, 54].any()
    assert not resultado.mascara_continuidad[24, 58]
    assert resultado.mascara_indeterminada[24, 80]


def test_frente_sin_superficie_humo_ni_contexto_se_abstiene():
    tc = np.full((80, 120, 3), (45, 115, 42), np.uint8)
    swir = np.full_like(tc, (50, 120, 46))
    tc[30:40, 80:90] = (230, 78, 32)
    swir[30:40, 80:90] = (232, 50, 24)
    vacia = np.zeros((80, 120), bool)
    features = extraer_caracteristicas_pareja(tc, swir)

    resultado = evaluar_evidencia_frente(features, vacia, vacia, vacia)

    assert not resultado.candidatos_fuertes.any()
    assert not resultado.candidatos_moderados.any()


def test_evidencia_vecinal_conserva_senal_roja_bajo_velo_sin_colorear_verde():
    tc = np.full((100, 150, 3), (48, 120, 45), np.uint8)
    swir = np.full_like(tc, (52, 124, 48))
    candidata = np.zeros((100, 150), bool)
    candidata[42:60, 24:40] = True
    tc[candidata] = (142, 104, 72)
    swir[candidata] = (186, 84, 55)
    humo = np.zeros_like(candidata)
    humo[32:68, 40:112] = True
    # El velo azulado reduce el contraste True Color, pero SWIR conserva una
    # señal rojiza débil dentro de la misma superficie.
    tc[42:60, 40:84] = (112, 130, 150)
    swir[42:60, 40:84] = (156, 108, 84)
    # Pequeño tramo con una señal más débil, rodeado por píxeles rojizos.
    tc[48:54, 58:61] = (98, 130, 158)
    swir[48:54, 58:61] = (150, 106, 86)
    agua = np.zeros_like(candidata)
    caracteristicas = extraer_caracteristicas_pareja(tc, swir)

    resultado = evaluar_evidencia_frente(caracteristicas, candidata, humo, agua)

    assert resultado.candidatos_moderados_vecinales[48:54, 58:61].any()
    assert not resultado.candidatos_moderados_vecinales[0:20, 120:145].any()
    assert not (resultado.candidatos_moderados_vecinales & ~humo).any()
