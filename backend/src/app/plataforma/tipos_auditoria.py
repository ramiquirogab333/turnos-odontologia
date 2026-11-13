"""Catálogo de tipos legibles de la auditoría (C-13, D5, O5).

Tabla pura ``(accion, entidad, origen) -> tipo`` que se evalúa al leer: nunca se guarda ni se migra, así los registros
históricos (tres convenciones de ``accion``) no se tocan. Lo que no está en el catálogo es ``otro`` con la acción original.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from sqlalchemy import ColumnElement, and_, not_, or_

from app.models.core import RegistroAuditoria

OTRO: Final = "otro"
CRUD_GENERICO: Final[frozenset[str]] = frozenset({"CREATE", "UPDATE", "DELETE"})


@dataclass(frozen=True)
class TipoAuditoria:
    codigo: str
    etiqueta: str


@dataclass(frozen=True)
class _Regla:
    codigo: str
    etiqueta: str
    accion: str
    entidad: str | None = None  # solo para las reglas que se distinguen por origen
    origen: str | None = None


def _semantica(codigo: str, etiqueta: str, accion: str | None = None) -> _Regla:
    return _Regla(codigo, etiqueta, accion or codigo)


def _turno(codigo: str, etiqueta: str, accion: str, origen: str) -> _Regla:
    return _Regla(codigo, etiqueta, accion, "turno", origen)


_REGLAS: Final[tuple[_Regla, ...]] = (
    # Caja y seña (C-06, C-12).
    _semantica("cierre_caja", "Cierre de caja"),
    _semantica("anulacion_cierre_caja", "Anulación de cierre de caja"),
    _semantica("devolucion_sena", "Devolución de seña", "devolucion_sena_registrada"),
    _semantica("devolucion_excedente", "Devolución de excedente", "devolucion_excedente_registrada"),
    _semantica("rechazo_revision_sena", "Rechazo de revisión de seña", "sena_revision_rechazada"),
    _semantica("lectura_caja", "Consulta de caja"),
    _semantica("configuracion_sena", "Cambio de la configuración de la seña"),
    # Turnos: se distinguen por el origen que graba cada caso de uso.
    _turno("deshacer_atendido", "Corrección de atendido", "UPDATE", "deshacer_atendido_panel"),
    _turno("marcado_ausente", "Turno marcado ausente", "UPDATE", "marcado_ausente_panel"),
    _turno("marcado_atendido", "Turno marcado atendido", "UPDATE", "marcado_atendido_panel"),
    _turno("cancelacion_panel", "Cancelación desde el panel", "UPDATE", "cancelacion_panel"),
    _turno("alta_manual", "Alta manual de turno", "CREATE", "alta_manual_panel"),
    _turno("acreditacion_sena", "Acreditación de seña", "UPDATE", "acreditacion_sena"),
    _turno("cancelacion_paciente", "Cancelación del paciente", "UPDATE", "cancelacion_paciente"),
    _turno("confirmacion_paciente", "Confirmación del paciente", "UPDATE", "confirmacion_paciente"),
    _turno("reprogramacion_paciente", "Reprogramación del paciente", "UPDATE", "reprogramacion_paciente"),
    _turno("vencimiento_sena", "Vencimiento de pre-reserva", "UPDATE", "vencimiento_sena"),
    _turno("reserva_publica", "Reserva pública", "CREATE", "reserva_publica"),
    # Nuevas de C-13.
    _semantica("alta_turno_interna", "Alta interna de turno"),
    _semantica("inicio_conexion_gcal", "Inicio de conexión con Google Calendar"),
    _semantica("lectura_listado_pacientes", "Lectura del listado de pacientes"),
    _semantica("busqueda_paciente_dni", "Búsqueda de paciente por DNI"),
    _semantica("lectura_paciente", "Lectura de datos de un paciente"),
    _semantica("exportacion", "Exportación de datos"),
    _semantica("lectura_auditoria", "Consulta de auditoría"),
    # Sesión (C-03, C-15).
    _semantica("login_ok", "Ingreso al panel", "LOGIN_OK"),
    _semantica("login_failed", "Ingreso fallido", "LOGIN_FAILED"),
    _semantica("login_bloqueado", "Ingreso bloqueado por límite", "LOGIN_BLOQUEADO"),
    _semantica("logout", "Cierre de sesión", "LOGOUT"),
    _semantica("sesiones_revocadas", "Sesiones revocadas", "SESIONES_REVOCADAS"),
    # Pacientes y clínica (C-11).
    _semantica("alta_paciente", "Alta de paciente"),
    _semantica("edicion_paciente", "Edición de paciente"),
    _semantica("vinculo_turno_paciente", "Vínculo de turno con paciente"),
    _semantica("lectura_ficha", "Lectura de ficha"),
    _semantica("edicion_ficha", "Edición de ficha"),
    _semantica("lectura_odontograma", "Lectura de odontograma"),
    _semantica("registro_odontograma", "Registro en odontograma"),
    _semantica("lectura_presupuesto", "Lectura de presupuesto"),
    _semantica("alta_presupuesto", "Alta de presupuesto"),
    _semantica("edicion_presupuesto", "Edición de presupuesto"),
    _semantica("transicion_presupuesto", "Cambio de estado de presupuesto"),
    _semantica("lectura_pagos_presupuesto", "Lectura de pagos de presupuesto"),
    _semantica("registro_pago_presupuesto", "Registro de pago de presupuesto"),
    _semantica("anulacion_pago_presupuesto", "Anulación de pago de presupuesto"),
)

TIPOS: Final[Mapping[str, str]] = {**{r.codigo: r.etiqueta for r in _REGLAS}, OTRO: "Otro"}
# Acciones que el catálogo reconoce (las que una política de ruta puede declarar): las semánticas y el CRUD genérico.
ACCIONES_CONOCIDAS: Final[frozenset[str]] = frozenset({r.accion for r in _REGLAS}) | CRUD_GENERICO

_POR_CODIGO: Final[Mapping[str, _Regla]] = {r.codigo: r for r in _REGLAS}


def _coincide(regla: _Regla, accion: str, entidad: str, origen: str | None) -> bool:
    if regla.accion != accion:
        return False
    if regla.origen is None:
        return True
    return regla.entidad == entidad and regla.origen == origen


def clasificar(accion: str, entidad: str, origen: str | None) -> TipoAuditoria:
    """Tipo legible de un registro; lo no catalogado es ``otro`` con la acción original como etiqueta."""
    for regla in _REGLAS:
        if _coincide(regla, accion, entidad, origen):
            return TipoAuditoria(regla.codigo, regla.etiqueta)
    return TipoAuditoria(OTRO, accion)


def _condicion(regla: _Regla) -> ColumnElement[bool]:
    por_accion = RegistroAuditoria.accion == regla.accion
    if regla.origen is None:
        return por_accion
    return and_(por_accion, RegistroAuditoria.entidad == regla.entidad,
                RegistroAuditoria.datos_despues["origen"].astext == regla.origen)


def condicion_de_tipo(codigo: str) -> ColumnElement[bool]:
    """Predicado SQL equivalente a ``clasificar(...).codigo == codigo`` (``KeyError`` si el tipo no existe)."""
    if codigo == OTRO:
        return not_(or_(*(_condicion(r) for r in _REGLAS)))
    return _condicion(_POR_CODIGO[codigo])
