"""Orquestación de clasificación semántica y formación de regiones."""

from __future__ import annotations

from dataclasses import replace
from collections.abc import Callable
import numpy as np

from .coordenadas import SistemaCoordenadasImagen
from .detectores.kmeans import clasificar_pixeles_area_afectada
from .detectores.registro import obtener_detector_superficie
from .detectores.random_forest import clasificar_random_forest
from .detectores.swir_histeresis import clasificar_pixeles_area_afectada_swir
from .geometria_segmentacion import segmentar_regiones_espaciales
from .imagenes import validar_par_alineado
from .modelos_segmentacion import (
    ResultadoAreaAfectada,
    ResultadoClasificacionSemantica,
    ResultadoRegionesEspaciales,
)
from .ontologia import ClaseSemantica
from .progreso import ProgresoSegmentacion, informar_progreso
from .observabilidad_pipeline import CallbackCheckpoint, PublicadorCheckpoint
from .visualizacion_etapas import (
    previsualizar_bajo_humo,
    previsualizar_clasificacion,
    previsualizar_mascara,
    previsualizar_resultado,
)


def _fusionar_evidencia_random_forest(
    clasificacion: ResultadoClasificacionSemantica,
    random_forest: ResultadoClasificacionSemantica,
    evidencia_base: np.ndarray,
) -> tuple[ResultadoClasificacionSemantica, np.ndarray]:
    """Añade RF solo donde coincide con evidencia previa de SWIR/contexto.

    Los valores son niveles ordinales de evidencia, no probabilidades. RF no
    elimina candidatos del detector habitual ni puede incorporar píxeles que
    contradigan el filtro existente de agua o humo.
    """
    from .evidencia_contextual import EvidenciaContextual
    from .ontologia import ClaseSemantica

    forma = clasificacion.mascara_candidata.shape
    evidencia = np.asarray(evidencia_base, dtype=np.float32).copy()
    mascara_rf = np.asarray(random_forest.mascara_candidata, dtype=bool)
    if evidencia.shape != forma or mascara_rf.shape != forma:
        raise ValueError("Las máscaras Random Forest deben coincidir con la rejilla contextual.")

    protegida = np.asarray(clasificacion.mascara_agua, dtype=bool) | np.asarray(
        clasificacion.mascara_humo, dtype=bool
    )
    # 0,38 es el nivel de evidencia contextual moderada que ya habilita el
    # crecimiento regional. RF solo aporta en esas zonas; no siembra incendios
    # independientes basándose únicamente en su propia predicción.
    apoyo = mascara_rf & (evidencia >= 0.38) & ~protegida
    agregada = apoyo & ~np.asarray(clasificacion.mascara_candidata, dtype=bool)
    candidata = np.asarray(clasificacion.mascara_candidata, dtype=bool) | apoyo
    clases = np.asarray(clasificacion.clase_por_pixel).copy()
    clases[agregada] = ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA

    # Dos fuentes coincidentes constituyen una semilla fuerte para el motor
    # regional; no se interpreta el score del clasificador como probabilidad.
    evidencia[apoyo] = np.maximum(evidencia[apoyo], 0.82)
    diagnosticos = dict(getattr(evidencia_base, "diagnosticos", {}) or {})
    diagnosticos.update(
        random_forest_candidates=mascara_rf,
        random_forest_support=apoyo,
        random_forest_unconfirmed=mascara_rf & ~apoyo,
    )
    evidencia_fusionada = EvidenciaContextual(evidencia, diagnosticos)

    diagnosticos_clasificacion = dict(clasificacion.diagnosticos_evidencia or {})
    diagnosticos_clasificacion.update(
        random_forest_candidates=mascara_rf,
        random_forest_support=apoyo,
        random_forest_unconfirmed=mascara_rf & ~apoyo,
    )
    return (
        replace(
            clasificacion,
            mascara_candidata=candidata,
            clase_por_pixel=clases,
            diagnosticos_evidencia=diagnosticos_clasificacion,
        ),
        evidencia_fusionada,
    )


def _aplicar_random_forest_contextual(
    clasificacion: ResultadoClasificacionSemantica,
    true_color: np.ndarray,
    swir: np.ndarray,
    caracteristicas: np.ndarray,
    on_progress: ProgresoSegmentacion | None,
) -> tuple[ResultadoClasificacionSemantica, np.ndarray | None, str | None]:
    """Ejecuta el apoyo RF de forma aislada; cualquier error conserva V2."""
    from .evidencia_contextual import evidencia_desde_v2

    try:
        evidencia_base = evidencia_desde_v2(clasificacion, caracteristicas)

        def progreso_random_forest(etapa: str, porcentaje: int) -> None:
            # El clasificador contextual ya llegó al hito 68. Mantener una
            # escala monotónica y dejar 73 para publicar la evidencia inicial.
            informar_progreso(on_progress, f"Random Forest · {etapa}", 68 + round(porcentaje * 0.05))

        random_forest = clasificar_random_forest(
            true_color, swir, on_progress=progreso_random_forest
        )
        fusionada, evidencia = _fusionar_evidencia_random_forest(
            clasificacion, random_forest, evidencia_base
        )
        return fusionada, evidencia, None
    except Exception as exc:
        detalle = str(exc).strip() or type(exc).__name__
        aviso = (
            f"Random Forest no se pudo aplicar ({detalle}). "
            "Se conservó la segmentación contextual habitual."
        )
        return clasificacion, None, aviso


def segmentar_superficie_afectada(
    true_color: np.ndarray,
    swir: np.ndarray,
    *,
    numero_clases: int = 7,
    sensibilidad: int = 5,
    area_minima_pct: float = 0.04,
    distancia_maxima_pct: float = 10.0,
    sistema_coordenadas: SistemaCoordenadasImagen | None = None,
    semilla: int = 42,
    on_progress: ProgresoSegmentacion | None = None,
    metodo: str = "kmeans",
    conservar_regiones_separadas: bool = False,
    ajustes_avanzados: dict[str, object] | None = None,
    on_checkpoint: CallbackCheckpoint | None = None,
    on_checkpoint_error: Callable[[Exception], None] | None = None,
) -> ResultadoAreaAfectada:
    """Ejecuta un detector registrado y la etapa espacial común.

    Los detectores solo clasifican evidencia por píxel. El filtrado espacial y
    la conversión al contrato de salida se mantienen iguales para todos.
    """
    validar_par_alineado(true_color, swir)
    alto, ancho = true_color.shape[:2]
    if sistema_coordenadas is None:
        sistema_coordenadas = SistemaCoordenadasImagen(ancho_px=ancho, alto_px=alto)
    elif (sistema_coordenadas.ancho_px, sistema_coordenadas.alto_px) != (ancho, alto):
        raise ValueError("La rejilla de coordenadas debe coincidir con la imagen analizada.")

    detector = obtener_detector_superficie(metodo)
    publicador = PublicadorCheckpoint(on_checkpoint, on_checkpoint_error)
    avanzado = ajustes_avanzados or {}
    ajuste_basico = bool(avanzado.get("basic_surface", False))
    informar_progreso(on_progress, "Pareja alineada; iniciando clasificación", 5)
    publicador.publicar(
        "entrada", "Imagen preparada", "True Color reducido y alineado con SWIR para este análisis.",
        kind="image", progress=5, image=lambda: _preview_entrada(true_color),
    )
    opciones_detector: dict[str, object] = {
        "on_progress": on_progress,
        "pesos_humo": avanzado.get("smoke_weights"),
        "umbral_humo": avanzado.get("smoke_threshold", 0.55),
        "umbrales_agua": avanzado.get("water_thresholds"),
    }
    if detector.usa_sensibilidad:
        opciones_detector["sensibilidad"] = sensibilidad
    if detector.usa_numero_clases:
        opciones_detector.update(numero_clases=numero_clases, semilla=semilla)
    if detector.id in ("kmeans", "fusion_ponderada"):
        opciones_detector["pesos_kmeans"] = avanzado.get("kmeans_weights")
        if detector.id == "kmeans":
            opciones_detector["pesos_score"] = opciones_detector.pop("pesos_kmeans")
    if detector.id in ("swir_histeresis", "fusion_ponderada", "contextual_hibrida"):
        opciones_detector["umbrales_swir"] = avanzado.get("swir_thresholds")
        if detector.id in ("swir_histeresis", "contextual_hibrida"):
            opciones_detector["umbrales_percentil"] = opciones_detector.pop("umbrales_swir")
    if detector.id == "fusion_ponderada":
        opciones_detector.update(
            peso_kmeans=avanzado.get("fusion_kmeans_weight", 0.5),
            peso_swir=avanzado.get("fusion_swir_weight", 0.5),
            umbral_voto=avanzado.get("fusion_threshold", 0.55),
        )

    if detector.id == "contextual_hibrida" and ajuste_basico:
        opciones_detector["ajuste_basico"] = True
    clasificacion = detector.clasificar(true_color, swir, **opciones_detector)
    avisos: list[str] = []
    diagnosticos = None
    estimacion = None
    es_contextual = detector.id == "contextual_hibrida"
    humo_para_superficie = np.asarray(clasificacion.mascara_humo, dtype=bool)
    caracteristicas = None
    evidencia_contextual = None
    if es_contextual:
        from .caracteristicas import extraer_caracteristicas_pareja
        from .evidencia_contextual import evidencia_desde_v2

        caracteristicas = clasificacion.caracteristicas_comunes
        if caracteristicas is None:
            caracteristicas = extraer_caracteristicas_pareja(true_color, swir)
        # El detector conserva la máscara previa de humo para no cambiar qué
        # píxeles V2 eran visibles. La capa ampliada sigue en `clasificacion`
        # para representación y para el análisis SWIR bajo humo.
        humo_referencia = (clasificacion.diagnosticos_evidencia or {}).get(
            "humo_referencia"
        )
        if humo_referencia is not None:
            humo_para_superficie = np.asarray(humo_referencia, dtype=bool)
            if humo_para_superficie.shape != (alto, ancho):
                raise ValueError("La máscara de humo de referencia no está alineada.")
        if ajuste_basico:
            humo_para_superficie = np.asarray(clasificacion.mascara_humo, dtype=bool)
        if avanzado.get("use_random_forest", False):
            informar_progreso(on_progress, "Combinando evidencia contextual y Random Forest", 68)
            clasificacion, evidencia_contextual, aviso_rf = _aplicar_random_forest_contextual(
                clasificacion, true_color, swir, caracteristicas, on_progress
            )
            if aviso_rf:
                avisos.append(aviso_rf)
        if evidencia_contextual is None:
            evidencia_contextual = evidencia_desde_v2(clasificacion, caracteristicas)

    progreso_clasificacion = {
        "fusion_ponderada": 83,
        "random_forest": 81,
    }.get(detector.id, 73)
    publicador.publicar(
        "clasificacion", "Evidencia inicial",
        "Candidatos del detector habitual y, si está activo, apoyo RF corroborado por evidencia contextual.",
        kind="diagnostic", progress=progreso_clasificacion,
        image=lambda: previsualizar_clasificacion(
            true_color, clasificacion.mascara_candidata,
            clasificacion.mascara_humo, clasificacion.mascara_agua,
            clasificacion.mascara_candidata_bajo_humo,
        ),
        applied=bool(clasificacion.mascara_candidata.any()),
    )
    if es_contextual:
        from .regiones_contextuales import segmentar_contextual
        from .evidencia_contextual import EvidenciaContextual

        # La evidencia bajo el humo no puede sembrar ni hacer crecer la capa
        # visible. Sí se conserva una semilla V2 previa aunque la máscara nueva
        # de humo se superponga sobre ella.
        evidencia_superficie = evidencia_contextual
        humo_nuevo = clasificacion.mascara_humo & ~humo_para_superficie
        oculto_sin_semilla_visible = humo_nuevo & ~clasificacion.mascara_candidata
        if np.any(oculto_sin_semilla_visible):
            valores_visibles = np.asarray(evidencia_contextual, dtype=np.float32).copy()
            valores_visibles[oculto_sin_semilla_visible] = 0
            evidencia_superficie = EvidenciaContextual(
                valores_visibles,
                getattr(evidencia_contextual, "diagnosticos", {}) or {},
            )
        informar_progreso(on_progress, "Organizando evidencia con SLIC y RAG", 75)
        candidata_regional = clasificacion.mascara_candidata
        if ajuste_basico:
            # Delimitar el trabajo antes de SLIC, con los mismos límites que
            # tendrá la salida. Las motas y regiones remotas no crean contexto.
            clases_roi = clasificacion.clase_por_pixel.copy()
            clases_roi[candidata_regional] = ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
            previa = segmentar_regiones_espaciales(
                replace(clasificacion, mascara_humo=humo_para_superficie, clase_por_pixel=clases_roi),
                area_minima_pct=area_minima_pct, distancia_maxima_pct=distancia_maxima_pct,
                conservar_regiones_separadas=conservar_regiones_separadas,
                preservar_geometria=True,
            )
            candidata_regional = previa.mascara
        contexto = segmentar_contextual(
            true_color, swir, candidata_regional,
            clasificacion.mascara_agua, humo_para_superficie,
            evidencia=evidencia_superficie, caracteristicas=caracteristicas,
            on_progress=on_progress,
            on_checkpoint=publicador,
        )
        diagnosticos = dict(contexto.diagnosticos)
        if ajuste_basico:
            fuentes = clasificacion.diagnosticos_evidencia or {}
            diagnosticos["under-smoke-cyan-evidence"] = fuentes.get(
                "superficie_bajo_humo_swir_cian", np.zeros((alto, ancho), bool))
            diagnosticos["smoke-contextual-veil"] = fuentes.get(
                "humo_velo_contextual", np.zeros((alto, ancho), bool))
        evidencia_rf = getattr(evidencia_contextual, "diagnosticos", {}) or {}
        for nombre in (
            "random_forest_candidates",
            "random_forest_support",
            "random_forest_unconfirmed",
        ):
            if nombre in evidencia_rf:
                diagnosticos[nombre] = evidencia_rf[nombre]
        clasificacion = replace(clasificacion, mascara_candidata=contexto.mascara)
    clasificacion_geometria = clasificacion
    if es_contextual:
        solape_superficie_humo_nuevo = (
            clasificacion.mascara_candidata
            & clasificacion.mascara_humo
            & ~humo_para_superficie
        )
        if np.any(solape_superficie_humo_nuevo):
            clases_geometria = clasificacion.clase_por_pixel.copy()
            clases_geometria[solape_superficie_humo_nuevo] = (
                ClaseSemantica.SUPERFICIE_AFECTADA_CANDIDATA
            )
            clasificacion_geometria = replace(
                clasificacion,
                mascara_humo=humo_para_superficie,
                clase_por_pixel=clases_geometria,
            )
    regiones = segmentar_regiones_espaciales(
        clasificacion_geometria,
        area_minima_pct=area_minima_pct,
        distancia_maxima_pct=distancia_maxima_pct,
        on_progress=on_progress,
        # El modo contextual ya mantiene agujeros y contornos internos, pero
        # también debe respetar el radio de proximidad elegido en la interfaz.
        # La casilla de focos separados desactiva ese filtro explícitamente.
        conservar_regiones_separadas=conservar_regiones_separadas,
        preservar_geometria=es_contextual,
    )
    publicador.publicar(
        "geometria", "Geometría filtrada",
        f"Resultado espacial tras filtros; {int(regiones.mascara.sum())} píxeles candidatos visibles.",
        kind="mask", progress=96,
        image=lambda: previsualizar_mascara(true_color, regiones.mascara),
        applied=bool(regiones.mascara.any()),
    )
    if es_contextual:
        from .estimacion_bajo_humo import estimar_bajo_humo
        # Una firma roja superviviente permite hipótesis espectral; ausencia de
        # contraste deja solo continuidad corta o suelo desconocido.
        contradiccion = ((caracteristicas[..., 2] > .25)
                         & (caracteristicas[..., 0] < -.05)
                         & (clasificacion.confianza_humo < .7))
        estimacion = estimar_bajo_humo(
            regiones.mascara, clasificacion.mascara_humo, clasificacion.mascara_agua,
            evidencia_contextual, contradiccion=contradiccion,
            distancia_maxima_px=max(3, min(24, round(min(alto, ancho) * .015))),
            # La firma SWIR moderada superviviente se distingue de puentes
            # puramente geométricos: puede sostener un recorrido algo mayor.
            umbral_espectral=.4,
            distancia_espectral_px=max(4, round(min(alto, ancho) * .04)),
            exigir_ancla_visible=ajuste_basico,
        )
        if ajuste_basico:
            from scipy import ndimage as ndi
            # Las semillas ocultas no justifican manchas en cualquier parte del
            # penacho: aplicar la proximidad elegida desde la superficie final.
            oculta = estimacion.mascara_candidata
            if not conservar_regiones_separadas:
                distancia = (ndi.distance_transform_edt(~regiones.mascara)
                             if regiones.mascara.any() else np.full((alto, ancho), np.inf))
                oculta = oculta & (distancia <= regiones.distancia_maxima_px)
            # Bajo el humo se refinan las fronteras sobre SWIR, nunca sobre la
            # textura del aerosol en True Color. El exterior queda protegido.
            score_swir = np.asarray((clasificacion.diagnosticos_evidencia or {}).get(
                "evidencia_bajo_humo_swir", np.zeros((alto, ancho), np.float32)))
            oculto_refinado = segmentar_contextual(
                swir, swir, oculta, ~clasificacion.mascara_humo,
                np.zeros((alto, ancho), bool), evidencia=score_swir,
                representacion="swir",
            )
            oculta = oculto_refinado.mascara & clasificacion.mascara_humo
            etiquetas_ocultas, _ = ndi.label(oculta, structure=np.ones((3, 3)))
            tamanos_ocultos = np.bincount(etiquetas_ocultas.ravel())
            minimo_oculto = max(16, round(alto * ancho * area_minima_pct / 1000))
            conservar_ocultas = tamanos_ocultos >= minimo_oculto
            # La superficie ocluida pequeña y apoyada por firma fuerte puede
            # continuar un borde visible. No confundirla con motas remotas.
            borde_visible = ndi.binary_dilation(regiones.mascara, iterations=3)
            contactos = np.bincount(etiquetas_ocultas[borde_visible],
                                   minlength=tamanos_ocultos.size) > 0
            fuertes = np.bincount(etiquetas_ocultas[oculta & (score_swir >= .82)],
                                 minlength=tamanos_ocultos.size)
            conservar_ocultas |= ((tamanos_ocultos >= 16) & contactos
                                  & (fuertes >= np.maximum(8, tamanos_ocultos * .25)))
            conservar_ocultas[0] = False
            oculta = conservar_ocultas[etiquetas_ocultas]
            estimacion = replace(
                estimacion,
                mascara_espectral=oculta & estimacion.mascara_espectral,
                mascara_continuidad=oculta & ~estimacion.mascara_espectral,
                mascara_indeterminada=clasificacion.mascara_humo & ~regiones.mascara & ~oculta,
            )
            diagnosticos["under-smoke-slic"] = oculto_refinado.etiquetas
            diagnosticos["under-smoke-context"] = oculto_refinado.diagnosticos["context"]
            from .visualizacion_etapas import previsualizar_slic
            publicador.publicar(
                "slic-bajo-humo", "SLIC bajo humo (SWIR)",
                "Refinamiento regional del suelo ocluido sobre SWIR, dentro de la zona de interés.",
                kind="regions", progress=98,
                image=lambda: previsualizar_slic(swir, oculto_refinado.etiquetas),
                applied=bool(oculta.any()),
            )
        if estimacion.mascara_candidata.any() or estimacion.mascara_indeterminada.any():
            publicador.publicar(
                "bajo-humo", "Hipótesis bajo humo",
                "Evidencia o continuidad ocluida separada del área visible; gris indica terreno indeterminado.",
                kind="diagnostic", progress=98,
                image=lambda: previsualizar_bajo_humo(
                    true_color, clasificacion.mascara_humo,
                    estimacion.mascara_candidata, estimacion.mascara_indeterminada,
                ),
                applied=bool(estimacion.mascara_candidata.any()),
            )

    continuidad_superficie = None
    if ajuste_basico and es_contextual:
        from .refinamiento_basico import refinar_superficie_local, refinar_humo_sobre_superficie
        union_previa = regiones.mascara | estimacion.mascara_candidata
        union_refinada = refinar_superficie_local(swir, union_previa, clasificacion.mascara_agua)
        continuidad_superficie = union_refinada & ~union_previa
        if not conservar_regiones_separadas:
            from .refinamiento_basico import seleccionar_soporte_regional
            visible = regiones.mascara
            anclas_claras = np.zeros((alto, ancho), bool)
            if visible.any():
                anclas_claras = (visible & (caracteristicas[..., 0] >= max(
                    .30, float(np.quantile(caracteristicas[..., 0][visible], .75))))
                    & (caracteristicas[..., 6] >= max(
                        .15, float(np.quantile(caracteristicas[..., 6][visible], .75))))
                    & (caracteristicas[..., 3] <= float(np.quantile(
                        caracteristicas[..., 3][visible], .50)))
                    & (caracteristicas[..., 2] <= .10))
            union_refinada, incierta = seleccionar_soporte_regional(union_refinada, anclas_claras)
            visible = regiones.mascara & union_refinada
            import cv2
            contornos, _ = cv2.findContours(visible.astype(np.uint8), cv2.RETR_LIST,
                                            cv2.CHAIN_APPROX_SIMPLE)
            regiones = replace(regiones, mascara=visible, contornos=tuple(contornos),
                                proporcion=float(visible.mean()))
            estimacion = replace(estimacion,
                mascara_espectral=estimacion.mascara_espectral & union_refinada,
                mascara_continuidad=estimacion.mascara_continuidad & union_refinada)
            continuidad_superficie &= union_refinada
            diagnosticos["surface-uncertain-regions"] = incierta
        humo_previo = clasificacion.mascara_humo
        humo_refinado = refinar_humo_sobre_superficie(
            true_color, swir, humo_previo, union_refinada, clasificacion.mascara_agua,
        )
        confianza = clasificacion.confianza_humo.copy()
        confianza[humo_refinado & ~humo_previo] = .55
        clases = clasificacion.clase_por_pixel.copy()
        clases[humo_refinado] = ClaseSemantica.HUMO_PROBABLE
        clasificacion = replace(clasificacion, mascara_humo=humo_refinado,
                                confianza_humo=confianza, clase_por_pixel=clases)
        estimacion = replace(estimacion, mascara_indeterminada=humo_refinado & ~union_refinada)
        diagnosticos["surface-local-refinement"] = continuidad_superficie
        diagnosticos["smoke-local-refinement"] = humo_refinado & ~humo_previo
        publicador.publicar(
            "refinamiento-local", "Continuidad y humo local",
            "Cierre de huecos pequeños con apoyo SWIR y refinamiento del velo sobre suelo estimado quemado.",
            kind="diagnostic", progress=98,
            image=lambda: previsualizar_clasificacion(
                true_color, union_refinada, humo_refinado, clasificacion.mascara_agua,
                np.zeros((alto, ancho), bool),
            ),
            applied=bool(continuidad_superficie.any() or np.any(humo_refinado & ~humo_previo)),
        )

    resultado = ResultadoAreaAfectada(
        sistema_coordenadas=sistema_coordenadas,
        mascara=regiones.mascara,
        mascara_clasificada=clasificacion.mascara_candidata,
        mascara_candidata_bajo_humo=(estimacion.mascara_candidata if estimacion is not None
                                    else clasificacion.mascara_candidata_bajo_humo),
        mascara_humo=clasificacion.mascara_humo,
        confianza_humo=clasificacion.confianza_humo,
        clase_por_pixel=clasificacion.clase_por_pixel,
        contornos=regiones.contornos,
        proporcion=regiones.proporcion,
        pixeles_humo_excluidos=regiones.pixeles_humo_excluidos,
        centros=clasificacion.centros,
        clases_seleccionadas=clasificacion.clases_seleccionadas,
        puntuaciones_clase=clasificacion.puntuaciones_clase,
        pixeles_agua_excluidos=regiones.pixeles_agua_excluidos,
        distancia_maxima_px=regiones.distancia_maxima_px,
        componentes_remotos_descartados=regiones.componentes_remotos_descartados,
        mascara_indeterminada=(estimacion.mascara_indeterminada if estimacion is not None else None),
        mascara_bajo_humo_espectral=(estimacion.mascara_espectral if estimacion is not None else None),
        mascara_bajo_humo_continuidad=(estimacion.mascara_continuidad if estimacion is not None else None),
        diagnosticos_contextuales=diagnosticos,
        avisos=tuple(avisos),
        mascara_continuidad_superficie=continuidad_superficie,
    )
    if ajuste_basico:
        from .visualizacion import crear_superposicion
    publicador.publicar(
        "resultado-final", "Resultado final",
        ("Zona quemada estimada unificada y humo probable superpuesto."
         if ajuste_basico else "Superficie candidata visible, oclusiones y contorno del resultado disponible."),
        kind="mask", progress=99,
        image=lambda: crear_superposicion(true_color, resultado, unir_superficie=True) if ajuste_basico else previsualizar_resultado(
            true_color, resultado.mascara, resultado.mascara_candidata_bajo_humo,
            resultado.mascara_humo, resultado.clase_por_pixel, resultado.contornos,
        ),
        final=True,
    )
    return resultado


def _preview_entrada(imagen: np.ndarray) -> np.ndarray:
    from .visualizacion_etapas import previsualizar_imagen

    return previsualizar_imagen(imagen)


__all__ = [
    "ResultadoAreaAfectada",
    "ResultadoClasificacionSemantica",
    "ResultadoRegionesEspaciales",
    "clasificar_pixeles_area_afectada",
    "clasificar_pixeles_area_afectada_swir",
    "segmentar_regiones_espaciales",
    "segmentar_superficie_afectada",
]
