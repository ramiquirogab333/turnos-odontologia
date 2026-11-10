"""Servicio del odontograma: registro en lote solo de alta, estado vigente e historial (C-11, D5; O4, O7, O16)."""

from datetime import datetime

from sqlalchemy import insert, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import PermissionContext
from app.clinica.models import OdontogramaRegistro
from app.clinica.odontograma import RegistroOdonto, vigente
from app.clinica.schemas import (
    HistorialOdontogramaOut,
    HistorialQuery,
    LoteOdontogramaIn,
    LoteOdontogramaOut,
    OdontogramaVigenteOut,
    PiezaVigenteOut,
    RegistroOdontogramaOut,
)
from app.pacientes.alcance import alcance_paciente
from app.pacientes.auditoria import auditar
from app.pacientes.ficha_service import exigir_escritura_clinica


def _out(r: OdontogramaRegistro) -> RegistroOdontogramaOut:
    return RegistroOdontogramaOut(id=int(r.id), pieza=r.pieza, cara=r.cara, estado=r.estado, nota=r.nota,
                                  registrado_por=r.registrado_por, registrado_en=r.registrado_en)


async def registrar_lote(session: AsyncSession, contexto: PermissionContext, paciente_id: int, lote: LoteOdontogramaIn,
                         ahora: datetime) -> LoteOdontogramaOut:
    """Un solo ``INSERT`` del lote (todo o nada). Raises: ``PacienteInexistenteError``, ``PacienteAjenoError``,
    ``AccesoClinicoVencidoError``."""
    exigir_escritura_clinica(await alcance_paciente(session, contexto, paciente_id, ahora))
    filas = [{"paciente_id": paciente_id, "pieza": r.pieza, "cara": r.cara, "estado": r.estado, "nota": r.nota,
              "registrado_por": contexto.usuario_id} for r in lote.registros]
    creados = (await session.execute(
        insert(OdontogramaRegistro).values(filas).returning(OdontogramaRegistro))).scalars().all()
    auditar(session, contexto.usuario_id, "registro_odontograma", "odontograma", paciente_id,
            {"cantidad": len(filas)})
    salida = LoteOdontogramaOut(registros=[_out(r) for r in sorted(creados, key=lambda r: r.id)])
    await session.commit()
    return salida


async def estado_vigente(session: AsyncSession, contexto: PermissionContext, paciente_id: int,
                         ahora: datetime) -> OdontogramaVigenteOut:
    await alcance_paciente(session, contexto, paciente_id, ahora)
    filas = (await session.execute(
        select(OdontogramaRegistro).where(OdontogramaRegistro.paciente_id == paciente_id))).scalars().all()
    por_pieza = vigente(RegistroOdonto(int(r.id), r.pieza, r.cara, r.estado, r.registrado_en) for r in filas)
    salida = OdontogramaVigenteOut(paciente_id=paciente_id, piezas=[
        PiezaVigenteOut(pieza=p, estado_pieza=v.estado_pieza, caras=v.caras) for p, v in sorted(por_pieza.items())])
    auditar(session, contexto.usuario_id, "lectura_odontograma", "odontograma", paciente_id)
    await session.commit()
    return salida


async def historial(session: AsyncSession, contexto: PermissionContext, paciente_id: int, query: HistorialQuery,
                    ahora: datetime) -> HistorialOdontogramaOut:
    """Del más reciente al más antiguo; el cursor ``antes_de_id`` trae lo anterior a ese registro."""
    await alcance_paciente(session, contexto, paciente_id, ahora)
    consulta = (select(OdontogramaRegistro).where(OdontogramaRegistro.paciente_id == paciente_id)
                .order_by(OdontogramaRegistro.registrado_en.desc(), OdontogramaRegistro.id.desc())
                .limit(query.limite + 1))
    if query.antes_de_id is not None:
        cursor = (await session.execute(select(OdontogramaRegistro.registrado_en).where(
            OdontogramaRegistro.id == query.antes_de_id, OdontogramaRegistro.paciente_id == paciente_id)
        )).scalar_one_or_none()
        if cursor is not None:
            consulta = consulta.where(tuple_(OdontogramaRegistro.registrado_en, OdontogramaRegistro.id)
                                      < tuple_(cursor, query.antes_de_id))
    filas = list((await session.execute(consulta)).scalars().all())
    pagina, hay_mas = filas[:query.limite], len(filas) > query.limite
    salida = HistorialOdontogramaOut(registros=[_out(r) for r in pagina],
                                     siguiente_antes_de_id=int(pagina[-1].id) if hay_mas else None)
    auditar(session, contexto.usuario_id, "lectura_odontograma", "odontograma", paciente_id)
    await session.commit()
    return salida
