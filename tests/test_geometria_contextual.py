import numpy as np
import cv2
import pytest

from lumbre.geometria_segmentacion import segmentar_regiones_espaciales
from lumbre.modelos_segmentacion import ResultadoClasificacionSemantica


@pytest.mark.parametrize("separadas", [False, True])
@pytest.mark.parametrize("radio", [0, 5, 50])
def test_filtro_componentes_coincide_con_referencia(separadas, radio):
    mascara = np.zeros((160, 200), bool)
    mascara[10:45, 10:45] = True
    mascara[12:22, 48:58] = True
    mascara[110:130, 160:180] = True
    mascara[70:72, 70:72] = True  # Ruido menor que el mínimo.
    cantidad, etiquetas, stats, _ = cv2.connectedComponentsWithStats(
        mascara.astype(np.uint8), connectivity=8,
    )
    ancla = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    distancia = cv2.distanceTransform((etiquetas != ancla).astype(np.uint8),
                                     cv2.DIST_L2, cv2.DIST_MASK_5)
    esperada = np.zeros_like(mascara)
    remotos = 0
    for etiqueta in range(1, cantidad):
        componente = etiquetas == etiqueta
        if stats[etiqueta, cv2.CC_STAT_AREA] < 16:
            continue
        if not separadas and distancia[componente].min() > round(200 * radio / 100):
            remotos += 1
            continue
        esperada |= componente
    resultado = segmentar_regiones_espaciales(
        clasificacion(mascara), area_minima_pct=0, preservar_geometria=True,
        conservar_regiones_separadas=separadas, distancia_maxima_pct=radio,
    )
    assert np.array_equal(resultado.mascara, esperada)
    assert resultado.componentes_remotos_descartados == remotos


def clasificacion(mascara, agua=None, humo=None):
    vacia = np.zeros_like(mascara, bool)
    return ResultadoClasificacionSemantica(
        mascara_candidata=mascara,
        mascara_candidata_bajo_humo=vacia.copy(),
        mascara_agua=vacia.copy() if agua is None else agua,
        mascara_humo=vacia.copy() if humo is None else humo,
        confianza_humo=np.zeros(mascara.shape, np.float32),
        clase_por_pixel=np.zeros(mascara.shape, np.uint8),
        centros=np.empty((0, 8)), clases_seleccionadas=(),
        puntuaciones_clase=np.empty(0),
    )


def test_preservar_geometria_conserva_agujeros_y_contornos_interiores():
    mascara = np.zeros((64, 64), bool)
    mascara[8:56, 8:56] = True
    mascara[20:44, 20:44] = False
    resultado = segmentar_regiones_espaciales(
        clasificacion(mascara), preservar_geometria=True,
        conservar_regiones_separadas=True,
    )
    assert np.array_equal(resultado.mascara, mascara)
    assert len(resultado.contornos) == 2
    assert resultado.proporcion == mascara.mean()


def test_proximidad_acepta_componente_entero_sin_recortarlo():
    mascara = np.zeros((100, 100), bool)
    mascara[10:60, 5:35] = True
    # Toca el radio de proximidad por el extremo izquierdo, pero se extiende
    # muy lejos del ancla. Debe aceptarse entero, no cortarse por distancia.
    mascara[25:30, 39:95] = True
    resultado = segmentar_regiones_espaciales(
        clasificacion(mascara), preservar_geometria=True,
        distancia_maxima_pct=5,
    )
    assert np.array_equal(resultado.mascara, mascara)
    assert resultado.componentes_remotos_descartados == 0
    assert np.all(resultado.mascara[25:30, 90:95])


def test_modo_independiente_conserva_cicatriz_remota_valida():
    mascara = np.zeros((100, 100), bool)
    mascara[5:25, 5:25] = True
    mascara[80:90, 80:90] = True
    resultado = segmentar_regiones_espaciales(
        clasificacion(mascara), preservar_geometria=True,
        conservar_regiones_separadas=True, distancia_maxima_pct=0,
    )
    assert np.array_equal(resultado.mascara, mascara)


def test_agua_y_humo_no_se_rellenan_con_morfologia():
    mascara = np.zeros((64, 64), bool)
    mascara[8:56, 8:56] = True
    agua, humo = np.zeros_like(mascara), np.zeros_like(mascara)
    agua[20:23, 20:23] = True
    humo[30:33, 30:33] = True
    for preservar in (False, True):
        resultado = segmentar_regiones_espaciales(
            clasificacion(mascara, agua, humo), preservar_geometria=preservar,
            conservar_regiones_separadas=True,
        )
        assert not resultado.mascara[agua | humo].any()
        assert resultado.pixeles_agua_excluidos == int(agua.sum())
        assert resultado.pixeles_humo_excluidos == int(humo.sum())
