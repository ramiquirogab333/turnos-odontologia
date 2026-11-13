import { describe, expect, it } from 'vitest';
import {
  consultaAuditoriaAQuery,
  etiquetaActor,
  mensajeDeExportacion,
  nombreArchivo,
  opcionesSegunRol,
  parametrosExportacion,
  puedeVerAuditoria,
  puedeVerDatos,
} from './datos';

describe('opcionesSegunRol (C-13 O7)', () => {
  it('recepción exporta turnos y cierres de caja, nunca pacientes', () => {
    expect(opcionesSegunRol(['recepcion']).map((o) => o.entidad)).toEqual(['turnos', 'cierres_caja']);
  });

  it('el admin exporta además pacientes', () => {
    expect(opcionesSegunRol(['admin']).map((o) => o.entidad)).toEqual(['turnos', 'pacientes', 'cierres_caja']);
  });

  it('con roles recepción y admin vale el permiso más amplio', () => {
    expect(opcionesSegunRol(['recepcion', 'admin'])).toHaveLength(3);
  });

  it('la odontóloga no tiene ninguna opción', () => {
    expect(opcionesSegunRol(['odontologo'])).toEqual([]);
    expect(opcionesSegunRol([])).toEqual([]);
  });

  it('cada opción trae una etiqueta legible', () => {
    expect(opcionesSegunRol(['admin']).map((o) => o.etiqueta)).toEqual(['Turnos', 'Pacientes', 'Cierres de caja']);
  });
});

describe('quién ve la sección y la auditoría', () => {
  it.each([
    [['recepcion'], true, false],
    [['admin'], true, true],
    [['recepcion', 'admin'], true, true],
    [['odontologo'], false, false],
    [[], false, false],
  ] as const)('roles %j: datos=%s auditoría=%s', (roles, datos, auditoria) => {
    expect(puedeVerDatos(roles)).toBe(datos);
    expect(puedeVerAuditoria(roles)).toBe(auditoria);
  });
});

describe('parametrosExportacion', () => {
  it('sin rango solo manda entidad y formato', () => {
    expect(parametrosExportacion({ entidad: 'turnos', desde: null, hasta: null, incluirInactivos: false })).toBe(
      'entidad=turnos&formato=csv',
    );
  });

  it('el rango opcional viaja con las fechas locales tal cual', () => {
    expect(
      parametrosExportacion({ entidad: 'cierres_caja', desde: '2026-11-16', hasta: '2026-11-20', incluirInactivos: false }),
    ).toBe('entidad=cierres_caja&formato=csv&desde=2026-11-16&hasta=2026-11-20');
  });

  it('un extremo vacío no se manda', () => {
    expect(parametrosExportacion({ entidad: 'turnos', desde: '2026-11-16', hasta: '', incluirInactivos: false })).toBe(
      'entidad=turnos&formato=csv&desde=2026-11-16',
    );
  });

  it('incluir_inactivos solo aplica a pacientes y solo si está tildado', () => {
    expect(parametrosExportacion({ entidad: 'pacientes', desde: null, hasta: null, incluirInactivos: true })).toBe(
      'entidad=pacientes&formato=csv&incluir_inactivos=true',
    );
    expect(parametrosExportacion({ entidad: 'pacientes', desde: null, hasta: null, incluirInactivos: false })).toBe(
      'entidad=pacientes&formato=csv',
    );
    expect(parametrosExportacion({ entidad: 'turnos', desde: null, hasta: null, incluirInactivos: true })).toBe(
      'entidad=turnos&formato=csv',
    );
  });
});

describe('nombreArchivo', () => {
  it('toma el nombre de Content-Disposition', () => {
    expect(nombreArchivo('attachment; filename="turnos_2026-11-13.csv"', 'turnos', '2026-11-13')).toBe('turnos_2026-11-13.csv');
  });

  it('sin cabecera o sin nombre usa entidad_fecha.csv', () => {
    expect(nombreArchivo(null, 'pacientes', '2026-11-13')).toBe('pacientes_2026-11-13.csv');
    expect(nombreArchivo('attachment', 'cierres_caja', '2026-11-13')).toBe('cierres_caja_2026-11-13.csv');
  });

  it('descarta un nombre con rutas o caracteres raros', () => {
    expect(nombreArchivo('attachment; filename="../../etc/passwd"', 'turnos', '2026-11-13')).toBe('turnos_2026-11-13.csv');
  });
});

describe('etiquetaActor', () => {
  it('muestra el nombre de la persona', () => {
    expect(etiquetaActor({ id: 3, nombre_completo: 'Recepción Ficticia' })).toBe('Recepción Ficticia');
  });

  it('sin usuario es el sistema o un paciente sin login', () => {
    expect(etiquetaActor(null)).toBe('Sistema / paciente');
  });
});

describe('mensajeDeExportacion', () => {
  it('429 con Retry-After de 600 s dice 10 minutos', () => {
    expect(mensajeDeExportacion({ tipo: 'limite', minutos: 10 })).toBe(
      'Hiciste muchas exportaciones seguidas. Probá de nuevo en 10 minutos.',
    );
  });

  it('un solo minuto va en singular', () => {
    expect(mensajeDeExportacion({ tipo: 'limite', minutos: 1 })).toBe(
      'Hiciste muchas exportaciones seguidas. Probá de nuevo en 1 minuto.',
    );
  });

  it('cada otro error tiene su frase', () => {
    expect(mensajeDeExportacion({ tipo: 'sin_permiso' })).toBe('No tenés permiso para exportar esto.');
    expect(mensajeDeExportacion({ tipo: 'validacion' })).toBe('Revisá el rango de fechas.');
    expect(mensajeDeExportacion({ tipo: 'servidor' })).toBe('No pudimos preparar el archivo. Probá de nuevo en un rato.');
    expect(mensajeDeExportacion({ tipo: 'red' })).toBe('No pudimos conectarnos. Revisá tu conexión e intentá de nuevo.');
  });
});

describe('consultaAuditoriaAQuery', () => {
  it('sin filtros no manda nada', () => {
    expect(
      consultaAuditoriaAQuery({ desde: null, hasta: null, usuarioId: null, tipo: null, entidad: null, entidadId: null, cursor: null }),
    ).toBe('');
  });

  it('manda solo los filtros con valor y recorta los espacios del texto', () => {
    expect(
      consultaAuditoriaAQuery({
        desde: '2026-11-01',
        hasta: '2026-11-13',
        usuarioId: 7,
        tipo: 'cierre_caja',
        entidad: ' turno ',
        entidadId: '501',
        cursor: 'abc_-',
      }),
    ).toBe('desde=2026-11-01&hasta=2026-11-13&usuario_id=7&tipo=cierre_caja&entidad=turno&entidad_id=501&cursor=abc_-');
  });

  it('un texto en blanco se trata como vacío', () => {
    expect(
      consultaAuditoriaAQuery({ desde: null, hasta: null, usuarioId: null, tipo: '', entidad: '   ', entidadId: '', cursor: null }),
    ).toBe('');
  });
});
