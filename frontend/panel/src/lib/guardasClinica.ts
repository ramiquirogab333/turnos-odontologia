/** Guardas de las respuestas de pacientes, ficha, odontograma y presupuestos (C-16). Sin `any` (R1). */
import { esNumero, esRegistro, esTexto, type Registro } from './guardas';
import type {
  AccesoClinico,
  CobroRegistrado,
  CualquierPresupuesto,
  ErrorClinico,
  EstadoPresupuesto,
  Ficha,
  HistorialOdontograma,
  LineaPresupuesto,
  OdontogramaVigente,
  PacienteDetalle,
  PagoPresupuesto,
  PiezaVigente,
  Presupuesto,
  Ref,
  RegistroOdontograma,
  TurnoHistoria,
  VinculoTurno,
} from './tipos';

const NIVELES: readonly string[] = ['total', 'clinico_completo', 'clinico_lectura'];
const ESTADOS_PRESUPUESTO: readonly string[] = ['borrador', 'presentado', 'aceptado', 'rechazado', 'anulado'];
const MEDIOS: readonly string[] = ['mercadopago', 'transferencia'];
const DECIMAL = /^-?\d+(\.\d+)?$/;

const textoONulo = (v: unknown): v is string | null => v === null || esTexto(v);
const numeroONulo = (v: unknown): v is number | null => v === null || esNumero(v);
const esDinero = (v: unknown): v is string => esTexto(v) && DECIMAL.test(v);

function esRef(v: unknown): v is Ref {
  return esRegistro(v) && esNumero(v['id']) && esTexto(v['nombre']);
}

function refONulo(v: unknown): v is Ref | null {
  return v === null || esRef(v);
}

export function esListaRef(v: unknown): v is readonly Ref[] {
  return Array.isArray(v) && (v as unknown[]).every(esRef);
}

function esAcceso(v: unknown): v is AccesoClinico {
  return esRegistro(v) && esTexto(v['nivel']) && NIVELES.includes(v['nivel']) && typeof v['puede_escribir'] === 'boolean';
}

/** Vista completa (con teléfono) o clínica (sin él): `telefono` y `email` quedan en `null` cuando el servidor no los envía. */
export function aPacienteDetalle(v: unknown): PacienteDetalle | null {
  if (
    !esRegistro(v) ||
    !esNumero(v['id']) ||
    !esTexto(v['nombre']) ||
    !esTexto(v['apellido']) ||
    !esTexto(v['dni']) ||
    !refONulo(v['obra_social']) ||
    !textoONulo(v['numero_afiliado']) ||
    !esAcceso(v['acceso_clinico'])
  ) {
    return null;
  }
  const telefono = v['telefono'];
  const email = v['email'];
  if (telefono !== undefined && !esTexto(telefono)) return null;
  if (email !== undefined && !textoONulo(email)) return null;
  return {
    id: v['id'],
    nombre: v['nombre'],
    apellido: v['apellido'],
    dni: v['dni'],
    telefono: telefono ?? null,
    email: email ?? null,
    obra_social: v['obra_social'],
    numero_afiliado: v['numero_afiliado'],
    acceso_clinico: v['acceso_clinico'],
  };
}

export function esPacienteDetalle(v: unknown): v is PacienteDetalle {
  return aPacienteDetalle(v) !== null;
}

export function esVinculo(v: unknown): v is VinculoTurno {
  return esRegistro(v) && esNumero(v['turno_id']) && esNumero(v['paciente_id']);
}

function esTurnoHistoria(v: unknown): v is TurnoHistoria {
  return (
    esRegistro(v) &&
    esNumero(v['turno_id']) &&
    esTexto(v['inicio']) &&
    esTexto(v['fin']) &&
    esTexto(v['estado']) &&
    esRef(v['profesional']) &&
    esRef(v['tratamiento'])
  );
}

export function esFicha(v: unknown): v is Ficha {
  return (
    esRegistro(v) &&
    esNumero(v['paciente_id']) &&
    esTexto(v['alergias']) &&
    esTexto(v['medicacion']) &&
    esTexto(v['antecedentes_medicos']) &&
    esTexto(v['observaciones']) &&
    esNumero(v['version']) &&
    numeroONulo(v['actualizado_por']) &&
    Array.isArray(v['historia']) &&
    (v['historia'] as unknown[]).every(esTurnoHistoria)
  );
}

function esPiezaVigente(v: unknown): v is PiezaVigente {
  return (
    esRegistro(v) &&
    esNumero(v['pieza']) &&
    textoONulo(v['estado_pieza']) &&
    esRegistro(v['caras']) &&
    Object.values(v['caras']).every(esTexto)
  );
}

export function esOdontograma(v: unknown): v is OdontogramaVigente {
  return esRegistro(v) && esNumero(v['paciente_id']) && Array.isArray(v['piezas']) && (v['piezas'] as unknown[]).every(esPiezaVigente);
}

export function esRegistroOdontograma(v: unknown): v is RegistroOdontograma {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esNumero(v['pieza']) &&
    textoONulo(v['cara']) &&
    esTexto(v['estado']) &&
    textoONulo(v['nota']) &&
    numeroONulo(v['registrado_por']) &&
    esTexto(v['registrado_en'])
  );
}

export function esHistorial(v: unknown): v is HistorialOdontograma {
  return (
    esRegistro(v) &&
    Array.isArray(v['registros']) &&
    (v['registros'] as unknown[]).every(esRegistroOdontograma) &&
    numeroONulo(v['siguiente_antes_de_id'])
  );
}

export function esLote(v: unknown): v is { readonly registros: readonly RegistroOdontograma[] } {
  return esRegistro(v) && Array.isArray(v['registros']) && (v['registros'] as unknown[]).every(esRegistroOdontograma);
}

function esLinea(v: unknown): v is LineaPresupuesto {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esNumero(v['orden']) &&
    esRef(v['tratamiento']) &&
    numeroONulo(v['pieza']) &&
    textoONulo(v['cara']) &&
    esNumero(v['cantidad']) &&
    esDinero(v['importe_bruto']) &&
    esDinero(v['importe_cobertura']) &&
    esDinero(v['importe_diferencial']) &&
    esDinero(v['importe_paciente']) &&
    typeof v['sin_cobertura'] === 'boolean'
  );
}

export function esPago(v: unknown): v is PagoPresupuesto {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esNumero(v['presupuesto_id']) &&
    esTexto(v['medio']) &&
    MEDIOS.includes(v['medio']) &&
    esDinero(v['monto']) &&
    esTexto(v['estado']) &&
    esTexto(v['fecha_cobro']) &&
    textoONulo(v['referencia']) &&
    textoONulo(v['anulado_en']) &&
    textoONulo(v['anulado_motivo'])
  );
}

function esBasePresupuesto(v: unknown): v is Registro {
  return (
    esRegistro(v) &&
    esNumero(v['id']) &&
    esNumero(v['paciente_id']) &&
    refONulo(v['obra_social']) &&
    esTexto(v['estado']) &&
    ESTADOS_PRESUPUESTO.includes(v['estado']) &&
    esDinero(v['subtotal']) &&
    esDinero(v['cobertura_total']) &&
    esDinero(v['diferencial_total']) &&
    esDinero(v['total_paciente']) &&
    esTexto(v['notas']) &&
    textoONulo(v['anulado_motivo']) &&
    esTexto(v['created_at']) &&
    Array.isArray(v['lineas']) &&
    (v['lineas'] as unknown[]).every(esLinea)
  );
}

export function esPresupuesto(v: unknown): v is Presupuesto {
  return (
    esBasePresupuesto(v) &&
    Array.isArray(v['pagos']) &&
    (v['pagos'] as unknown[]).every(esPago) &&
    esDinero(v['total_pagado']) &&
    esDinero(v['saldo'])
  );
}

/** La vista de la odontóloga no trae `pagos`; si los trae, tiene que ser la completa válida. */
export function esCualquierPresupuesto(v: unknown): v is CualquierPresupuesto {
  return esBasePresupuesto(v) && (v['pagos'] === undefined ? true : esPresupuesto(v));
}

export function esCobroRegistrado(v: unknown): v is CobroRegistrado {
  return esRegistro(v) && esPago(v['pago']) && esDinero(v['total_pagado']) && esDinero(v['saldo']);
}

export function estadoValido(v: string): v is EstadoPresupuesto {
  return ESTADOS_PRESUPUESTO.includes(v);
}

// --- errores ---------------------------------------------------------------------------------------------------

function mensajeDeValidacion(detail: unknown): string {
  if (Array.isArray(detail)) {
    for (const item of detail as unknown[]) {
      if (esRegistro(item) && esTexto(item['msg'])) return item['msg'].replace(/^Value error,\s*/i, '');
    }
  }
  return 'Revisá los datos ingresados.';
}

const MOTIVOS_409: Readonly<Record<string, ErrorClinico>> = {
  version_desactualizada: { tipo: 'version_desactualizada' },
  dni_duplicado: { tipo: 'dni_duplicado' },
  presupuesto_no_editable: { tipo: 'presupuesto_no_editable' },
  transicion_invalida: { tipo: 'transicion_invalida' },
  presupuesto_con_pagos: { tipo: 'presupuesto_con_pagos' },
  presupuesto_no_aceptado: { tipo: 'presupuesto_no_aceptado' },
  referencia_duplicada: { tipo: 'referencia_duplicada' },
  caja_cerrada: { tipo: 'caja_cerrada' },
};

/** Rechazo del servidor a una escritura clínica; el motivo manda sobre el status. */
export function errorClinico(status: number, cuerpo: Registro): ErrorClinico {
  const motivo = cuerpo['motivo'];
  if (status === 403) {
    if (motivo === 'paciente_ajeno') return { tipo: 'paciente_ajeno' };
    if (motivo === 'acceso_clinico_vencido') return { tipo: 'acceso_vencido' };
    return { tipo: 'sin_permiso' };
  }
  if (status === 404) return { tipo: 'no_encontrado' };
  if (status === 409) {
    if (motivo === 'monto_excede_saldo') return { tipo: 'monto_excede_saldo', saldo: esDinero(cuerpo['saldo']) ? cuerpo['saldo'] : null };
    return (esTexto(motivo) ? MOTIVOS_409[motivo] : undefined) ?? { tipo: 'desconocido' };
  }
  if (status === 422) {
    if (motivo === 'obra_social_inactiva') return { tipo: 'obra_social_inactiva' };
    return { tipo: 'validacion', mensaje: mensajeDeValidacion(cuerpo['detail']) };
  }
  return { tipo: 'desconocido' };
}
