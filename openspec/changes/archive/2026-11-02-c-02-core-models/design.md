# Design: c-02-core-models

## Context
En C-01 se crearon las tablas iniciales `profesionales`, `sillones`, `tratamientos` y `turnos` con la constraint GiST anti-solape. C-02 amplía el modelo de datos a todas las entidades del dominio odontológico requeridas por la base de conocimiento (`knowledge-base/04_modelo_de_datos.md`), respetando las reglas duras **R4** (sin tipos sin zona horaria, floats para dinero ni strings sin límite), **R6** (índice explícito sobre cada FK), **R13** (firmas 100% tipadas con type hints), **R14** (SQLAlchemy ORM + Alembic reversible, sin SQL crudo) y **R19** (datos sintéticos).

---

## Goals / Non-Goals

**Goals:**
- Extender el esquema relacional con las 7 entidades restantes: `Paciente`, `Disponibilidad`, `Usuario`, `Rol`, `UsuarioRol`, `RegistroAuditoria`, `ObraSocial`, `Nomenclador`.
- Incorporar la clave foránea `Turno.paciente_id` con su índice correspondiente y migración reversible.
- Proveer los patrones arquitectónicos base: `TimestampMixin`, `ActiveMixin`, `BaseRepository[T]` y `UnitOfWork` asíncrono.
- Implementar un runner de seeds 100% idempotente que precargue roles, usuario administrador, catálogo de tratamientos, nomenclador OS y recursos de consultorio (múltiples odontólogos y sillones).

**Non-Goals:**
- Endpoints de autenticación JWT (login, refresh, logout) y middlewares RBAC (pertenecen a **C-03 `auth-panel-rbac`**).
- Endpoints de consulta pública y cálculo dinámico de franjas horarias libres (pertenecen a **C-04** y **C-05**).
- Máquina de estados de seña (`en_espera`) y pasarela Mercado Pago (pertenecen a **C-06**).

---

## Decisions

### Decision 1: Modelado Declarativo SQLAlchemy 2.0 y Convención de Tipos
* **Decisión:** Utilizar la sintaxis moderna `Mapped[T]` y `mapped_column()` de SQLAlchemy 2.0.
* **Tipos estrictos (Regla R4):**
  * Fechas y marcas de tiempo: `DateTime(timezone=True)` obligatorio con default `func.now()`.
  * Dinero / Aranceles / Precios: `Numeric(10, 2)` (prohibido `Float`).
  * Textos: `String(N)` acotados o `Text` acompañados de constraints de longitud.
  * Identificadores: Claves primarias enteras con secuencia o BigInteger (`id = mapped_column(BigInteger, primary_key=True, autoincrement=True)`).
* **Alternativas descartadas:** SQLAlchemy 1.4 tradicional con `Column()` sin tipado estricto (descartado para cumplir con R13).

### Decision 2: Indexación Manual Obligatoria sobre Claves Foráneas (Regla R6)
* **Decisión:** PostgreSQL no indexa automáticamente las columnas de Foreign Keys. Se declaran índices explícitos sobre:
  * `turnos(paciente_id)`
  * `disponibilidades(profesional_id)`
  * `usuarios_roles(usuario_id)` y `usuarios_roles(rol_id)`
  * `registros_auditoria(usuario_id)` y `registros_auditoria(created_at)`
  * `nomenclador(obra_social_id)`
* **Alternativas descartadas:** Confiar en los índices automáticos del motor (riesgo de table-scans en queries de joins de agenda).

### Decision 3: Identidad y Unicidad de Paciente (DNI y Teléfono Obligatorios)
* **Decisión:** El paciente se identifica en el consultorio mediante su **DNI obligatorio** (cadena numérica de 7 u 8 dígitos con constraint `CHECK` en PostgreSQL) y su **número de teléfono normalizado** en formato internacional E.164 (ej. `+5491144445555`). Nombre, apellido y DNI son obligatorios en la ficha y en la reserva; la obra social y número de afiliado permanecen opcionales.
* **Alternativas descartadas:** DNI opcional (descartado por requerimiento explícito del usuario para trazabilidad clínica unívoca e historia clínica).

### Decision 4: Idempotencia Absoluta en Scripts de Seeding
* **Decisión:** Los scripts de seed utilizan sentencias de inserción con cláusula `ON CONFLICT DO NOTHING` o verificación previa por identificadores únicos (`codigo` en tratamientos/nomenclador, `nombre` en roles, `email` en usuario admin).
* **Garantía:** Ejecutar el seed dos o más veces seguidas debe resultar en cero duplicaciones y cero errores de constraint violada.

### Decision 5: Registro de Auditoría Estructurado (RN-GL-01)
* **Decisión:** La tabla `registros_auditoria` almacena `accion` (`CREATE`, `UPDATE`, `DELETE`, `LOGIN`, `LOGOUT`), `entidad`, `entidad_id`, `usuario_id` (nullable para acciones públicas), `ip_origen` y una columna `datos_antes`/`datos_despues` en formato JSONB con índice GIN para búsquedas estructuradas futuras (C-13).

---

## Risks / Trade-offs

- **[Riesgo: Migración de base de datos con tabla `turnos` existente]** → *Mitigación:* La columna `paciente_id` agregada a `turnos` en la migración 002 debe admitir `nullable=True` inicialmente si existen turnos de prueba de C-01, o poblarse con un paciente seed por defecto antes de aplicar la restricción si se requiere.
- **[Riesgo: Manejo de múltiples zonas horarias]** → *Mitigación:* Almacenamiento unificado en UTC en PostgreSQL con `timezone=True`, delegando la conversión a la zona horaria del consultorio (`America/Argentina/Buenos_Aires`) en la capa de presentación.
- **[Riesgo: Duplicación en seeds en entornos de desarrollo y testing]** → *Mitigación:* Test automatizado específico que corre el seed dos veces consecutivas y comprueba la invariante de cardinalidad idéntica.
