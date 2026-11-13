# Arquitectura Propuesta

Stack **congelado (Resoluciones 2026-09-30, ver `10_preguntas_abiertas.md` §Resoluciones y `AGENTS.md`)**: Backend Python + FastAPI + SQLAlchemy (+ Alembic) + PostgreSQL + Redis + JWT (expiración corta + refresh) + Docker Compose; Frontend React + TypeScript + Vite; E2E Playwright. Lo técnico abajo se lee sobre ese stack.

## Patrones aplicados

| Patrón | Dónde se usa | Por qué |
|--------|--------------|---------|
| Reserva pública sin login | Frontend paciente | Fricción mínima: nombre + teléfono por turno |
| Panel con RBAC | Gestión interna | Separa paciente / odontólogo / recepción-admin |
| Scheduler para recordatorios | Envío WhatsApp MANUAL v1 (links `wa.me/`) vía workers Redis | Los recordatorios son diferidos, no sincrónicos; v1 sin API paga |
| Sincronización bidireccional | Google Calendar | GCal es hoy el sistema principal en uso |
| Duraciones configurables | Catálogo de tratamientos | Evita valores fijos en código (RN-TU-05) |
| Auditoría de acciones | Panel admin | Trazabilidad de quién hizo cada cambio |

## Estructura de directorios (orientativa, agnóstica del stack)

```
proyecto/
├── frontend-paciente/     # reserva pública mobile-first (sin login)
├── frontend-panel/        # panel odontólogo + recepción/admin
├── backend/
│   ├── agenda/            # turnos, disponibilidad, anti-solape
│   ├── pacientes/         # fichas, ausentismo
│   ├── clinica/           # tratamientos, odontograma, presupuestos, nomenclador
│   ├── pagos/             # Mercado Pago + transferencia, caja
│   ├── notificaciones/    # WhatsApp (recordatorios/confirmación)
│   ├── integraciones/     # Google Calendar sync (C-10: `integraciones/gcal/` = puerto `ProveedorCalendario`, adaptador `httpx`, proveedor falso, OAuth, push por reconciliación, pull incremental, conflictos y servidor falso para E2E)
│   └── plataforma/        # usuarios, roles, auditoría, exportación
└── jobs/                  # recordatorios programados, sincronización
```

(Si el stack elegido es monolítico, estas son módulos internos en vez de servicios.)

## Seguridad

- Autenticación: solo panel interno (odontólogo, recepción/admin); reserva pública sin login con código de gestión por turno.
- Autorización: RBAC según matriz de `03_actores_y_roles.md`.
- Validación de input: teléfono requerido, ventana 24 hs y anti-solape verificados en backend (nunca solo en cliente).
- Secrets management: credenciales de WhatsApp (API futura; v1 MANUAL sin token de envío), Google OAuth y Mercado Pago fuera del código (variables de entorno / gestor de secretos).
- Multi-odontólogo / multi-sillón día 1: agenda y anti-solape siempre por `profesional_id` + `sillon_id` (ver RN-TU-03 y DDL de C-01).

## Variables de entorno

| Variable | Descripción | Ejemplo | Sensible |
|----------|-------------|---------|----------|
| `DATABASE_URL` | Conexión a la base de datos | `postgres://…` | Y |
| `WHATSAPP_API_TOKEN` | Token del proveedor WhatsApp (FUTURO: solo si se migra a API; C-09 no lo introduce, v1 MANUAL sin envío) | `EAAB…` | Y |
| `WHATSAPP_SENDER` | Número remitente | `+54911…` | N |
| `GCAL_CLIENT_ID` / `GCAL_CLIENT_SECRET` | OAuth Google Calendar (cliente «Aplicación web»). Sin ellas la API arranca, `conexion/iniciar` responde 503 `gcal_no_configurado` y el worker no registra `gcal_sync` | `….apps.googleusercontent.com` | Y |
| `GCAL_TOKEN_CLAVE` | Clave Fernet (32 bytes en base64) con la que se cifran los tokens OAuth en la base (C-10 O1); obligatoria si hay `GCAL_CLIENT_ID` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | Y |
| `GCAL_REDIRECT_URI` / `PUBLIC_PANEL_URL` | Callback OAuth del backend y URL del panel a la que vuelve el navegador (`#/google-calendar?resultado=…`) | `http://localhost:8000/api/panel/google-calendar/oauth/callback` / `http://localhost:5174` | N |
| `GCAL_SYNC_HABILITADO` / `GCAL_SYNC_INTERVALO_SEGUNDOS` / `GCAL_HORIZONTE_DIAS` | Trabajo `gcal_sync`, cada cuánto corre (> 0) y hasta cuántos días adelante sincroniza (1–365) | `true` / `60` / `60` | N |
| `GCAL_OAUTH_BASE_URL` / `GCAL_TOKEN_BASE_URL` / `GCAL_API_BASE_URL` | URLs de Google; **solo con `APP_ENV=test` o `e2e`** pueden apuntar al servidor falso (`gcal-falso`) | `https://accounts.google.com` / `https://oauth2.googleapis.com` / `https://www.googleapis.com` | N |
| `MP_ACCESS_TOKEN` | Token Mercado Pago | `APP-…` | Y |
| `REMINDER_LEAD_TIME` | Anticipación del recordatorio (horas; acepta `48` o `48h`). **C-09 O5 (2026-11-11): default 48 h** en lugar del ejemplo original de 24 h, porque con 24 h el enlace de cancelar casi siempre cae fuera de la ventana de 24 h de C-07 | `48h` | N |
| `REDIS_URL` | Redis del worker (la API no lo usa) | `redis://redis:6379/0` | N |
| `RECORDATORIOS_HABILITADO` / `RECORDATORIOS_INTERVALO_SEGUNDOS` | Trabajo de recordatorios y cada cuánto corre (> 0) | `true` / `300` | N |
| `SENA_BARRIDO_HABILITADO` / `SENA_BARRIDO_SEGUNDOS` / `SENA_BARRIDO_EN_API` | Barrido de pre-reservas vencidas: lo corre el worker; la API solo con `SENA_BARRIDO_EN_API=true` (desarrollo sin Redis) | `true` / `60` / `false` | N |
| `WHATSAPP_PROVEEDOR` | Proveedor de WhatsApp (`manual` en v1; `falso` solo con `APP_ENV=test`) | `manual` | N |
| `CLINICA_NOMBRE` | Nombre de la clínica en el mensaje del recordatorio | `la clínica` | N |
| `CANCEL_WINDOW_HOURS` | Ventana de cancelación | `24` | N |

Stack congelado (ver arriba); nombres exactos vigentes para FastAPI + Docker Compose. `SENA_PORCENTAJE` y config de `PagoSena` se introducen en C-06.
