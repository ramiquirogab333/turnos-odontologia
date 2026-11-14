"""Esquemas Pydantic de entrada/salida para el catálogo (R15).

Cada entidad expone tres esquemas:
- ``Create``: sin ``id``, ``extra="forbid"`` (rechaza campos inesperados con 422).
- ``Read``: con ``id`` y ``from_attributes=True`` (para serializar modelos ORM).
- ``Update``: campos opcionales, ``extra="forbid"``.

Tipos: ``int``, ``str``, ``Decimal`` para dinero y ``time`` para horas (R4).
Las longitudes y CHECKs del dominio se replican como validadores de borde. C-14 suma ``activo`` (baja lógica; en el
modelo es ``is_active``), los topes de duración y precio (O12) y el recorte de espacios en los textos.
"""

from datetime import datetime, time
from decimal import Decimal
from typing import Final

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_serializer, field_validator

# Topes aprobados en C-14 (O12). El rango de duración es un [SUPUESTO] a confirmar con la clínica: cambiarlo es tocar
# estas constantes y su test. El máximo del precio es el de la columna ``NUMERIC(10,2)``.
DURACION_MIN: Final[int] = 5
DURACION_MAX: Final[int] = 480
DURACION_PASO: Final[int] = 5
PRECIO_MAX: Final[Decimal] = Decimal("99999999.99")

_CON_RECORTE = ConfigDict(extra="forbid", str_strip_whitespace=True)
_ALIAS_ACTIVO = AliasChoices("is_active", "activo")


def _validar_longitud(valor: str, minimo: int, maximo: int, campo: str) -> str:
    if not (minimo <= len(valor) <= maximo):
        raise ValueError(f"{campo} debe tener entre {minimo} y {maximo} caracteres")
    return valor


def _validar_estado(valor: str, permitidos: tuple[str, ...], campo: str) -> str:
    if valor not in permitidos:
        raise ValueError(f"{campo} debe ser uno de {permitidos}")
    return valor


def _validar_duracion(valor: int) -> int:
    if not (DURACION_MIN <= valor <= DURACION_MAX):
        raise ValueError(f"duracion_minutos debe estar entre {DURACION_MIN} y {DURACION_MAX} minutos")
    if valor % DURACION_PASO != 0:
        raise ValueError(f"duracion_minutos debe ser múltiplo de {DURACION_PASO}")
    return valor


def _validar_precio(valor: Decimal) -> Decimal:
    if not valor.is_finite():
        raise ValueError("precio_base debe ser un importe válido")
    if valor < 0:
        raise ValueError("precio_base debe ser >= 0")
    if valor > PRECIO_MAX:
        raise ValueError(f"precio_base no puede superar {PRECIO_MAX}")
    if int(valor.as_tuple().exponent) < -2:
        raise ValueError("precio_base admite hasta dos decimales")
    return valor


# ---------------------------------------------------------------------------
# Tratamiento
# ---------------------------------------------------------------------------

class TratamientoCreate(BaseModel):
    model_config = _CON_RECORTE

    nombre: str
    duracion_minutos: int
    precio_base: Decimal
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return _validar_longitud(v, 1, 120, "nombre")

    @field_validator("duracion_minutos")
    @classmethod
    def _duracion(cls, v: int) -> int:
        return _validar_duracion(v)

    @field_validator("precio_base")
    @classmethod
    def _precio(cls, v: Decimal) -> Decimal:
        return _validar_precio(v)


class TratamientoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    duracion_minutos: int
    precio_base: Decimal
    activo: bool = Field(validation_alias=_ALIAS_ACTIVO)

    @field_serializer("precio_base")
    def _serializar_precio(self, v: Decimal) -> str:
        return str(v)


class TratamientoUpdate(BaseModel):
    model_config = _CON_RECORTE

    nombre: str | None = None
    duracion_minutos: int | None = None
    precio_base: Decimal | None = None
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validar_longitud(v, 1, 120, "nombre")

    @field_validator("duracion_minutos")
    @classmethod
    def _duracion(cls, v: int | None) -> int | None:
        return None if v is None else _validar_duracion(v)

    @field_validator("precio_base")
    @classmethod
    def _precio(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None else _validar_precio(v)


# ---------------------------------------------------------------------------
# Profesional
# ---------------------------------------------------------------------------

class ProfesionalCreate(BaseModel):
    model_config = _CON_RECORTE

    nombre: str
    matricula: str
    especialidad: str = ""
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return _validar_longitud(v, 1, 120, "nombre")

    @field_validator("matricula")
    @classmethod
    def _matricula(cls, v: str) -> str:
        return _validar_longitud(v, 1, 40, "matricula")

    @field_validator("especialidad")
    @classmethod
    def _especialidad(cls, v: str) -> str:
        return _validar_longitud(v, 0, 120, "especialidad")


class ProfesionalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    matricula: str
    especialidad: str
    activo: bool = Field(validation_alias=_ALIAS_ACTIVO)


class ProfesionalUpdate(BaseModel):
    model_config = _CON_RECORTE

    nombre: str | None = None
    matricula: str | None = None
    especialidad: str | None = None
    activo: bool | None = None

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validar_longitud(v, 1, 120, "nombre")

    @field_validator("matricula")
    @classmethod
    def _matricula(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validar_longitud(v, 1, 40, "matricula")

    @field_validator("especialidad")
    @classmethod
    def _especialidad(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validar_longitud(v, 0, 120, "especialidad")


# ---------------------------------------------------------------------------
# Sillon
# ---------------------------------------------------------------------------

_ESTADOS_SILLON = ("activo", "inactivo", "mantenimiento")


class SillonCreate(BaseModel):
    model_config = _CON_RECORTE

    nombre: str
    estado: str = "activo"

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return _validar_longitud(v, 1, 60, "nombre")

    @field_validator("estado")
    @classmethod
    def _estado(cls, v: str) -> str:
        return _validar_estado(v, _ESTADOS_SILLON, "estado")


class SillonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    estado: str


class SillonUpdate(BaseModel):
    model_config = _CON_RECORTE

    nombre: str | None = None
    estado: str | None = None

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validar_longitud(v, 1, 60, "nombre")

    @field_validator("estado")
    @classmethod
    def _estado(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validar_estado(v, _ESTADOS_SILLON, "estado")


# ---------------------------------------------------------------------------
# Disponibilidad
# ---------------------------------------------------------------------------

class DisponibilidadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profesional_id: int
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    sillon_defecto_id: int | None = None
    activo: bool = True

    @field_validator("dia_semana")
    @classmethod
    def _dia_semana(cls, v: int) -> int:
        if not (0 <= v <= 6):
            raise ValueError("dia_semana debe estar entre 0 y 6")
        return v

    @field_validator("hora_fin")
    @classmethod
    def _hora_fin(cls, v: time, info) -> time:
        hora_inicio = info.data.get("hora_inicio")
        if hora_inicio is not None and v <= hora_inicio:
            raise ValueError("hora_fin debe ser mayor que hora_inicio")
        return v


class DisponibilidadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profesional_id: int
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    sillon_defecto_id: int | None = None
    activo: bool = Field(validation_alias=_ALIAS_ACTIVO)


class DisponibilidadUpdate(BaseModel):
    """Edición parcial. La relación entre horas se valida en el servicio contra lo guardado (D4)."""

    model_config = ConfigDict(extra="forbid")

    profesional_id: int | None = None
    dia_semana: int | None = None
    hora_inicio: time | None = None
    hora_fin: time | None = None
    sillon_defecto_id: int | None = None
    activo: bool | None = None

    @field_validator("dia_semana")
    @classmethod
    def _dia_semana(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if not (0 <= v <= 6):
            raise ValueError("dia_semana debe estar entre 0 y 6")
        return v

    @field_validator("hora_fin")
    @classmethod
    def _hora_fin(cls, v: time | None, info) -> time | None:
        if v is None:
            return v
        hora_inicio = info.data.get("hora_inicio")
        if hora_inicio is not None and v <= hora_inicio:
            raise ValueError("hora_fin debe ser mayor que hora_inicio")
        return v


# ---------------------------------------------------------------------------
# Impacto de un cambio (D2)
# ---------------------------------------------------------------------------

class ImpactoRead(BaseModel):
    """Turnos futuros vigentes que alcanza un cambio. Solo conteo y fecha del primero: sin datos de pacientes."""

    turnos_futuros: int
    primero: datetime | None = None
