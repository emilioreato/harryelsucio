from pathlib import Path

from lumbre.interfaz import configuracion


def _crear_par(carpeta: Path, fecha: str) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{fecha}_Sentinel-2_L2A_True_color.jpg").write_bytes(b"true")
    (carpeta / f"{fecha}_Sentinel-2_L2A_SWIR.jpg").write_bytes(b"swir")


def test_escenas_canonicas_incluyen_solo_su_referencia_wildfires(monkeypatch, tmp_path):
    imagenes = tmp_path / "imagenes"
    referencias = tmp_path / "DOCUMENTACION" / "Presentacion reto"
    escenas = {
        "La Mierla (Guadalajara)": "2026-07-21-00_00_2026-07-21-23_59",
        "Madrid-Avila": "2026-07-26-00_00_2026-07-26-23_59",
        "Niebla (Huelva)": "2026-08-08-00_00_2026-08-08-23_59",
    }
    for nombre, fecha in escenas.items():
        _crear_par(imagenes / nombre, fecha)
        (referencias / nombre).mkdir(parents=True)
    mierla_ref = referencias / "La Mierla (Guadalajara)" / (
        f"{escenas['La Mierla (Guadalajara)']}_Sentinel-2_L2A_Wildfires.jpg"
    )
    niebla_ref = referencias / "Niebla (Huelva)" / (
        f"{escenas['Niebla (Huelva)']}_Sentinel-2_L2A_Wildfires.jpg"
    )
    mierla_ref.write_bytes(b"mierla")
    niebla_ref.write_bytes(b"niebla")
    (referencias / "Niebla (Huelva)" / "2026-07-21_Wildfires.jpg").write_bytes(b"otro-dia")
    monkeypatch.setattr(configuracion, "CARPETA_IMAGENES", imagenes)
    monkeypatch.setattr(configuracion, "CARPETA_REFERENCIAS_RETO", referencias)

    escenas_disponibles = {
        escena.nombre: escena for escena in configuracion.listar_escenas_disponibles()
    }

    assert escenas_disponibles["La Mierla (Guadalajara)"].referencia_wildfires == mierla_ref
    assert escenas_disponibles["Niebla (Huelva)"].referencia_wildfires == niebla_ref
    assert escenas_disponibles["Madrid-Avila"].referencia_wildfires is None
