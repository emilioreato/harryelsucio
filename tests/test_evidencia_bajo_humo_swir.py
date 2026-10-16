import numpy as np

from lumbre.evidencia_bajo_humo_swir import evaluar_evidencia_bajo_humo_swir
from lumbre.evidencia_contextual import EvidenciaContextual
from lumbre.estimacion_bajo_humo import estimar_bajo_humo
from lumbre.humo_visible import detectar_humo_por_niveles


def test_compensacion_cian_es_solo_diagnostico_no_superficie_quemada():
    swir = np.full((80, 130, 3), (50, 130, 55), np.uint8)
    visible = np.zeros((80, 130), bool)
    visible[20:50, 5:25] = True
    swir[visible] = (185, 85, 55)
    humo = np.zeros_like(visible)
    humo[15:65, 30:125] = True
    swir[25:45, 35:55] = (85, 140, 130)  # Rojo absoluto atenuado por cian.
    swir[25:45, 60:80] = (65, 160, 100)  # Vegetación con verde residual.
    swir[25:45, 85:105] = (5, 180, 180)  # Cian puro: sin firma de suelo.
    swir[48:58, 35:55] = (8, 20, 30)  # Respuesta oscura, compatible con agua.
    swir[48:58, 60:80] = (85, 140, 155)  # Velo azul sin firma residual separable.
    anterior = evaluar_evidencia_bajo_humo_swir(swir, humo, visible)
    actual = evaluar_evidencia_bajo_humo_swir(swir, humo, visible, conservadora=True)
    assert not anterior.candidatos_fuertes[30, 40]
    assert not actual.candidatos_fuertes[30, 40]
    assert not actual.candidatos_moderados[30, 40]
    assert actual.candidatos_cian[30, 40]
    assert not actual.candidatos_cian[30, 70]
    assert not actual.candidatos_cian[30, 90]
    assert not actual.candidatos_cian[52, 40]
    assert not actual.candidatos_cian[52, 70]


def test_usa_firma_swir_para_distinguir_rojo_verde_bajo_humo():
    swir = np.full((72, 104, 3), (52, 140, 58), dtype=np.uint8)
    visible = np.zeros((72, 104), dtype=bool)
    humo = np.zeros_like(visible)
    visible[24:46, 12:29] = True
    swir[24:46, 12:29] = (186, 84, 55)
    humo[16:56, 27:91] = True

    # La firma roja queda atenuada, pero sigue siendo separable de verde.
    swir[29:45, 30:43] = (174, 91, 60)
    swir[29:45, 43:59] = (130, 112, 95)
    swir[29:45, 59:76] = (65, 135, 72)
    swir[29:45, 76:84] = (35, 65, 170)  # respuesta azul, incompatible

    resultado = evaluar_evidencia_bajo_humo_swir(swir, humo, visible)

    assert resultado.candidatos_fuertes[34, 35]
    assert resultado.candidatos_moderados[34, 50]
    assert not resultado.candidatos_fuertes[34, 67]
    assert not resultado.candidatos_moderados[34, 67]
    assert not resultado.candidatos_fuertes[34, 80]
    assert np.all((resultado.evidencia >= 0) & (resultado.evidencia <= 1))


def test_sin_firma_visible_se_abstiene_bajo_humo():
    swir = np.full((48, 64, 3), (60, 120, 65), dtype=np.uint8)
    humo = np.zeros((48, 64), dtype=bool)
    visible = np.zeros_like(humo)
    visible[14:28, 8:24] = True
    humo[10:38, 20:55] = True
    swir[16:32, 24:42] = (130, 112, 95)

    resultado = evaluar_evidencia_bajo_humo_swir(swir, humo, visible)

    assert not resultado.candidatos_fuertes.any()
    assert not resultado.candidatos_moderados.any()
    assert not resultado.evidencia.any()


def test_firma_residual_cian_no_es_suelo_ni_siquiera_conectada_a_una_cicatriz():
    forma = (50, 120)
    visible = np.zeros(forma, bool)
    visible[15:35, 5:20] = True
    humo = np.zeros(forma, bool)
    humo[10:40, 20:110] = True
    cian = np.zeros(forma, bool)
    cian[15:35, 20:35] = True
    cian[15:35, 80:95] = True  # Isla residual sin ancla visible ni roja directa.
    score = EvidenciaContextual(cian.astype(np.float32) * .9, {
        "evidencia_bajo_humo_swir": cian.astype(np.float32) * .9,
        "superficie_bajo_humo_swir_fuerte": cian,
        "superficie_bajo_humo_swir_cian": cian,
    })
    r = estimar_bajo_humo(visible, humo, np.zeros(forma, bool), score,
                          distancia_espectral_px=100)
    assert not r.mascara_candidata[25, 25]
    assert r.mascara_indeterminada[25, 25]
    assert not r.mascara_candidata[25, 85]


def test_cian_conectado_no_puede_resembrarse_hasta_cubrir_el_penacho():
    forma = (50, 120)
    visible = np.zeros(forma, bool)
    visible[15:35, 5:20] = True
    humo = np.zeros(forma, bool)
    humo[10:40, 20:110] = True
    cian = np.zeros(forma, bool)
    cian[15:35, 20:110] = True
    score = EvidenciaContextual(cian.astype(np.float32) * .9, {
        "evidencia_bajo_humo_swir": cian.astype(np.float32) * .9,
        "superficie_bajo_humo_swir_fuerte": cian,
        "superficie_bajo_humo_swir_cian": cian,
    })
    r = estimar_bajo_humo(visible, humo, np.zeros(forma, bool), score,
                          distancia_espectral_px=20)
    assert not r.mascara_candidata[25, 30]
    assert not r.mascara_candidata[25, 70]


def test_escena_sin_superficie_visible_no_inventa_semillas():
    swir = np.zeros((40, 60, 3), dtype=np.uint8)
    swir[:] = (50, 130, 55)
    swir[15:25, 20:35] = (180, 80, 50)
    humo = np.zeros((40, 60), dtype=bool)
    humo[10:30, 15:40] = True

    resultado = evaluar_evidencia_bajo_humo_swir(
        swir, humo, np.zeros_like(humo)
    )

    assert not resultado.candidatos_fuertes.any()
    assert not resultado.candidatos_moderados.any()


def test_estimador_bajo_humo_solo_usa_evidencia_swir_y_no_rellena_por_continuidad():
    visible = np.zeros((40, 100), dtype=bool)
    visible[14:26, 8:20] = True
    humo = np.zeros_like(visible)
    humo[8:32, 20:92] = True
    agua_conjunta = np.zeros_like(visible)
    agua_conjunta[18:22, 30:34] = True
    agua_conjunta[:, 46:50] = True
    contradiccion_true_color = humo.copy()
    evidencia = np.zeros(visible.shape, np.float32)
    evidencia[17:23, 30:38] = .88
    evidencia[17:23, 38:46] = .42
    # La respuesta SWIR azul detiene la conexión, aunque el score a ambos lados
    # sea compatible. La observación conjunta de agua y el veto True Color no
    # deben decidir el píxel bajo el velo.
    evidencia[17:23, 50:58] = .42
    fuerte = np.zeros_like(visible)
    fuerte[17:23, 30:38] = True
    score = EvidenciaContextual(
        evidencia,
        {
            "evidencia_bajo_humo_swir": evidencia,
            "superficie_bajo_humo_swir_fuerte": fuerte,
        },
    )

    resultado = estimar_bajo_humo(
        visible, humo, agua_conjunta, score,
        contradiccion=contradiccion_true_color,
        distancia_maxima_px=4, distancia_espectral_px=20,
    )

    assert resultado.mascara_espectral[20, 32]
    assert resultado.mascara_continuidad[20, 42]
    assert not resultado.mascara_candidata[:, 47].any()
    assert not resultado.mascara_continuidad[20, 54]
    assert resultado.mascara_indeterminada[20, 76]
    # No se dibuja un puente geométrico basado solo en un ancla visible.
    assert not resultado.mascara_candidata[10:13, 20:25].any()


def test_humo_sobre_firma_roja_swir_no_se_descarta_como_terreno():
    rng = np.random.default_rng(2026)
    tc = np.full((72, 112, 3), (48, 105, 42), dtype=np.uint8)
    swir = np.full_like(tc, (50, 130, 54))
    nube = np.zeros((72, 112), dtype=bool)
    nube[20:52, 20:84] = True
    variacion = np.clip(
        np.array((166, 169, 174))
        + rng.normal(0, 1.2, (32, 64, 3)), 0, 255
    ).astype(np.uint8)
    tc[20:52, 20:84] = variacion
    swir[20:52, 20:84] = (175, 92, 60)
    nucleo = np.zeros_like(nube)
    nucleo[32:40, 28:36] = True
    confianza = np.zeros(nube.shape, dtype=np.float32)
    confianza[nucleo] = .94

    resultado = detectar_humo_por_niveles(
        tc, swir, nucleo, confianza, mascara_nucleo=nucleo,
        fraccion_distancia_nucleo=.16,
    )

    assert resultado.mascara_probable[32:40, 36:44].mean() > .90
    assert resultado.candidatos_perdidos_por_swir[32:40, 36:44].any()

