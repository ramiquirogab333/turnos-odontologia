"""C-13 (4.1, D5, O5): catálogo de tipos legibles derivado de ``accion`` + ``entidad`` + ``origen``, sin tocar lo guardado."""

import pytest
from sqlalchemy.dialects import postgresql

from app.plataforma.tipos_auditoria import (
    ACCIONES_CONOCIDAS,
    TIPOS,
    TipoAuditoria,
    clasificar,
    condicion_de_tipo,
)


@pytest.mark.parametrize("accion,entidad,origen,codigo", [
    ("cierre_caja", "cierre_caja", None, "cierre_caja"),
    ("anulacion_cierre_caja", "cierre_caja", None, "anulacion_cierre_caja"),
    ("devolucion_sena_registrada", "pago_sena", None, "devolucion_sena"),
    ("devolucion_excedente_registrada", "pago_sena_aprobacion", None, "devolucion_excedente"),
    ("sena_revision_rechazada", "pago_sena", None, "rechazo_revision_sena"),
    ("UPDATE", "turno", "deshacer_atendido_panel", "deshacer_atendido"),
    ("UPDATE", "turno", "marcado_ausente_panel", "marcado_ausente"),
    ("UPDATE", "turno", "marcado_atendido_panel", "marcado_atendido"),
    ("UPDATE", "turno", "cancelacion_panel", "cancelacion_panel"),
    ("CREATE", "turno", "alta_manual_panel", "alta_manual"),
    ("UPDATE", "turno", "acreditacion_sena", "acreditacion_sena"),
    ("lectura_listado_pacientes", "paciente", None, "lectura_listado_pacientes"),
    ("busqueda_paciente_dni", "paciente", None, "busqueda_paciente_dni"),
    ("lectura_paciente", "paciente", None, "lectura_paciente"),
    ("alta_turno_interna", "turno", None, "alta_turno_interna"),
    ("inicio_conexion_gcal", "gcal_conexion", None, "inicio_conexion_gcal"),
    ("LOGIN_OK", "usuario", None, "login_ok"),
    ("LOGIN_FAILED", "usuario", None, "login_failed"),
    ("LOGIN_BLOQUEADO", "usuario", None, "login_bloqueado"),
    ("LOGOUT", "usuario", None, "logout"),
    ("SESIONES_REVOCADAS", "usuario", None, "sesiones_revocadas"),
    ("exportacion", "exportacion", None, "exportacion"),
    ("lectura_auditoria", "auditoria", None, "lectura_auditoria"),
])
def test_cada_fila_del_catalogo_da_su_tipo_y_una_etiqueta_legible(
        accion: str, entidad: str, origen: str | None, codigo: str) -> None:
    tipo = clasificar(accion, entidad, origen)
    assert isinstance(tipo, TipoAuditoria) and tipo.codigo == codigo
    assert tipo.etiqueta == TIPOS[codigo] and tipo.etiqueta != codigo  # legible, no el código crudo


def test_un_update_de_configuracion_sin_origen_es_otro_con_la_accion_original() -> None:
    tipo = clasificar("UPDATE", "configuracion_sena", None)
    assert (tipo.codigo, tipo.etiqueta) == ("otro", "UPDATE")


@pytest.mark.parametrize("accion,entidad,origen", [
    ("UPDATE", "turno", "origen_que_no_existe"),  # el origen no catalogado no inventa tipo
    ("UPDATE", "turno", None),
    ("CREATE", "profesional", None),
    ("accion_historica_rara", "lo_que_sea", None),
])
def test_lo_que_no_esta_en_el_catalogo_es_otro_con_su_accion(accion: str, entidad: str, origen: str | None) -> None:
    assert clasificar(accion, entidad, origen) == TipoAuditoria("otro", accion)


def test_el_origen_solo_cuenta_para_la_entidad_y_accion_que_lo_definen() -> None:
    # Un origen de turno sobre otra entidad no se confunde con el tipo del turno.
    assert clasificar("UPDATE", "pago_sena", "marcado_ausente_panel").codigo == "otro"


def _sql(codigo: str) -> str:
    return str(condicion_de_tipo(codigo).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_el_predicado_de_un_tipo_semantico_filtra_solo_por_accion() -> None:
    sql = _sql("cierre_caja")
    assert "registro_auditoria.accion = 'cierre_caja'" in sql and "origen" not in sql


def test_el_predicado_de_un_tipo_con_origen_filtra_accion_entidad_y_origen() -> None:
    sql = _sql("marcado_ausente")
    assert "registro_auditoria.accion = 'UPDATE'" in sql
    assert "registro_auditoria.entidad = 'turno'" in sql
    assert "datos_despues ->> 'origen') = 'marcado_ausente_panel'" in sql


def test_el_predicado_de_otro_excluye_todos_los_tipos_conocidos() -> None:
    sql = _sql("otro")
    assert sql.startswith("NOT") or "NOT (" in sql
    assert "'cierre_caja'" in sql and "'marcado_ausente_panel'" in sql


def test_un_tipo_desconocido_no_tiene_predicado() -> None:
    with pytest.raises(KeyError):
        condicion_de_tipo("inventado")


def test_todos_los_codigos_tienen_etiqueta_y_las_acciones_conocidas_incluyen_el_crud_generico() -> None:
    assert "otro" in TIPOS and all(TIPOS.values())
    assert {"CREATE", "UPDATE", "DELETE", "exportacion", "lectura_auditoria", "cierre_caja"} <= ACCIONES_CONOCIDAS
