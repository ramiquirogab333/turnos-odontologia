"""Pydantic schemas de entrada/salida para auth (R15)."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginIn(BaseModel):
    """Credenciales de login del panel."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=6, max_length=128)


class LoginOut(BaseModel):
    """Respuesta de login: solo el access. El refresh viaja en una cookie HttpOnly (C-08, D10), nunca en el JSON."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"


class RefreshOut(BaseModel):
    """Respuesta de refresh: access nuevo; el refresh rotado reemplaza la cookie HttpOnly."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"


class LogoutOut(BaseModel):
    """Respuesta de logout."""

    model_config = ConfigDict(extra="forbid")

    detalle: str = "sesión revocada"


class MeOut(BaseModel):
    """Usuario autenticado con sus roles."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    email: str
    nombre_completo: str
    roles: list[str] = []


class TokenData(BaseModel):
    """Claims decodificados de un JWT (interno, no se expone al cliente)."""

    sub: int
    email: str
    roles: list[str]
    jti: str
    type: str
