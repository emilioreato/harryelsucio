"""Refinamientos locales posteriores a la detección, sin realimentar semillas."""

import cv2
import numpy as np
from scipy import ndimage as ndi

from .imagenes import validar_par_alineado


def _mascara(valor, forma):
    matriz = np.asarray(valor)
    if matriz.shape != forma or not np.all((matriz == 0) | (matriz == 1)):
        raise ValueError("Las máscaras deben ser binarias y compartir la rejilla RGB.")
    return matriz.astype(bool)


def refinar_superficie_local(swir, superficie, agua):
    """Cierra discontinuidades cortas compatibles con SWIR; no rellena islas grandes.

    Devuelve la unión estimada refinada. Los píxeles añadidos son continuidad
    inferida, no observación visible ni nuevas semillas espectrales.
    """
    validar_par_alineado(swir, swir)
    superficie = _mascara(superficie, swir.shape[:2])
    agua = _mascara(agua, superficie.shape)
    if not superficie.any():
        return superficie.copy()
    r, g, b = np.moveaxis(swir.astype(np.float32) / 255, -1, 0)
    rojo = (2 * r - g - b) / (r + g + b + .001)
    rg = (r - g) / (r + g + .001)
    compatible = (
        (rojo >= max(.02, float(np.quantile(rojo[superficie], .10)) - .16))
        & (rg >= max(-.06, float(np.quantile(rg[superficie], .10)) - .10))
        & (r >= .10) & ~agua
    )
    radio = max(1, min(3, round(min(superficie.shape) * .002)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radio + 1,) * 2)
    cerrada = cv2.morphologyEx(superficie.astype(np.uint8), cv2.MORPH_CLOSE,
                             kernel, borderType=cv2.BORDER_CONSTANT, borderValue=0) > 0
    huecos = ndi.binary_fill_holes(superficie) & ~superficie
    etiquetas, _ = ndi.label(huecos)
    tamanos = np.bincount(etiquetas.ravel())
    pequenas = tamanos <= max(16, round(np.pi * (2 * radio) ** 2))
    pequenas[0] = False
    # Un cierre no puede tapar un hueco grande ni parcialmente una isla de agua
    # o vegetación: el tamaño se decide antes de aplicar el veto espectral.
    huecos_permitidos = pequenas[etiquetas]
    propuestas = (cerrada | huecos_permitidos) & ~superficie
    propuestas &= ~huecos | huecos_permitidos
    return superficie | (propuestas & compatible)


def refinar_soporte_regional(true_color, swir, superficie, visible, humo, agua, *, area_minima_pct):
    """Audita cuerpos unidos por cuellos finos sin elegir una única cicatriz.

    Conserva todos los cuerpos con el área mínima del análisis. Los pequeños
    necesitan una observación mayoritariamente despejada y contraste local en
    ambas vistas. Los descartes son incertidumbre, no terreno sano.
    """
    validar_par_alineado(true_color, swir)
    forma = swir.shape[:2]
    superficie, visible, humo, agua = (
        _mascara(m, forma) for m in (superficie, visible, humo, agua)
    )
    if not np.isfinite(area_minima_pct) or area_minima_pct < 0:
        raise ValueError("El área mínima regional debe ser finita y no negativa.")
    vacia = np.zeros(forma, bool)
    if not superficie.any() or area_minima_pct == 0:
        return superficie.copy(), vacia
    radio = max(1, min(4, round(min(forma) * .0025)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radio + 1,) * 2)
    interior = cv2.morphologyEx(superficie.astype(np.uint8), cv2.MORPH_OPEN, kernel)
    etiquetas, n = ndi.label(interior, structure=np.ones((3, 3), bool))
    if not n:
        return superficie.copy(), vacia
    # Devolver los bordes originales a su cuerpo cercano: no erosionar las
    # ramas delgadas solo porque no sobrevivieron a la apertura.
    indices = ndi.distance_transform_edt(~interior.astype(bool),
                                       return_distances=False, return_indices=True)
    cuerpos = etiquetas[tuple(indices)]
    tamanos = np.bincount(cuerpos[superficie], minlength=n + 1)
    conservar = tamanos >= superficie.size * area_minima_pct / 100
    conservar[0] = False
    if not conservar.any():
        return superficie.copy(), vacia
    tc = true_color.astype(np.float32) / 255
    luma = .2126 * tc[..., 0] + .7152 * tc[..., 1] + .0722 * tc[..., 2]
    r, g, b = np.moveaxis(swir.astype(np.float32) / 255, -1, 0)
    rojo = (2 * r - g - b) / (r + g + b + .001)
    margen = 4 * radio
    for i, caja in enumerate(ndi.find_objects(etiquetas), 1):
        if caja is None or conservar[i]:
            continue
        caja = tuple(slice(max(0, s.start - margen), min(t, s.stop + margen))
                     for s, t in zip(caja, forma))
        cuerpo = etiquetas[caja] == i
        despejado = cuerpo & visible[caja] & ~humo[caja] & ~agua[caja]
        if despejado.sum() < 16 or despejado.sum() < .8 * cuerpo.sum():
            continue
        entorno = ndi.binary_dilation(cuerpo, iterations=margen)
        fondo = entorno & ~superficie[caja] & ~humo[caja] & ~agua[caja]
        if fondo.sum() < 16:
            continue
        conservar[i] = (
            np.median(luma[caja][fondo]) - np.median(luma[caja][despejado]) >= .03
            and np.median(rojo[caja][despejado]) - np.median(rojo[caja][fondo]) >= .10
        )
    confirmada = superficie & conservar[cuerpos]
    return confirmada, superficie & ~confirmada


def recuperar_continuidad_swir(swir, superficie, visible, humo, *, area_minima_pct):
    """Continuidad ocluida con firma residual regional; nunca cambia el humo.

    SLIC evalúa la zona de búsqueda antes de descartar píxeles atenuados. El
    residuo RGB es una pista ordinal, no una recuperación de bandas físicas.
    No crea semillas aisladas y mide las distancias desde el visible original.
    """
    from .regiones_contextuales import _normalizar, _slic_contexto

    validar_par_alineado(swir, swir)
    forma = swir.shape[:2]
    superficie, visible, humo = (_mascara(m, forma) for m in (superficie, visible, humo))
    vacia = np.zeros(forma, bool)
    etiquetas = np.zeros(forma, np.int32)
    anclas = visible & ~humo
    if anclas.sum() < 16 or not humo.any():
        return vacia, etiquetas
    r, g, b = np.moveaxis(swir.astype(np.float32) / 255, -1, 0)
    verde_residual = np.maximum(g - b, 0)
    residuo = (r - verde_residual) / (r + verde_residual + .001)
    umbral = max(.70, float(np.quantile(residuo[anclas], .75)))
    minimo_rojo = max(.12, float(np.quantile(r[anclas], .10)) * .45)
    distancia = ndi.distance_transform_edt(~anclas)
    radio_corto = max(4, round(min(forma) * .04))
    radio_interior = max(radio_corto, round(min(forma) * .10))
    # La caja delimita dónde analizar, no etiqueta su contenido como quemado.
    # Cada cicatriz aporta su propia zona, sin unir regiones remotas.
    contexto = np.zeros(forma, bool)
    contornos, _ = cv2.findContours(superficie.astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    for contorno in contornos:
        if cv2.contourArea(contorno) >= superficie.size * area_minima_pct / 100:
            x, y, ancho, alto = cv2.boundingRect(contorno)
            # La oclusión puede ocultar justamente el borde de la cicatriz.
            # Admitir su incertidumbre dentro del mismo margen corto, en vez
            # de recortar la búsqueda por el borde observado incompleto.
            contexto[max(0, y - radio_corto):min(forma[0], y + alto + radio_corto),
                     max(0, x - radio_corto):min(forma[1], x + ancho + radio_corto)] = True
    busqueda = humo & ((distancia <= radio_corto)
                       | (contexto & (distancia <= radio_interior)))
    if not busqueda.any():
        return vacia, etiquetas
    etiquetas = _slic_contexto(_normalizar(swir.astype(np.float32) / 255),
                              ndi.binary_dilation(busqueda, iterations=2), 144)
    medianas = ndi.median(residuo, etiquetas, np.arange(etiquetas.max() + 1))
    compatibles = medianas >= umbral
    compatibles[0] = False
    # A distancia mayor exigir amplitud roja comparable a las anclas claras,
    # o predominio azul regional sin el verde residual que confundía terreno
    # sano con quemado. Esta compuerta no modifica la detección de humo.
    ids = np.arange(etiquetas.max() + 1)
    rojo_regional = ndi.median(r, etiquetas, ids)
    verde_regional = ndi.median(g - b, etiquetas, ids)
    senal_lejana = ((rojo_regional >= float(np.quantile(r[anclas], .25)))
                    | (verde_regional <= 0))
    senal_lejana[0] = False
    permitida = (busqueda & compatibles[etiquetas]
                 & ((distancia <= radio_corto) | senal_lejana[etiquetas])
                 & (residuo >= max(.45, umbral - .20))
                 & (r >= minimo_rojo) & (b >= .10) & (b <= 1.08 * g))
    alcanzable = ndi.binary_propagation(superficie, mask=superficie | permitida,
                                       structure=np.ones((3, 3), bool))
    return alcanzable & ~superficie, etiquetas


def refinar_velo_contextual(true_color, swir, humo, agua):
    """Velo conectado sobre cualquier terreno, antes de evaluar suelo ocluido.

    No usa una máscara de quemado y no fabrica semillas en zonas aisladas.
    Exige neutralidad visible y apoyo azul SWIR; la distancia se mide desde
    el humo de entrada, sin iteraciones que lo reutilicen como nuevas semillas.
    """
    validar_par_alineado(true_color, swir)
    forma = true_color.shape[:2]
    humo, agua = (_mascara(m, forma) for m in (humo, agua))
    if not humo.any():
        return humo.copy()
    tc = true_color.astype(np.float32) / 255
    r, g, b = np.moveaxis(tc, -1, 0)
    luma = .2126 * r + .7152 * g + .0722 * b
    croma = np.ptp(tc, axis=2) / (tc.max(axis=2) + .025)
    textura = np.sqrt(np.maximum(0, ndi.uniform_filter(luma * luma, 7)
                                 - ndi.uniform_filter(luma, 7) ** 2))
    sr, sg, sb = np.moveaxis(swir.astype(np.float32) / 255, -1, 0)
    verde_swir = (sg - sb) / (sg + sb + .001)
    velo = ((croma <= .16) & (b >= .88 * r) & (b >= .88 * g)
            & (luma >= .40) & (textura <= .10))
    apoyo_swir = (verde_swir <= .42) & (sr <= 1.15 * sg) & (sb >= .10)
    distancia = ndi.distance_transform_edt(~humo)
    radio = max(8, min(128, round(min(forma) * .08)))
    permitida = velo & apoyo_swir & ~agua & (distancia <= radio)
    return ndi.binary_propagation(humo, mask=humo | permitida,
                                  structure=np.ones((3, 3), bool))


def refinar_humo_sobre_superficie(true_color, swir, humo, superficie, agua):
    """Recupera velo en el borde del penacho sobre suelo estimado quemado.

    La superficie solo delimita dónde mirar. Se exige señal atmosférica visible,
    contraste con suelo despejado y conexión al humo previo. No se reutiliza
    este refinamiento para volver a clasificar el suelo.
    """
    validar_par_alineado(true_color, swir)
    forma = true_color.shape[:2]
    humo, superficie, agua = (_mascara(m, forma) for m in (humo, superficie, agua))
    if not humo.any() or not superficie.any():
        return humo.copy()
    tc = true_color.astype(np.float32) / 255
    r, g, b = np.moveaxis(tc, -1, 0)
    luma = .2126 * r + .7152 * g + .0722 * b
    croma = np.ptp(tc, axis=2) / (tc.max(axis=2) + .025)
    suelo_despejado = superficie & ~humo & ~agua & (b < .90 * r) & (croma >= .18)
    if suelo_despejado.sum() < 16:
        return humo.copy()
    brillo_suelo = float(np.quantile(luma[suelo_despejado], .40))
    sigma = max(3, round(min(forma) * .008))
    peso_suelo = ndi.gaussian_filter(suelo_despejado.astype(np.float32), sigma)
    brillo_local = ndi.gaussian_filter(luma * suelo_despejado, sigma) / np.maximum(peso_suelo, 1e-5)
    brillo_local = np.where(peso_suelo >= .05, brillo_local, brillo_suelo)
    contraste = ndi.gaussian_filter(luma, 1) >= np.maximum(.18, brillo_local + .015)
    # La tierra amarilla puede ser clara, pero no tiene este equilibrio azulado.
    velo = (croma <= .28) & (b >= .92 * r) & (b >= .92 * g)
    textura = np.sqrt(np.maximum(0, ndi.uniform_filter(luma * luma, 7)
                                 - ndi.uniform_filter(luma, 7) ** 2))
    margen = max(2, min(6, round(min(forma) * .003)))
    entorno = ndi.binary_dilation(superficie, iterations=margen)
    # La oclusión puede interrumpir precisamente la firma SWIR del suelo.
    # Esa ausencia no es un veto de humo. Construir un contexto que atraviese
    # interrupciones interiores; no modifica la clasificación de superficie.
    radio_contexto = max(2, min(24, round(min(forma) * .015)))
    kernel_contexto = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * radio_contexto + 1,) * 2,
    )
    envolvente = cv2.morphologyEx(superficie.astype(np.uint8), cv2.MORPH_CLOSE,
                                kernel_contexto) > 0
    entorno |= ndi.binary_fill_holes(envolvente | superficie)
    distancia = ndi.distance_transform_edt(~humo)
    radio = max(8, min(128, round(min(forma) * .08)))
    permitida = entorno & contraste & velo & (textura <= .10) & ~agua & (distancia <= radio)
    return ndi.binary_propagation(humo, mask=humo | permitida,
                                  structure=np.ones((3, 3), bool))
