"""Integración C-02: Escenarios 1 (Happy Path), 2 (Error de Negocio), 3 (Caso de Borde - doble seed).

Strict TDD: RED primero (test falla), luego GREEN tras aplicar migración + seeds.
"""

from decimal import Decimal
from datetime import datetime, time, timedelta, timezone
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seeds.runner import run_seeds
from app.models.base import Base
from app.models.core import (
    Disponibilidad,
    Nomenclador,
    ObraSocial,
    Paciente,
    RegistroAuditoria,
    Rol,
    Usuario,
    UsuarioRol,
)
from app.turnos.models import Profesional, Sillon, Tratamiento, Turno
from app.repositories.uow import UnitOfWork


async def _count(session: AsyncSession, model) -> int:
    result = await session.execute(select(model))
    return len(result.scalars().all())


# ---------------------------------------------------------------
# Escenario 1 — Happy Path: persistencia válida de entidades relacionadas
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_escenario1_happy_path_entidades_relacionadas(session_factory):
    """Persiste Paciente + Usuario + Rol + Disponibilidad + ObraSocial + Nomenclador con FKs válidas."""
    async with session_factory() as session:
        # Obra social
        os_ = ObraSocial(codigo="OSDE", nombre="OSDE", sigla="OSDE")
        session.add(os_)
        await session.flush()

        # Paciente con DNI válido (8 dígitos) y teléfono E.164
        paciente = Paciente(
            nombre="Juan",
            apellido="Pérez",
            dni="38123456",
            telefono="+5491144445555",
            obra_social_id=os_.id,
        )
        session.add(paciente)
        await session.flush()

        # Rol + Usuario
        rol = Rol(nombre="odontologo", descripcion="Odontólogo")
        session.add(rol)
        await session.flush()

        usuario = Usuario(
            email="odontologo@consultorio.test",
            nombre_completo="Dr. Test",
            hashed_password="$2b$12$placeholder",
        )
        session.add(usuario)
        await session.flush()

        # UsuarioRol
        ur = UsuarioRol(usuario_id=usuario.id, rol_id=rol.id)
        session.add(ur)

        # Disponibilidad (FK a profesional existente — crear profesional primero)
        profesional = Profesional(nombre="Dr. Test", matricula="MAT-001", especialidad="General")
        session.add(profesional)
        await session.flush()

        disp = Disponibilidad(
            profesional_id=profesional.id,
            dia_semana=0,
            hora_inicio=time(8, 0),
            hora_fin=time(12, 0),
        )
        session.add(disp)

        # Tratamiento + Nomenclador
        tratamiento = Tratamiento(
            nombre="Consulta", duracion_minutos=30, precio_base=Decimal("15000.00")
        )
        session.add(tratamiento)
        await session.flush()

        nom = Nomenclador(
            obra_social_id=os_.id,
            tratamiento_id=tratamiento.id,
            codigo_prestacion="OSDE-CON",
            cobertura_porcentaje=Decimal("100.00"),
            arancel_diferencial=Decimal("0.00"),
        )
        session.add(nom)

        # Registro de auditoría
        auditoria = RegistroAuditoria(
            usuario_id=usuario.id,
            accion="CREATE",
            entidad="paciente",
            entidad_id=str(paciente.id),
        )
        session.add(auditoria)

        await session.commit()

        # Verificar timestamps tz-aware
        assert paciente.created_at.tzinfo is not None
        assert paciente.updated_at.tzinfo is not None
        assert usuario.created_at.tzinfo is not None

        # Verificar Numeric
        assert isinstance(nom.cobertura_porcentaje, Decimal)
        assert isinstance(nom.arancel_diferencial, Decimal)

        # Verificar FKs resueltas
        assert paciente.obra_social_id == os_.id
        assert ur.usuario_id == usuario.id
        assert ur.rol_id == rol.id
        assert disp.profesional_id == profesional.id
        assert nom.obra_social_id == os_.id
        assert nom.tratamiento_id == tratamiento.id
        assert auditoria.usuario_id == usuario.id

        # Cardinalidad
        assert await _count(session, ObraSocial) == 1
        assert await _count(session, Paciente) == 1
        assert await _count(session, Rol) == 1
        assert await _count(session, Usuario) == 1
        assert await _count(session, UsuarioRol) == 1
        assert await _count(session, Disponibilidad) == 1
        assert await _count(session, Nomenclador) == 1
        assert await _count(session, RegistroAuditoria) == 1


# ---------------------------------------------------------------
# Escenario 2 — Error de Negocio: violación de integridad
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_escenario2_dni_duplicado_rechazado(session_factory):
    """DNI duplicado → IntegrityError, rollback atómico (no persiste parcial)."""
    async with session_factory() as session:
        p1 = Paciente(nombre="A", apellido="B", dni="38123456", telefono="+549111111111")
        session.add(p1)
        await session.commit()

        p2 = Paciente(nombre="C", apellido="D", dni="38123456", telefono="+549222222222")
        session.add(p2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        # Rollback atómico: solo p1 persiste
        result = await session.execute(select(Paciente).where(Paciente.dni == "38123456"))
        pacientes = result.scalars().all()
        assert len(pacientes) == 1
        assert pacientes[0].nombre == "A"


@pytest.mark.asyncio
async def test_escenario2_email_duplicado_rechazado(session_factory):
    """Email duplicado → IntegrityError, rollback atómico."""
    async with session_factory() as session:
        u1 = Usuario(
            email="dup@test.com",
            nombre_completo="Uno",
            hashed_password="$2b$12$x",
        )
        session.add(u1)
        await session.commit()

        u2 = Usuario(
            email="dup@test.com",
            nombre_completo="Dos",
            hashed_password="$2b$12$y",
        )
        session.add(u2)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        result = await session.execute(select(Usuario).where(Usuario.email == "dup@test.com"))
        usuarios = result.scalars().all()
        assert len(usuarios) == 1


@pytest.mark.asyncio
async def test_escenario2_turno_paciente_id_inexistente_rechazado(session_factory):
    """Turno con paciente_id inexistente → FK violation, rollback atómico."""
    async with session_factory() as session:
        # Crear turno con paciente_id que no existe
        turno = Turno(
            profesional_id=1,  # puede no existir tampoco, pero el error será FK a paciente primero
            sillon_id=1,
            tratamiento_id=1,
            paciente_id=999999,  # inexistente
        )
        # Ajustar inicio/fin para que sea válido
        from datetime import datetime, time, timedelta, timezone
        now = datetime.now(timezone.utc)
        turno.inicio = now + timedelta(hours=1)
        turno.fin = now + timedelta(hours=2)

        session.add(turno)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        # Nada persistido
        result = await session.execute(select(Turno))
        assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_escenario2_uow_rollback_atomico(session_factory):
    """UnitOfWork hace rollback automático ante excepción dentro del contexto."""
    uow = UnitOfWork(session_factory)
    try:
        async with uow:
            paciente = Paciente(
                nombre="UOW", apellido="Test", dni="38000001", telefono="+549333333333"
            )
            uow.session.add(paciente)
            await uow.session.flush()
            # Forzar error: DNI duplicado en siguiente insert dentro mismo contexto
            paciente_dup = Paciente(
                nombre="UOW2", apellido="Test2", dni="38000001", telefono="+549444444444"
            )
            uow.session.add(paciente_dup)
            await uow.session.commit()  # Esto fallará
    except IntegrityError:
        pass

    # Verificar que nada se persistió (rollback automático)
    async with session_factory() as session:
        result = await session.execute(select(Paciente).where(Paciente.dni == "38000001"))
        assert len(result.scalars().all()) == 0


# ---------------------------------------------------------------
# Escenario 3 — Caso de Borde: doble ejecución del seeder
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_escenario3_seed_doble_ejecucion_sin_duplicados(session_factory):
    """Ejecutar seeder dos veces: sin violaciones de clave única, cardinalidad idéntica, fechas sin alterar."""
    async with session_factory() as session:
        # Primera ejecución
        await run_seeds(session)
        await session.commit()

        # Capturar cardinalidad y created_at después de la primera corrida
        counts_first = {}
        created_ats_first = {}
        for model, label in [
            (Rol, "rol"),
            (Usuario, "usuario"),
            (ObraSocial, "obra_social"),
            (Paciente, "paciente"),
            (Profesional, "profesional"),
            (Sillon, "sillon"),
            (Tratamiento, "tratamiento"),
            (Disponibilidad, "disponibilidad"),
            (Nomenclador, "nomenclador"),
        ]:
            result = await session.execute(select(model))
            rows = result.scalars().all()
            counts_first[label] = len(rows)
            created_ats_first[label] = [getattr(r, "created_at", None) for r in rows]

        # Segunda ejecución
        await run_seeds(session)
        await session.commit()

        # Verificar cardinalidad idéntica
        for model, label in [
            (Rol, "rol"),
            (Usuario, "usuario"),
            (ObraSocial, "obra_social"),
            (Paciente, "paciente"),
            (Profesional, "profesional"),
            (Sillon, "sillon"),
            (Tratamiento, "tratamiento"),
            (Disponibilidad, "disponibilidad"),
            (Nomenclador, "nomenclador"),
        ]:
            result = await session.execute(select(model))
            rows = result.scalars().all()
            assert len(rows) == counts_first[label], f"Cardinalidad cambiada en {label}: {counts_first[label]} -> {len(rows)}"

        # Verificar que created_at no se alteró (misma referencia de objetos)
        for model, label in [
            (Rol, "rol"),
            (Usuario, "usuario"),
            (ObraSocial, "obra_social"),
            (Profesional, "profesional"),
            (Sillon, "sillon"),
            (Tratamiento, "tratamiento"),
        ]:
            result = await session.execute(select(model))
            rows = result.scalars().all()
            for row, first_created in zip(rows, created_ats_first[label]):
                if first_created is not None:
                    assert row.created_at == first_created, f"created_at alterado en {label} id={row.id}"

        # Verificar roles esperados
        result = await session.execute(select(Rol).order_by(Rol.nombre))
        roles = [r.nombre for r in result.scalars().all()]
        assert set(roles) == {"admin", "odontologo", "recepcion"}

        # Verificar obras sociales esperadas
        result = await session.execute(select(ObraSocial).order_by(ObraSocial.codigo))
        codigos = [o.codigo for o in result.scalars().all()]
        assert set(codigos) == {"OSDE", "SWISS", "GALICIA", "OMEGA", "PARTICULAR"}

        # Verificar tratamientos esperados (al menos los 5 del seed, sin duplicados)
        result = await session.execute(select(Tratamiento).order_by(Tratamiento.nombre))
        tratamientos = result.scalars().all()
        assert len(tratamientos) >= 5
        nombres_trat = {t.nombre for t in tratamientos}
        assert {"Consulta odontológica", "Limpieza dental", "Empaste / obturación", "Extracción simple", "Blanqueamiento"}.issubset(nombres_trat)
        for t in tratamientos:
            assert isinstance(t.precio_base, Decimal)
            assert t.duracion_minutos > 0

        # Múltiples profesionales y sillones (multi-odontólogo/multi-sillón día 1)
        assert counts_first["profesional"] >= 2
        assert counts_first["sillon"] >= 2


@pytest.mark.asyncio
async def test_escenario3_seed_no_violaciones_clave_unica(session_factory):
    """Doble corrida del seed nunca arroja IntegrityError por clave única duplicada."""
    async with session_factory() as session:
        await run_seeds(session)
        await session.commit()  # primera corrida ok
        await run_seeds(session)  # segunda corrida: no debe lanzar
        await session.commit()


# ---------------------------------------------------------------
# Limpieza entre tests (hereda de conftest clean_db, pero extendemos)
# ---------------------------------------------------------------

@pytest.fixture(autouse=True)
async def _clean_all_core(session_factory):
    """Limpia todas las tablas core después de cada test."""
    yield
    async with session_factory() as session:
        # C-13 (D6): la auditoría es de solo agregado (trigger); se vacía con TRUNCATE antes que usuario (FK RESTRICT).
        await session.execute(text("TRUNCATE registro_auditoria RESTART IDENTITY CASCADE"))
        for model in (
            Nomenclador,
            Disponibilidad,
            UsuarioRol,
            Paciente,
            Usuario,
            ObraSocial,
            Rol,
            Turno,
        ):
            await session.execute(delete(model))
        await session.commit()
