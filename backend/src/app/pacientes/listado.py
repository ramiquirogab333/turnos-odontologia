"""Listado de pacientes con búsqueda libre y ausentismo por paciente (C-12, D8; O13).

``q`` busca sin distinguir mayúsculas ni acentos (``unaccent``) en ``nombre apellido``, en ``apellido nombre`` y, si son
solo dígitos, en el comienzo del DNI. Los comodines de ``q`` se escapan. Los contadores salen de UNA subconsulta
agregada por ``paciente_id`` unida con ``LEFT JOIN``: la página y el total son las dos únicas consultas (sin N+1).
Sin índice de texto (una clínica tiene miles de pacientes, SU-02); si creciera, ``pg_trgm``. El texto buscado no se
audita ni se loguea: la auditoría de la lectura (C-13, D8) guarda solo la página, los filtros booleanos y la cantidad.
"""

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import ObraSocial, Paciente
from app.pacientes.schemas_listado import ListadoOut, ListadoQuery, PacienteListadoOut
from app.panel.schemas import Ref
from app.plataforma.auditoria import registrar
from app.panel.service import zona_clinica
from app.turnos.models import Turno

ESTADOS_CON_FECHA = ("reservado", "confirmado", "atendido", "ausente")
ESCAPE = "\\"


def _escapar(texto: str) -> str:
    return texto.replace(ESCAPE, ESCAPE * 2).replace("%", ESCAPE + "%").replace("_", ESCAPE + "_")


def _condicion_q(q: str) -> ColumnElement[bool]:
    patron = func.unaccent(func.lower("%" + _escapar(q) + "%"))
    nombre_apellido = func.unaccent(func.lower(Paciente.nombre + " " + Paciente.apellido))
    apellido_nombre = func.unaccent(func.lower(Paciente.apellido + " " + Paciente.nombre))
    condiciones = [nombre_apellido.like(patron, escape=ESCAPE), apellido_nombre.like(patron, escape=ESCAPE)]
    if q.isdigit():
        condiciones.append(Paciente.dni.like(_escapar(q) + "%", escape=ESCAPE))
    return or_(*condiciones)


async def listar_pacientes(session: AsyncSession, query: ListadoQuery, usuario_id: int) -> ListadoOut:
    """Página de pacientes con su total y, por persona, atendidos, ausentes y fecha de su último turno vinculado.

    Un turno sin paciente vinculado no cuenta para nadie; ``en_espera`` y ``cancelado`` tampoco.
    """
    contadores = (
        select(Turno.paciente_id.label("paciente_id"),
               func.count().filter(Turno.estado == "atendido").label("atendidos"),
               func.count().filter(Turno.estado == "ausente").label("ausentes"),
               func.max(Turno.inicio).label("ultimo"))
        .where(Turno.paciente_id.is_not(None), Turno.estado.in_(ESTADOS_CON_FECHA))
        .group_by(Turno.paciente_id).subquery())
    atendidos = func.coalesce(contadores.c.atendidos, 0)
    ausentes = func.coalesce(contadores.c.ausentes, 0)

    filtros: list[ColumnElement[bool]] = []
    if query.q is not None:
        filtros.append(_condicion_q(query.q))
    if query.con_ausencias:
        filtros.append(ausentes > 0)

    total = (await session.execute(
        select(func.count()).select_from(Paciente)
        .outerjoin(contadores, contadores.c.paciente_id == Paciente.id).where(and_(True, *filtros)))).scalar_one()
    orden = ([ausentes.desc()] if query.orden == "ausencias" else []) + [Paciente.apellido, Paciente.nombre, Paciente.id]
    filas = (await session.execute(
        select(Paciente, ObraSocial.nombre, atendidos, ausentes, contadores.c.ultimo)
        .outerjoin(ObraSocial, ObraSocial.id == Paciente.obra_social_id)
        .outerjoin(contadores, contadores.c.paciente_id == Paciente.id)
        .where(and_(True, *filtros)).order_by(*orden)
        .limit(query.por_pagina).offset((query.pagina - 1) * query.por_pagina))).all()
    zona = zona_clinica()
    # C-13 (D8): sin rastro no hay datos; el texto de ``q`` nunca entra (la guarda de ``registrar`` lo bloquea).
    registrar(session, accion="lectura_listado_pacientes", entidad="paciente", entidad_id=None, usuario_id=usuario_id,
              despues={"pagina": query.pagina, "por_pagina": query.por_pagina, "orden": query.orden,
                       "con_ausencias": query.con_ausencias, "con_busqueda": query.q is not None,
                       "devueltos": len(filas)})
    await session.commit()
    return ListadoOut(
        total=total, pagina=query.pagina, por_pagina=query.por_pagina,
        pacientes=[PacienteListadoOut(
            id=p.id, nombre=p.nombre, apellido=p.apellido, dni=p.dni, telefono=p.telefono,
            obra_social=None if p.obra_social_id is None else Ref(id=p.obra_social_id, nombre=os_nombre),
            atendidos=a, ausentes=b, ultimo_turno=None if ultimo is None else ultimo.astimezone(zona))
            for p, os_nombre, a, b, ultimo in filas])
