"""Comando para crear usuarios del panel (C-08, O4). Idempotente y sin secretos en el repo (R17).

Uso (dentro de Docker Compose, con la contraseña por entorno, nunca por argumento):

    PANEL_USUARIO_PASSWORD='...' python -m app.panel.usuarios \\
        --email recepcion@clinica.test --nombre "Rita Recepción" --rol recepcion

Desactivar y reactivar (C-15, O13), sin pedir contraseña:

    python -m app.panel.usuarios --email dra.ficticia@clinica.test --desactivar
    python -m app.panel.usuarios --email dra.ficticia@clinica.test --reactivar

Desactivar marca al usuario inactivo y revoca todas sus sesiones en la misma transacción (queda auditado). Reactivar no
revive sesiones revocadas: hay que ingresar de nuevo. El alta sobre un usuario desactivado ya NO lo reactiva (avisa).

Un ``odontologo`` exige ``--profesional-id`` (su agenda). Repetir el comando no duplica nada: actualiza el nombre, la
contraseña y la profesional, y suma el rol si faltaba. La contraseña no se imprime ni se registra en logs.
"""

import argparse
import asyncio
import os
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sesiones import MOTIVO_DESACTIVADO, revocar_de_usuario
from app.models.core import RegistroAuditoria, Rol, Usuario, UsuarioRol
from app.shared.db import get_engine, get_session_factory
from app.shared.logger import get_logger
from app.turnos.models import Profesional

logger = get_logger(__name__)

VAR_PASSWORD = "PANEL_USUARIO_PASSWORD"
ROLES = ("admin", "odontologo", "recepcion")
LARGO_MIN_PASSWORD = 12
LARGO_MAX_PASSWORD = 128  # tope de LoginIn
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UsuarioInvalidoError(Exception):
    """Los datos del usuario no son válidos; el mensaje nunca incluye la contraseña."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.panel.usuarios", add_help=True,
                                     description="Crea o actualiza un usuario del panel (la contraseña va en "
                                                 f"la variable de entorno {VAR_PASSWORD}).")
    parser.add_argument("--email", required=True)
    parser.add_argument("--nombre", default=None)
    parser.add_argument("--rol", default=None)
    parser.add_argument("--profesional-id", type=int, default=None)
    parser.add_argument("--desactivar", action="store_true", help="marca inactivo y revoca todas sus sesiones")
    parser.add_argument("--reactivar", action="store_true", help="vuelve a activar (no revive sesiones revocadas)")
    return parser


async def crear_o_actualizar_usuario(session: AsyncSession, *, email: str, nombre: str, rol: str, password: str,
                                     profesional_id: int | None) -> Usuario:
    """Valida, crea o actualiza el usuario y confirma la transacción."""
    email = email.strip().lower()
    nombre = nombre.strip()
    if not (5 <= len(email) <= 120) or not _EMAIL.match(email):
        raise UsuarioInvalidoError("email inválido (5 a 120 caracteres, con formato nombre@dominio)")
    if not 2 <= len(nombre) <= 120:
        raise UsuarioInvalidoError("nombre inválido (2 a 120 caracteres)")
    if rol not in ROLES:
        raise UsuarioInvalidoError(f"rol inexistente: {rol!r}. Los roles son {', '.join(ROLES)}")
    if not LARGO_MIN_PASSWORD <= len(password) <= LARGO_MAX_PASSWORD:
        raise UsuarioInvalidoError(
            f"contraseña inválida: debe tener entre {LARGO_MIN_PASSWORD} y {LARGO_MAX_PASSWORD} caracteres")
    if rol == "odontologo" and profesional_id is None:
        raise UsuarioInvalidoError("un odontologo necesita --profesional-id para tener agenda (profesional)")
    if profesional_id is not None and await session.get(Profesional, profesional_id) is None:
        raise UsuarioInvalidoError(f"profesional inexistente: {profesional_id}")

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    usuario = (await session.execute(select(Usuario).where(Usuario.email == email))).scalar_one_or_none()
    if usuario is None:
        usuario = Usuario(email=email, nombre_completo=nombre, hashed_password=hashed, profesional_id=profesional_id)
        session.add(usuario)
    else:
        usuario.nombre_completo = nombre
        usuario.hashed_password = hashed  # NO se reactiva: un usuario desactivado sigue inactivo (C-15, O13)
        if profesional_id is not None:
            usuario.profesional_id = profesional_id
    objeto_rol = (await session.execute(select(Rol).where(Rol.nombre == rol))).scalar_one_or_none()
    if objeto_rol is None:
        objeto_rol = Rol(nombre=rol)
        session.add(objeto_rol)
    await session.flush()
    ya_tiene = (await session.execute(select(UsuarioRol.id).where(
        UsuarioRol.usuario_id == usuario.id, UsuarioRol.rol_id == objeto_rol.id))).first()
    if ya_tiene is None:
        session.add(UsuarioRol(usuario_id=usuario.id, rol_id=objeto_rol.id))
    await session.commit()
    return usuario


async def _usuario_por_email(session: AsyncSession, email: str) -> Usuario:
    usuario = (await session.execute(select(Usuario).where(Usuario.email == email.strip().lower()))).scalar_one_or_none()
    if usuario is None:
        raise UsuarioInvalidoError(f"no existe un usuario con el email {email.strip().lower()}")
    return usuario


async def desactivar_usuario(session: AsyncSession, *, email: str, ahora: datetime) -> int:
    """Desactiva al usuario y revoca todas sus sesiones abiertas en una transacción; devuelve cuántas revocó."""
    usuario = await _usuario_por_email(session, email)
    usuario.is_active = False
    revocadas = await revocar_de_usuario(session, int(usuario.id), motivo=MOTIVO_DESACTIVADO, ahora=ahora)
    session.add(RegistroAuditoria(usuario_id=None, accion="SESIONES_REVOCADAS", entidad="usuario",
                                  entidad_id=str(usuario.id), datos_despues={"cantidad": revocadas}))
    await session.commit()
    return revocadas


async def reactivar_usuario(session: AsyncSession, *, email: str) -> None:
    """Vuelve a activar al usuario. No toca las sesiones: las revocadas siguen revocadas."""
    usuario = await _usuario_por_email(session, email)
    usuario.is_active = True
    await session.commit()


async def ejecutar(argv: Sequence[str], entorno: Mapping[str, str]) -> int:
    """Corre el comando. Devuelve 0 si salió bien y distinto de 0 si no; los errores van a stderr sin la contraseña."""
    try:
        args = _parser().parse_args(list(argv))
    except SystemExit as salida:
        return int(salida.code) if isinstance(salida.code, int) and salida.code else 2
    if args.desactivar or args.reactivar:
        otras = [n for n, v in (("--nombre", args.nombre), ("--rol", args.rol), ("--profesional-id", args.profesional_id))
                 if v is not None]
        if args.desactivar and args.reactivar:
            print("Error: --desactivar y --reactivar no pueden usarse juntos.", file=sys.stderr)
            return 2
        if otras:
            print(f"Error de uso: --desactivar/--reactivar no se combinan con {', '.join(otras)}.", file=sys.stderr)
            return 2
        try:
            async with get_session_factory()() as session:
                if args.desactivar:
                    cantidad = await desactivar_usuario(session, email=args.email, ahora=datetime.now(timezone.utc))
                else:
                    await reactivar_usuario(session, email=args.email)
        except UsuarioInvalidoError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if args.desactivar:
            print(f"Listo: {args.email.strip().lower()} desactivado; sesiones revocadas: {cantidad}.")
        else:
            print(f"Listo: {args.email.strip().lower()} reactivado (debe ingresar de nuevo).")
        return 0
    if args.nombre is None or args.rol is None:
        print("Error de uso: el alta necesita --nombre y --rol.", file=sys.stderr)
        return 2
    password = entorno.get(VAR_PASSWORD, "")
    if not password:
        print(f"Error: definí la variable de entorno {VAR_PASSWORD} con la contraseña (no se acepta por argumento).",
              file=sys.stderr)
        return 2
    try:
        async with get_session_factory()() as session:
            usuario = await crear_o_actualizar_usuario(
                session, email=args.email, nombre=args.nombre, rol=args.rol, password=password,
                profesional_id=args.profesional_id)
            email, activo = usuario.email, usuario.is_active
    except UsuarioInvalidoError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not activo:
        print(f"Aviso: {email} está desactivado y sigue desactivado; usá --reactivar para habilitarlo.", file=sys.stderr)
    logger.info("usuario del panel creado o actualizado: %s (rol %s)", email, args.rol)
    print(f"Listo: {email} con rol {args.rol}.")
    return 0


def main() -> None:
    async def _correr() -> int:
        try:
            return await ejecutar(sys.argv[1:], os.environ)
        finally:
            await get_engine().dispose()

    raise SystemExit(asyncio.run(_correr()))


if __name__ == "__main__":
    main()
