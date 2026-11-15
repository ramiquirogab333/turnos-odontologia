import { describe, expect, it, vi } from 'vitest';
import { crearApi, ErrorApiPanel, ErrorDeRespuesta } from './api';
import { Sesion } from './sesion';

/** Contratos de C-16 (pacientes, ficha, vínculo y obras sociales). Datos 100 % sintéticos (R19). */

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });
}

function montar(fetchFn: typeof fetch) {
  const sesion = new Sesion({ fetchFn, candados: null, canal: null });
  sesion.fijarToken('ACCESS-1');
  return crearApi(sesion, fetchFn);
}

const urlDe = (llamada: Parameters<typeof fetch> | undefined): string => {
  const u = llamada?.[0];
  if (u === undefined) return '';
  return typeof u === 'string' ? u : u instanceof URL ? u.href : u.url;
};
const metodoDe = (llamada: Parameters<typeof fetch> | undefined): string => llamada?.[1]?.method ?? 'GET';
const cuerpoDe = (llamada: Parameters<typeof fetch> | undefined): unknown => {
  const c = llamada?.[1]?.body;
  return typeof c === 'string' ? (JSON.parse(c) as unknown) : undefined;
};

const ACCESO = { nivel: 'total', puede_escribir: true };
const COMPLETO = {
  id: 7,
  nombre: 'Lucía',
  apellido: 'Ejemplo',
  dni: '99000001',
  telefono: '+5491100000001',
  email: null,
  obra_social: { id: 2, nombre: 'Swiss Medical' },
  numero_afiliado: 'SM-0001',
  acceso_clinico: ACCESO,
};
const CLINICA = {
  id: 7,
  nombre: 'Lucía',
  apellido: 'Ejemplo',
  dni: '99000001',
  obra_social: null,
  numero_afiliado: null,
  acceso_clinico: { nivel: 'clinico_lectura', puede_escribir: false },
};
const FICHA = {
  paciente_id: 7,
  alergias: 'Penicilina (sintético)',
  medicacion: '',
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
  ],
};
const DATOS = {
  nombre: 'Mateo',
  apellido: 'Prueba',
  dni: '99000002',
  telefono: '+5491100000002',
  email: null,
  obra_social_id: null,
  numero_afiliado: null,
};

describe('paciente()', () => {
  it('acepta la vista completa y la clínica (sin teléfono ni email)', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockResolvedValueOnce(json(COMPLETO)).mockResolvedValueOnce(json(CLINICA));
    const api = montar(fetchFn);
    const completo = await api.paciente(7);
    expect(completo.telefono).toBe('+5491100000001');
    expect(completo.acceso_clinico).toEqual(ACCESO);
    const clinico = await api.paciente(7);
    expect(clinico.telefono).toBeNull();
    expect(clinico.email).toBeNull();
    expect(clinico.acceso_clinico.puede_escribir).toBe(false);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7');
  });

  it('una respuesta sin acceso_clinico es malformada', async () => {
    const sinAcceso = { ...COMPLETO, acceso_clinico: undefined }; // JSON.stringify omite la clave
    const api = montar(vi.fn<typeof fetch>().mockImplementation(() => Promise.resolve(json(sinAcceso))));
    await expect(api.paciente(7)).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('un 403 conserva el status y el motivo', async () => {
    const api = montar(vi.fn<typeof fetch>().mockImplementation(() => Promise.resolve(json({ detail: 'ajena', motivo: 'paciente_ajeno' }, 403))));
    await expect(api.paciente(7)).rejects.toMatchObject({ status: 403, motivo: 'paciente_ajeno' });
    await expect(api.paciente(7)).rejects.toBeInstanceOf(ErrorApiPanel);
  });
});

describe('alta, edición, búsqueda y vínculo', () => {
  it('crearPaciente envía el cuerpo exacto y devuelve el paciente', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockResolvedValue(json(COMPLETO, 201));
    const r = await montar(fetchFn).crearPaciente(DATOS);
    expect(r).toMatchObject({ ok: true, valor: { id: 7 } });
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('POST');
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual(DATOS);
  });

  it('dni_duplicado y obra_social_inactiva son errores tipados', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'dni_duplicado' }, 409))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'obra_social_inactiva' }, 422));
    const api = montar(fetchFn);
    expect(await api.crearPaciente(DATOS)).toEqual({ ok: false, error: { tipo: 'dni_duplicado' } });
    expect(await api.editarPaciente(7, DATOS)).toEqual({ ok: false, error: { tipo: 'obra_social_inactiva' } });
  });

  it('editarPaciente usa PUT sobre el id', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockResolvedValue(json(COMPLETO));
    await montar(fetchFn).editarPaciente(7, DATOS);
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('PUT');
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7');
  });

  it('buscarPorDni devuelve cero o un paciente', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockResolvedValueOnce(json([COMPLETO])).mockResolvedValueOnce(json([]));
    const api = montar(fetchFn);
    expect(await api.buscarPorDni('99000001')).toHaveLength(1);
    expect(await api.buscarPorDni('99000003')).toEqual([]);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes?dni=99000001');
  });

  it('vincularTurno envía el paciente y valida la respuesta', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ turno_id: 11, paciente_id: 7 }))
      .mockResolvedValueOnce(json({ detail: 'x' }, 403))
      .mockResolvedValueOnce(json({ otra: 1 }));
    const api = montar(fetchFn);
    expect(await api.vincularTurno(11, 7)).toEqual({ ok: true, valor: { turno_id: 11, paciente_id: 7 } });
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('PUT');
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/turnos/11/paciente');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual({ paciente_id: 7 });
    expect(await api.vincularTurno(11, 7)).toEqual({ ok: false, error: { tipo: 'sin_permiso' } });
    expect(await api.vincularTurno(11, 7)).toEqual({ ok: false, error: { tipo: 'desconocido' } });
  });

  it('obrasSociales devuelve la lista y rechaza lo malformado', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json([{ id: 2, nombre: 'Swiss Medical' }]))
      .mockResolvedValueOnce(json([{ id: 'x' }]));
    const api = montar(fetchFn);
    expect(await api.obrasSociales()).toEqual([{ id: 2, nombre: 'Swiss Medical' }]);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/obras-sociales');
    await expect(api.obrasSociales()).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });
});

describe('ficha', () => {
  it('ficha() valida la historia', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(FICHA))
      .mockResolvedValueOnce(json({ ...FICHA, historia: [{ turno_id: 'x' }] }));
    const api = montar(fetchFn);
    expect((await api.ficha(7)).version).toBe(2);
    expect(urlDe(fetchFn.mock.calls[0])).toBe('/api/panel/pacientes/7/ficha');
    await expect(api.ficha(7)).rejects.toBeInstanceOf(ErrorDeRespuesta);
  });

  it('guardarFicha envía los cuatro campos con la versión', async () => {
    const fetchFn = vi.fn<typeof fetch>().mockResolvedValue(json({ ...FICHA, version: 3 }));
    const cuerpo = { alergias: 'a', medicacion: 'b', antecedentes_medicos: 'c', observaciones: 'd', version: 2 };
    const r = await montar(fetchFn).guardarFicha(7, cuerpo);
    expect(r).toMatchObject({ ok: true, valor: { version: 3 } });
    expect(metodoDe(fetchFn.mock.calls[0])).toBe('PUT');
    expect(cuerpoDe(fetchFn.mock.calls[0])).toEqual(cuerpo);
  });

  it('403 y 409 conservan el motivo y la red caída es desconocido', async () => {
    const fetchFn = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'version_desactualizada' }, 409))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'acceso_clinico_vencido' }, 403))
      .mockResolvedValueOnce(json({ detail: 'x', motivo: 'paciente_ajeno' }, 403))
      .mockRejectedValueOnce(new TypeError('red'));
    const api = montar(fetchFn);
    const cuerpo = { alergias: '', medicacion: '', antecedentes_medicos: '', observaciones: '', version: 0 };
    expect(await api.guardarFicha(7, cuerpo)).toEqual({ ok: false, error: { tipo: 'version_desactualizada' } });
    expect(await api.guardarFicha(7, cuerpo)).toEqual({ ok: false, error: { tipo: 'acceso_vencido' } });
    expect(await api.guardarFicha(7, cuerpo)).toEqual({ ok: false, error: { tipo: 'paciente_ajeno' } });
    expect(await api.guardarFicha(7, cuerpo)).toEqual({ ok: false, error: { tipo: 'desconocido' } });
  });
});
