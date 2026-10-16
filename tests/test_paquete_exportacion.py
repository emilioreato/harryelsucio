import json
from io import BytesIO
from types import SimpleNamespace
import uuid
from zipfile import ZipFile

import numpy as np
import pytest
from PIL import Image

from lumbre import servidor_web
from lumbre.ontologia import ClaseSemantica
from lumbre.paquete_exportacion import crear_paquete_resultado, validar_anotaciones


def _png(datos, modo="RGB"):
    salida = BytesIO()
    Image.fromarray(datos, mode=modo).save(salida, format="PNG")
    return salida.getvalue()


def _trabajo():
    base = np.full((24, 32, 3), (45, 70, 90), dtype=np.uint8)
    mascara = np.zeros((24, 32), dtype=np.uint8)
    mascara[5:15, 7:20] = 255
    humo = np.zeros_like(mascara)
    humo[2:12, 18:29] = 255
    return {
        "id": str(uuid.uuid4()),
        "state": "complete",
        "input_source": "preloaded",
        "scene_id": "escena-demo",
        "input_filenames": {"true_color": "true.png", "swir": "swir.png"},
        "settings": {"detector": {"id": "contextual_hibrida", "name": "Contextual"}},
        "grid": {
            "ancho_px": 32,
            "alto_px": 24,
            "tipo": "local_metrico",
            "gsd_x_m": 20,
            "gsd_y_m": 20,
            "transformacion_affine": None,
            "crs": None,
            "origen_pixel": "esquina_superior_izquierda",
            "ejes_pixel": {"x": "columna hacia la derecha", "y": "fila hacia abajo"},
        },
        "metrics": {"coverage_pct": 10.0},
        "outputs": {
            "true-color": _png(base),
            "swir": _png(base + 10),
            "overlay-true-color": _png(base + 20),
            "overlay-swir": _png(base + 30),
            "candidates": _png(base + 40),
            "mask": _png(mascara, "L"),
            "visible-surface": _png(mascara, "L"),
            "smoke": _png(humo, "L"),
            "smoke-candidates": _png(mascara, "L"),
            "diagnostic-border": _png(mascara, "L"),
            "semantic-classes": _png(np.zeros((24, 32), dtype=np.uint8), "L"),
            "class-water": _png(mascara, "L"),
            "visible-surface-border": _png(mascara, "L"),
        },
    }


def _anotaciones():
    return [
        {"id": "dibujo", "kind": "freehand", "points": [{"x": 2, "y": 2}, {"x": 8, "y": 5}], "color": "#ff4fa3", "width": 4},
        {"id": "linea", "kind": "line", "points": [{"x": 2, "y": 20}, {"x": 28, "y": 20}], "color": "#ffdf45", "width": 3},
        {"id": "flecha", "kind": "arrow", "points": [{"x": 3, "y": 18}, {"x": 20, "y": 4}], "color": "#38d8ff", "width": 4},
        {"id": "rectangulo", "kind": "rectangle", "points": [{"x": 10, "y": 4}, {"x": 22, "y": 12}], "color": "#ffffff", "width": 2},
        {"id": "elipse", "kind": "ellipse", "points": [{"x": 5, "y": 8}, {"x": 13, "y": 16}], "color": "#ff4fa3", "width": 2},
        {"id": "texto", "kind": "text", "points": [{"x": 12, "y": 14}], "text": "Revisar borde", "color": "#ffdf45", "width": 4},
    ]


def _leer_png_binario(datos):
    with Image.open(BytesIO(datos)) as imagen:
        return np.asarray(imagen.convert("L")) == 255


def test_capas_adicionales_exportan_mascaras_bordes_y_ontologia():
    superficie = np.zeros((8, 9), dtype=bool)
    superficie[2:6, 2:7] = True
    humo = np.zeros_like(superficie)
    humo[1:4, 6:8] = True
    bajo_humo = np.zeros_like(superficie)
    bajo_humo[3:6, 6:8] = True
    clases = np.arange(8, dtype=np.uint8).reshape(2, 4)
    clases = np.pad(clases, ((0, 6), (0, 5)))
    resultado = SimpleNamespace(
        mascara_humo=humo,
        mascara_candidata_bajo_humo=bajo_humo,
        mascara_superficie_visible=superficie,
        mascara_clasificada=superficie.copy(),
        mascara_indeterminada=None,
        mascara_bajo_humo_espectral=None,
        mascara_bajo_humo_continuidad=None,
        clase_por_pixel=clases,
        diagnosticos_contextuales={},
    )

    capas = servidor_web._capas_adicionales(resultado)

    assert {
        "classified-candidates", "semantic-classes", "smoke-border",
        "visible-surface-border", "smoke-candidates-border",
        "class-undetermined", "class-vegetation", "class-water",
        "class-smoke-probable", "class-affected-surface-candidate",
        "class-active-fire-possible", "class-cloud-haze", "class-bare-soil-urban",
    } <= capas.keys()
    assert np.array_equal(_leer_png_binario(capas["visible-surface"]), superficie)
    assert np.array_equal(
        _leer_png_binario(capas["visible-surface-border"]),
        servidor_web._mascara_borde(superficie),
    )
    assert np.array_equal(
        _leer_png_binario(capas["class-water"]),
        clases == int(ClaseSemantica.AGUA_POSIBLE),
    )
    with Image.open(BytesIO(capas["semantic-classes"])) as imagen:
        assert np.array_equal(np.asarray(imagen), clases)


def test_paquete_incluye_entradas_capas_anotaciones_y_mapa_editado():
    paquete = crear_paquete_resultado(
        _trabajo(),
        _anotaciones(),
        {"layer": "true-color", "show_smoke": True, "show_visible_surface": True},
    )

    with ZipFile(BytesIO(paquete)) as archivo:
        nombres = set(archivo.namelist())
        assert {
            "README.md",
            "manifest.json",
            "entradas/true_color_rejilla_analisis.png",
            "entradas/swir_rejilla_analisis.png",
            "capas/smoke.png",
            "capas/visible-surface.png",
            "capas/smoke-candidates.png",
            "capas/diagnostic-border.png",
            "capas/semantic-classes.png",
            "capas/class-water.png",
            "capas/visible-surface-border.png",
            "revision/mapa_anotado.png",
            "anotaciones/anotaciones.json",
            "anotaciones/anotaciones.svg",
        } <= nombres

        manifiesto = json.loads(archivo.read("manifest.json"))
        assert manifiesto["grid"]["ancho_px"] == 32
        assert manifiesto["input"]["analysis_grid_pair"] == [
            "entradas/true_color_rejilla_analisis.png", "entradas/swir_rejilla_analisis.png"
        ]
        assert len(manifiesto["layers"]) == len(_trabajo()["outputs"])
        assert manifiesto["semantic_class_values"]["5"] == "fuego_activo_posible"
        assert manifiesto["annotations"]["count"] == 6

        anotaciones = json.loads(archivo.read("anotaciones/anotaciones.json"))
        assert anotaciones["coordinate_system"]["origin"] == "top_left"
        assert [item["kind"] for item in anotaciones["features"]] == [
            "freehand", "line", "arrow", "rectangle", "ellipse", "text"
        ]
        svg = archivo.read("anotaciones/anotaciones.svg").decode("utf-8")
        assert "Revisar borde" in svg
        assert "<ellipse" in svg and "<rect" in svg
        with Image.open(BytesIO(archivo.read("revision/mapa_anotado.png"))) as mapa:
            assert mapa.size == (32, 24)
            assert mapa.format == "PNG"


def test_anotaciones_fuera_de_rejilla_o_con_color_invalido_se_rechazan():
    with pytest.raises(ValueError, match="se sale de la rejilla"):
        validar_anotaciones([
            {"kind": "text", "points": [{"x": 32, "y": 4}], "text": "zona"}
        ], 32, 24)

    with pytest.raises(ValueError, match="color"):
        validar_anotaciones([
            {"kind": "text", "points": [{"x": 4, "y": 4}], "text": "zona", "color": "red"}
        ], 32, 24)


def test_endpoint_package_devuelve_zip_y_rechaza_trabajo_incompleto(monkeypatch):
    job_id = str(uuid.uuid4())
    trabajo = {**_trabajo(), "id": job_id}
    monkeypatch.setitem(servidor_web._JOBS, job_id, trabajo)
    payload = {"annotations": _anotaciones(), "view": {"layer": "swir"}}

    handler = object.__new__(servidor_web.LumbreHandler)
    handler.path = f"/api/jobs/{job_id}/package.zip"
    handler._leer_json = lambda: payload
    response = {}
    handler._bytes = lambda status, body, content_type: response.update(
        status=status, body=body, content_type=content_type,
    )
    handler._json = lambda status, body: response.update(status=status, json=body)
    handler.do_POST()

    assert response["status"] == 200
    assert response["content_type"] == "application/zip"
    with ZipFile(BytesIO(response["body"])) as archivo:
        assert "revision/mapa_anotado.png" in archivo.namelist()

    trabajo["state"] = "running"
    response.clear()
    handler.do_POST()
    assert response["status"] == 409
