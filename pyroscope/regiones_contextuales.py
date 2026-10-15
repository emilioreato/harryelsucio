"""Organización espacial experimental, independiente de la fuente semántica.

Acepta máscaras o scores heurísticos [0, 1]. No calcula probabilidades, bandas
físicas ni fuego activo. SLIC nunca decide por sí solo la clase del terreno.
"""
from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.graph import RAG
from skimage.segmentation import slic, watershed

from .caracteristicas import extraer_caracteristicas_pareja
from .imagenes import validar_par_alineado


@dataclass(frozen=True)
class ResultadoContextual:
    mascara: np.ndarray
    etiquetas: np.ndarray
    estadisticas: dict[str, np.ndarray]
    diagnosticos: dict[str, np.ndarray]
    uniones: int
    watershed_aplicado: bool


def _normalizar(imagen):
    bajo, alto = np.quantile(imagen, [0.02, 0.98], axis=(0, 1))
    return np.clip((imagen - bajo) / np.maximum(alto - bajo, 0.15), 0, 1).astype(np.float32)


def _gradiente(imagen):
    # Mismo operador y normalización para ambas vistas; máximo evita cancelar
    # una frontera que solo aparece en una composición. Sin mezcla de pesos.
    gris = imagen.astype(np.float32).mean(axis=2) / 255
    gx = ndi.sobel(gris, axis=1) / 8
    gy = ndi.sobel(gris, axis=0) / 8
    g = np.hypot(gx, gy)
    return np.clip(g / max(float(np.quantile(g, .95)), .02), 0, 1)


def _slic_contexto(imagen, contexto, area_superpixel):
    """Recortes por contexto conectado, sin el costoso sembrado de SLIC mask.

    Se conservan todas las zonas, incluso las remotas entre sí. Las etiquetas
    exteriores son cero y nunca se usan como un puente del grafo.
    """
    componentes, _ = ndi.label(contexto)
    salida = np.zeros(contexto.shape, np.int32)
    desplazamiento = 0
    for i, caja in enumerate(ndi.find_objects(componentes), 1):
        if caja is None:
            continue
        zona = componentes[caja] == i
        recorte = imagen[caja]
        etiquetas = slic(recorte, n_segments=max(1, min(24000, round(zona.size / area_superpixel))),
                         compactness=.12, sigma=.6, convert2lab=False,
                         channel_axis=-1, start_label=1, enforce_connectivity=True)
        salida[caja][zona] = etiquetas[zona] + desplazamiento
        desplazamiento += int(etiquetas.max())
    # Compactar IDs evita estadísticas de etiquetas recortadas y huecos.
    _, inversa = np.unique(salida, return_inverse=True)
    # Mantener cero reservado aun cuando toda la imagen esté en el contexto.
    if not np.any(salida == 0):
        inversa += 1
    return inversa.reshape(salida.shape).astype(np.int32)


def refinar_frontera_local(mascara, score, gradiente, protegida, radio=2):
    """Watershed solo en bandas con marcadores de ambos signos y fallback."""
    interior = ndi.binary_erosion(mascara, iterations=radio)
    exterior = ~ndi.binary_dilation(mascara, iterations=radio)
    banda = ~(interior | exterior) & ~protegida
    positivas = banda & mascara & (score >= .8)
    negativas = banda & ~mascara & (score <= .2)
    etiquetas, cantidad = ndi.label(banda)
    salida = mascara.copy()
    aplicado = False
    for i, caja in enumerate(ndi.find_objects(etiquetas), 1):
        if caja is None:
            continue
        zona = etiquetas[caja] == i
        pos, neg = positivas[caja] & zona, negativas[caja] & zona
        if pos.sum() < 3 or neg.sum() < 3:
            continue
        marcadores = np.zeros(zona.shape, np.int32)
        marcadores[pos], marcadores[neg] = 1, 2
        nueva = watershed(gradiente[caja], marcadores, mask=zona) == 1
        previa = mascara[caja] & zona
        cambios = np.count_nonzero((nueva ^ previa) & zona)
        # No permitir grandes reinterpretaciones ni añadir píxeles sin evidencia.
        if cambios > max(8, round(.15 * zona.sum())) or np.any(nueva & (score[caja] < .3)):
            continue
        salida[caja][zona] = nueva[zona]
        aplicado |= cambios > 0
    salida[protegida] = False
    return salida, aplicado, positivas, negativas


def segmentar_contextual(
    true_color, swir, candidata, agua, humo, *, evidencia=None,
    caracteristicas=None, usar_rag=True, refinar=True,
    representacion="conjunta", area_superpixel=144, distancia_crecimiento_px=8,
    limitar_contexto=True,
):
    """SLIC → estadísticas → RAG restringido → histéresis → Watershed local.

    La evidencia puede proceder de cualquier detector, incluido RF. Si falta,
    la máscara binaria conserva todos sus detalles sin inventar scores débiles.
    La distancia de crecimiento se mide siempre desde la evidencia original,
    nunca desde regiones recién incorporadas.
    """
    validar_par_alineado(true_color, swir)
    forma = true_color.shape[:2]
    if any(np.asarray(m).shape != forma for m in (candidata, agua, humo)):
        raise ValueError("Las máscaras deben compartir la rejilla de la pareja.")
    if (not np.isfinite(area_superpixel) or not np.isfinite(distancia_crecimiento_px)
            or area_superpixel < 16 or distancia_crecimiento_px < 0):
        raise ValueError("Área SLIC >=16 y distancia de crecimiento >=0 requeridas.")
    candidata, agua, humo = (np.asarray(m, dtype=bool) for m in (candidata, agua, humo))
    score = candidata.astype(np.float32) if evidencia is None else np.asarray(evidencia, np.float32)
    if score.shape != forma or not np.isfinite(score).all() or np.any((score < 0) | (score > 1)):
        raise ValueError("La evidencia debe ser finita, de la misma rejilla y estar en [0, 1].")
    f = extraer_caracteristicas_pareja(true_color, swir) if caracteristicas is None else np.asarray(caracteristicas)
    if f.shape != (*forma, 8) or not np.isfinite(f).all():
        raise ValueError("Se requieren las ocho características comunes finitas.")
    vistas = {"true_color": true_color, "swir": swir,
              "conjunta": np.concatenate((true_color, swir), axis=2)}
    if representacion not in vistas:
        raise ValueError("Representación SLIC desconocida.")
    imagen = _normalizar(vistas[representacion].astype(np.float32) / 255)
    original = candidata & ~agua & ~humo
    distancia = ndi.distance_transform_edt(~original) if original.any() else np.full(forma, np.inf)
    # Todas las cicatrices aportan contexto. No se reduce resolución ni se
    # utiliza la más grande como única ancla. El terreno remoto sigue exterior.
    contexto = (distancia <= max(24, distancia_crecimiento_px + 4)) if limitar_contexto else np.ones(forma, bool)
    if not contexto.any():
        vacia = np.zeros(forma, bool)
        ceros = np.zeros(forma, np.int32)
        return ResultadoContextual(vacia, ceros, {},
            {"slic": ceros, "region-classes": ceros, "rag": ceros,
             "seeds": vacia, "growth": vacia, "before-watershed": vacia,
             "positive-markers": vacia, "negative-markers": vacia,
             "watershed-changes": vacia, "context": vacia}, 0, False)
    etiquetas = _slic_contexto(imagen, contexto, area_superpixel)
    n = int(etiquetas.max()) + 1
    ids = np.arange(n)
    cuentas = np.maximum(1, np.bincount(etiquetas.ravel(), minlength=n))

    def media(x):
        return np.bincount(etiquetas.ravel(), weights=x.ravel(), minlength=n) / cuentas

    medias = np.stack([media(imagen[..., j]) for j in range(imagen.shape[2])], axis=1)
    medianas = np.nan_to_num(np.stack([ndi.median(imagen[..., j], etiquetas, ids)
                                     for j in range(imagen.shape[2])], axis=1))
    dispersion = np.stack([np.sqrt(np.maximum(0, media(imagen[..., j] ** 2) - medias[:, j] ** 2))
                           for j in range(imagen.shape[2])], axis=1)
    fraccion, fuerte, moderada = media(candidata), media(score >= .8), media(score >= .4)
    agua_r, humo_r = media(agua), media(humo)
    gradiente = np.maximum(_gradiente(true_color), _gradiente(swir))
    # 0 exterior, 1 interior fiable, 2 ambiguo, 3 parcialmente ocluido.
    clases = np.full(n, 2, np.uint8)
    clases[(fraccion <= .05) & (moderada <= .1)] = 0
    clases[(fraccion >= .65) & (fuerte >= .35) & (dispersion.mean(axis=1) < .22)] = 1
    clases[humo_r > .05] = 3
    clases[agua_r > .5] = 0
    clases[0] = 0
    protegida = agua | humo
    # Conservar evidencia por píxel en superpíxeles mixtos y cicatrices aisladas.
    semillas = original & (score >= .8)
    base = original.copy()
    padres = np.arange(n)

    def raiz(x):
        while padres[x] != x:
            padres[x] = padres[padres[x]]
            x = padres[x]
        return x

    grafo = RAG(etiquetas, connectivity=1)
    bordes = {}
    for a, b, g in ((etiquetas[:, :-1], etiquetas[:, 1:], gradiente[:, :-1]),
                    (etiquetas[:-1], etiquetas[1:], gradiente[:-1])):
        distinto = a != b
        pares = np.stack((np.minimum(a[distinto], b[distinto]), np.maximum(a[distinto], b[distinto])), axis=1)
        if not pares.size:
            continue
        claves = pares[:, 0] * n + pares[:, 1]
        unicas, inv = np.unique(claves, return_inverse=True)
        sumas = np.bincount(inv, weights=g[distinto])
        cantidades = np.bincount(inv)
        for clave, suma, cantidad in zip(unicas, sumas, cantidades):
            anterior = bordes.get(int(clave), (0., 0))
            bordes[int(clave)] = (anterior[0] + suma, anterior[1] + cantidad)
    uniones = 0
    if usar_rag:
        for a, b in sorted(grafo.edges):
            a, b = min(a, b), max(a, b)
            if a == 0:
                continue
            suma, cantidad = bordes.get(a * n + b, (1., 1))
            borde = suma / cantidad
            compatible = (min(moderada[a], moderada[b]) >= .2
                          and max(agua_r[a], agua_r[b], humo_r[a], humo_r[b]) < .1
                          and np.linalg.norm(medianas[a] - medianas[b]) / np.sqrt(imagen.shape[2]) < .18
                          and (borde < .35 or min(fraccion[a], fraccion[b]) > .75))
            if compatible:
                ra, rb = raiz(a), raiz(b)
                if ra != rb:
                    padres[rb] = ra
                    uniones += 1
    grupos = np.array([raiz(i) for i in ids])
    fiables = np.unique(grupos[(clases == 1)])
    soporte = np.isin(grupos, fiables)[etiquetas]
    # Verdor contradictorio exige además señal SWIR roja positiva.
    incompatible = (f[..., 2] > .2) & (f[..., 0] < .05)
    permitida = (score >= .4) & soporte & ~protegida & ~incompatible & (distancia <= distancia_crecimiento_px)
    permitida &= (gradiente < .6) | (score >= .8)
    # Misma histéresis por componentes que V2; no sustituye su detector.
    _, cc = cv2.connectedComponents((permitida | original).astype(np.uint8), connectivity=8)
    con_semilla = np.unique(cc[semillas])
    crecimiento = np.isin(cc, con_semilla[con_semilla != 0]) & permitida
    con_rag = base | crecimiento
    final, aplicado = con_rag.copy(), False
    positivas = negativas = np.zeros(forma, bool)
    if refinar and semillas.any():
        final, aplicado, positivas, negativas = refinar_frontera_local(con_rag, score, gradiente, protegida)
    return ResultadoContextual(
        final, etiquetas,
        {"medias": medias, "medianas": medianas, "dispersion": dispersion,
         "fraccion_candidata": fraccion, "evidencia_fuerte": fuerte, "evidencia_moderada": moderada,
         "agua": agua_r, "humo": humo_r, "borde": media(gradiente), "clase": clases,
         "vecinos": np.array([grafo.degree[i] if i in grafo else 0 for i in ids])},
        {"slic": etiquetas, "region-classes": clases[etiquetas], "rag": grupos[etiquetas],
         "seeds": semillas, "growth": crecimiento & ~original, "before-watershed": con_rag,
         "positive-markers": positivas, "negative-markers": negativas,
         "watershed-changes": final ^ con_rag, "context": contexto}, uniones, aplicado,
    )
