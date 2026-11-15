/** Datos 100 % sintéticos (R19) y un `Api` falso para las pruebas de componentes. */
import { vi } from 'vitest';
import type { Api } from '../lib/api';
import type {
  Agenda,
  Ausentismo,
  CajaDia,
  CambioEstado,
  CierreDetalle,
  Devolucion,
  ListadoPacientes,
  Ocupacion,
  Opciones,
  PacienteListado,
  Pendiente,
  Rechazo,
  Recordatorio,
  Acreditacion,
  ConexionGoogle,
  ConflictoGoogle,
  TurnoAgenda,
  TurnoCreado,
  AccesoClinico,
  Ficha,
  LineaPresupuesto,
  OdontogramaVigente,
  PacienteDetalle,
  PagoPresupuesto,
  PiezaVigente,
  Presupuesto,
  PresupuestoClinico,
  RegistroOdontograma,
  PaginaAuditoria,
  RegistroAuditoria,
  CatalogoAdmin,
  FranjaAdmin,
  Impacto,
  ProfesionalAdmin,
  SillonAdmin,
  TratamientoAdmin,
} from '../lib/tipos';

export function turno(sobre: Partial<TurnoAgenda> = {}): TurnoAgenda {
  return {
    id: 11,
    inicio: '2031-11-18T09:00:00-03:00',
    fin: '2031-11-18T09:30:00-03:00',
    estado: 'reservado',
    bloquea_agenda: true,
    origen: 'web',
    profesional: { id: 1, nombre: 'Dra. Ana Ficticia' },
    sillon: { id: 2, nombre: 'Sillón 1' },
    tratamiento: { id: 3, nombre: 'Limpieza dental', duracion_minutos: 30 },
    paciente_id: null,
    paciente_nombre: 'Carlos Sintético',
    paciente_telefono: '+5491144445555',
    sena: { estado: 'acreditado', monto: '3000.00' },
    vence_en: null,
    acciones: [],
    calendario: { estado: 'sin_evento', conflicto_abierto: false },
    ...sobre,
  };
}

export function agenda(
  turnos: readonly TurnoAgenda[],
  vista: 'dia' | 'semana' = 'dia',
  fecha = '2031-11-18',
  ocupados_google: Agenda['ocupados_google'] = [],
): Agenda {
  return vista === 'dia'
    ? { vista, desde: fecha, hasta: fecha, turnos, ocupados_google }
    : { vista, desde: '2031-11-17', hasta: '2031-11-23', turnos, ocupados_google };
}

export const OPCIONES: Opciones = {
  profesionales: [
    { id: 1, nombre: 'Dra. Ana Ficticia', activo: true },
    { id: 4, nombre: 'Dr. Bruno Ejemplo', activo: true },
  ],
  sillones: [
    { id: 2, nombre: 'Sillón 1' },
    { id: 5, nombre: 'Sillón 2' },
  ],
  tratamientos: [
    { id: 3, nombre: 'Limpieza dental', duracion_minutos: 30, activo: true },
    { id: 6, nombre: 'Empaste', duracion_minutos: 45, activo: true },
  ],
  puede_escribir: true,
};

/** Un profesional y un tratamiento retirados del catálogo (C-14): se ven en la agenda pero no se ofrecen para turnos nuevos. */
export const OPCIONES_CON_INACTIVOS: Opciones = {
  ...OPCIONES,
  profesionales: [...OPCIONES.profesionales, { id: 7, nombre: 'Dr. Juan Ejemplo', activo: false }],
  tratamientos: [...OPCIONES.tratamientos, { id: 8, nombre: 'Ortodoncia demo', duracion_minutos: 60, activo: false }],
};

export const SOLO_LECTURA: Opciones = {
  ...OPCIONES,
  profesionales: [{ id: 1, nombre: 'Dra. Ana Ficticia', activo: true }],
  puede_escribir: false,
};

export const CREADO: TurnoCreado = {
  id: 99,
  inicio: '2031-11-18T11:00:00-03:00',
  fin: '2031-11-18T11:30:00-03:00',
  estado: 'reservado',
  origen: 'manual',
  profesional_id: 1,
  sillon_id: 2,
  tratamiento_id: 3,
  codigo_gestion: 'CODIGO-SINTETICO-0001',
  aviso_google_calendar: false,
};

export const CAMBIO: CambioEstado = { turno_id: 11, estado: 'ausente', estado_sena: 'no_reembolsado' };

export const SLOTS = [
  { inicio: '2031-11-18T11:00:00-03:00', fin: '2031-11-18T11:30:00-03:00', profesional_id: 1, sillon_id: 2 },
  { inicio: '2031-11-18T11:30:00-03:00', fin: '2031-11-18T12:00:00-03:00', profesional_id: 1, sillon_id: 2 },
];

// --- C-12 --------------------------------------------------------------------------------------------------------

export function caja(sobre: Partial<CajaDia> = {}): CajaDia {
  return {
    dia: '2031-11-18',
    estado: 'abierto',
    cierre_id: null,
    lineas: [{ concepto: 'sena', medio: 'mercadopago', cantidad: 1, total: '3000.00' }],
    total_ingresos: '3000.00',
    total_egresos: '0.00',
    total_neto: '3000.00',
    senas_retenidas: { cantidad: 0, total: '0.00' },
    movimientos: [
      { concepto: 'sena', medio: 'mercadopago', importe: '3000.00', hora: '2031-11-18T10:00:00-03:00', referencia: null, turno_id: 4, presupuesto_id: null },
    ],
    ...sobre,
  };
}

export const CAJA_VACIA: CajaDia = caja({
  lineas: [],
  total_ingresos: '0.00',
  total_neto: '0.00',
  movimientos: [],
});

export function pendiente(sobre: Partial<Pendiente> = {}): Pendiente {
  return {
    tipo: 'revision',
    id: 5,
    pago_id: 5,
    turno_id: 9,
    estado_turno: 'en_espera',
    medio: 'mercadopago',
    importe: '2000.00',
    importe_a_verificar: false,
    mp_payment_id: 'MP-SINT-1',
    pendiente_desde: '2031-11-18T10:00:00-03:00',
    ...sobre,
  };
}

export const DEVOLUCION: Devolucion = {
  id: 5,
  tipo: 'sena',
  pago_id: 5,
  turno_id: 9,
  importe: '3000.00',
  reembolsado_en: '2031-11-18T10:00:00-03:00',
  referencia: 'DEV-SINT-0001',
};
export const RECHAZO: Rechazo = { pago_id: 5, turno_id: 9, estado_pago: 'a_reembolsar', estado_turno: 'en_espera', importe: '2000.00' };
export const ACREDITACION: Acreditacion = { pago_id: 5, turno_id: 9, efecto: 'acreditado', estado_pago: 'acreditado', estado_turno: 'reservado' };

export function cierre(sobre: Partial<CierreDetalle> = {}): CierreDetalle {
  return {
    id: 3,
    dia: '2031-11-17',
    estado: 'vigente',
    total_ingresos: '3000.00',
    total_egresos: '0.00',
    total_neto: '3000.00',
    observaciones: null,
    cerrado_por_nombre: 'Rita Recepción',
    cerrado_en: '2031-11-18T00:20:00-03:00',
    anulado_en: null,
    anulado_motivo: null,
    lineas: [{ concepto: 'sena', medio: 'mercadopago', cantidad: 1, total: '3000.00' }],
    cuadra: true,
    diferencias: [],
    ...sobre,
  };
}

export function pacienteListado(sobre: Partial<PacienteListado> = {}): PacienteListado {
  return {
    id: 8,
    nombre: 'Lucía',
    apellido: 'Ejemplo',
    dni: '30111222',
    telefono: '+5491144445555',
    obra_social: null,
    atendidos: 2,
    ausentes: 1,
    ultimo_turno: '2031-11-10T09:00:00-03:00',
    ...sobre,
  };
}

export function listado(pacientes: readonly PacienteListado[], sobre: Partial<ListadoPacientes> = {}): ListadoPacientes {
  return { total: pacientes.length, pagina: 1, por_pagina: 20, pacientes, ...sobre };
}

export const OCUPACION: Ocupacion = {
  desde: '2031-11-18',
  hasta: '2031-11-18',
  sillones: [
    {
      sillon_id: 2,
      nombre: 'Sillón 1',
      estado: 'activo',
      dias: [{ dia: '2031-11-18', minutos_ocupados: 90, minutos_atencion: 240, porcentaje: '37.50', turnos: 3, minutos_perdidos: 0 }],
    },
    {
      sillon_id: 5,
      nombre: 'Sillón 2',
      estado: 'activo',
      dias: [{ dia: '2031-11-18', minutos_ocupados: 0, minutos_atencion: 0, porcentaje: null, turnos: 0, minutos_perdidos: 0 }],
    },
  ],
};

export const AUSENTISMO: Ausentismo = {
  desde: '2031-11-18',
  hasta: '2031-11-18',
  atendidos: 3,
  ausentes: 1,
  tasa: '25.00',
  sin_marcar: 2,
  por_profesional: [{ profesional_id: 1, nombre: 'Dra. Ana Ficticia', atendidos: 3, ausentes: 1, tasa: '25.00', sin_marcar: 2 }],
  recupero: { senas_retenidas: 1, importe_retenido: '3000.00', porcentaje: '100.00' },
};

// --- C-14: catálogo ----------------------------------------------------------------------------------------------

export function tratamientoAdmin(sobre: Partial<TratamientoAdmin> = {}): TratamientoAdmin {
  return { id: 3, nombre: 'Limpieza dental', duracion_minutos: 45, precio_base: '18500.00', activo: true, ...sobre };
}

export function profesionalAdmin(sobre: Partial<ProfesionalAdmin> = {}): ProfesionalAdmin {
  return { id: 1, nombre: 'Dra. Ana Ficticia', matricula: 'MP-99001', especialidad: 'Odontología general', activo: true, ...sobre };
}

export function sillonAdmin(sobre: Partial<SillonAdmin> = {}): SillonAdmin {
  return { id: 2, nombre: 'Sillón 1', estado: 'activo', ...sobre };
}

export function franjaAdmin(sobre: Partial<FranjaAdmin> = {}): FranjaAdmin {
  return {
    id: 10,
    profesional_id: 1,
    dia_semana: 0,
    hora_inicio: '09:00:00',
    hora_fin: '13:00:00',
    sillon_defecto_id: null,
    activo: true,
    ...sobre,
  };
}

export function catalogoAdmin(sobre: Partial<CatalogoAdmin> = {}): CatalogoAdmin {
  return {
    tratamientos: [tratamientoAdmin(), tratamientoAdmin({ id: 6, nombre: 'Empaste', duracion_minutos: 60, precio_base: '32000.00' })],
    profesionales: [profesionalAdmin()],
    sillones: [sillonAdmin(), sillonAdmin({ id: 5, nombre: 'Sillón 2' })],
    franjas: [franjaAdmin()],
    ...sobre,
  };
}

export const SIN_IMPACTO: Impacto = { turnos_futuros: 0, primero: null };

/** Un `Api` con todos los métodos espías; cada prueba sobreescribe los que le importan. */
export function recordatorio(sobre: Partial<Recordatorio> = {}): Recordatorio {
  return {
    id: 7,
    turno_id: 11,
    estado: 'pendiente',
    motivo: null,
    turno_inicio: '2031-11-18T09:00:00-03:00',
    profesional: 'Dra. Ana Ficticia',
    tratamiento: 'Limpieza dental',
    contacto_nombre: 'Carlos Sintético',
    enviado_en: null,
    intentos_fallidos: 0,
    link: 'https://wa.me/5491144445555?text=Hola%20Carlos',
    ...sobre,
  };
}

// --- C-10 --------------------------------------------------------------------------------------------------------

export function conexionGoogle(sobre: Partial<ConexionGoogle> = {}): ConexionGoogle {
  return {
    profesional_id: 1,
    profesional_nombre: 'Dra. Ana Ficticia',
    estado: 'sin_conectar',
    cuenta_email: null,
    ultima_sync_ok_en: null,
    conflictos_abiertos: 0,
    indicacion: null,
    ...sobre,
  };
}

export const CONEXION_ACTIVA: ConexionGoogle = conexionGoogle({
  estado: 'activa',
  cuenta_email: 'ana.prueba@example.com',
  ultima_sync_ok_en: '2031-11-18T08:30:00-03:00',
});

export function conflictoGoogle(sobre: Partial<ConflictoGoogle> = {}): ConflictoGoogle {
  return {
    id: 21,
    tipo: 'movido_en_google',
    estado: 'abierto',
    criterio: 'El evento se movió en Google Calendar. El turno sigue en el horario del sistema.',
    turno_id: 11,
    profesional_id: 1,
    profesional_nombre: 'Dra. Ana Ficticia',
    tratamiento: 'Limpieza dental',
    sistema_inicio: '2031-11-18T10:00:00-03:00',
    sistema_fin: '2031-11-18T10:30:00-03:00',
    google_inicio: '2031-11-18T12:00:00-03:00',
    google_fin: '2031-11-18T12:30:00-03:00',
    acciones: ['restaurar_en_google', 'desvincular'],
    resolucion: null,
    detectado_en: '2031-11-18T09:00:00-03:00',
    resuelto_en: null,
    ...sobre,
  };
}

export function registroAuditoria(sobre: Partial<RegistroAuditoria> = {}): RegistroAuditoria {
  return {
    id: 91,
    fecha_hora: '2026-11-13T09:05:00-03:00',
    usuario: { id: 3, nombre_completo: 'Recepción Ficticia' },
    accion: 'cierre_caja',
    tipo: 'cierre_caja',
    tipo_etiqueta: 'Cierre de caja',
    entidad: 'cierre_caja',
    entidad_id: '42',
    datos_antes: null,
    datos_despues: { total_neto: '15000.00' },
    ip: '203.0.113.20',
    ...sobre,
  };
}

export function paginaAuditoria(items: readonly RegistroAuditoria[], siguiente: string | null = null): PaginaAuditoria {
  return { items, siguiente };
}

// --- C-16: paciente, ficha, odontograma y presupuestos (datos sintéticos, R19) -----------------------------------

export const ACCESO_TOTAL: AccesoClinico = { nivel: 'total', puede_escribir: true };
export const ACCESO_COMPLETO: AccesoClinico = { nivel: 'clinico_completo', puede_escribir: true };
export const ACCESO_LECTURA: AccesoClinico = { nivel: 'clinico_lectura', puede_escribir: false };

export function pacienteDetalle(sobre: Partial<PacienteDetalle> = {}): PacienteDetalle {
  return {
    id: 7,
    nombre: 'Lucía',
    apellido: 'Ejemplo',
    dni: '99000001',
    telefono: '+5491100000001',
    email: null,
    obra_social: { id: 2, nombre: 'Swiss Medical' },
    numero_afiliado: 'SM-0001',
    acceso_clinico: ACCESO_TOTAL,
    ...sobre,
  };
}

/** La vista de la odontóloga: sin teléfono ni email. */
export function pacienteClinico(sobre: Partial<PacienteDetalle> = {}): PacienteDetalle {
  return pacienteDetalle({ telefono: null, email: null, acceso_clinico: ACCESO_COMPLETO, ...sobre });
}

export function ficha(sobre: Partial<Ficha> = {}): Ficha {
  return {
    paciente_id: 7,
    alergias: 'Penicilina (sintético)',
    medicacion: 'Ninguna (sintético)',
    antecedentes_medicos: '',
    observaciones: '',
    version: 2,
    actualizado_por: 3,
    historia: [
      {
        turno_id: 11,
        inicio: '2031-11-18T09:00:00-03:00',
        fin: '2031-11-18T09:30:00-03:00',
        estado: 'atendido',
        profesional: { id: 1, nombre: 'Dra. Ana Ficticia' },
        tratamiento: { id: 3, nombre: 'Limpieza dental' },
      },
      {
        turno_id: 10,
        inicio: '2031-10-02T10:00:00-03:00',
        fin: '2031-10-02T10:30:00-03:00',
        estado: 'atendido',
        profesional: { id: 4, nombre: 'Dr. Juan Ejemplo' },
        tratamiento: { id: 3, nombre: 'Limpieza dental' },
      },
    ],
    ...sobre,
  };
}

export function odontograma(piezas: readonly PiezaVigente[] = []): OdontogramaVigente {
  return { paciente_id: 7, piezas };
}

export function registroOdonto(sobre: Partial<RegistroOdontograma> = {}): RegistroOdontograma {
  return { id: 1, pieza: 16, cara: 'O', estado: 'caries', nota: null, registrado_por: 3, registrado_en: '2031-11-18T09:00:00-03:00', ...sobre };
}

export function lineaPresupuesto(sobre: Partial<LineaPresupuesto> = {}): LineaPresupuesto {
  return {
    id: 1,
    orden: 1,
    tratamiento: { id: 3, nombre: 'Limpieza dental' },
    pieza: null,
    cara: null,
    cantidad: 1,
    importe_bruto: '25000.00',
    importe_cobertura: '22500.00',
    importe_diferencial: '0.00',
    importe_paciente: '2500.00',
    sin_cobertura: false,
    ...sobre,
  };
}

export function pagoPresupuesto(sobre: Partial<PagoPresupuesto> = {}): PagoPresupuesto {
  return {
    id: 5,
    presupuesto_id: 9,
    medio: 'transferencia',
    monto: '1000.00',
    estado: 'registrado',
    fecha_cobro: '2031-11-18T12:00:00-03:00',
    referencia: 'TRF-0001',
    anulado_en: null,
    anulado_motivo: null,
    ...sobre,
  };
}

export function presupuesto(sobre: Partial<Presupuesto> = {}): Presupuesto {
  return {
    id: 9,
    paciente_id: 7,
    obra_social: { id: 2, nombre: 'Swiss Medical' },
    estado: 'aceptado',
    subtotal: '25000.00',
    cobertura_total: '22500.00',
    diferencial_total: '0.00',
    total_paciente: '2500.00',
    notas: '',
    anulado_motivo: null,
    created_at: '2031-11-18T09:00:00-03:00',
    lineas: [lineaPresupuesto()],
    pagos: [pagoPresupuesto()],
    total_pagado: '1000.00',
    saldo: '1500.00',
    ...sobre,
  };
}

export function presupuestoClinico(sobre: Partial<PresupuestoClinico> = {}): PresupuestoClinico {
  const p = presupuesto();
  return {
    id: p.id,
    paciente_id: p.paciente_id,
    obra_social: p.obra_social,
    estado: p.estado,
    subtotal: p.subtotal,
    cobertura_total: p.cobertura_total,
    diferencial_total: p.diferencial_total,
    total_paciente: p.total_paciente,
    notas: p.notas,
    anulado_motivo: p.anulado_motivo,
    created_at: p.created_at,
    lineas: p.lineas,
    ...sobre,
  };
}

export function apiFalsa(sobre: Partial<Api> = {}) {
  const api = {
    me: vi.fn<Api['me']>(),
    agenda: vi.fn<Api['agenda']>().mockResolvedValue(agenda([])),
    opciones: vi.fn<Api['opciones']>().mockResolvedValue(OPCIONES),
    disponibilidad: vi.fn<Api['disponibilidad']>().mockResolvedValue(SLOTS),
    crearTurno: vi.fn<Api['crearTurno']>().mockResolvedValue({ ok: true, valor: CREADO }),
    marcar: vi.fn<Api['marcar']>().mockResolvedValue({ ok: true, valor: CAMBIO }),
    deshacerAtendido: vi
      .fn<Api['deshacerAtendido']>()
      .mockResolvedValue({ ok: true, valor: { turno_id: 11, estado: 'reservado', estado_sena: 'acreditado' } }),
    caja: vi.fn<Api['caja']>().mockResolvedValue(caja()),
    pendientes: vi.fn<Api['pendientes']>().mockResolvedValue([]),
    rechazarRevision: vi.fn<Api['rechazarRevision']>().mockResolvedValue({ ok: true, valor: RECHAZO }),
    acreditarRevision: vi.fn<Api['acreditarRevision']>().mockResolvedValue({ ok: true, valor: ACREDITACION }),
    registrarDevolucion: vi.fn<Api['registrarDevolucion']>().mockResolvedValue({ ok: true, valor: DEVOLUCION }),
    registrarDevolucionExcedente: vi
      .fn<Api['registrarDevolucionExcedente']>()
      .mockResolvedValue({ ok: true, valor: { ...DEVOLUCION, tipo: 'excedente_mp' } }),
    cerrarCaja: vi.fn<Api['cerrarCaja']>().mockResolvedValue({ ok: true, valor: cierre() }),
    cierre: vi.fn<Api['cierre']>().mockResolvedValue(cierre()),
    anularCierre: vi.fn<Api['anularCierre']>().mockResolvedValue({ ok: true, valor: cierre({ estado: 'anulado' }) }),
    ocupacion: vi.fn<Api['ocupacion']>().mockResolvedValue(OCUPACION),
    ausentismo: vi.fn<Api['ausentismo']>().mockResolvedValue(AUSENTISMO),
    listarPacientes: vi.fn<Api['listarPacientes']>().mockResolvedValue(listado([])),
    recordatorios: vi.fn<Api['recordatorios']>().mockResolvedValue([]),
    marcarRecordatorioEnviado: vi
      .fn<Api['marcarRecordatorioEnviado']>()
      .mockResolvedValue({ ok: true, valor: recordatorio({ estado: 'enviado' }) }),
    marcarRecordatorioFallido: vi
      .fn<Api['marcarRecordatorioFallido']>()
      .mockResolvedValue({ ok: true, valor: recordatorio({ estado: 'fallido', motivo: 'otro' }) }),
    conexionesGoogle: vi.fn<Api['conexionesGoogle']>().mockResolvedValue([conexionGoogle()]),
    conflictosGoogle: vi.fn<Api['conflictosGoogle']>().mockResolvedValue([]),
    iniciarGoogle: vi
      .fn<Api['iniciarGoogle']>()
      .mockResolvedValue({ ok: true, valor: { url_autorizacion: 'https://accounts.google.com/o/oauth2/v2/auth?state=x' } }),
    desconectarGoogle: vi.fn<Api['desconectarGoogle']>().mockResolvedValue({ ok: true, valor: null }),
    resolverConflicto: vi
      .fn<Api['resolverConflicto']>()
      .mockResolvedValue({ ok: true, valor: conflictoGoogle({ estado: 'resuelto', acciones: [] }) }),
    descargarExportacion: vi.fn<Api['descargarExportacion']>().mockResolvedValue({
      ok: true,
      valor: { blob: new Blob(['id'], { type: 'text/csv' }), nombre: 'turnos_2026-11-13.csv' },
    }),
    consultarAuditoria: vi.fn<Api['consultarAuditoria']>().mockResolvedValue(paginaAuditoria([])),
    listarUsuarios: vi
      .fn<Api['listarUsuarios']>()
      .mockResolvedValue([{ id: 3, nombre_completo: 'Recepción Ficticia', activo: true }]),
    catalogo: vi.fn<Api['catalogo']>().mockResolvedValue(catalogoAdmin()),
    impactoCatalogo: vi.fn<Api['impactoCatalogo']>().mockResolvedValue(SIN_IMPACTO),
    crearCatalogo: vi.fn<Api['crearCatalogo']>(),
    actualizarCatalogo: vi.fn<Api['actualizarCatalogo']>(),
    borrarCatalogo: vi.fn<Api['borrarCatalogo']>().mockResolvedValue({ ok: true, valor: null }),
    paciente: vi.fn<Api['paciente']>().mockResolvedValue(pacienteDetalle()),
    crearPaciente: vi.fn<Api['crearPaciente']>().mockResolvedValue({ ok: true, valor: pacienteDetalle() }),
    editarPaciente: vi.fn<Api['editarPaciente']>().mockResolvedValue({ ok: true, valor: pacienteDetalle() }),
    buscarPorDni: vi.fn<Api['buscarPorDni']>().mockResolvedValue([]),
    vincularTurno: vi.fn<Api['vincularTurno']>().mockResolvedValue({ ok: true, valor: { turno_id: 11, paciente_id: 7 } }),
    obrasSociales: vi.fn<Api['obrasSociales']>().mockResolvedValue([{ id: 2, nombre: 'Swiss Medical' }]),
    ficha: vi.fn<Api['ficha']>().mockResolvedValue(ficha()),
    guardarFicha: vi.fn<Api['guardarFicha']>().mockResolvedValue({ ok: true, valor: ficha({ version: 3 }) }),
    odontograma: vi.fn<Api['odontograma']>().mockResolvedValue(odontograma()),
    historialOdontograma: vi.fn<Api['historialOdontograma']>().mockResolvedValue({ registros: [], siguiente_antes_de_id: null }),
    registrarOdontograma: vi.fn<Api['registrarOdontograma']>().mockResolvedValue({ ok: true, valor: [registroOdonto()] }),
    presupuestos: vi.fn<Api['presupuestos']>().mockResolvedValue([]),
    crearPresupuesto: vi.fn<Api['crearPresupuesto']>().mockResolvedValue({ ok: true, valor: presupuesto({ estado: 'borrador', pagos: [], total_pagado: '0.00', saldo: '2500.00' }) }),
    editarPresupuesto: vi.fn<Api['editarPresupuesto']>().mockResolvedValue({ ok: true, valor: presupuesto({ estado: 'borrador', pagos: [], total_pagado: '0.00', saldo: '2500.00' }) }),
    transicionarPresupuesto: vi.fn<Api['transicionarPresupuesto']>().mockResolvedValue({ ok: true, valor: presupuesto() }),
    anularPresupuesto: vi.fn<Api['anularPresupuesto']>().mockResolvedValue({ ok: true, valor: presupuesto({ estado: 'anulado' }) }),
    registrarCobro: vi.fn<Api['registrarCobro']>().mockResolvedValue({ ok: true, valor: { pago: pagoPresupuesto(), total_pagado: '1000.00', saldo: '1500.00' } }),
    anularCobro: vi.fn<Api['anularCobro']>().mockResolvedValue({ ok: true, valor: { pago: pagoPresupuesto({ estado: 'anulado' }), total_pagado: '0.00', saldo: '2500.00' } }),
    ...sobre,
  };
  return api;
}
