"""Política de auditoría por ruta + verificación de cobertura (C-13, D3; O1, RN-GL-01).

Cada ruta autenticada del panel, de administración, del alta interna y de sesión declara qué hace con la auditoría:
``semantica`` (audita la acción), ``lectura`` (audita el acceso) o ``exenta`` (con el motivo por escrito). El test de
contrato falla si una ruta no tiene política o si sobra una política: la garantía pasa de runtime a CI, sin costo por pedido.
Verifica la **declaración**; que cada dominio efectivamente escriba lo prueban sus propios tests.
"""

from collections.abc import Mapping
from typing import Final, Literal

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, ConfigDict

from app.plataforma.tipos_auditoria import ACCIONES_CONOCIDAS

PREFIJOS_AUTENTICADOS: Final[tuple[str, ...]] = ("/api/panel", "/api/admin", "/api/turnos", "/api/auth")
METODOS: Final[frozenset[str]] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

Clave = tuple[str, str]  # (método, plantilla de ruta)


class Politica(BaseModel):
    model_config = ConfigDict(frozen=True)

    tipo: Literal["semantica", "lectura", "exenta"]
    acciones: tuple[str, ...] = ()
    motivo: str = ""


def _sem(*acciones: str) -> Politica:
    return Politica(tipo="semantica", acciones=acciones)


def _lec(*acciones: str) -> Politica:
    return Politica(tipo="lectura", acciones=acciones)


def _ex(motivo: str) -> Politica:
    return Politica(tipo="exenta", motivo=motivo)


_OPERATIVA = "lectura operativa de alta frecuencia, cubierta por el rastro de sesión (C-13 O2)"
_AGREGADO = "agregado o importes sin personas (C-12)"
_CONFIG = "configuración o catálogo sin datos de pacientes"
_GCAL = "sin datos del paciente (RN-GC)"
_P = "/api/panel/pacientes/{paciente_id}"
_PRES = f"{_P}/presupuestos"
_PRES_ID = f"{_PRES}/{{presupuesto_id}}"


def _catalogo() -> dict[Clave, Politica]:
    """Los cuatro CRUD de ``/api/admin`` (tratamientos, profesionales, sillones, disponibilidad)."""
    tabla: dict[Clave, Politica] = {}
    for base in ("tratamientos", "profesionales", "sillones", "disponibilidad"):
        tabla[("GET", f"/api/admin/{base}")] = _ex(_CONFIG)
        tabla[("POST", f"/api/admin/{base}")] = _sem("CREATE")
        tabla[("GET", f"/api/admin/{base}/{{id_}}")] = _ex(_CONFIG)
        tabla[("PUT", f"/api/admin/{base}/{{id_}}")] = _sem("UPDATE")
        tabla[("DELETE", f"/api/admin/{base}/{{id_}}")] = _sem("DELETE")
    return tabla


POLITICAS: Final[Mapping[Clave, Politica]] = {
    # Sesión.
    ("POST", "/api/auth/login"): _sem("LOGIN_OK", "LOGIN_FAILED", "LOGIN_BLOQUEADO"),
    ("POST", "/api/auth/logout"): _sem("LOGOUT"),
    ("POST", "/api/auth/refresh"): _ex("renovación técnica de la sesión (C-15 D7)"),
    ("GET", "/api/auth/me"): _ex("lectura de la propia identidad, sin datos de pacientes"),
    # Alta interna (C-01).
    ("POST", "/api/turnos"): _sem("alta_turno_interna"),
    # Agenda e indicadores.
    ("GET", "/api/panel/agenda"): _ex(_OPERATIVA),
    ("GET", "/api/panel/agenda/opciones"): _ex(_OPERATIVA),
    ("GET", "/api/panel/ocupacion"): _ex(_AGREGADO),
    ("GET", "/api/panel/ausentismo"): _ex(_AGREGADO),
    ("GET", "/api/panel/recordatorios"): _ex(_OPERATIVA),
    ("POST", "/api/panel/recordatorios/{recordatorio_id}/enviado"): _sem("UPDATE"),
    ("POST", "/api/panel/recordatorios/{recordatorio_id}/fallido"): _sem("UPDATE"),
    # Turnos del panel.
    ("POST", "/api/panel/turnos"): _sem("CREATE"),
    ("POST", "/api/panel/turnos/{turno_id}/atendido"): _sem("UPDATE"),
    ("POST", "/api/panel/turnos/{turno_id}/ausente"): _sem("UPDATE"),
    ("POST", "/api/panel/turnos/{turno_id}/cancelar"): _sem("UPDATE"),
    ("POST", "/api/panel/turnos/{turno_id}/deshacer-atendido"): _sem("UPDATE"),
    ("PUT", "/api/panel/turnos/{turno_id}/paciente"): _sem("vinculo_turno_paciente"),
    # Caja y seña.
    ("GET", "/api/panel/caja"): _lec("lectura_caja"),
    ("POST", "/api/panel/caja/cierres"): _sem("cierre_caja"),
    ("GET", "/api/panel/caja/cierres"): _ex(_AGREGADO),
    ("GET", "/api/panel/caja/cierres/{cierre_id}"): _ex(_AGREGADO),
    ("POST", "/api/panel/caja/cierres/{cierre_id}/anular"): _sem("anulacion_cierre_caja"),
    ("GET", "/api/panel/caja/liquidacion"): _ex(_AGREGADO),
    ("GET", "/api/panel/caja/pendientes"): _ex(_AGREGADO),
    ("POST", "/api/panel/caja/revisiones/{pago_id}/rechazar"): _sem("sena_revision_rechazada"),
    ("POST", "/api/panel/caja/devoluciones/senas/{pago_id}"): _sem("devolucion_sena_registrada"),
    ("POST", "/api/panel/caja/devoluciones/excedentes/{aprobacion_id}"): _sem("devolucion_excedente_registrada"),
    ("POST", "/api/admin/pagos-sena/{pago_id}/acreditar"): _sem("UPDATE"),
    ("GET", "/api/admin/config/sena"): _ex(_CONFIG),
    ("PUT", "/api/admin/config/sena"): _sem("UPDATE"),
    # Pacientes y clínica.
    ("POST", "/api/panel/pacientes"): _sem("alta_paciente"),
    ("GET", "/api/panel/pacientes"): _lec("busqueda_paciente_dni"),
    ("GET", "/api/panel/pacientes/listado"): _lec("lectura_listado_pacientes"),
    ("GET", _P): _lec("lectura_paciente"),
    ("PUT", _P): _sem("edicion_paciente"),
    ("GET", f"{_P}/ficha"): _lec("lectura_ficha"),
    ("PUT", f"{_P}/ficha"): _sem("edicion_ficha"),
    ("POST", f"{_P}/odontograma"): _sem("registro_odontograma"),
    ("GET", f"{_P}/odontograma"): _lec("lectura_odontograma"),
    ("GET", f"{_P}/odontograma/historial"): _lec("lectura_odontograma"),
    ("POST", _PRES): _sem("alta_presupuesto"),
    ("GET", _PRES): _lec("lectura_presupuesto"),
    ("GET", _PRES_ID): _lec("lectura_presupuesto"),
    ("PUT", _PRES_ID): _sem("edicion_presupuesto"),
    ("POST", f"{_PRES_ID}/presentar"): _sem("transicion_presupuesto"),
    ("POST", f"{_PRES_ID}/aceptar"): _sem("transicion_presupuesto"),
    ("POST", f"{_PRES_ID}/rechazar"): _sem("transicion_presupuesto"),
    ("POST", f"{_PRES_ID}/anular"): _sem("transicion_presupuesto"),
    ("POST", f"{_PRES_ID}/pagos"): _sem("registro_pago_presupuesto"),
    ("GET", f"{_PRES_ID}/pagos"): _lec("lectura_pagos_presupuesto"),
    ("POST", f"{_PRES_ID}/pagos/{{pago_id}}/anular"): _sem("anulacion_pago_presupuesto"),
    # Google Calendar.
    ("POST", "/api/panel/google-calendar/conexion/iniciar"): _sem("inicio_conexion_gcal"),
    ("GET", "/api/panel/google-calendar/oauth/callback"): _sem("UPDATE"),
    ("GET", "/api/panel/google-calendar/conexiones"): _ex(_GCAL),
    ("DELETE", "/api/panel/google-calendar/conexiones/{profesional_id}"): _sem("UPDATE"),
    ("GET", "/api/panel/google-calendar/conflictos"): _ex(_GCAL),
    ("POST", "/api/panel/google-calendar/conflictos/{conflicto_id}/resolver"): _sem("UPDATE"),
    # Plataforma (C-13).
    ("GET", "/api/panel/auditoria"): _lec("lectura_auditoria"),
    ("GET", "/api/panel/export"): _sem("exportacion"),
    ("GET", "/api/panel/usuarios"): _ex("directorio del personal (id y nombre) sin datos de pacientes (C-13 O3)"),
    **_catalogo(),
}


def rutas_autenticadas(app: FastAPI) -> set[Clave]:
    """Pares ``(método, ruta)`` de la app bajo los prefijos autenticados (el esquema se arma fresco: sin caché)."""
    esquema = get_openapi(title="auditoria", version="0", routes=app.routes)
    return {(metodo.upper(), ruta) for ruta, ops in esquema["paths"].items() if ruta.startswith(PREFIJOS_AUTENTICADOS)
            for metodo in ops if metodo.upper() in METODOS}


def verificar(app: FastAPI, politicas: Mapping[Clave, Politica] = POLITICAS) -> list[str]:
    """Problemas de cobertura (vacío = cumple): ruta sin política, política sin ruta, exención sin motivo, acción desconocida."""
    rutas = rutas_autenticadas(app)
    problemas = [f"Ruta sin política de auditoría: {m} {r}" for m, r in sorted(rutas - set(politicas))]
    problemas += [f"Política de una ruta inexistente: {m} {r}" for m, r in sorted(set(politicas) - rutas)]
    for (metodo, ruta), politica in sorted(politicas.items()):
        donde = f"{metodo} {ruta}"
        if politica.tipo == "exenta":
            if not politica.motivo.strip():
                problemas.append(f"Ruta exenta sin motivo: {donde}")
            continue
        if not politica.acciones:
            problemas.append(f"Ruta {politica.tipo} sin acciones declaradas: {donde}")
        problemas += [f"Acción fuera del catálogo de tipos ({a}): {donde}" for a in politica.acciones
                      if a not in ACCIONES_CONOCIDAS]
    return problemas
