"""Runner de seeds idempotentes (C-02, task 4.1).

Utiliza ``ON CONFLICT DO NOTHING`` sobre las columnas únicas de cada tabla
para garantizar que ejecutar el seed dos o más veces no duplique registros ni
falle por violación de clave única (Decision 4 del design.md, R19: datos sintéticos).
"""

from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seeds import data


async def _insert_roles(session: AsyncSession) -> dict[str, int]:
    """Inserta roles si no existen; devuelve {nombre: id}."""
    result: dict[str, int] = {}
    for role in data.SEED_ROLES:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO rol (nombre, descripcion)
                    VALUES (:nombre, :descripcion)
                    ON CONFLICT (nombre) DO NOTHING
                    RETURNING id, nombre
                    """
                ),
                role,
            )
        ).first()
        if row is not None:
            result[row.nombre] = row.id
        else:
            existing = (
                await session.execute(
                    text("SELECT id FROM rol WHERE nombre = :nombre"),
                    {"nombre": role["nombre"]},
                )
            ).first()
            result[role["nombre"]] = existing.id
    return result


async def _insert_usuario_admin(session: AsyncSession) -> int:
    """Inserta el usuario admin si no existe; devuelve su id."""
    row = (
        await session.execute(
            text(
                """
                INSERT INTO usuario (email, nombre_completo, hashed_password)
                VALUES (:email, :nombre_completo, :hashed_password)
                ON CONFLICT (email) DO NOTHING
                RETURNING id, email
                """
            ),
            data.SEED_USUARIO_ADMIN,
        )
    ).first()
    if row is not None:
        return row.id
    existing = (
        await session.execute(
            text("SELECT id FROM usuario WHERE email = :email"),
            {"email": data.SEED_USUARIO_ADMIN["email"]},
        )
    ).first()
    return existing.id


async def _assign_admin_role(session: AsyncSession, usuario_id: int, rol_admin_id: int) -> None:
    """Asigna el rol admin al usuario admin (idempotente por unique constraint)."""
    await session.execute(
        text(
            """
            INSERT INTO usuario_rol (usuario_id, rol_id)
            VALUES (:usuario_id, :rol_id)
            ON CONFLICT (usuario_id, rol_id) DO NOTHING
            """
        ),
        {"usuario_id": usuario_id, "rol_id": rol_admin_id},
    )


async def _insert_obras_sociales(session: AsyncSession) -> dict[str, int]:
    """Inserta obras sociales si no existen; devuelve {codigo: id}."""
    result: dict[str, int] = {}
    for os_data in data.SEED_OBRAS_SOCIALES:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO obra_social (codigo, nombre, sigla)
                    VALUES (:codigo, :nombre, :sigla)
                    ON CONFLICT (codigo) DO NOTHING
                    RETURNING id, codigo
                    """
                ),
                os_data,
            )
        ).first()
        if row is not None:
            result[row.codigo] = row.id
        else:
            existing = (
                await session.execute(
                    text("SELECT id FROM obra_social WHERE codigo = :codigo"),
                    {"codigo": os_data["codigo"]},
                )
            ).first()
            result[os_data["codigo"]] = existing.id
    return result


async def _insert_tratamientos(session: AsyncSession) -> dict[str, int]:
    """Inserta tratamientos si no existen (SELECT-first: no hay unique en nombre)."""
    result: dict[str, int] = {}
    for trat in data.SEED_TRATAMIENTOS:
        existing = (
            await session.execute(
                text("SELECT id FROM tratamiento WHERE nombre = :nombre"),
                {"nombre": trat["nombre"]},
            )
        ).first()
        if existing is not None:
            result[trat["nombre"]] = existing.id
            continue
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO tratamiento (nombre, duracion_minutos, precio_base)
                    VALUES (:nombre, :duracion_minutos, :precio_base)
                    RETURNING id, nombre
                    """
                ),
                {
                    "nombre": trat["nombre"],
                    "duracion_minutos": trat["duracion_minutos"],
                    "precio_base": Decimal(trat["precio_base"]),
                },
            )
        ).first()
        result[row.nombre] = row.id
    return result


async def _insert_profesionales(session: AsyncSession) -> dict[str, int]:
    """Inserta profesionales si no existen (SELECT-first: no hay unique en matricula)."""
    result: dict[str, int] = {}
    for prof in data.SEED_PROFESIONALES:
        existing = (
            await session.execute(
                text("SELECT id FROM profesional WHERE matricula = :matricula"),
                {"matricula": prof["matricula"]},
            )
        ).first()
        if existing is not None:
            result[prof["matricula"]] = existing.id
            continue
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO profesional (nombre, matricula, especialidad)
                    VALUES (:nombre, :matricula, :especialidad)
                    RETURNING id, matricula
                    """
                ),
                prof,
            )
        ).first()
        result[row.matricula] = row.id
    return result


async def _insert_sillones(session: AsyncSession) -> dict[str, int]:
    """Inserta sillones si no existen (SELECT-first: no hay unique en nombre)."""
    result: dict[str, int] = {}
    for sill in data.SEED_SILLONES:
        existing = (
            await session.execute(
                text("SELECT id FROM sillon WHERE nombre = :nombre"),
                {"nombre": sill["nombre"]},
            )
        ).first()
        if existing is not None:
            result[sill["nombre"]] = existing.id
            continue
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO sillon (nombre, estado)
                    VALUES (:nombre, :estado)
                    RETURNING id, nombre
                    """
                ),
                sill,
            )
        ).first()
        result[row.nombre] = row.id
    return result


async def _insert_disponibilidad(
    session: AsyncSession, profesional_ids: list[int], sillon_ids: list[int]
) -> int:
    """Inserta disponibilidades (idempotente: SELECT-first, no hay unique constraint en esas columnas)."""
    count = 0
    sillon_id = sillon_ids[0] if sillon_ids else None
    for disp in data.SEED_DISPONIBILIDAD:
        prof_id = profesional_ids[disp["profesional_id"] - 1]
        exists = (
            await session.execute(
                text(
                    """
                    SELECT 1 FROM disponibilidad
                    WHERE profesional_id = :profesional_id
                      AND dia_semana = :dia_semana
                      AND hora_inicio = :hora_inicio
                    LIMIT 1
                    """
                ),
                {
                    "profesional_id": prof_id,
                    "dia_semana": disp["dia_semana"],
                    "hora_inicio": disp["hora_inicio"],
                },
            )
        ).first()
        if exists is not None:
            continue
        await session.execute(
            text(
                """
                INSERT INTO disponibilidad (profesional_id, dia_semana, hora_inicio, hora_fin, sillon_defecto_id)
                VALUES (:profesional_id, :dia_semana, :hora_inicio, :hora_fin, :sillon_defecto_id)
                """
            ),
            {
                "profesional_id": prof_id,
                "dia_semana": disp["dia_semana"],
                "hora_inicio": disp["hora_inicio"],
                "hora_fin": disp["hora_fin"],
                "sillon_defecto_id": sillon_id,
            },
        )
        count += 1
    return count


async def _insert_nomenclador(
    session: AsyncSession, os_ids: dict[str, int], trat_ids: dict[str, int]
) -> int:
    """Inserta filas del nomenclador (idempotente por (obra_social_id, tratamiento_id))."""
    count = 0
    coberturas = {
        "OSDE": Decimal("100.00"),
        "SWISS": Decimal("90.00"),
        "GALICIA": Decimal("80.00"),
        "OMEGA": Decimal("85.00"),
        "PARTICULAR": Decimal("0.00"),
    }
    for os_code, os_id in os_ids.items():
        cobertura = coberturas.get(os_code, Decimal("100.00"))
        for trat_name, trat_id in trat_ids.items():
            row = (
                await session.execute(
                    text(
                        """
                        INSERT INTO nomenclador (obra_social_id, tratamiento_id, codigo_prestacion, cobertura_porcentaje, arancel_diferencial)
                        VALUES (:obra_social_id, :tratamiento_id, :codigo_prestacion, :cobertura_porcentaje, :arancel_diferencial)
                        ON CONFLICT (obra_social_id, tratamiento_id) DO NOTHING
                        RETURNING id
                        """
                    ),
                    {
                        "obra_social_id": os_id,
                        "tratamiento_id": trat_id,
                        "codigo_prestacion": f"{os_code}-{trat_name[:3].upper()}",
                        "cobertura_porcentaje": cobertura,
                        "arancel_diferencial": Decimal("0.00"),
                    },
                )
            ).first()
            if row is not None:
                count += 1
    return count


async def run_seeds(session: AsyncSession) -> None:
    """Ejecuta todos los seeds de forma idempotente en una sola transacción.

    Puede llamarse múltiples veces sin duplicar registros ni fallar por
    violación de clave única (Escenario 3 del spec).
    """
    # 1. Roles
    role_ids = await _insert_roles(session)
    rol_admin_id = role_ids["admin"]

    # 2. Usuario admin
    usuario_admin_id = await _insert_usuario_admin(session)

    # 3. Asignar rol admin al usuario admin
    await _assign_admin_role(session, usuario_admin_id, rol_admin_id)

    # 4. Obras sociales
    os_ids = await _insert_obras_sociales(session)

    # 5. Tratamientos
    trat_ids = await _insert_tratamientos(session)

    # 6. Profesionales
    prof_ids = await _insert_profesionales(session)
    profesional_ids = list(prof_ids.values())

    # 7. Sillones
    sill_ids = await _insert_sillones(session)
    sillon_ids = list(sill_ids.values())

    # 8. Disponibilidad
    await _insert_disponibilidad(session, profesional_ids, sillon_ids)

    # 9. Nomenclador
    await _insert_nomenclador(session, os_ids, trat_ids)
