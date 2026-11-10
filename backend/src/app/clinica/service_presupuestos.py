"""Servicio de presupuestos: cálculo con cobertura, borrador, estados y consulta por rol (C-11, D6/D7; O3, O4, O9-O11).

El cálculo vive en ``calculo.py`` (puro); acá solo se cargan precios y nomenclador con UNA consulta por presupuesto
(sin N+1), se guarda el snapshot por línea y se serializan las transiciones con ``SELECT … FOR UPDATE``.
"""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext
from app.clinica.calculo import LineaCalculada, calcular_linea, totalizar
from app.clinica.errores import (
    PresupuestoConPagosError,
    PresupuestoInexistenteError,
    PresupuestoNoEditableError,
    TratamientoInexistenteError,
)
from app.clinica.estados import validar_transicion
from app.clinica.models import PagoPresupuesto, Presupuesto, PresupuestoLinea
from app.clinica.schemas import (
    LineaIn,
    LineaOut,
    PagoOut,
    PresupuestoCreate,
    PresupuestoOut,
    PresupuestoVistaClinicaOut,
)
from app.models.core import Nomenclador, ObraSocial, Paciente
from app.pacientes.alcance import alcance_paciente
from app.pacientes.auditoria import auditar
from app.pacientes.errores import ObraSocialInactivaError, PacienteInexistenteError
from app.panel.schemas import Ref
from app.turnos.models import Tratamiento

CERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# Cálculo y snapshot de las líneas
# ---------------------------------------------------------------------------

async def _obra_social_efectiva(session: AsyncSession, paciente: Paciente, data: PresupuestoCreate) -> int | None:
    """Ausente = la del paciente si está activa; ``null`` = particular; otra = debe estar activa (422)."""
    pedida = data.obra_social_id if "obra_social_id" in data.model_fields_set else paciente.obra_social_id
    if pedida is None:
        return None
    activa = (await session.execute(
        select(ObraSocial.id).where(ObraSocial.id == pedida, ObraSocial.is_active.is_(True)))).scalar_one_or_none()
    if activa is None:
        if "obra_social_id" in data.model_fields_set:
            raise ObraSocialInactivaError()
        return None  # la obra social del paciente se dio de baja: se presupuesta como particular
    return int(pedida)


async def _filas_de_linea(session: AsyncSession, presupuesto_id: int, obra_social_id: int | None,
                          lineas: Sequence[LineaIn]) -> tuple[list[dict[str, Any]], list[LineaCalculada]]:
    """Precio base y fila de nomenclador de todas las líneas en una sola consulta; arma el snapshot de cada una."""
    ids = sorted({l.tratamiento_id for l in lineas})
    consulta = select(Tratamiento.id, Tratamiento.precio_base, Nomenclador.id, Nomenclador.codigo_prestacion,
                      Nomenclador.cobertura_porcentaje, Nomenclador.arancel_diferencial).select_from(Tratamiento)
    if obra_social_id is not None:
        consulta = consulta.outerjoin(Nomenclador, (Nomenclador.tratamiento_id == Tratamiento.id)
                                      & (Nomenclador.obra_social_id == obra_social_id))
    else:
        consulta = consulta.outerjoin(Nomenclador, Nomenclador.id.is_(None))
    datos = {int(t): (precio, nid, codigo, cob, dif)
             for t, precio, nid, codigo, cob, dif in (await session.execute(
                 consulta.where(Tratamiento.id.in_(ids)))).all()}
    if len(datos) != len(ids):
        raise TratamientoInexistenteError()
    filas: list[dict[str, Any]] = []
    calculadas: list[LineaCalculada] = []
    for orden, l in enumerate(lineas, start=1):
        precio, nid, codigo, cob, dif = datos[l.tratamiento_id]
        calc = calcular_linea(precio, l.cantidad, cob, dif)
        calculadas.append(calc)
        filas.append({
            "presupuesto_id": presupuesto_id, "orden": orden, "tratamiento_id": l.tratamiento_id, "nomenclador_id": nid,
            "codigo_prestacion": codigo, "pieza": l.pieza, "cara": l.cara, "cantidad": l.cantidad,
            "precio_unitario": precio, "cobertura_porcentaje": cob if cob is not None else CERO,
            "arancel_diferencial": dif if dif is not None else CERO, "importe_bruto": calc.bruto,
            "importe_cobertura": calc.cobertura, "importe_diferencial": calc.diferencial,
            "importe_paciente": calc.a_cargo})
    return filas, calculadas


async def _reemplazar_lineas(session: AsyncSession, p: Presupuesto, lineas: Sequence[LineaIn]) -> None:
    """Recalcula con los valores vigentes y reemplaza líneas y totales (borrador o al presentar)."""
    filas, calculadas = await _filas_de_linea(session, int(p.id), p.obra_social_id, lineas)
    await session.execute(delete(PresupuestoLinea).where(PresupuestoLinea.presupuesto_id == p.id))
    await session.execute(insert(PresupuestoLinea), filas)
    t = totalizar(calculadas)
    p.subtotal, p.cobertura_total, p.diferencial_total, p.total_paciente = t.subtotal, t.cobertura, t.diferencial, t.a_cargo


# ---------------------------------------------------------------------------
# Lectura y serialización por rol
# ---------------------------------------------------------------------------

async def _armar(session: AsyncSession, presupuestos: Sequence[Presupuesto],
                 completo: bool) -> list[PresupuestoOut | PresupuestoVistaClinicaOut]:
    """Serializa varios presupuestos con 3 consultas (líneas, pagos, obras sociales), sin N+1."""
    if not presupuestos:
        return []
    ids = [int(p.id) for p in presupuestos]
    lineas_por: dict[int, list[LineaOut]] = {i: [] for i in ids}
    for l, nombre, nid in (await session.execute(
            select(PresupuestoLinea, Tratamiento.nombre, PresupuestoLinea.nomenclador_id)
            .join(Tratamiento, Tratamiento.id == PresupuestoLinea.tratamiento_id)
            .where(PresupuestoLinea.presupuesto_id.in_(ids)).order_by(PresupuestoLinea.orden))).all():
        lineas_por[int(l.presupuesto_id)].append(LineaOut(
            id=int(l.id), orden=l.orden, tratamiento=Ref(id=l.tratamiento_id, nombre=nombre), pieza=l.pieza, cara=l.cara,
            cantidad=l.cantidad, precio_unitario=l.precio_unitario, cobertura_porcentaje=l.cobertura_porcentaje,
            arancel_diferencial=l.arancel_diferencial, codigo_prestacion=l.codigo_prestacion,
            importe_bruto=l.importe_bruto, importe_cobertura=l.importe_cobertura,
            importe_diferencial=l.importe_diferencial, importe_paciente=l.importe_paciente,
            sin_cobertura=nid is None))
    os_ids = {p.obra_social_id for p in presupuestos if p.obra_social_id is not None}
    nombres = {int(i): n for i, n in (await session.execute(
        select(ObraSocial.id, ObraSocial.nombre).where(ObraSocial.id.in_(os_ids)))).all()} if os_ids else {}
    pagos_por: dict[int, list[PagoPresupuesto]] = {i: [] for i in ids}
    if completo:
        for pago in (await session.execute(select(PagoPresupuesto).where(PagoPresupuesto.presupuesto_id.in_(ids))
                                           .order_by(PagoPresupuesto.id))).scalars():
            pagos_por[int(pago.presupuesto_id)].append(pago)
    salida: list[PresupuestoOut | PresupuestoVistaClinicaOut] = []
    for p in presupuestos:
        comunes: dict[str, Any] = dict(
            id=int(p.id), paciente_id=p.paciente_id,
            obra_social=Ref(id=p.obra_social_id, nombre=nombres[p.obra_social_id]) if p.obra_social_id else None,
            estado=p.estado, subtotal=p.subtotal, cobertura_total=p.cobertura_total,
            diferencial_total=p.diferencial_total, total_paciente=p.total_paciente, notas=p.notas,
            presentado_en=p.presentado_en, resuelto_en=p.resuelto_en, anulado_en=p.anulado_en,
            anulado_motivo=p.anulado_motivo, created_at=p.created_at, lineas=lineas_por[int(p.id)])
        if not completo:
            salida.append(PresupuestoVistaClinicaOut(**comunes))
            continue
        pagos = pagos_por[int(p.id)]
        pagado = sum((x.monto for x in pagos if x.estado == "registrado"), CERO)
        salida.append(PresupuestoOut(**comunes, pagos=[pago_out(x) for x in pagos], total_pagado=pagado,
                                     saldo=p.total_paciente - pagado))
    return salida


def pago_out(x: PagoPresupuesto) -> PagoOut:
    return PagoOut(id=int(x.id), presupuesto_id=x.presupuesto_id, medio=x.medio, monto=x.monto, estado=x.estado,
                   fecha_cobro=x.fecha_cobro, referencia=x.referencia, registrado_por=x.registrado_por,
                   anulado_en=x.anulado_en, anulado_motivo=x.anulado_motivo)


async def detalle_completo(session: AsyncSession, presupuesto_id: int) -> PresupuestoOut:
    p = (await session.execute(select(Presupuesto).where(Presupuesto.id == presupuesto_id)
                               .execution_options(populate_existing=True))).scalar_one()
    [salida] = await _armar(session, [p], completo=True)
    assert isinstance(salida, PresupuestoOut)
    return salida


async def _exigir_paciente(session: AsyncSession, paciente_id: int) -> Paciente:
    paciente = await session.get(Paciente, paciente_id)
    if paciente is None:
        raise PacienteInexistenteError()
    return paciente


async def listar_presupuestos(session: AsyncSession, contexto: PermissionContext, paciente_id: int,
                              ahora: datetime) -> list[PresupuestoOut | PresupuestoVistaClinicaOut]:
    alcance = await alcance_paciente(session, contexto, paciente_id, ahora)
    filas = (await session.execute(select(Presupuesto).where(Presupuesto.paciente_id == paciente_id)
                                   .order_by(Presupuesto.created_at.desc(), Presupuesto.id.desc()))).scalars().all()
    salida = await _armar(session, filas, completo=alcance.ve_pagos)
    auditar(session, contexto.usuario_id, "lectura_presupuesto", "presupuesto", paciente_id,
            {"cantidad": len(salida)})
    await session.commit()
    return salida


async def obtener_presupuesto(session: AsyncSession, contexto: PermissionContext, paciente_id: int,
                              presupuesto_id: int, ahora: datetime) -> PresupuestoOut | PresupuestoVistaClinicaOut:
    alcance = await alcance_paciente(session, contexto, paciente_id, ahora)
    p = (await session.execute(select(Presupuesto).where(
        Presupuesto.id == presupuesto_id, Presupuesto.paciente_id == paciente_id))).scalar_one_or_none()
    if p is None:
        raise PresupuestoInexistenteError()
    [salida] = await _armar(session, [p], completo=alcance.ve_pagos)
    auditar(session, contexto.usuario_id, "lectura_presupuesto", "presupuesto", paciente_id,
            {"presupuesto_id": presupuesto_id})
    await session.commit()
    return salida


# ---------------------------------------------------------------------------
# Escritura (solo recepción y admin: el router corta antes por rol)
# ---------------------------------------------------------------------------

async def crear_presupuesto(session: AsyncSession, usuario_id: int, paciente_id: int,
                            data: PresupuestoCreate) -> PresupuestoOut:
    paciente = await _exigir_paciente(session, paciente_id)
    obra_social_id = await _obra_social_efectiva(session, paciente, data)
    p = Presupuesto(paciente_id=paciente_id, obra_social_id=obra_social_id, notas=data.notas, creado_por=usuario_id)
    session.add(p)
    await session.flush()
    await _reemplazar_lineas(session, p, data.lineas)
    auditar(session, usuario_id, "alta_presupuesto", "presupuesto", p.id,
            {"paciente_id": paciente_id, "lineas": len(data.lineas)})
    await session.commit()
    return await detalle_completo(session, int(p.id))


async def _bloquear(session: AsyncSession, paciente_id: int, presupuesto_id: int) -> Presupuesto:
    """``SELECT … FOR UPDATE`` del presupuesto del paciente: serializa ediciones, transiciones y cobros."""
    await _exigir_paciente(session, paciente_id)
    p = (await session.execute(
        select(Presupuesto).where(Presupuesto.id == presupuesto_id, Presupuesto.paciente_id == paciente_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if p is None:
        raise PresupuestoInexistenteError()
    return p


async def editar_presupuesto(session: AsyncSession, usuario_id: int, paciente_id: int, presupuesto_id: int,
                             data: PresupuestoCreate) -> PresupuestoOut:
    p = await _bloquear(session, paciente_id, presupuesto_id)
    if p.estado != "borrador":
        raise PresupuestoNoEditableError(p.estado)
    paciente = await _exigir_paciente(session, paciente_id)
    p.obra_social_id = await _obra_social_efectiva(session, paciente, data) if (
        "obra_social_id" in data.model_fields_set) else p.obra_social_id
    p.notas = data.notas
    await _reemplazar_lineas(session, p, data.lineas)
    auditar(session, usuario_id, "edicion_presupuesto", "presupuesto", p.id,
            {"paciente_id": paciente_id, "lineas": len(data.lineas)})
    await session.commit()
    return await detalle_completo(session, presupuesto_id)


async def transicionar_presupuesto(session: AsyncSession, usuario_id: int, paciente_id: int, presupuesto_id: int,
                                   destino: str, ahora: datetime, motivo: str | None = None) -> PresupuestoOut:
    """presentar / aceptar / rechazar / anular. Raises: ``TransicionInvalidaError``, ``PresupuestoConPagosError``."""
    p = await _bloquear(session, paciente_id, presupuesto_id)
    anterior = p.estado
    validar_transicion(anterior, destino)
    if destino == "presentado":  # último recálculo con los valores vigentes; desde acá queda congelado
        existentes = (await session.execute(select(PresupuestoLinea).where(PresupuestoLinea.presupuesto_id == p.id)
                                            .order_by(PresupuestoLinea.orden))).scalars().all()
        await _reemplazar_lineas(session, p, [LineaIn(tratamiento_id=l.tratamiento_id, cantidad=l.cantidad,
                                                      pieza=l.pieza, cara=l.cara) for l in existentes])
        p.presentado_en = ahora
    elif destino in ("aceptado", "rechazado"):
        p.resuelto_en = ahora
    elif destino == "anulado":
        if anterior == "aceptado" and (await session.execute(
                select(func.count()).select_from(PagoPresupuesto).where(
                    PagoPresupuesto.presupuesto_id == p.id, PagoPresupuesto.estado == "registrado"))).scalar_one():
            raise PresupuestoConPagosError()
        p.anulado_en, p.anulado_motivo = ahora, motivo
    p.estado = destino
    auditar(session, usuario_id, "transicion_presupuesto", "presupuesto", p.id,
            {"paciente_id": paciente_id, "estado_anterior": anterior, "estado_nuevo": destino})
    await session.commit()
    return await detalle_completo(session, presupuesto_id)
