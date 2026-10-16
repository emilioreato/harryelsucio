import numpy as np

from lumbre.observabilidad_pipeline import PublicadorCheckpoint
from lumbre.regiones_contextuales import segmentar_contextual


def test_callback_nulo_no_ejecuta_renderizado_extra():
    renderizados = []
    publicador = PublicadorCheckpoint(None)
    resultado = publicador.publicar(
        "entrada", "Entrada", "Imagen preparada", kind="image", progress=5,
        image=lambda: renderizados.append(True),
    )
    assert resultado is None
    assert renderizados == []


def test_error_de_observabilidad_no_se_propaga_y_conserva_el_orden():
    capturas = []
    errores = []
    publicador = PublicadorCheckpoint(
        lambda captura: capturas.append(captura), on_error=errores.append,
    )
    vista = np.zeros((12, 20, 3), dtype=np.uint8)
    primera = publicador.publicar(
        "entrada", "Entrada", "Imagen preparada", kind="image", progress=5, image=vista,
    )
    fallida = publicador.publicar(
        "slic", "SLIC", "Vista fallida", kind="regions", progress=40,
        image=lambda: (_ for _ in ()).throw(RuntimeError("falló el render")),
    )
    segunda = publicador.publicar(
        "resultado", "Resultado", "Imagen final", kind="mask", progress=99,
        image=vista, final=True,
    )
    assert primera.order == 1
    assert fallida is None
    assert segunda.order == 2
    assert segunda.comparison_to == primera.id
    assert [captura.order for captura in capturas] == [1, 2]
    assert len(errores) == 1


def test_checkpoint_no_cambia_el_resultado_contextual():
    true_color = np.full((48, 64, 3), 100, dtype=np.uint8)
    candidata = np.zeros((48, 64), dtype=bool)
    candidata[8:25, 6:23] = True
    candidata[30:43, 46:60] = True
    vacia = np.zeros_like(candidata)
    entrada = (true_color, true_color.copy(), candidata, vacia, vacia)

    base = segmentar_contextual(*entrada, refinar=False)
    capturas = []
    con_observabilidad = segmentar_contextual(
        *entrada, refinar=False,
        on_checkpoint=PublicadorCheckpoint(capturas.append),
    )

    assert np.array_equal(base.mascara, con_observabilidad.mascara)
    assert np.array_equal(base.etiquetas, con_observabilidad.etiquetas)
    assert base.uniones == con_observabilidad.uniones
    assert all(
        np.array_equal(base.diagnosticos[nombre], con_observabilidad.diagnosticos[nombre])
        for nombre in base.diagnosticos
    )
    assert [captura.label for captura in capturas] == [
        "Superpíxeles SLIC", "Clasificación regional", "Agrupaciones RAG", "Crecimiento",
    ]
    assert all(max(captura.image.shape[:2]) <= 900 for captura in capturas)
