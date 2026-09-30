# Arquitectura Propuesta

Stack sin definir: lo técnico abajo es orientativo y debe validarse al elegir stack. Nada de lo aquí descrito fija tecnología.

## Patrones aplicados

| Patrón | Dónde se usa | Por qué |
|--------|--------------|---------|
| Reserva pública sin login | Frontend paciente | Fricción mínima: nombre + teléfono por turno |
| Panel con RBAC | Gestión interna | Separa paciente / odontólogo / recepción-admin |
| Scheduler para recordatorios | Envío WhatsApp | Los recordatorios son diferidos, no sincrónicos |
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
│   ├── integraciones/     # Google Calendar sync
│   └── plataforma/        # usuarios, roles, auditoría, exportación
└── jobs/                  # recordatorios programados, sincronización
```

(Si el stack elegido es monolítico, estas son módulos internos en vez de servicios.)

## Seguridad

- Autenticación: solo panel interno (odontólogo, recepción/admin); reserva pública sin login con código de gestión por turno.
- Autorización: RBAC según matriz de `03_actores_y_roles.md`.
- Validación de input: teléfono requerido, ventana 24 hs y anti-solape verificados en backend (nunca solo en cliente).
- Secrets management: credenciales de WhatsApp API, Google OAuth y Mercado Pago fuera del código (variables de entorno / gestor de secretos).

## Variables de entorno

| Variable | Descripción | Ejemplo | Sensible |
|----------|-------------|---------|----------|
| `DATABASE_URL` | Conexión a la base de datos | `postgres://…` | Y |
| `WHATSAPP_API_TOKEN` | Token del proveedor WhatsApp (si API) | `EAAB…` | Y |
| `WHATSAPP_SENDER` | Número remitente | `+54911…` | N |
| `GCAL_CLIENT_ID` / `GCAL_CLIENT_SECRET` | OAuth Google Calendar | `….apps.googleusercontent.com` | Y |
| `MP_ACCESS_TOKEN` | Token Mercado Pago | `APP-…` | Y |
| `REMINDER_LEAD_TIME` | Anticipación del recordatorio | `24h` | N |
| `CANCEL_WINDOW_HOURS` | Ventana de cancelación | `24` | N |

Nombres exactos a confirmar al definir el stack.
