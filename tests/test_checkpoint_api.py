import json
import uuid
import time
from io import BytesIO

import numpy as np
from PIL import Image

from lumbre import servidor_web
from lumbre.observabilidad_pipeline import PublicadorCheckpoint


def _get(handler_path):
    handler = object.__new__(servidor_web.LumbreHandler)
    handler.path = handler_path
    response = {}
    handler._bytes = lambda status, body, content_type: response.update(
        status=status, body=body, content_type=content_type,
    )
    handler.do_GET()
    return response


def test_checkpoint_disponible_mientras_job_sigue_en_ejecucion(monkeypatch):
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    for job_id in ids:
        monkeypatch.setitem(servidor_web._JOBS, job_id, {
            "id": job_id, "state": "running", "stage": "Procesando", "progress": 20,
            "updated_at": time.time(), "checkpoints": [], "checkpoint_images": {},
            "checkpoint_bytes": 0, "checkpoint_warnings": [],
        })

    for job_id, color in zip(ids, ((220, 40, 30), (20, 80, 220))):
        publicador = PublicadorCheckpoint(
            lambda captura, actual=job_id: servidor_web._publicar_checkpoint_trabajo(actual, captura)
        )
        publicador.publicar(
            "entrada", "Imagen preparada", "Previsualización real", kind="image", progress=5,
            image=np.full((600, 1200, 3), color, dtype=np.uint8),
        )
        publicador.publicar(
            "resultado", "Resultado final", "Captura final", kind="mask", progress=99,
            image=np.full((600, 1200, 3), color[::-1], dtype=np.uint8), final=True,
        )

    resumenes = []
    imagenes = []
    for job_id in ids:
        resumen_respuesta = _get(f"/api/jobs/{job_id}")
        assert resumen_respuesta["status"] == 200
        resumen = json.loads(resumen_respuesta["body"].decode("utf-8"))
        assert resumen["state"] == "running"
        assert [item["order"] for item in resumen["checkpoints"]] == [1, 2]
        assert resumen["checkpoints"][1]["comparison_to"] == resumen["checkpoints"][0]["id"]
        for checkpoint in resumen["checkpoints"]:
            captura = _get(checkpoint["image"])
            assert captura["status"] == 200
            assert captura["content_type"] == "image/jpeg"
            with Image.open(BytesIO(captura["body"])) as imagen:
                assert imagen.size == (900, 450)
                assert imagen.format == "JPEG"
            imagenes.append(captura["body"])
        resumenes.append(resumen)

    assert resumenes[0]["checkpoints"][0]["id"] == resumenes[1]["checkpoints"][0]["id"]
    assert resumenes[0]["checkpoints"][0]["image"] != resumenes[1]["checkpoints"][0]["image"]
    assert imagenes[0] != imagenes[2]
