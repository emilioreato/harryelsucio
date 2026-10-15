"""Fusión interpretable de V2 y evidencia visual experimental del frente."""
import numpy as np


class EvidenciaContextual(np.ndarray):
    """Array compatible con el motor que conserva las capas fuente aparte."""

    def __new__(cls, valores, diagnosticos):
        obj = np.asarray(valores, dtype=np.float32).view(cls)
        obj.diagnosticos = diagnosticos
        return obj

    def __array_finalize__(self, origen):
        self.diagnosticos = getattr(origen, "diagnosticos", {})


def evidencia_desde_v2(clasificacion, caracteristicas):
    """Scores ordinales (no probabilidades), con los umbrales reales de V2.

    Los píxeles moderados requieren contraste rojo y rojo/verde positivos.
    Una escena plana sin contraste no obtiene semillas adicionales.
    Otros clasificadores pueden omitir este adaptador y dar sus propios scores.
    """
    f = caracteristicas
    roja = f[..., 0]
    despejado = ~clasificacion.mascara_humo & ~clasificacion.mascara_agua
    mascara_v2 = getattr(clasificacion, "mascara_candidata_v2", None)
    if mascara_v2 is None:
        mascara_v2 = clasificacion.mascara_candidata
    else:
        mascara_v2 = np.asarray(mascara_v2, dtype=bool)
    score_v2 = np.zeros(roja.shape, np.float32)
    if np.any(despejado) and len(clasificacion.puntuaciones_clase) >= 2:
        alto, bajo = clasificacion.puntuaciones_clase[:2]
        moderada = (roja >= max(float(bajo), .05)) & (f[..., 6] >= .05)
        fuerte = (roja >= max(float(alto), .1)) & (f[..., 6] >= .1)
        score_v2[moderada & despejado], score_v2[fuerte & despejado] = .5, .85
    score_v2[mascara_v2] = 1
    score_v2[clasificacion.mascara_candidata_bajo_humo] = np.maximum(
        score_v2[clasificacion.mascara_candidata_bajo_humo], .5
    )

    diagnosticos = dict(getattr(clasificacion, "diagnosticos_evidencia", None) or {})
    score = score_v2.copy()
    frente = diagnosticos.get("evidencia_frente")
    frente_fuerte = diagnosticos.get("frente_candidato_fuerte")
    frente_moderada = diagnosticos.get("frente_candidato_moderado")
    if frente is not None:
        frente = np.asarray(frente, dtype=np.float32)
        if frente.shape != score.shape or not np.isfinite(frente).all():
            raise ValueError("La evidencia del frente debe ser finita y estar alineada.")
        # La nueva fuente solo añade semillas cuando supera el nivel fuerte;
        # la moderada se reserva para el crecimiento geodésico condicionado.
        if frente_moderada is not None:
            frente_moderada = np.asarray(frente_moderada, dtype=bool)
            score[frente_moderada] = np.maximum(score[frente_moderada], .38)
        if frente_fuerte is not None:
            frente_fuerte = np.asarray(frente_fuerte, dtype=bool)
            score[frente_fuerte] = np.maximum(score[frente_fuerte], .85)
    score[clasificacion.mascara_agua] = 0
    diagnosticos["evidencia_swir_v2"] = score_v2
    diagnosticos["evidencia_combinada"] = score.copy()
    return EvidenciaContextual(score, diagnosticos)
