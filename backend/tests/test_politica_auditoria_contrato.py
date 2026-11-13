"""C-13 (4.3, D3, O1): toda ruta autenticada declara su política de auditoría; la suite falla si falta o sobra una."""

from fastapi import FastAPI

from app.plataforma.politica_auditoria import POLITICAS, Politica, rutas_autenticadas, verificar
from app.plataforma.tipos_auditoria import ACCIONES_CONOCIDAS


def _app_de_prueba(*rutas: tuple[str, str]) -> FastAPI:
    app = FastAPI()
    for metodo, ruta in rutas:
        app.add_api_route(ruta, lambda: None, methods=[metodo])
    return app


def test_todas_las_rutas_actuales_tienen_exactamente_una_politica_y_la_verificacion_pasa() -> None:
    from app.main import app

    assert verificar(app, POLITICAS) == []
    assert set(POLITICAS) == rutas_autenticadas(app)


def test_las_rutas_publicas_y_de_salud_no_requieren_politica() -> None:
    app = _app_de_prueba(("GET", "/api/health"), ("POST", "/api/public/turnos"), ("POST", "/api/webhooks/mercadopago"))
    assert rutas_autenticadas(app) == set()


def test_una_ruta_nueva_sin_politica_falla_nombrando_metodo_y_ruta() -> None:
    app = _app_de_prueba(("POST", "/api/panel/algo-nuevo"))
    problemas = verificar(app, {})
    assert len(problemas) == 1 and "POST /api/panel/algo-nuevo" in problemas[0]


def test_una_politica_de_una_ruta_inexistente_falla() -> None:
    politicas = {("GET", "/api/panel/fantasma"): Politica(tipo="exenta", motivo="no existe")}
    problemas = verificar(_app_de_prueba(), politicas)
    assert len(problemas) == 1 and "GET /api/panel/fantasma" in problemas[0]


def test_una_ruta_exenta_sin_motivo_o_con_motivo_en_blanco_falla() -> None:
    app = _app_de_prueba(("GET", "/api/panel/a"), ("GET", "/api/panel/b"))
    politicas = {("GET", "/api/panel/a"): Politica(tipo="exenta", motivo=""),
                 ("GET", "/api/panel/b"): Politica(tipo="exenta", motivo="   ")}
    problemas = verificar(app, politicas)
    assert len(problemas) == 2 and all("motivo" in p for p in problemas)


def test_una_ruta_semantica_o_de_lectura_sin_acciones_falla() -> None:
    app = _app_de_prueba(("POST", "/api/panel/a"), ("GET", "/api/panel/b"))
    politicas = {("POST", "/api/panel/a"): Politica(tipo="semantica"),
                 ("GET", "/api/panel/b"): Politica(tipo="lectura")}
    assert len(verificar(app, politicas)) == 2


def test_una_accion_que_no_esta_en_el_catalogo_falla_nombrandola() -> None:
    app = _app_de_prueba(("POST", "/api/panel/a"))
    politicas = {("POST", "/api/panel/a"): Politica(tipo="semantica", acciones=("accion_inventada",))}
    problemas = verificar(app, politicas)
    assert len(problemas) == 1 and "accion_inventada" in problemas[0]


def test_toda_accion_declarada_existe_en_el_catalogo_de_tipos() -> None:
    declaradas = {a for p in POLITICAS.values() for a in p.acciones}
    assert declaradas and declaradas <= ACCIONES_CONOCIDAS


def test_toda_exencion_real_lleva_motivo() -> None:
    exentas = [p for p in POLITICAS.values() if p.tipo == "exenta"]
    assert exentas and all(p.motivo.strip() for p in exentas)
