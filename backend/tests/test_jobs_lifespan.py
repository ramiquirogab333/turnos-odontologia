"""C-09 (5.2, O11): el barrido de pre-reservas vive en el worker; la API solo lo corre con ``SENA_BARRIDO_EN_API=true``."""

import pytest

from app.main import app, lifespan


@pytest.mark.parametrize("en_api,habilitado,hay_tarea", [
    ("false", "true", False),   # API sin bandera: no barre aunque el barrido esté habilitado (lo hace el worker)
    (None, "true", False),      # por defecto la API no barre
    ("true", "true", True),     # desarrollo y pruebas sin worker
    ("true", "false", False),   # el barrido apagado manda sobre todo
])
async def test_la_api_solo_crea_la_tarea_del_barrido_con_la_bandera(
        monkeypatch: pytest.MonkeyPatch, en_api: str | None, habilitado: str, hay_tarea: bool) -> None:
    monkeypatch.setenv("SENA_BARRIDO_HABILITADO", habilitado)
    if en_api is None:
        monkeypatch.delenv("SENA_BARRIDO_EN_API", raising=False)
    else:
        monkeypatch.setenv("SENA_BARRIDO_EN_API", en_api)
    async with lifespan(app):
        assert (app.state.barrido_task is not None) is hay_tarea
    assert app.state.barrido_task is None or app.state.barrido_task.cancelled() or app.state.barrido_task.done()
