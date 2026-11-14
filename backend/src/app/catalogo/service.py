"""Servicios CRUD del catálogo sobre BaseRepository + UnitOfWork (R13, R16).

Cada servicio hereda de ``BaseRepository[T]`` y opera sobre una sesión
asíncrona inyectada (el router es quien confirma la transacción, por lo que
datos de escritura y su fila de ``RegistroAuditoria`` comparten la misma
transacción atómica — RN-GL-01).

C-14: baja lógica (``activo``), borrado con 409 ``en_uso``, unicidad de nombres y matrículas, franjas activas sin
superposición y edición de franjas validada contra lo guardado. Las reglas se pre-chequean para devolver un mensaje
útil y la base de datos es la garantía final (EXCLUDE y índices únicos de la migración 014): los errores de integridad
que igual lleguen se traducen con ``_traducir`` (nunca un 500).

Todas las firmas están 100% tipadas y el I/O es asíncrono (no se bloquea el event loop).
"""

import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, ClassVar, Literal, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import Time, cast, exists, extract, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogo.schemas import ImpactoRead
from app.catalogo.errores import CatalogoEnUsoError, DatoInvalidoError, DuplicadoError, FranjaSuperpuestaError
from app.models.base import Base
from app.plataforma.auditoria import AUTO, registrar
from app.repositories.base import BaseRepository
from app.shared.settings import get_settings
from app.shared.exceptions import ReferenceNotFoundError

ModelType = TypeVar("ModelType", bound=Base)

# Columnas que identifican a una persona (el personal): nunca van a la auditoría; solo su nombre de campo (C-13, D2).
COLUMNAS_DE_IDENTIDAD: frozenset[str] = frozenset({"nombre", "matricula"})

SQLSTATE_UNICO = "23505"
SQLSTATE_FK = "23503"
SQLSTATE_NO_NULO = "23502"
SQLSTATE_CHECK = "23514"
SQLSTATE_EXCLUSION = "23P01"
SQLSTATE_DEADLOCK = "40P01"

# Índice único / FK -> campo de la API.
_CAMPO_DE_INDICE = {"ux_tratamiento_nombre": "nombre", "ux_sillon_nombre": "nombre", "ux_profesional_matricula": "matricula"}


def _jsonable(value: Any) -> Any:
    """Convierte un valor a tipo serializable en JSONB (JSONB no admite
    datetime/date/time/Decimal nativos de asyncpg)."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _jsonable_dict(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {k: _jsonable(v) for k, v in data.items()}


def _sqlstate(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "sqlstate", "") or "")


def _nombre_de_restriccion(exc: DBAPIError) -> str:
    """Nombre de la restricción violada: del error original de asyncpg o, si no, del texto del mensaje."""
    causa = getattr(exc.orig, "__cause__", None)
    nombre = getattr(causa, "constraint_name", None) or getattr(exc.orig, "constraint_name", None)
    if nombre:
        return str(nombre)
    encontrado = re.search(r'constraint "([^"]+)"', str(exc.orig))
    return encontrado.group(1) if encontrado else ""


def _columna_de_error(exc: DBAPIError) -> str | None:
    encontrado = re.search(r'column "([^"]+)"', str(exc.orig))
    return encontrado.group(1) if encontrado else None


class BaseCatalogoService(BaseRepository[ModelType]):
    """Servicio base CRUD con auditoría atómica en la misma sesión."""

    entidad: str
    #: Campos únicos sin distinguir mayúsculas ni espacios en los extremos (índices ``ux_*`` de la migración 014).
    unicos: ClassVar[tuple[str, ...]] = ()

    def __init__(self, model: type[ModelType], session: AsyncSession, entidad: str) -> None:
        super().__init__(model, session)
        self.entidad = entidad

    # -- ganchos para los servicios concretos ----------------------------------------------------------------------

    async def _validar(self, entity: ModelType | None, valores: dict[str, Any]) -> None:
        """Pre-chequeos de negocio antes de escribir; ``valores`` ya usa nombres de columna."""
        for campo in self.unicos:
            if campo in valores and valores[campo] is not None:
                await self._verificar_unico(campo, str(valores[campo]), None if entity is None else int(entity.id))  # type: ignore[attr-defined]

    async def _en_uso(self, entity: ModelType) -> bool:
        """``True`` si algo depende del ítem y borrarlo dejaría sin historia a otros registros."""
        return False

    # -- utilidades -------------------------------------------------------------------------------------------------

    @staticmethod
    def _columnas(valores: dict[str, Any]) -> dict[str, Any]:
        """La API habla de ``activo``; el modelo, de ``is_active``."""
        return {("is_active" if k == "activo" else k): v for k, v in valores.items()}

    def _datos(self, entity: ModelType) -> dict[str, Any]:
        """Valores auditables de la fila: sin identidad del personal (``nombre``, ``matricula``; D2, R19)."""
        return {c.name: getattr(entity, c.name) for c in entity.__table__.columns
                if c.name not in COLUMNAS_DE_IDENTIDAD}

    async def _verificar_unico(self, campo: str, valor: str, excluir_id: int | None) -> None:
        columna = getattr(self.model, campo)
        consulta = select(self.model.id).where(  # type: ignore[attr-defined]
            func.lower(func.btrim(columna)) == func.lower(func.btrim(valor)))
        if excluir_id is not None:
            consulta = consulta.where(self.model.id != excluir_id)  # type: ignore[attr-defined]
        if (await self.session.execute(consulta.limit(1))).first() is not None:
            raise DuplicadoError(campo)

    async def _audit(
        self,
        accion: str,
        entidad_id: str | None,
        antes: dict[str, Any] | None,
        despues: dict[str, Any] | None,
        usuario_id: int | None,
        ip: str | None,
    ) -> None:
        registrar(self.session, accion=accion, entidad=self.entidad, entidad_id=entidad_id, usuario_id=usuario_id,
                  antes=_jsonable_dict(antes), despues=_jsonable_dict(despues), ip=ip if ip is not None else AUTO)

    async def _traducir(self, exc: DBAPIError, valores: dict[str, Any] | None, id_: int | None,
                        borrando: bool = False) -> Exception:
        """Error de integridad que se coló pese a los pre-chequeos (carrera o dato inesperado) → error de negocio."""
        estado = _sqlstate(exc)
        restriccion = _nombre_de_restriccion(exc)
        if estado == SQLSTATE_FK:
            if borrando:
                return CatalogoEnUsoError()
            campo = re.sub(r"^.*?_(\w+_id)_fkey$", r"\1", restriccion) if restriccion.endswith("_fkey") else None
            return ReferenceNotFoundError(campo=campo or "referencia")
        if estado == SQLSTATE_UNICO:
            return DuplicadoError(_CAMPO_DE_INDICE.get(restriccion))
        if estado == SQLSTATE_EXCLUSION:
            return FranjaSuperpuestaError(await self._franja_en_choque(valores, id_))
        if estado == SQLSTATE_DEADLOCK and valores is not None and "hora_inicio" in valores:
            # Dos altas de franjas superpuestas a la vez pueden cruzarse en el EXCLUDE: Postgres aborta una y es un choque.
            return FranjaSuperpuestaError(await self._franja_en_choque(valores, id_))
        if estado in (SQLSTATE_NO_NULO, SQLSTATE_CHECK):
            campo = _columna_de_error(exc)
            return DatoInvalidoError(campo, f"{campo or 'El dato'} no es válido")
        return exc

    async def _franja_en_choque(self, valores: dict[str, Any] | None, id_: int | None) -> dict[str, Any] | None:
        return None

    async def _persistir(self, valores: dict[str, Any] | None, id_: int | None, borrando: bool = False) -> None:
        try:
            await self.session.flush()
        except (IntegrityError, DBAPIError) as exc:
            await self.session.rollback()
            traducido = await self._traducir(exc, valores, id_, borrando)
            if traducido is exc:
                raise
            raise traducido from exc

    # -- CRUD -------------------------------------------------------------------------------------------------------

    async def create(
        self,
        data: Any,
        usuario_id: int | None = None,
        ip: str | None = None,
    ) -> ModelType:
        valores = self._columnas(data.model_dump())
        await self._validar(None, valores)
        entity = self.model(**valores)
        await self.add(entity)
        await self._persistir(valores, None)
        # Refresh para poblar campos generados por la BD (ej. ID con Identity)
        await self.session.refresh(entity)
        await self._audit(
            "CREATE",
            str(entity.id),
            None,
            {**(_jsonable_dict(self._datos(entity)) or {}), "campos": sorted(valores)},
            usuario_id,
            ip,
        )
        await self.session.commit()
        return entity

    async def update(
        self,
        id_: int,
        data: Any,
        usuario_id: int | None = None,
        ip: str | None = None,
    ) -> ModelType | None:
        entity = await self.get_by_id(id_)
        if entity is None:
            return None
        antes = _jsonable_dict(self._datos(entity))
        cambios = self._columnas(data.model_dump(exclude_unset=True))
        await self._validar(entity, cambios)
        for field, value in cambios.items():
            setattr(entity, field, value)
        await self._persistir(cambios, id_)
        await self.session.refresh(entity)  # columnas que la base recalcula (``updated_at``) tras el UPDATE
        despues = {**(_jsonable_dict(self._datos(entity)) or {}), "campos": sorted(cambios)}
        await self._audit(
            "UPDATE",
            str(entity.id),
            antes,
            despues,
            usuario_id,
            ip,
        )
        await self.session.commit()
        return entity

    async def delete(
        self,
        id_: int,
        usuario_id: int | None = None,
        ip: str | None = None,
    ) -> bool:
        entity = await self.get_by_id(id_)
        if entity is None:
            return False
        if await self._en_uso(entity):
            raise CatalogoEnUsoError()
        antes = _jsonable_dict(self._datos(entity))
        await self.session.delete(entity)
        await self._persistir(None, id_, borrando=True)
        await self._audit(
            "DELETE",
            str(entity.id),
            antes,
            None,
            usuario_id,
            ip,
        )
        await self.session.commit()
        return True


# ---------------------------------------------------------------------------
# Servicios concretos
# ---------------------------------------------------------------------------

from app.clinica.models import PresupuestoLinea  # noqa: E402
from app.integraciones.gcal.models import GcalConexion  # noqa: E402
from app.models.core import Disponibilidad  # noqa: E402
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno  # noqa: E402


class TratamientoService(BaseCatalogoService[Tratamiento]):
    unicos = ("nombre",)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Tratamiento, session, "tratamiento")

    async def _en_uso(self, entity: Tratamiento) -> bool:
        turnos = exists().where(Turno.tratamiento_id == entity.id)
        lineas = exists().where(PresupuestoLinea.tratamiento_id == entity.id)
        return bool((await self.session.execute(select(turnos | lineas))).scalar_one())


class ProfesionalService(BaseCatalogoService[Profesional]):
    unicos = ("matricula",)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Profesional, session, "profesional")

    async def _en_uso(self, entity: Profesional) -> bool:
        turnos = exists().where(Turno.profesional_id == entity.id)
        conexion = exists().where(GcalConexion.profesional_id == entity.id)
        return bool((await self.session.execute(select(turnos | conexion))).scalar_one())


class SillonService(BaseCatalogoService[Sillon]):
    unicos = ("nombre",)

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Sillon, session, "sillon")

    async def _en_uso(self, entity: Sillon) -> bool:
        return bool((await self.session.execute(select(exists().where(Turno.sillon_id == entity.id)))).scalar_one())


class DisponibilidadService(BaseCatalogoService[Disponibilidad]):
    _intento: dict[str, Any] | None = None

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Disponibilidad, session, "disponibilidad")

    async def _validar(self, entity: Disponibilidad | None, valores: dict[str, Any]) -> None:
        """Valida lo enviado combinado con lo guardado (D4): referencias, orden de las horas y superposición."""
        if "profesional_id" in valores and await self.session.get(Profesional, valores["profesional_id"]) is None:
            raise ReferenceNotFoundError(campo="profesional_id")
        sillon = valores.get("sillon_defecto_id")
        if sillon is not None and await self.session.get(Sillon, sillon) is None:
            raise ReferenceNotFoundError(campo="sillon_defecto_id")
        resultante = self._resultante(entity, valores)
        self._intento = resultante  # para localizar la franja que choca si la base rechaza igual (carrera)
        if resultante["hora_fin"] <= resultante["hora_inicio"]:
            campo = "hora_fin" if "hora_fin" in valores or "hora_inicio" not in valores else "hora_inicio"
            raise DatoInvalidoError(campo, "hora_fin debe ser mayor que hora_inicio")
        if resultante["is_active"]:
            choque = await self._franja_en_choque(resultante, None if entity is None else int(entity.id))
            if choque is not None:
                raise FranjaSuperpuestaError(choque)

    @staticmethod
    def _resultante(entity: Disponibilidad | None, valores: dict[str, Any]) -> dict[str, Any]:
        base: dict[str, Any] = {"is_active": True}
        if entity is not None:
            base = {c: getattr(entity, c) for c in
                    ("profesional_id", "dia_semana", "hora_inicio", "hora_fin", "sillon_defecto_id", "is_active")}
        return {**base, **valores}

    async def _franja_en_choque(self, valores: dict[str, Any] | None, id_: int | None) -> dict[str, Any] | None:
        """La primera franja activa del mismo profesional y día que se superpone (rango semiabierto), o ``None``."""
        valores = self._intento if self._intento is not None else valores
        if valores is None or not {"profesional_id", "dia_semana", "hora_inicio", "hora_fin"} <= valores.keys():
            return None
        consulta = select(Disponibilidad).where(
            Disponibilidad.profesional_id == valores["profesional_id"],
            Disponibilidad.dia_semana == valores["dia_semana"],
            Disponibilidad.is_active.is_(True),
            Disponibilidad.hora_inicio < valores["hora_fin"],
            Disponibilidad.hora_fin > valores["hora_inicio"],
        ).order_by(Disponibilidad.id).limit(1)
        if id_ is not None:
            consulta = consulta.where(Disponibilidad.id != id_)
        otra = (await self.session.execute(consulta)).scalar_one_or_none()
        if otra is None:
            return None
        return {"id": int(otra.id), "dia_semana": otra.dia_semana, "hora_inicio": otra.hora_inicio.isoformat(),
                "hora_fin": otra.hora_fin.isoformat()}


# ---------------------------------------------------------------------------
# Impacto de un cambio: turnos futuros vigentes que usan el ítem (D2, O2)
# ---------------------------------------------------------------------------

RecursoImpacto = Literal["tratamientos", "profesionales", "sillones", "disponibilidad"]
ESTADOS_VIGENTES: tuple[str, ...] = ("en_espera", "reservado", "confirmado")


async def calcular_impacto(session: AsyncSession, recurso: RecursoImpacto, id_: int, ahora: datetime) -> ImpactoRead | None:
    """Cuenta los turnos futuros vigentes del ítem y la fecha del primero; ``None`` si el ítem no existe.

    Para una franja cuenta los turnos del mismo profesional cuyo inicio, en la hora de la clínica, cae ese día de la
    semana dentro de ``[hora_inicio, hora_fin)``. Sin datos de pacientes y sin escribir nada (R14: ORM, sin SQL crudo).
    """
    condiciones: list[Any] = [Turno.inicio > ahora, Turno.estado.in_(ESTADOS_VIGENTES)]
    if recurso == "disponibilidad":
        franja = await session.get(Disponibilidad, id_)
        if franja is None:
            return None
        zona = get_settings().app_tz
        local = func.timezone(zona, Turno.inicio)
        condiciones += [
            Turno.profesional_id == franja.profesional_id,
            extract("isodow", local) == franja.dia_semana + 1,
            cast(local, Time) >= franja.hora_inicio,
            cast(local, Time) < franja.hora_fin,
        ]
    else:
        modelo, columna = {
            "tratamientos": (Tratamiento, Turno.tratamiento_id),
            "profesionales": (Profesional, Turno.profesional_id),
            "sillones": (Sillon, Turno.sillon_id),
        }[recurso]
        if await session.get(modelo, id_) is None:
            return None
        condiciones.append(columna == id_)
    cantidad, primero = (await session.execute(select(func.count(Turno.id), func.min(Turno.inicio)).where(*condiciones))).one()
    zona_clinica = ZoneInfo(get_settings().app_tz)
    return ImpactoRead(turnos_futuros=int(cantidad), primero=None if primero is None else primero.astimezone(zona_clinica))
