# Algoritmos orientativos para segmentar fuego, humo y agua

**Lumbre · Propuesta técnica inicial · 15/10/2026**

## 1. Objetivo y alcance

Este documento propone un punto de partida funcional para obtener tres máscaras separadas a partir de dos imágenes de una misma escena Sentinel-2:

1. **Fuego / candidatos de combustión activa**.
2. **Humo / penachos candidatos**.
3. **Agua**.

La regla específica para este conjunto de datos es importante: **un píxel que parece fuego en la composición SWIR no se acepta automáticamente como fuego**. Se contrasta con el píxel correspondiente de True Color y se rechazan los candidatos cuya apariencia RGB sea compatible con agua.

Los algoritmos son heurísticos para prototipado, no un detector científico validado. Las imágenes del repositorio son JPG renderizados; no se ha confirmado que todos los productos usen la misma asignación de bandas, estiramiento de contraste, dimensiones o georreferenciación. Por eso, los umbrales deben ajustarse y evaluarse con regiones etiquetadas. No se deben presentar sus resultados como probabilidad real de incendio.

**Limitación física:** una imagen Sentinel-2 no garantiza que un foco activo se vea como una llama naranja en RGB. La máscara de fuego descrita aquí busca candidatos visibles en los productos exportados y puede perder focos pequeños o calientes. Si se dispone de bandas originales, conviene diseñar una vía distinta con valores radiométricos, metadatos y productos térmicos apropiados; Sentinel-2 no es un sensor térmico dedicado.

## 2. Condiciones previas

- Las dos imágenes deben representar **la misma adquisición** y estar alineadas píxel a píxel. Confirmar fecha/hora, extensión, CRS y geotransformación.
- No basta con que tengan las mismas dimensiones. Si no coinciden geográficamente, hay que alinearlas con sus metadatos mediante una reproyección/remuestreo geoespacial. No corregir una desalineación desconocida usando solamente `resize()`.
- Los JPG se leen como valores de color de pantalla, no como reflectancia original. Las reglas de color dependen del renderizado.
- Las salidas son máscaras binarias para revisión; deben guardarse junto con los parámetros y la versión de las imágenes.

## 3. Lógica de clasificación

### A. Agua: máscara de exclusión prioritaria

Buscar en True Color tonos azul/cian compatibles con agua. La máscara se usa de dos maneras: como clase propia y como **veto** para no etiquetar como fuego un candidato SWIR que coincide con agua en RGB.

El agua no siempre es azul: puede verse negra, marrón, verdosa o brillante según turbidez, sombras, profundidad y composición. Por eso, la regla cromática no es suficiente para todos los casos. En esta primera versión se evita etiquetar automáticamente todo píxel oscuro como agua, ya que también podría ser sombra, suelo quemado o vegetación oscura.

### B. Fuego: candidato SWIR + confirmación RGB

1. Generar candidatos de color cálido/intenso en SWIR (regla inicial para composiciones renderizadas con apariencia rojiza/anaranjada).
2. Calcular una evidencia RGB de color cálido: rojo dominante respecto de verde y azul, con saturación/valor suficientes.
3. Excluir todos los candidatos que coincidan con la máscara de agua RGB.
4. Aceptar como fuego solamente la intersección entre candidato SWIR y evidencia RGB cálida. Esta regla conservadora reduce falsos positivos de agua, aunque puede omitir fuego que no destaque en True Color.
5. Limpiar ruido con operaciones morfológicas y descartar componentes diminutos.

Si la composición SWIR no muestra los candidatos de fuego con tonos cálidos, habrá que cambiar el primer umbral tras inspeccionar las imágenes. No se debe asumir una asignación de bandas por el nombre del archivo.

### C. Humo: región clara, poco saturada y espacialmente suave

Buscar zonas de True Color claras y poco saturadas, compatibles con gris/blanco, que también tengan una apariencia relativamente neutra en SWIR. Excluir agua y píxeles ya asignados a fuego.

Esta regla es deliberadamente simple: **nubes, bruma, suelo claro, roca y algunas superficies artificiales pueden parecer humo**. Para separar humo de nubes se necesita contexto adicional (forma, posición, otras bandas, escenas temporales o anotaciones manuales). La máscara debe llamarse “humo candidato”, no detección confirmada.

### D. Exclusividad y prioridad

Las máscaras finales se hacen mutuamente excluyentes con este orden: agua → fuego → humo. Guardar también las máscaras candidatas intermedias para poder diagnosticar por qué se ha clasificado una región.

## 4. Implementación Python de referencia

Dependencias:

```bash
pip install opencv-python numpy
```

Guarda el siguiente código como `segmentacion_multiclase.py`. Está escrito para JPG renderizados y umbrales configurables. Requiere que ambas imágenes estén ya alineadas y tengan las mismas dimensiones.

```python
from pathlib import Path
import cv2
import numpy as np


def limpiar_mascara(mask, kernel_size=3, min_area=8):
    """Cierra pequeños huecos y elimina componentes de menos de min_area píxeles."""
    mask = (mask.astype(np.uint8) * 255)
    k = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    result = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            result[labels == i] = 255
    return result > 0


def leer_par_rgb(path):
    """Devuelve imagen BGR uint8; OpenCV almacena los canales en orden B,G,R."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"No se pudo leer la imagen: {path}")
    return image


def segmentar_incendio(rgb_path, swir_path, salida_dir="resultados",
                       min_area_fuego=8, min_area_humo=30,
                       min_area_agua=20):
    """
    Segmentación heurística de imágenes RGB + SWIR renderizadas.
    IMPORTANTE: el alineamiento espacial debe haberse verificado antes.
    Devuelve máscaras booleanas (agua, fuego, humo) y guarda PNGs.
    """
    rgb = leer_par_rgb(rgb_path)
    swir = leer_par_rgb(swir_path)

    if rgb.shape[:2] != swir.shape[:2]:
        raise ValueError(
            "RGB y SWIR tienen dimensiones distintas. "
            "Alinea las imágenes con CRS/geotransformación; no uses resize "
            "a ciegas porque no garantiza correspondencia geográfica."
        )

    # Suavizado leve para reducir ruido de compresión JPEG.
    rgb_blur = cv2.GaussianBlur(rgb, (3, 3), 0)
    swir_blur = cv2.GaussianBlur(swir, (3, 3), 0)

    # BGR -> HSV. En OpenCV H está en [0,179], S y V en [0,255].
    rgb_hsv = cv2.cvtColor(rgb_blur, cv2.COLOR_BGR2HSV)
    swir_hsv = cv2.cvtColor(swir_blur, cv2.COLOR_BGR2HSV)

    b, g, r = cv2.split(rgb_blur)
    _, rgb_s, rgb_v = cv2.split(rgb_hsv)
    swir_h, swir_s, swir_v = cv2.split(swir_hsv)

    # 1) AGUA en True Color: tonos azul/cian moderados, evitando píxeles
    # casi negros cuyo tono HSV es inestable.
    agua_rgb = (
        (rgb_hsv[:, :, 0] >= 82) &
        (rgb_hsv[:, :, 0] <= 132) &
        (rgb_s >= 25) &
        (rgb_v >= 25) &
        (rgb_v <= 210)
    )

    # Un candidato oscuro en SWIR solo refuerza la clase agua si RGB también
    # lo reconoce como azul/cian. No se clasifica agua solo por ser oscuro.
    agua_swir_oscura = (swir_v < 95) & (swir_s < 110)
    agua = limpiar_mascara(
        agua_rgb & (agua_swir_oscura | (swir_v >= 95)),
        min_area=min_area_agua
    )

    # 2) FUEGO candidato en SWIR. Regla de apariencia para un render cálido;
    # ajustar si la composición real asigna otros colores a las bandas.
    swir_calido = (
        ((swir_h <= 28) | (swir_h >= 170)) &
        (swir_s >= 55) &
        (swir_v >= 65)
    )

    # Confirmación RGB conservadora: rojo dominante, suficiente saturación
    # y brillo. Los factores son umbrales iniciales, no constantes físicas.
    rgb_calido = (
        (r.astype(np.int16) >= g.astype(np.int16) * 1.12) &
        (r.astype(np.int16) >= b.astype(np.int16) * 1.18) &
        (r >= 90) &
        (rgb_s >= 55) &
        (rgb_v >= 70)
    )

    fuego_candidato = swir_calido & rgb_calido & (~agua)
    fuego = limpiar_mascara(fuego_candidato, min_area=min_area_fuego)
    fuego &= ~agua

    # 3) HUMO candidato: claro y poco saturado en RGB, y relativamente
    # poco saturado y claro en SWIR. Esto también puede capturar nubes.
    humo_rgb = (rgb_v >= 145) & (rgb_s <= 75)
    humo_swir = (swir_v >= 115) & (swir_s <= 100)
    humo_candidato = humo_rgb & humo_swir & (~agua) & (~fuego)
    humo = limpiar_mascara(humo_candidato, min_area=min_area_humo)
    humo &= ~agua
    humo &= ~fuego

    # 4) Guardar máscaras binarias. Blanco = clase detectada.
    out = Path(salida_dir)
    out.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out / "mascara_agua.png"), agua.astype(np.uint8) * 255)
    cv2.imwrite(str(out / "mascara_fuego_candidato.png"),
                fuego.astype(np.uint8) * 255)
    cv2.imwrite(str(out / "mascara_humo_candidato.png"),
                humo.astype(np.uint8) * 255)

    # Vista rápida: BGR, agua=azul, fuego=rojo, humo=gris/blanco.
    overlay = rgb.copy()
    overlay[agua] = (255, 80, 0)
    overlay[fuego] = (0, 0, 255)
    overlay[humo] = (220, 220, 220)
    mezcla = cv2.addWeighted(rgb, 0.55, overlay, 0.45, 0)
    cv2.imwrite(str(out / "superposicion.png"), mezcla)

    total = rgb.shape[0] * rgb.shape[1]
    resumen = {
        "pixeles_totales": int(total),
        "pixeles_agua": int(agua.sum()),
        "pixeles_fuego_candidato": int(fuego.sum()),
        "pixeles_humo_candidato": int(humo.sum()),
        "porcentaje_agua": round(100 * float(agua.sum()) / total, 3),
        "porcentaje_fuego_candidato": round(100 * float(fuego.sum()) / total, 3),
        "porcentaje_humo_candidato": round(100 * float(humo.sum()) / total, 3),
        "nota": "Porcentajes de píxeles de imagen; no equivalen a superficie terrestre sin georreferenciación."
    }
    return {"agua": agua, "fuego": fuego, "humo": humo, "resumen": resumen}


if __name__ == "__main__":
    resultado = segmentar_incendio(
        "True_color.jpg",
        "SWIR.jpg",
        salida_dir="resultados"
    )
    print(resultado["resumen"])
```

El código no ajusta automáticamente los umbrales a todas las escenas. Si no encuentra fuego o detecta demasiado, inspeccionar primero las máscaras y los histogramas, y ajustar los parámetros sobre escenas anotadas; no rebajar umbrales hasta conseguir un resultado visualmente atractivo sin medir errores.

## 5. Algoritmo espacial: agrupar y filtrar regiones

La limpieza morfológica y los componentes conexos del código anterior ya eliminan píxeles aislados. Como siguiente etapa, se recomienda:

1. Mantener componentes conexos por clase.
2. Calcular área en píxeles, caja delimitadora, centroide y perímetro de cada componente.
3. Descartar componentes minúsculos solo tras medir el tamaño de los focos que se desea detectar.
4. Permitir al operador aceptar, borrar o reclasificar componentes en la interfaz.
5. No exigir que fuego y humo sean contiguos: el humo puede extenderse fuera de la zona quemada.
6. Si hay CRS y geotransformación válidos, convertir geometrías a coordenadas del mapa y medir en un CRS proyectado apropiado. Si no los hay, informar solo píxeles y proporción de imagen.

La vecindad espacial no sustituye evidencia espectral. No propagar la etiqueta “fuego” a todos los píxeles cercanos: podría incluir agua, humo, roca o vegetación.

## 6. Calibración con las imágenes del repositorio

Para cada ubicación (La Mierla, Madrid-Ávila y Niebla):

- Confirmar que True Color y SWIR pertenecen a la misma escena y están alineadas.
- Crear pequeñas anotaciones manuales independientes para fuego visible/candidato, humo, agua y “otro”. Incluir ejemplos difíciles: agua que parece fuego en SWIR, sombras, suelo desnudo, nubes y vegetación.
- Ajustar los umbrales solo con un subconjunto de escenas y evaluar en otra escena no usada para el ajuste.
- Calcular por clase precision, recall, F1 e IoU. Para agua es especialmente importante medir cuántos píxeles de agua acaban clasificados como fuego (**falsos positivos de fuego sobre agua**).
- Visualizar siempre RGB, SWIR, máscaras individuales y superposición lado a lado.
- Guardar configuración, nombres de archivo, fecha de adquisición y versión del código.

Como regla de seguridad, la primera versión debe priorizar precisión en la clase fuego y mostrar las detecciones como **candidatos para revisión humana**. La validación cuantitativa determinará si después conviene aumentar recall o usar un clasificador entrenado.

## 7. Limitaciones y siguiente iteración

- **JPG renderizado:** los umbrales de color pueden fallar si cambian el contraste, la paleta o la composición de bandas.
- **Fuego activo:** puede ocupar menos que un píxel o no ser visible como rojo/naranja en RGB; esta implementación no detecta de forma fiable todos los focos.
- **Humo y nubes:** pueden compartir tonos claros y poca saturación. Sin bandas originales, geometría/temporalidad y etiquetas, no se pueden separar de forma robusta en todos los casos.
- **Agua oscura o no azul:** la máscara RGB puede omitirla. Es preferible que el operador revise esos casos a aplicar una regla genérica de “todo píxel oscuro es agua”.
- **Área física:** contar píxeles no basta para calcular hectáreas. Se necesita tamaño de celda real y georreferenciación, y distinguir resolución nominal de capacidad efectiva de resolución.

Mejora recomendada, en orden: (1) verificar y alinear metadatos, (2) probar este baseline y revisar máscaras, (3) etiquetar píxeles/regiones, (4) entrenar un clasificador ligero (por ejemplo, Random Forest con canales RGB/HSV, canales de SWIR y textura local), y (5) evaluar en escenas separadas. Si se consiguen las bandas originales, preferir reflectancias y reglas espectrales documentadas en vez de colores de pantalla.

**Conclusión:** la defensa contra el falso positivo solicitado es explícita: **un candidato de fuego en SWIR se rechaza si RGB lo clasifica como agua, y en esta primera versión solo se conserva si además hay evidencia RGB de color cálido**. Esto es conservador y comprobable, pero no equivale a una detección validada de incendio.
