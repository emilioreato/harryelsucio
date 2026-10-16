from pathlib import Path

from scripts._salidas import directorio_salida, resolver_ruta_repositorio


def test_salida_predeterminada_se_elimina_al_terminar():
    with directorio_salida(None, "lumbre-test-") as salida:
        assert salida.is_dir()
        (salida / "capa.png").write_bytes(b"test")

    assert not salida.exists()


def test_salida_explicita_se_conserva(tmp_path: Path):
    salida = tmp_path / "resultados-prueba"

    with directorio_salida(salida, "lumbre-test-") as actual:
        assert actual == salida.resolve()
        (actual / "capa.png").write_bytes(b"test")

    assert (salida / "capa.png").read_bytes() == b"test"


def test_ruta_relativa_se_resuelve_desde_la_raiz_del_repo():
    raiz = Path(__file__).resolve().parents[1]

    assert resolver_ruta_repositorio(".tmp/pruebas/escena") == raiz / ".tmp" / "pruebas" / "escena"
