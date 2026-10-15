"""Adaptador de evidencia V2 para experimentos; no modifica el clasificador."""
import numpy as np


def evidencia_desde_v2(clasificacion, caracteristicas):
    """Scores ordinales (no probabilidades), con los umbrales reales de V2.

    Los píxeles moderados requieren contraste rojo y rojo/verde positivos.
    Una escena plana sin contraste no obtiene semillas adicionales.
    Otros clasificadores pueden omitir este adaptador y dar sus propios scores.
    """
    f = caracteristicas
    roja = f[..., 0]
    despejado = ~clasificacion.mascara_humo & ~clasificacion.mascara_agua
    score = np.zeros(roja.shape, np.float32)
    if np.any(despejado) and len(clasificacion.puntuaciones_clase) >= 2:
        alto, bajo = clasificacion.puntuaciones_clase[:2]
        moderada = (roja >= max(float(bajo), .05)) & (f[..., 6] >= .05)
        fuerte = (roja >= max(float(alto), .1)) & (f[..., 6] >= .1)
        score[moderada], score[fuerte] = .5, .85
    score[clasificacion.mascara_candidata] = 1
    score[clasificacion.mascara_agua] = 0
    return score
