import numpy as np
import pytest

from lumbre.refinamiento_basico import (
    refinar_humo_sobre_superficie, refinar_superficie_local, refinar_velo_contextual,
    seleccionar_soporte_regional,
)


def test_un_corredor_fino_no_confirma_otra_region_sin_anclas_propias():
    superficie = np.zeros((160, 200), bool)
    superficie[20:100, 20:100] = True
    superficie[40:75, 140:175] = True
    superficie[54:56, 100:140] = True  # Conexión insuficiente entre dos cuerpos.
    superficie[115:145, 140:170] = True  # Otra cicatriz con evidencia propia.
    anclas = np.zeros_like(superficie)
    anclas[40:60, 40:60] = True
    anclas[120:140, 145:165] = True
    principal, incierta = seleccionar_soporte_regional(superficie, anclas)
    assert principal[30:90, 30:90].all()
    assert not principal[45:70, 145:170].any()
    assert incierta[45:70, 145:170].all()
    assert principal[120:140, 145:165].all()
    assert np.array_equal(principal | incierta, superficie)
    assert not (principal & incierta).any()


def test_velo_sobre_suelo_sano_no_necesita_mascara_quemada():
    tc = np.full((100, 150, 3), (145, 120, 75), np.uint8)
    sw = np.full_like(tc, (145, 150, 70))
    humo = np.zeros(tc.shape[:2], bool)
    humo[30:65, 45:60] = True
    tc[30:65, 45:68] = (155, 155, 150)
    sw[30:65, 45:68] = (100, 145, 110)
    # Suelo claro con apariencia de velo pero SWIR claramente verde.
    tc[30:65, 68:80] = (155, 155, 150)
    sw[30:65, 68:80] = (40, 160, 45)
    # Otro fragmento gris aislado no obtiene semillas propias.
    tc[10:15, 20:25] = (155, 155, 150)
    sw[10:15, 20:25] = (100, 145, 110)
    actual = refinar_velo_contextual(tc, sw, humo, np.zeros_like(humo))
    assert actual[45, 65]
    assert not actual[45, 73]
    assert not actual[12, 22]
    assert actual[humo].all()


def test_humo_refina_velo_conectado_sobre_quemado_y_rechaza_tierra_y_manchas_aisladas():
    forma = (120, 160)
    tc = np.full((*forma, 3), (105, 85, 65), np.uint8)
    sw = np.full_like(tc, (160, 95, 70))
    superficie = np.zeros(forma, bool)
    superficie[20:100, 20:130] = True
    humo = np.zeros(forma, bool)
    humo[45:75, 70:90] = True
    tc[45:75, 62:90] = (160, 168, 175)  # Velo omitido conectado.
    tc[45:75, 90:110] = (190, 178, 150)  # Tierra amarillenta clara.
    tc[25:30, 35:40] = (160, 168, 175)  # Mancha desconectada.
    tc[45:75, 10:18] = (160, 168, 175)  # Fuera del suelo candidato.
    agua = np.zeros(forma, bool)
    agua[50:55, 62:66] = True
    actual = refinar_humo_sobre_superficie(tc, sw, humo, superficie, agua)
    assert actual[60, 65]
    assert not actual[60, 98]
    assert not actual[27, 37]
    assert not actual[60, 12]
    assert not actual[52, 64]
    assert actual[humo].all()
    # Estimar suelo quemado no basta para etiquetarlo todo como humo.
    assert not actual[85, 50]


def test_sin_humo_o_sin_suelo_despejado_no_inventa_refinamiento():
    tc = np.full((40, 50, 3), 180, np.uint8)
    vacia = np.zeros((40, 50), bool)
    llena = np.ones_like(vacia)
    assert not refinar_humo_sobre_superficie(tc, tc, vacia, llena, vacia).any()
    assert np.array_equal(refinar_humo_sobre_superficie(tc, tc, llena, llena, vacia), llena)


def test_humo_opaco_no_se_veta_por_un_hueco_en_la_mascara_de_suelo():
    tc = np.full((120, 160, 3), (105, 85, 65), np.uint8)
    sw = np.full_like(tc, (160, 95, 70))
    superficie = np.zeros(tc.shape[:2], bool)
    superficie[20:100, 20:130] = True
    superficie[40:80, 76:90] = False  # SWIR no clasificó suelo bajo la oclusión.
    original = superficie.copy()
    tc[40:80, 50:100] = (180, 185, 185)
    tc[55:60, 80:83] = (55, 105, 45)  # Isla verde: no se rellena como humo.
    humo = np.zeros_like(superficie)
    humo[40:80, 90:100] = True
    actual = refinar_humo_sobre_superficie(tc, sw, humo, superficie,
                                         np.zeros_like(superficie))
    assert actual[65, 83]
    assert actual[65:75, 81:90].all()
    assert not actual[55:60, 80:83].any()
    assert np.array_equal(superficie, original)


def test_superficie_cierra_microhuecos_y_puentes_sin_tapar_vegetacion_agua_o_islas_grandes():
    sw = np.full((100, 120, 3), (175, 95, 65), np.uint8)
    superficie = np.zeros((100, 120), bool)
    superficie[15:85, 15:105] = True
    superficie[30:32, 30:32] = False  # Hueco diminuto compatible.
    superficie[45:47, 35:37] = False  # Vegetación real.
    sw[45:47, 35:37] = (50, 145, 60)
    superficie[60:62, 35:37] = False  # Agua.
    agua = np.zeros_like(superficie)
    agua[60:62, 35:37] = True
    superficie[30:50, 65:85] = False  # Isla grande, aunque sea rojiza.
    superficie[60:80, 55:57] = False  # Interrupción estrecha con salida al borde.
    superficie[79:85, 55:57] = False
    actual = refinar_superficie_local(sw, superficie, agua)
    assert actual[30:32, 30:32].all()
    assert not actual[45:47, 35:37].any()
    assert not actual[60:62, 35:37].any()
    assert not actual[30:50, 65:85].any()
    assert actual[65, 55]
    assert actual[superficie].all()


def test_refinamiento_valida_rejilla():
    sw = np.zeros((20, 30, 3), np.uint8)
    with pytest.raises(ValueError):
        refinar_superficie_local(sw, np.zeros((10, 30), bool), np.zeros((20, 30), bool))
