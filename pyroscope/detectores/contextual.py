"""Adaptador experimental: V2 aporta semántica, el motor regional la organiza."""
from .swir_histeresis import clasificar_pixeles_area_afectada_swir
from dataclasses import replace
import numpy as np
from ..ontologia import ClaseSemantica


def clasificar_base_contextual(true_color, swir, **opciones):
    resultado = clasificar_pixeles_area_afectada_swir(true_color, swir, **opciones)
    from ..humo_visible import ampliar_humo_true_color, detectar_humo_por_niveles
    from ..evidencia_frente import evaluar_evidencia_frente

    # Mantener primero la ampliación contextual que ya producía la aplicación.
    # El detector por niveles añade evidencia a esa referencia, no la sustituye.
    humo_nucleo = resultado.mascara_humo.copy()
    humo_referencia, confianza_referencia = ampliar_humo_true_color(
        true_color, swir, humo_nucleo, resultado.confianza_humo
    )
    humo_niveles = detectar_humo_por_niveles(
        true_color, swir, humo_referencia, confianza_referencia,
        mascara_nucleo=humo_nucleo,
        # Extiende más allá del núcleo conservando las mismas compuertas
        # espectrales; solo afecta al modo contextual experimental.
        fraccion_distancia_nucleo=.16,
    )
    humo, confianza = humo_niveles.mascara_probable, humo_niveles.puntuacion
    candidata_v2 = resultado.mascara_candidata & ~humo & ~resultado.mascara_agua
    caracteristicas = resultado.caracteristicas_comunes
    evidencia_frente = evaluar_evidencia_frente(
        caracteristicas, candidata_v2, humo, resultado.mascara_agua
    )
    nuevas_semillas_frente = evidencia_frente.candidatos_fuertes & ~candidata_v2 & ~humo
    candidata = candidata_v2 | (evidencia_frente.candidatos_fuertes & ~humo)
    subyacente = (resultado.mascara_candidata_bajo_humo
                  | (resultado.mascara_candidata & humo)) & ~resultado.mascara_agua
    clases = resultado.clase_por_pixel.copy()
    clases[humo] = ClaseSemantica.HUMO_PROBABLE
    resultado = replace(resultado, mascara_humo=humo, confianza_humo=confianza,
                        mascara_candidata=candidata,
                        mascara_candidata_bajo_humo=subyacente, clase_por_pixel=clases,
                        mascara_candidata_v2=candidata_v2,
                        diagnosticos_evidencia={
                            "humo_nucleo": humo_nucleo,
                            "humo_referencia": humo_referencia,
                            "humo_fuerte": humo_niveles.mascara_fuerte,
                            "humo_moderado": humo_niveles.mascara_moderada,
                            "evidencia_humo": humo_niveles.puntuacion,
                            "humo_candidatos_debiles": humo_niveles.candidatos_debiles,
                            "humo_descartado_distancia": humo_niveles.descartados_por_distancia,
                            "humo_descartado_conectividad": humo_niveles.descartados_por_conectividad,
                            "evidencia_frente": evidencia_frente.puntuacion,
                            "frente_candidato_fuerte": evidencia_frente.candidatos_fuertes,
                            "frente_candidato_moderado": evidencia_frente.candidatos_moderados,
                            "frente_candidato_moderado_vecinal": evidencia_frente.candidatos_moderados_vecinales,
                            "frente_semillas_nuevas": nuevas_semillas_frente,
                        })
    f = caracteristicas
    # Percentiles iguales en una escena plana no constituyen semillas de fuego.
    # Corrección exclusiva del adaptador; los detectores anteriores se conservan.
    if f is not None and np.ptp(f[..., 0]) < 1e-5 and np.max(f[..., 0]) <= .05:
        vacia = np.zeros(true_color.shape[:2], bool)
        clases = resultado.clase_por_pixel.copy()
        clases[resultado.mascara_candidata] = ClaseSemantica.INDETERMINADO
        resultado = replace(resultado, mascara_candidata=vacia,
                            mascara_candidata_bajo_humo=vacia.copy(),
                            mascara_candidata_v2=vacia.copy(), clase_por_pixel=clases)
    return resultado
